#!/usr/bin/env python3
"""
Research Lab — autonomous, GATED knowledge-base grower for Alim's marketing co-pilot.

Runs on a cron cadence (every 3 days). One run:
  1. KILL-switch check  -> if /opt/research-lab/KILL exists, exit immediately.
  2. Cost/run guard      -> if monthly run cap reached, notify + exit.
  3. Research (Claude subscription CLI + WebSearch) -> latest creative/AI marketing signal.
  4. Quality gate (LLM-as-judge, separate call) -> score each finding; drop noise + dupes.
  5. Store ONLY accepted findings as markdown into knowledge/ + update INDEX.md.
  6. Telegram digest -> always sent (success OR failure) so the run is never silent.

HARD RULE: this never applies anything to client work. It researches, curates, notifies.
Kill switch:  touch /opt/research-lab/KILL      (re-enable: rm /opt/research-lab/KILL)
"""
import os, sys, json, re, time, datetime, pathlib, subprocess, urllib.request, urllib.error, traceback

BASE   = pathlib.Path(__file__).resolve().parent
KNOW   = BASE / "knowledge"
LOGS   = BASE / "logs"
KILL   = BASE / "KILL"
LEDGER = BASE / "ledger.json"
INDEX  = KNOW / "INDEX.md"
CONFIG = BASE / "config.json"
RADAR  = KNOW / "creator-radar"
PROTOTYPES = BASE / "prototypes"
BACKLOG = PROTOTYPES / "backlog.json"
# Loaded in order; later files override earlier keys. Stack holds the chat_id;
# the lab's own .env overrides the Telegram bot token with the valid one
# (stack's is stale). No shared file is mutated.
ENV_FILES = ["/opt/stack/.env", str(BASE / ".env")]
# Subscription auth: heavy reasoning runs on the flat-rate Claude sub, never on
# per-token API credits. Only this one key is read from the OS env file so its
# other vars can't shadow the lab's.
TOKEN_FILE = "/opt/marketing-hub-os/.env"
CLAUDE_BIN = "/usr/bin/claude"
HEADLESS = BASE / ".headless"   # empty cwd so the CLI loads no project context

NOW = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
STAMP = NOW.strftime("%Y-%m-%d_%H%M")

# ---------- tiny helpers ----------
def log(msg):
    LOGS.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat()}] {msg}"
    print(line, flush=True)
    with open(LOGS / f"{NOW:%Y-%m-%d}.log", "a") as f:
        f.write(line + "\n")

def load_env(path):
    env = {}
    try:
        with open(path) as f:
            for ln in f:
                ln = ln.strip()
                if not ln or ln.startswith("#") or "=" not in ln:
                    continue
                k, v = ln.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return env

def load_all_env():
    env = {}
    for p in ENV_FILES:
        env.update(load_env(p))   # later files override
    env.setdefault("CLAUDE_CODE_OAUTH_TOKEN",
                   load_env(TOKEN_FILE).get("CLAUDE_CODE_OAUTH_TOKEN", ""))
    return env

def load_config():
    defaults = {
        "mission": ("latest, concrete, genuinely-new developments in AI-assisted creative / "
                    "marketing — image/video/voice generation, viral creative formats, brand "
                    "'vibe' trends — useful to a freelance digital-marketing co-pilot serving "
                    "the Azerbaijani (AZ) market"),
        "research_model": "claude-sonnet-4-6",
        "judge_model": "claude-haiku-4-5-20251001",
        "max_web_searches": 6,
        "min_score": 7,            # judge keeps findings scoring >= this (out of 10)
        "notify_min": 9,           # push to Telegram immediately only if score >= this
        "digest_every_days": 5,    # otherwise, a light nudge at most this often
        "max_runs_per_month": 15,  # safety cap on autonomous runs
        "max_findings": 6,
        "creator_radar": {
            "enabled": False,
            "lookback_days": 90,
            "max_items": 8,
            "prototype_min_score": 8,
            "sources": [],
        },
    }
    if CONFIG.exists():
        try:
            defaults.update(json.load(open(CONFIG)))
        except Exception as e:
            log(f"config.json parse error, using defaults: {e}")
    return defaults

def extract_json(text):
    """Pull the first JSON array/object out of model text."""
    text = text.strip()
    # strip ```json fences
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    for opener, closer in (("[", "]"), ("{", "}")):
        s = text.find(opener)
        if s == -1:
            continue
        depth = 0
        for i in range(s, len(text)):
            if text[i] == opener: depth += 1
            elif text[i] == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[s:i+1])
                    except json.JSONDecodeError:
                        break
    return None

DENY_TOOLS = "Bash,Read,Write,Edit,Glob,Grep,WebFetch,NotebookEdit,Task,TodoWrite"

def claude_env(env):
    """Force subscriber auth: strip API keys so the CLI never bills per-token."""
    sub = dict(os.environ)
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        sub.pop(k, None)
    sub["CLAUDE_CODE_OAUTH_TOKEN"] = env["CLAUDE_CODE_OAUTH_TOKEN"]
    return sub

def claude_call(env, model, prompt, web_search=False, max_web_searches=6, retries=3):
    """One prompt through the Claude subscription CLI (headless print mode).
    Returns (text, usage) — same contract as the old direct-API helper."""
    HEADLESS.mkdir(parents=True, exist_ok=True)
    cmd = [CLAUDE_BIN, "-p", "--output-format", "json", "--model", model]
    if web_search:
        cmd += ["--allowedTools", "WebSearch", "--disallowedTools", DENY_TOOLS,
                "--max-turns", str(max_web_searches * 2 + 6)]
    else:
        cmd += ["--disallowedTools", DENY_TOOLS + ",WebSearch", "--max-turns", "2"]
    last_err = None
    for attempt in range(retries):
        try:
            proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                                  timeout=1800, cwd=HEADLESS, env=claude_env(env))
            if proc.returncode == 0:
                data = json.loads(proc.stdout)
                if not data.get("is_error"):
                    return data.get("result") or "", data.get("usage", {})
                last_err = RuntimeError(f"claude cli error: {str(data.get('result'))[:300]}")
            else:
                last_err = RuntimeError(
                    f"claude cli exit {proc.returncode}: {(proc.stderr or proc.stdout)[:300]}")
        except subprocess.TimeoutExpired as e:
            last_err = e
        except (json.JSONDecodeError, OSError) as e:
            last_err = e
        wait = min(2 ** attempt * 10, 120)
        log(f"claude_call failed (attempt {attempt+1}/{retries}): {last_err} — retry in {wait}s")
        if attempt < retries - 1:
            time.sleep(wait)
    raise last_err

def telegram(env, msg):
    token = env.get("TELEGRAM_BOT_TOKEN"); chat = env.get("TELEGRAM_ADMIN_CHAT_ID")
    if not (token and chat):
        log("telegram creds missing, skipping notify"); return
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=json.dumps({"chat_id": chat, "text": msg[:4000],
                             "disable_web_page_preview": True}).encode(),
            headers={"content-type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=30).read()
    except Exception as e:
        log(f"telegram send failed: {e}")

def ledger_runs_this_month():
    if not LEDGER.exists(): return []
    try:
        runs = json.load(open(LEDGER))
    except Exception:
        return []
    ym = NOW.strftime("%Y-%m")
    return [r for r in runs if r.get("ts", "").startswith(ym)]

def ledger_append(entry):
    runs = []
    if LEDGER.exists():
        try: runs = json.load(open(LEDGER))
        except Exception: runs = []
    runs.append(entry)
    json.dump(runs, open(LEDGER, "w"), indent=2)

def existing_titles():
    if not INDEX.exists(): return []
    return re.findall(r"^- \[(.+?)\]", INDEX.read_text(), flags=re.MULTILINE)

STATE = BASE / "state.json"
def load_state():
    if STATE.exists():
        try: return json.load(open(STATE))
        except Exception: return {}
    return {}
def save_state(s):
    json.dump(s, open(STATE, "w"), indent=2)

def accepted_since(ts):
    """How many findings were stored across runs since timestamp ts (excl. current run)."""
    if not (ts and LEDGER.exists()): return 0
    try:
        return sum(r.get("accepted", 0) for r in json.load(open(LEDGER)) if r.get("ts", "") > ts)
    except Exception:
        return 0

def slugify(text, fallback="item"):
    slug = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return (slug or fallback)[:80]

def read_json(path, default):
    if not path.exists():
        return default
    try:
        return json.load(open(path))
    except Exception:
        return default

def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    json.dump(data, open(path, "w"), indent=2, ensure_ascii=False)

def format_sources(sources):
    if not sources:
        return "- No source recorded\n"
    lines = []
    for src in sources:
        if isinstance(src, dict):
            title = src.get("title") or src.get("url") or "source"
            url = src.get("url")
            lines.append(f"- [{title}]({url})\n" if url else f"- {title}\n")
        else:
            lines.append(f"- {src}\n")
    return "".join(lines)

def prototype_name(item):
    proto = item.get("prototype") or {}
    if isinstance(proto, dict):
        return proto.get("name") or item.get("topic")
    return proto or item.get("topic")

def write_creator_radar_finding(item):
    RADAR.mkdir(parents=True, exist_ok=True)
    topic = item.get("topic") or "Untitled trend"
    fp = RADAR / f"{NOW:%Y-%m-%d}_{slugify(topic)}.md"
    prototype = item.get("prototype") if isinstance(item.get("prototype"), dict) else {}
    fp.write_text(
        f"# {topic}\n\n"
        f"*Discovered {NOW:%Y-%m-%d} · creator radar score {item.get('score','?')}/10 · "
        f"status {item.get('status','watch')}*\n\n"
        f"**Source:** {item.get('source','')}\n\n"
        f"**Window:** {item.get('window','')}\n\n"
        f"**What:** {item.get('what','')}\n\n"
        f"**Integration idea:** {item.get('integration_idea','')}\n\n"
        f"**Prototype:** {prototype.get('goal') or item.get('prototype','')}\n\n"
        f"**Dependencies:** {', '.join(item.get('dependencies', []))}\n\n"
        f"**Risks:** {', '.join(item.get('risks', []))}\n\n"
        f"**Next action:** {item.get('next_action','')}\n\n"
        f"**Evidence:**\n{format_sources(item.get('evidence', []))}"
    )
    return fp

def upsert_prototype_backlog(items, min_score):
    PROTOTYPES.mkdir(parents=True, exist_ok=True)
    backlog = read_json(BACKLOG, [])
    by_id = {b.get("id"): b for b in backlog if b.get("id")}
    updated = []

    for item in items:
        if item.get("score", 0) < min_score:
            continue
        name = prototype_name(item)
        pid = slugify(name, fallback="prototype")
        proto = item.get("prototype") if isinstance(item.get("prototype"), dict) else {}
        entry = {
            "id": pid,
            "topic": item.get("topic"),
            "source": item.get("source"),
            "window": item.get("window"),
            "status": item.get("status", "prototype-soon"),
            "score": item.get("score"),
            "evidence": item.get("evidence", []),
            "what": item.get("what", ""),
            "integration_idea": item.get("integration_idea", ""),
            "prototype": {
                "name": name,
                "goal": proto.get("goal", item.get("integration_idea", "")),
                "acceptance": proto.get("acceptance", []),
            },
            "dependencies": item.get("dependencies", []),
            "risks": item.get("risks", []),
            "next_action": item.get("next_action", ""),
            "first_seen": by_id.get(pid, {}).get("first_seen", NOW.date().isoformat()),
            "last_seen": NOW.date().isoformat(),
        }
        by_id[pid] = entry
        updated.append(pid)
        write_prototype_spec(entry)

    write_json(BACKLOG, sorted(by_id.values(), key=lambda x: x.get("score", 0), reverse=True))
    return updated

def write_prototype_spec(entry):
    fp = PROTOTYPES / f"{entry['id']}.md"
    proto = entry.get("prototype", {})
    acceptance = proto.get("acceptance") or []
    fp.write_text(
        f"# {proto.get('name') or entry['topic']}\n\n"
        f"**Status:** {entry.get('status')}\n\n"
        f"**Score:** {entry.get('score')}/10\n\n"
        f"**Topic:** {entry.get('topic')}\n\n"
        f"**Goal:** {proto.get('goal','')}\n\n"
        f"**System integration idea:** {entry.get('integration_idea','')}\n\n"
        f"**Acceptance:**\n" + "".join(f"- {a}\n" for a in acceptance) + "\n"
        f"**Dependencies:**\n" + "".join(f"- {d}\n" for d in entry.get("dependencies", [])) + "\n"
        f"**Risks:**\n" + "".join(f"- {r}\n" for r in entry.get("risks", [])) + "\n"
        f"**Next action:** {entry.get('next_action','')}\n\n"
        f"**Evidence:**\n{format_sources(entry.get('evidence', []))}"
    )

def run_creator_radar(cfg, env):
    rcfg = cfg.get("creator_radar") or {}
    if not rcfg.get("enabled"):
        return {"enabled": False, "candidates": 0, "accepted": 0, "prototype_updates": []}

    sources = rcfg.get("sources") or []
    if not sources:
        log("creator radar enabled but no sources configured")
        return {"enabled": True, "candidates": 0, "accepted": 0, "prototype_updates": []}

    lookback = int(rcfg.get("lookback_days", 90))
    start = (NOW - datetime.timedelta(days=lookback)).date().isoformat()
    end = NOW.date().isoformat()
    existing = read_json(BACKLOG, [])
    known_topics = [b.get("topic") for b in existing if b.get("topic")]

    research_prompt = f"""You are an AI trend radar for Alim's research lab.

Scope: research these creators/sources ONLY for the window {start}..{end}.
{json.dumps(sources, ensure_ascii=False, indent=2)}

Goal: find recent AI/technology/content-production signals that could become system
capabilities, automations, agent features, or prototype backlog items. This is NOT a
popularity summary. Ignore older content except as context. Avoid these existing backlog topics:
{json.dumps(known_topics, ensure_ascii=False)}

For each candidate, verify the implementation path with official docs/product pages when
possible. If the platform blocks full access, mark coverage honestly. Prefer creator post
metadata/captions plus official vendor docs over third-party summaries.

Return ONLY a JSON array, max {rcfg.get('max_items', 8)} items. Each item:
{{
  "topic": "...",
  "source": "creator/source name",
  "window": "{start}..{end}",
  "status": "do-now|prototype-soon|watch|skip",
  "evidence": [{{"title": "...", "url": "..."}}],
  "what": "1-2 sentences",
  "integration_idea": "concrete way this could enter Alim's system",
  "prototype": {{"name": "...", "goal": "...", "acceptance": ["...", "..."]}},
  "dependencies": ["official app/API/model/service"],
  "risks": ["privacy/cost/region/API/quality risks"],
  "next_action": "smallest next implementation step"
}}"""
    rtext, rusage = claude_call(env, cfg["research_model"], research_prompt,
                                web_search=True, max_web_searches=cfg["max_web_searches"])
    candidates = extract_json(rtext) or []
    if not isinstance(candidates, list):
        candidates = []
    log(f"creator radar returned {len(candidates)} candidate signals")

    if not candidates:
        return {"enabled": True, "candidates": 0, "accepted": 0,
                "prototype_updates": [], "research_usage": rusage}

    judge_prompt = f"""You are a strict integration judge for Alim's AI research lab.
Score each candidate 1-10 using: recent novelty inside {start}..{end}, product/system fit,
prototype feasibility in 1-3 days, leverage, and manageable risk.

Candidates:
{json.dumps(candidates, ensure_ascii=False)}

Return ONLY a JSON array of candidates worth keeping, each with the same fields plus:
  "score": <int 1-10>
  "why_kept": "short reason"

Use status:
- do-now for score >= 8 and testable this week
- prototype-soon for score 7-8 with dependencies to check
- watch for score 5-6 or major access uncertainty
- skip only if you keep it as a warning, otherwise omit it

Keep only score >= {cfg['min_score']}."""
    jtext, jusage = claude_call(env, cfg["judge_model"], judge_prompt)
    accepted = extract_json(jtext) or []
    accepted = [a for a in accepted if isinstance(a, dict)
                and a.get("score", 0) >= cfg["min_score"]]
    log(f"creator radar judge accepted {len(accepted)} signals")

    stored = []
    for item in accepted:
        stored.append(str(write_creator_radar_finding(item).relative_to(BASE)))

    prototype_updates = upsert_prototype_backlog(
        accepted, int(rcfg.get("prototype_min_score", 8)))

    loud = [a for a in accepted if a.get("score", 0) >= cfg.get("notify_min", 9)]
    if loud:
        lines = "\n".join(
            f"• {a.get('topic')} ({a.get('score')}/10)\n   → {a.get('next_action','')}"
            for a in loud
        )
        telegram(env, f"📡 Creator Radar — yüksək siqnal:\n{lines}\n\nPrototype backlog yeniləndi.")

    return {
        "enabled": True,
        "window": f"{start}..{end}",
        "candidates": len(candidates),
        "accepted": len(accepted),
        "stored": stored,
        "prototype_updates": prototype_updates,
        "research_usage": rusage,
        "judge_usage": jusage,
    }

def safe_creator_radar(cfg, env):
    try:
        return run_creator_radar(cfg, env)
    except Exception as e:
        log("creator radar failed: " + str(e) + "\n" + traceback.format_exc())
        return {"enabled": bool((cfg.get("creator_radar") or {}).get("enabled")),
                "error": str(e), "candidates": 0, "accepted": 0,
                "prototype_updates": []}

# ---------- main ----------
def main():
    cfg = load_config()
    env = load_all_env()

    if KILL.exists():
        log("KILL switch present — exiting without action."); return

    if not env.get("CLAUDE_CODE_OAUTH_TOKEN"):
        msg = "🧪 Research Lab ❌ CLAUDE_CODE_OAUTH_TOKEN tapılmadı — abunəlik auth-u qurulmayıb, run dayandı."
        log(msg); telegram(env, msg); return

    runs = ledger_runs_this_month()
    if len(runs) >= cfg["max_runs_per_month"]:
        msg = (f"🧪 Research Lab: bu ay run limiti dolub "
               f"({len(runs)}/{cfg['max_runs_per_month']}). Bu run keçildi.")
        log(msg); telegram(env, msg); return

    KNOW.mkdir(parents=True, exist_ok=True)
    known = existing_titles()
    log(f"run start | known findings: {len(known)} | runs this month: {len(runs)}")

    # --- 1. RESEARCH ---
    research_prompt = f"""You are the research arm of a marketing co-pilot. Mission: find {cfg['mission']}.

Use web search to find what is genuinely NEW in roughly the last 7-10 days. Avoid evergreen
basics and anything already well-known months ago. Be concrete and specific.

Do NOT repeat anything already in this list of known findings:
{json.dumps(known, ensure_ascii=False)}

Return ONLY a JSON array (max {cfg['max_findings']} items), each:
{{"title": "...", "what": "1-2 sentences", "why_it_matters_AZ": "why useful for an AZ-market
freelance digital-marketing co-pilot", "sources": ["url", ...]}}"""
    rtext, rusage = claude_call(env, cfg["research_model"], research_prompt,
                                web_search=True, max_web_searches=cfg["max_web_searches"])
    findings = extract_json(rtext) or []
    if not isinstance(findings, list): findings = []
    log(f"research returned {len(findings)} candidate findings")

    if not findings:
        radar_summary = safe_creator_radar(cfg, env)
        log("no candidate findings — base unchanged for general research")
        ledger_append({"ts": NOW.isoformat(), "candidates": 0, "accepted": 0,
                       "usage": rusage, "creator_radar": radar_summary})
        return

    # --- 2. QUALITY GATE (LLM-as-judge) ---
    judge_prompt = f"""You are a strict quality gate for a marketing research knowledge base.
Score each candidate finding 1-10 on: novelty, concreteness, and real usefulness to an
AZ-market freelance digital-marketing co-pilot. Reject hype, vagueness, and rehashed basics.

Candidates:
{json.dumps(findings, ensure_ascii=False)}

Also decide, per finding, "notify": true ONLY if it is genuinely LOUD in the market right
now / a serious shift Alim should hear about immediately — not just nice-to-know. Default false.

Return ONLY a JSON array of the candidates that deserve to be kept, each:
{{"title": "...", "score": <int>, "notify": true|false, "why_kept": "...", "what": "...",
  "why_it_matters_AZ": "...", "application_idea": "one concrete way Alim could use it",
  "sources": [...]}}
Only include items you would score >= {cfg['min_score']}. If none qualify, return []."""
    jtext, jusage = claude_call(env, cfg["judge_model"], judge_prompt)
    accepted = extract_json(jtext) or []
    accepted = [a for a in accepted if isinstance(a, dict)
                and a.get("score", 0) >= cfg["min_score"]
                and a.get("title") not in known]
    log(f"judge accepted {len(accepted)} findings")

    # --- 3. STORE ---
    stored = []
    for a in accepted:
        slug = re.sub(r"[^a-z0-9]+", "-", a["title"].lower()).strip("-")[:60] or "finding"
        fp = KNOW / f"{NOW:%Y-%m-%d}_{slug}.md"
        fp.write_text(
            f"# {a['title']}\n\n"
            f"*Discovered {NOW:%Y-%m-%d} · judge score {a.get('score')}/10*\n\n"
            f"**What:** {a.get('what','')}\n\n"
            f"**Why it matters (AZ market):** {a.get('why_it_matters_AZ','')}\n\n"
            f"**Application idea:** {a.get('application_idea','')}\n\n"
            f"**Sources:**\n" + "".join(f"- {s}\n" for s in a.get("sources", [])))
        stored.append(a["title"])
        with open(INDEX, "a") as idx:
            idx.write(f"- [{a['title']}]({fp.name}) — {NOW:%Y-%m-%d}, score {a.get('score')}/10\n")

    radar_summary = safe_creator_radar(cfg, env)

    # --- 4. NOTIFY (gated: silent growth; ping only when it earns it) ---
    state = load_state()
    last = state.get("last_notify_ts")
    try:
        days_since = (NOW - datetime.datetime.fromisoformat(last)).days if last else 999
    except Exception:
        days_since = 999
    new_since = accepted_since(last) + len(accepted)

    push = [a for a in accepted
            if a.get("notify") is True or a.get("score", 0) >= cfg["notify_min"]]
    notified = None
    if push:
        # Serious / loud-in-market -> tell Alim now, regardless of the digest window.
        lines = "\n".join(f"• {a['title']} ({a.get('score')}/10)\n   → {a.get('application_idea','')}"
                          for a in push)
        telegram(env, f"🔥 Research Lab — DİQQƏT, ciddi yenilik:\n{lines}\n\nLabda detal var, soruş bax verim.")
        notified = "urgent"
    elif accepted and days_since >= cfg["digest_every_days"]:
        # Quiet 5-day nudge, only if something has actually accumulated.
        telegram(env, f"🧪 Research Lab: son xəbərdən bəri labda {new_since} yeni tapıntı toplanıb. "
                       f"İstəsən 'labda nə var / nə tövsiyə edirsən' soruş.")
        notified = "digest"
    else:
        log(f"stored {len(accepted)} silently — no notify (push=0, days_since={days_since})")

    if notified:
        state["last_notify_ts"] = NOW.isoformat()
        save_state(state)

    ledger_append({"ts": NOW.isoformat(), "candidates": len(findings),
                   "accepted": len(stored), "pushed": len(push), "notified": notified,
                   "stored": stored, "research_usage": rusage, "judge_usage": jusage,
                   "creator_radar": radar_summary})
    log(f"run done | stored: {stored} | notified: {notified}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        err = f"🧪 Research Lab ❌ run xətası: {e}"
        log(err + "\n" + traceback.format_exc())
        try:
            telegram(load_all_env(), err)
        except Exception:
            pass
        sys.exit(1)

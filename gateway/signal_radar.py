"""Read-only public signal radar for Ramin-OS.

This module turns public channel noise into governed lab material:

    public source -> claim extraction -> official-source gate -> module fit
    -> lab knowledge note -> prototype backlog -> report

It never reads secrets, never opens local/private URLs, never enables providers,
never spends money, and never publishes. The supervisor may run it on a cadence,
but all outputs are local artifacts for later human-reviewed action.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import html
import ipaddress
import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "signal_radar"
OUTPUT_DIR = ROOT / "output" / "signal-radar"
LAB_KNOWLEDGE = ROOT / "lab" / "knowledge"
LAB_PROTOTYPES = ROOT / "lab" / "prototypes"
STATE_PATH = DATA_DIR / "state.json"
LEDGER_PATH = DATA_DIR / "public_signals.jsonl"

DEFAULT_INTERVAL_HOURS = 24.0
DEFAULT_MAX_MESSAGES = 30
DEFAULT_SOURCES = [
    {
        "name": "Perplexity Discover",
        "url": "https://t.me/s/perplexity",
        "kind": "telegram_public",
    }
]

OFFICIAL_DOMAINS = {
    "openai.com",
    "learn.chatgpt.com",
    "help.openai.com",
    "developers.openai.com",
    "blog.google",
    "deepmind.google",
    "ai.meta.com",
    "meta.com",
    "github.com",
    "nationalcrimeagency.gov.uk",
    "iwf.org.uk",
    "x.ai",
    "apple.com",
}

KNOWN_OFFICIAL_LINKS = {
    "chatgpt_work": [
        "https://openai.com/chatgpt-work/",
        "https://learn.chatgpt.com/docs/get-started-with-work",
    ],
    "google_media": [
        "https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-omni-flash-nano-banana-2-lite/",
    ],
    "meta_muse": [
        "https://ai.meta.com/blog/introducing-muse-image-muse-video-msl/",
    ],
    "plant_talk": [
        "https://github.com/openai/planttalk",
    ],
    "child_image_safety": [
        "https://www.nationalcrimeagency.gov.uk/news/new-guidance-for-parents-and-carers-as-ai-manipulated-images-of-children-become-a-growing-concern",
    ],
    "grok": [
        "https://x.ai/news/grok-4-5",
    ],
}


@dataclass
class SignalMessage:
    source_name: str
    source_url: str
    post: str
    datetime: str
    text: str
    links: list[str]

    @property
    def url(self) -> str:
        if self.post and "/" in self.post:
            return f"https://t.me/{self.post}"
        return self.source_url


@dataclass
class SignalFinding:
    id: str
    title: str
    status: str
    score: int
    source_name: str
    source_url: str
    post_url: str
    observed_at: str
    what: str
    module_fit: list[str]
    risk_controls: list[str]
    next_action: str
    official_links: list[str]
    official_status: str
    prototype_id: str | None = None


def _now_utc(now: dt.datetime | None = None) -> dt.datetime:
    out = now or dt.datetime.now(dt.timezone.utc)
    if out.tzinfo is None:
        out = out.replace(tzinfo=dt.timezone.utc)
    return out.astimezone(dt.timezone.utc)


def _json_load(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def _json_write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_jsonl(path: Path, item: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(item, ensure_ascii=False) + "\n")


def _slug(text: str, fallback: str = "signal") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-")
    return (slug or fallback)[:80]


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _title(text: str) -> str:
    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            return line[:140]
    return "Untitled public signal"


def _signal_id(msg: SignalMessage) -> str:
    raw = "|".join([msg.source_name, msg.post, msg.datetime, _title(msg.text)])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _hostname(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return (parsed.hostname or "").casefold().strip(".")


def is_public_http_url(url: str) -> bool:
    """Allow only ordinary public http(s) URLs.

    This blocks localhost, private IPs, link-local, credentials-in-URL, and
    private-ish hostnames. It does not resolve DNS; the radar is read-only and
    uses a short timeout, but it still fails closed on obvious unsafe targets.
    """

    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    if parsed.username or parsed.password:
        return False
    host = (parsed.hostname or "").casefold()
    if not host:
        return False
    if host in {"localhost", "0.0.0.0"}:
        return False
    if host.endswith((".local", ".lan", ".internal")):
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def fetch_url(url: str, timeout: int = 20) -> str:
    if not is_public_http_url(url):
        raise ValueError(f"blocked non-public URL: {url}")
    req = urllib.request.Request(
        url,
        headers={
            "user-agent": "Ramin-OS SignalRadar/1.0 (+read-only public-source triage)",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - guarded above
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def _strip_html(fragment: str) -> str:
    fragment = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.I)
    fragment = re.sub(r"<[^>]+>", "", fragment)
    return html.unescape(fragment).replace("\r", "").strip()


_MESSAGE_RE = re.compile(
    r'<div class="tgme_widget_message[^>]*data-post="(?P<post>[^"]+)"'
    r"(?P<body>.*?)"
    r'<time datetime="(?P<datetime>[^"]+)"',
    re.S,
)
_TEXT_RE = re.compile(
    r'<div class="tgme_widget_message_text js-message_text"[^>]*>(?P<text>.*?)</div>',
    re.S,
)
_LINK_RE = re.compile(r'<a href="(?P<href>[^"]+)"', re.S)


def parse_telegram_public_html(html_text: str, source: dict[str, str]) -> list[SignalMessage]:
    messages: list[SignalMessage] = []
    for match in _MESSAGE_RE.finditer(html_text or ""):
        body = match.group("body") or ""
        text_match = _TEXT_RE.search(body)
        if not text_match:
            continue
        links = [
            html.unescape(m.group("href"))
            for m in _LINK_RE.finditer(text_match.group("text") or "")
            if is_public_http_url(html.unescape(m.group("href")))
        ]
        messages.append(
            SignalMessage(
                source_name=source.get("name", "public source"),
                source_url=source.get("url", ""),
                post=match.group("post"),
                datetime=match.group("datetime"),
                text=_strip_html(text_match.group("text") or ""),
                links=links,
            )
        )
    return messages


def _is_official_link(url: str) -> bool:
    host = _hostname(url)
    if host in OFFICIAL_DOMAINS:
        return True
    return any(host.endswith("." + domain) for domain in OFFICIAL_DOMAINS)


def _official_links(msg: SignalMessage, topic: str | None) -> tuple[list[str], str]:
    direct = [link for link in msg.links if _is_official_link(link)]
    if direct:
        return direct, "official_link_present"
    if topic and topic in KNOWN_OFFICIAL_LINKS:
        return KNOWN_OFFICIAL_LINKS[topic], "official_candidate_inferred"
    return [], "needs_official_source"


def evaluate_message(msg: SignalMessage) -> SignalFinding:
    text = msg.text.casefold()
    title = _title(msg.text)
    status = "skip"
    score = 2
    topic: str | None = None
    prototype_id: str | None = None
    module_fit: list[str] = ["lab/knowledge"]
    risk_controls: list[str] = ["Treat public channel claims as unverified until official sources are checked."]
    next_action = "No action."
    what = msg.text[:500]

    if "chatgpt work" in text or "gpt-5.6" in text:
        status, score, topic = "do-now", 9, "chatgpt_work"
        prototype_id = "chatgpt-work-operating-pattern"
        module_fit = ["gateway", "workspace_agent", "panel", "config/agent_permissions.json"]
        risk_controls = [
            "Connector, local-file, desktop-app, browser, and scheduled actions stay approval-gated.",
            "No secrets, customer data, claims, policies, or private strategy in external connectors.",
        ]
        next_action = "Fold the Work-package pattern into governed job packaging and panel deliverables."
    elif ("child" in text or "children" in text or "parent" in text) and (
        "photo" in text or "image" in text or "ai fake" in text
    ):
        status, score, topic = "do-now", 10, "child_image_safety"
        prototype_id = "publisher-privacy-guard"
        module_fit = ["publisher", "atelier", "media_studio", "config/agent_permissions.json"]
        risk_controls = [
            "Minor/family imagery requires human review before any public use.",
            "Prefer synthetic, blurred, cropped, or non-identifiable alternatives.",
            "Never automate child-photo harvesting or public reposting.",
        ]
        next_action = "Add minor/family image checks to Publisher and Media Studio safety passes."
    elif "muse image" in text or "muse video" in text:
        status, score, topic = "prototype", 8, "meta_muse"
        prototype_id = "creative-capability-audition"
        module_fit = ["atelier", "media_studio", "mediagen", "publisher"]
        risk_controls = [
            "Use synthetic or approved/licensed assets only.",
            "No Instagram/person/minor/customer imagery in external AI tests.",
            "Outputs stay draft-only until QA and Publisher dry-run.",
        ]
        next_action = "Add Muse-like agentic media behavior to the creative provider audition benchmark."
    elif "nano banana" in text or "gemini omni" in text:
        status, score, topic = "prototype", 8, "google_media"
        prototype_id = "creative-capability-audition"
        module_fit = ["mediagen", "media_studio", "atelier"]
        risk_controls = [
            "Verify model IDs, region, pricing, and API policy before any provider route.",
            "Use only synthetic briefs and approved assets for audition runs.",
            "Paid/API runs require human approval.",
        ]
        next_action = "Benchmark against current free-first media providers before integration."
    elif "plant talk" in text or "arduino" in text:
        status, score, topic = "prototype", 7, "plant_talk"
        prototype_id = "sensor-backed-ambient-agent"
        module_fit = ["lab/prototypes", "gateway approval rail", "brain"]
        risk_controls = [
            "Camera, microphone, serial, Arduino, and device actuation are approval-gated.",
            "Mock sensors first; private observation logs stay under data/.",
            "External voice/realtime API spend requires approval.",
        ]
        next_action = "Keep as a mock-only ambient-agent prototype until hardware is explicitly requested."
    elif "grok" in text:
        status, score, topic = "watch", 6, "grok"
        prototype_id = "official-source-gate"
        module_fit = ["gateway/agent_radar.py", "llm_router.py", "lab/knowledge"]
        risk_controls = [
            "No router/provider change from a launch post.",
            "Use public synthetic evals only; no private data or secrets.",
            "API key setup and paid calls require approval.",
        ]
        next_action = "Watch via Agent Radar; revisit only after official docs, model IDs, cost, and terms are checked."
    elif "apple" in text and ("price" in text or "hike" in text):
        status, score = "watch", 5
        module_fit = ["price-hunter", "lab/knowledge"]
        risk_controls = [
            "Procurement and subscription decisions require human approval.",
            "Do not create a new module for one pricing signal.",
        ]
        next_action = "Optional procurement watch item for Price Hunter if hardware budgets become relevant."
    elif "naruto" in text or "casting" in text:
        status, score = "skip", 2
        module_fit = ["lab/knowledge"]
        risk_controls = [
            "Pop-culture trend has weak insurance fit and IP/casting/minor risks.",
            "No outreach, impersonation, or campaign generator from this signal.",
        ]
        next_action = "Skip unless a human asks for a brand-fit trend bank."
    elif any(k in text for k in ("ai", "model", "video", "image", "voice", "agent", "creator")):
        status, score = "watch", 5
        module_fit = ["lab/knowledge"]
        next_action = "Keep as watch material until an official source and concrete Ramin-OS module fit are found."

    official_links, official_status = _official_links(msg, topic)
    return SignalFinding(
        id=_signal_id(msg),
        title=title,
        status=status,
        score=score,
        source_name=msg.source_name,
        source_url=msg.source_url,
        post_url=msg.url,
        observed_at=msg.datetime,
        what=what,
        module_fit=module_fit,
        risk_controls=risk_controls,
        next_action=next_action,
        official_links=official_links,
        official_status=official_status,
        prototype_id=prototype_id,
    )


PROTOTYPE_TEMPLATES: dict[str, dict[str, Any]] = {
    "public-signal-triage-report": {
        "topic": "Public signal triage report",
        "status": "prototype-soon",
        "score": 9,
        "what": "Turn public channel claims into source-checked lab notes with module routing and risk status.",
        "integration_idea": "A read-only Signal Radar workflow that writes lab findings and prototype candidates without creating new services.",
        "prototype": {
            "name": "Public Signal Triage Report",
            "goal": "Produce a dated report with claim, source, verification status, module fit, risk controls, and next action.",
            "acceptance": [
                "Every claim is marked verified, watch, prototype, do-now, or skip.",
                "Official-source links are attached before provider/workflow recommendations.",
                "No secrets, private data, customer data, or credentials are read or sent.",
            ],
        },
        "dependencies": ["gateway/signal_radar.py", "lab/knowledge", "lab/prototypes"],
        "risks": ["hype intake", "stale provider claims", "source spoofing", "service sprawl"],
        "next_action": "Keep the supervisor loop enabled and review output/signal-radar reports.",
    },
    "official-source-gate": {
        "topic": "Official-source gate for model and provider claims",
        "status": "do-now",
        "score": 9,
        "what": "Require official-source verification before a public claim becomes a provider, agent, permission, or workflow.",
        "integration_idea": "Fail closed in Agent Radar/provider auditions unless official docs, pricing, model IDs, availability, and terms are checked.",
        "prototype": {
            "name": "Official Source Gate",
            "goal": "Fail closed on unverified model/provider claims.",
            "acceptance": [
                "Provider claims cannot reach router/config changes without official source URLs.",
                "Pricing, model IDs, availability, data policy, and region limits are rechecked before implementation.",
                "Reports separate channel claims from verified facts.",
            ],
        },
        "dependencies": ["gateway/agent_radar.py", "config/agent_permissions.json", "lab/knowledge"],
        "risks": ["provider hallucination", "wrong model IDs", "unexpected API spend"],
        "next_action": "Use this gate before any new model/provider route.",
    },
    "creative-capability-audition": {
        "topic": "Creative capability audition for emerging media providers",
        "status": "prototype-soon",
        "score": 8,
        "what": "Benchmark emerging media models against Ramin-OS needs before routing them into Media Studio, Atelier, or Mediagen.",
        "integration_idea": "Synthetic benchmark pack with cost, safety, exact-text, brand-fit, and QA scoring.",
        "prototype": {
            "name": "Creative Capability Audition",
            "goal": "Decide whether a media model is worth a governed provider path.",
            "acceptance": [
                "Uses only synthetic or approved/licensed assets.",
                "Compares exact Azerbaijani text, prompt adherence, editing precision, cost, latency, and policy risk.",
                "Produces a draft-only report; no provider route is added automatically.",
            ],
        },
        "dependencies": ["atelier", "mediagen", "media_studio", "publisher"],
        "risks": ["private asset leakage", "minor imagery", "unlicensed references", "paid generation cost"],
        "next_action": "Define 5 synthetic benchmark briefs and expected scoring fields.",
    },
    "publisher-privacy-guard": {
        "topic": "Publisher privacy guard for child and family imagery",
        "status": "do-now",
        "score": 10,
        "what": "Add a strong consent and minor-image safety checklist before any public media package.",
        "integration_idea": "Publisher and Media Studio flag minors/family imagery, ask for consent proof, and prefer synthetic or non-identifiable alternatives.",
        "prototype": {
            "name": "Publisher Privacy Guard",
            "goal": "Prevent unsafe use of child, family, event, or UGC imagery in public marketing.",
            "acceptance": [
                "Minor/family imagery forces human review before publishing.",
                "Checklist asks for consent, audience scope, necessity, and safer substitutions.",
                "External AI editing/generation with minor imagery is blocked unless explicitly approved.",
            ],
        },
        "dependencies": ["publisher", "atelier", "media_studio", "config/agent_permissions.json"],
        "risks": ["AI manipulation harm", "consent gap", "public reposting risk", "brand safety failure"],
        "next_action": "Add this checklist to the next Publisher or Media Studio safety pass.",
    },
    "sensor-backed-ambient-agent": {
        "topic": "Sensor-backed ambient agent pattern",
        "status": "prototype-soon",
        "score": 7,
        "what": "A local agent pattern that combines camera, voice, sensor readings, and memory into a status surface.",
        "integration_idea": "Prototype with mock sensors first; later adapt to an office/lab pulse or local hardware demo.",
        "prototype": {
            "name": "Sensor-backed Ambient Agent",
            "goal": "Explore local sensor/context patterns without touching real devices by default.",
            "acceptance": [
                "Initial prototype uses mock images and JSON sensor readings.",
                "Camera, microphone, serial, Arduino, and actuation are disabled by default.",
                "Any real hardware, voice, or API spend requires human approval.",
            ],
        },
        "dependencies": ["lab/prototypes", "gateway approval rail", "brain local memory"],
        "risks": ["camera privacy", "microphone privacy", "device actuation", "API spend"],
        "next_action": "Write a mock-only proof spec if the lab needs a hardware-adjacent demo.",
    },
    "chatgpt-work-operating-pattern": {
        "topic": "Work package operating pattern for Ramin-OS",
        "status": "do-now",
        "score": 8,
        "what": "Substantial, reviewable work across files, tools, connectors, scheduled tasks, and artifacts.",
        "integration_idea": "Strengthen job packaging: source status, plan, artifact, approval checklist, and reviewable output.",
        "prototype": {
            "name": "Work Package Skill",
            "goal": "Turn broad work requests into governed, reviewable work packages.",
            "acceptance": [
                "Every package records sources, redaction status, deliverables, risk gates, and approvals.",
                "Outward actions and scheduled tasks park for approval.",
                "Output appears in the panel deliverables gallery.",
            ],
        },
        "dependencies": ["gateway/workspace_agent.py", "gateway/panel.py", "publisher", "brain"],
        "risks": ["connector overreach", "local file exposure", "unapproved scheduled sending"],
        "next_action": "Fold this pattern into the next workspace-agent or panel refinement.",
    },
}


def _prototype_entry(pid: str, finding: SignalFinding | None, now: dt.datetime) -> dict[str, Any]:
    template = dict(PROTOTYPE_TEMPLATES[pid])
    template["id"] = pid
    template["source"] = finding.source_name if finding else "Signal Radar"
    template["window"] = now.date().isoformat()
    evidence = []
    if finding:
        evidence.append({"title": finding.title, "url": finding.post_url})
        evidence.extend({"title": "official source", "url": u} for u in finding.official_links)
    template["evidence"] = evidence
    template["last_seen"] = now.date().isoformat()
    return template


def upsert_prototypes(findings: list[SignalFinding], now: dt.datetime) -> list[str]:
    LAB_PROTOTYPES.mkdir(parents=True, exist_ok=True)
    path = LAB_PROTOTYPES / "backlog.json"
    backlog = _json_load(path, [])
    if not isinstance(backlog, list):
        backlog = []
    by_id = {str(item.get("id")): item for item in backlog if isinstance(item, dict) and item.get("id")}
    touched: list[str] = []

    required = {"public-signal-triage-report", "official-source-gate"}
    required.update(f.prototype_id for f in findings if f.prototype_id)
    for pid in sorted(x for x in required if x and x in PROTOTYPE_TEMPLATES):
        source_finding = next((f for f in findings if f.prototype_id == pid), None)
        entry = _prototype_entry(pid, source_finding, now)
        prior = by_id.get(pid, {})
        entry["first_seen"] = prior.get("first_seen", now.date().isoformat())
        by_id[pid] = entry
        touched.append(pid)
        write_prototype_spec(entry)

    _json_write(path, sorted(by_id.values(), key=lambda x: x.get("score", 0), reverse=True))
    return touched


def write_prototype_spec(entry: dict[str, Any]) -> Path:
    proto = entry.get("prototype") or {}
    acceptance = proto.get("acceptance") or []
    path = LAB_PROTOTYPES / f"{entry['id']}.md"
    path.write_text(
        f"# {proto.get('name') or entry.get('topic')}\n\n"
        f"**Status:** {entry.get('status')}\n\n"
        f"**Score:** {entry.get('score')}/10\n\n"
        f"**Topic:** {entry.get('topic')}\n\n"
        f"**Goal:** {proto.get('goal','')}\n\n"
        f"**System integration idea:** {entry.get('integration_idea','')}\n\n"
        "**Acceptance:**\n"
        + "".join(f"- {x}\n" for x in acceptance)
        + "\n**Dependencies:**\n"
        + "".join(f"- {x}\n" for x in entry.get("dependencies", []))
        + "\n**Risks:**\n"
        + "".join(f"- {x}\n" for x in entry.get("risks", []))
        + f"\n**Next action:** {entry.get('next_action','')}\n\n"
        "**Evidence:**\n"
        + "".join(
            f"- [{e.get('title') or e.get('url')}]({e.get('url')})\n"
            for e in entry.get("evidence", [])
            if isinstance(e, dict) and e.get("url")
        ),
        encoding="utf-8",
    )
    return path


def write_lab_note(finding: SignalFinding, now: dt.datetime) -> Path:
    LAB_KNOWLEDGE.mkdir(parents=True, exist_ok=True)
    path = LAB_KNOWLEDGE / f"{now:%Y-%m-%d}_{_slug(finding.title)}.md"
    source_lines = "".join(f"- {u}\n" for u in finding.official_links) or "- Official source not found yet\n"
    path.write_text(
        f"# {finding.title}\n\n"
        f"*Signal Radar {now:%Y-%m-%d} · status {finding.status} · score {finding.score}/10*\n\n"
        f"**Source:** {finding.post_url}\n\n"
        f"**Official-source status:** {finding.official_status}\n\n"
        f"**What:** {finding.what}\n\n"
        "**Ramin-OS fit:**\n"
        + "".join(f"- {x}\n" for x in finding.module_fit)
        + "\n**Risk controls:**\n"
        + "".join(f"- {x}\n" for x in finding.risk_controls)
        + f"\n**Next action:** {finding.next_action}\n\n"
        f"**Official / source links:**\n{source_lines}",
        encoding="utf-8",
    )
    index = LAB_KNOWLEDGE / "INDEX.md"
    line = f"- [{finding.title}]({path.name}) - {finding.status}, score {finding.score}/10\n"
    if index.exists():
        current = index.read_text(encoding="utf-8", errors="replace")
        if path.name not in current:
            with index.open("a", encoding="utf-8") as fh:
                fh.write(line)
    else:
        index.write_text("# Research Lab Knowledge Index\n\n" + line, encoding="utf-8")
    return path


def render_report(findings: list[SignalFinding], errors: list[str], now: dt.datetime) -> str:
    lines = [
        "# Public Signal Radar Report",
        "",
        f"Generated UTC: {now.isoformat()}",
        "",
        "This report is read-only research material. It does not enable providers, spend credits, publish, send, or change production data.",
        "",
        "## Summary",
        "",
    ]
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.status] = counts.get(finding.status, 0) + 1
    if counts:
        lines.extend(f"- {key}: {counts[key]}" for key in sorted(counts))
    else:
        lines.append("- no new public signals")
    if errors:
        lines.extend(["", "## Fetch Errors", ""])
        lines.extend(f"- {err}" for err in errors)
    lines.extend(
        [
            "",
            "## Findings",
            "",
            "| Status | Score | Signal | Fit | Official source | Next action |",
            "|---|---:|---|---|---|---|",
        ]
    )
    for finding in findings:
        fit = ", ".join(finding.module_fit)
        official = finding.official_status
        if finding.official_links:
            official += f" ({finding.official_links[0]})"
        lines.append(
            "| {status} | {score} | [{title}]({url}) | {fit} | {official} | {next_action} |".format(
                status=finding.status,
                score=finding.score,
                title=finding.title.replace("|", "/"),
                url=finding.post_url,
                fit=fit.replace("|", "/"),
                official=official.replace("|", "/"),
                next_action=finding.next_action.replace("|", "/"),
            )
        )
    return "\n".join(lines) + "\n"


def _configured_sources() -> list[dict[str, str]]:
    raw = os.getenv("SIGNAL_RADAR_SOURCES", "").strip()
    if not raw:
        return list(DEFAULT_SOURCES)
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict) and x.get("url")]
    except json.JSONDecodeError:
        pass
    return [
        {"name": f"source-{i+1}", "url": part.strip(), "kind": "telegram_public"}
        for i, part in enumerate(raw.split(","))
        if part.strip()
    ]


def run_once(
    *,
    now: dt.datetime | None = None,
    sources: list[dict[str, str]] | None = None,
    fetcher: Callable[[str], str] = fetch_url,
    max_messages: int = DEFAULT_MAX_MESSAGES,
) -> dict[str, Any]:
    current = _now_utc(now)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    state = _json_load(STATE_PATH, {})
    seen = set(state.get("seen_ids") or [])

    findings: list[SignalFinding] = []
    errors: list[str] = []
    for source in sources or _configured_sources():
        url = source.get("url", "")
        if not is_public_http_url(url):
            errors.append(f"{source.get('name','source')}: blocked non-public URL {url}")
            continue
        try:
            html_text = fetcher(url)
            messages = parse_telegram_public_html(html_text, source)[-max_messages:]
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{source.get('name','source')}: {exc}")
            continue
        for msg in messages:
            finding = evaluate_message(msg)
            if finding.id in seen:
                continue
            seen.add(finding.id)
            findings.append(finding)
            _append_jsonl(LEDGER_PATH, asdict(finding))
            if finding.status != "skip":
                write_lab_note(finding, current)

    prototype_updates = upsert_prototypes([f for f in findings if f.status != "skip"], current)
    report_path = OUTPUT_DIR / f"{current:%Y-%m-%d_%H%M}-public-signal-radar.md"
    report_path.write_text(render_report(findings, errors, current), encoding="utf-8")

    summary = {
        "ok": not errors,
        "generated_at": current.isoformat(),
        "sources": [s.get("url") for s in sources or _configured_sources()],
        "new_signals": len(findings),
        "kept": len([f for f in findings if f.status != "skip"]),
        "prototype_updates": prototype_updates,
        "report": _rel(report_path),
        "errors": errors,
    }
    state.update(
        {
            "last_run_ts": current.isoformat(),
            "seen_ids": sorted(seen)[-1000:],
            "last_summary": summary,
        }
    )
    _json_write(STATE_PATH, state)
    return summary


def run_if_due(
    *,
    now: dt.datetime | None = None,
    interval_hours: float | None = None,
    fetcher: Callable[[str], str] = fetch_url,
) -> dict[str, Any]:
    if os.getenv("SIGNAL_RADAR_ENABLED", "1").strip().casefold() in {"0", "false", "no", "off"}:
        return {"ok": True, "skipped": "disabled"}
    current = _now_utc(now)
    state = _json_load(STATE_PATH, {})
    interval = interval_hours if interval_hours is not None else float(
        os.getenv("SIGNAL_RADAR_INTERVAL_HOURS", str(DEFAULT_INTERVAL_HOURS))
    )
    last_raw = state.get("last_run_ts")
    if last_raw:
        try:
            last = dt.datetime.fromisoformat(last_raw)
            if last.tzinfo is None:
                last = last.replace(tzinfo=dt.timezone.utc)
            age = (current - last.astimezone(dt.timezone.utc)).total_seconds() / 3600
            if age < interval:
                return {"ok": True, "skipped": "not_due", "hours_until_due": round(interval - age, 2)}
        except Exception:
            pass
    return run_once(now=current, fetcher=fetcher)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Read-only public signal radar.")
    parser.add_argument("command", nargs="?", default="due", choices=["due", "run", "status"])
    args = parser.parse_args(argv)
    if args.command == "status":
        print(json.dumps(_json_load(STATE_PATH, {}), ensure_ascii=False, indent=2))
        return 0
    summary = run_once() if args.command == "run" else run_if_due()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

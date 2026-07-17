"""Marketing OS — service drift audit (the blind-spot catcher).

Why this exists: the hub was once declared "unified" while two services
(8501 Streamlit HQ, 8840 Influencer Hunter) were missing — because it was built
from memory, not from reality. This script removes that failure mode: it compares
the registry (services.json) against what is ACTUALLY running and what the repo
ACTUALLY references, and flags anything that exists but isn't registered.

Run before claiming the system is "complete/unified", or any time:

    python audit_services.py            # report + exit 1 if drift
    python audit_services.py --quiet     # only problems

Exit code 0 = registry matches reality. Non-zero = drift found (fix it).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = os.path.dirname(os.path.abspath(__file__))
REGISTRY = os.path.join(ROOT, "services.json")

_SKIP_DIRS = {".venv", ".audit-tools", "__pycache__", "node_modules", ".git",
              "data", "browser_profiles", "tmp", "output", ".claude", "tests"}
# Top-level dirs that are plumbing, not organs — never need a front-door card.
# Everything else at the repo root must be accounted for: a service dir, a
# capability home, or a conscious entry in services.json "audit_ignore_dirs".
_SUPPORT_DIRS = {"docs", "tests", "config", "scripts", "data", "output", "logs",
                 "tmp", "memory", "secrets", "workspace", "__pycache__",
                 "node_modules"}
_NON_SERVICE_PORTS = {
    # Local/private dependency endpoints, not Marketing OS HTTP services.
    8080,  # TEI / OpenAI-compatible embedding sidecar
    8199,  # Suno-compatible local music sidecar
    8787,  # Whisper-compatible local transcription sidecar
}
_PORT_PATTERNS = [
    re.compile(r"--port[ \"']+(\d{4})"),
    re.compile(r"server\.port[ \"',:=]+(\d{4})"),
    re.compile(r"localhost:(\d{4})"),
    re.compile(r"127\.0\.0\.1:(\d{4})"),
    re.compile(r"\.port[ ]*[:=][ ]*(\d{4})"),
]


def load_registry() -> tuple[list[dict], tuple[int, int]]:
    with open(REGISTRY, encoding="utf-8") as f:
        data = json.load(f)
    lo, hi = data.get("port_range", [8000, 8999])
    return data["services"], (lo, hi)


def listening_ports(lo: int, hi: int) -> set[int]:
    """Ports actually LISTENING right now. Windows netstat says LISTENING,
    Linux (ss) says LISTEN — the audit was blind on the VPS until it spoke
    both dialects, so try netstat first and fall back to ss."""
    found: set[int] = set()
    for cmd, marker in ((["netstat", "-ano", "-p", "tcp"], "LISTENING"),
                        (["ss", "-tln"], "LISTEN")):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=15).stdout
        except Exception:
            continue
        for line in out.splitlines():
            if marker not in line:
                continue
            m = re.search(r":(\d{4,5})\b", line)
            if m:
                p = int(m.group(1))
                if lo <= p <= hi:
                    found.add(p)
        if found:
            break
    return found


def referenced_ports(lo: int, hi: int) -> set[int]:
    """Ports mentioned in code/scripts (a service can exist but be stopped)."""
    found: set[int] = set()
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in filenames:
            if not fn.endswith((".py", ".ps1", ".bat", ".cmd")):
                continue
            try:
                text = open(os.path.join(dirpath, fn), encoding="utf-8",
                            errors="ignore").read()
            except OSError:
                continue
            for pat in _PORT_PATTERNS:
                for m in pat.findall(text):
                    p = int(m)
                    if lo <= p <= hi:
                        found.add(p)
    return found


def _service_dirs(services: list[dict]) -> set[str]:
    """Top-level dir each service occupies. dir='.' services live at the root —
    their real home is the first module segment of the uvicorn target
    (e.g. 'media_studio.server:app' → 'media_studio')."""
    dirs: set[str] = set()
    for s in services:
        d = (s.get("dir") or "").strip()
        if d and d != ".":
            dirs.add(d.split("/")[0])
        else:
            head = (s.get("target") or "").split(":")[0].split(".")[0]
            if head and os.path.isdir(os.path.join(ROOT, head)):
                dirs.add(head)
    return dirs


def organ_coverage(reg: dict) -> dict:
    """The sonarzum rule, enforced: every organ dir at the repo root must have a
    front-door presence — a registered service, a capability card, or a conscious
    'audit_ignore_dirs' entry. An organ nobody can see from the hub is a motor
    rusting outside the car; this check turns that into red drift, not a memory."""
    accounted = _service_dirs(reg.get("services", []))
    caps = reg.get("capabilities", [])
    accounted |= {c.get("home", "").split("/")[0] for c in caps if c.get("home")}
    accounted |= set(reg.get("audit_ignore_dirs", []))

    unaccounted = []
    for name in sorted(os.listdir(ROOT)):
        if name.startswith(".") or name in _SUPPORT_DIRS or name in _SKIP_DIRS:
            continue
        if not os.path.isdir(os.path.join(ROOT, name)):
            continue
        if name not in accounted:
            unaccounted.append(name)

    missing_home = [{"key": c["key"], "home": c["home"]} for c in caps
                    if c.get("home") and not os.path.isdir(os.path.join(ROOT, c["home"]))]
    return {"capabilities": len(caps), "unaccounted": unaccounted,
            "missing_home": missing_home}


def audit_data() -> dict:
    """The one place the audit is computed. Both the CLI and the hub's
    /api/audit consume this — so console and UI can never disagree."""
    services, (lo, hi) = load_registry()
    registered = {s["port"] for s in services}
    # external worlds (services.json "external") are known, not drift — the
    # front door shows them separately; drift = truly UNKNOWN ports only.
    # audit_ignore_ports = reviewed non-services (see _comment_audit_ignore).
    with open(REGISTRY, encoding="utf-8") as f:
        extra = json.load(f)
    registered |= {e["port"] for e in extra.get("external", []) if e.get("port")}
    registered |= set(extra.get("audit_ignore_ports", []))
    listening = listening_ports(lo, hi)
    referenced = referenced_ports(lo, hi)
    organs = organ_coverage(extra)

    drift = []
    for p in sorted((listening | referenced) - registered - _NON_SERVICE_PORTS):
        why = []
        if p in listening:
            why.append("işləyir")
        if p in referenced:
            why.append("kodda var")
        drift.append({"port": p, "why": why})

    missing_dir = [{"key": s["key"], "dir": s["dir"]} for s in services
                   if s.get("dir") and not os.path.isdir(os.path.join(ROOT, s["dir"]))]

    rows = [{"key": s["key"], "name": s["name"], "port": s["port"],
             "up": s["port"] in listening}
            for s in sorted(services, key=lambda x: x["port"])]

    return {
        "ok": (not drift and not missing_dir
               and not organs["unaccounted"] and not organs["missing_home"]),
        "counts": {"registered": len(services), "listening": len(listening),
                   "referenced": len(referenced), "range": [lo, hi],
                   "capabilities": organs["capabilities"]},
        "services": rows, "drift": drift, "missing_dir": missing_dir,
        "organs": organs,
    }


def _telegram_text(a: dict) -> str:
    """Compact alert body. No LLM — plain string formatting (free)."""
    c = a["counts"]
    head = ("✅ <b>Marketing OS — hər şey qaydasında</b>" if a["ok"]
            else "🚨 <b>Marketing OS — DRIFT aşkarlandı</b>")
    lines = [head,
             f"Reyestr {c['registered']} · işləyən {c['listening']} · istinad {c['referenced']}"]
    down = [s for s in a["services"] if not s["up"]]
    if down:
        lines.append("Dayanıb: " + ", ".join(f"{s['key']}({s['port']})" for s in down))
    if a["drift"]:
        lines.append("⚠ Qeydiyyatsız port: "
                     + ", ".join(f"{d['port']} ({', '.join(d['why'])})" for d in a["drift"]))
    if a["missing_dir"]:
        lines.append("⚠ Qovluq yox: " + ", ".join(s["key"] for s in a["missing_dir"]))
    org = a.get("organs", {})
    if org.get("unaccounted"):
        lines.append("⚠ Vitrinsiz orqan (hub-da kartı yoxdur): "
                     + ", ".join(org["unaccounted"]))
    if org.get("missing_home"):
        lines.append("⚠ Qabiliyyət evi itib: "
                     + ", ".join(f"{m['key']}→{m['home']}" for m in org["missing_home"]))
    return "\n".join(lines)


def _send_telegram(text: str) -> bool:
    """Post to Telegram Bot API — FREE, no LLM tokens, just an HTTPS call.
    Lazy imports so the core audit stays stdlib-only."""
    try:
        import requests
        from dotenv import load_dotenv
    except ImportError:
        print("  (telegram: requests/dotenv yoxdur)", file=sys.stderr)
        return False
    load_dotenv(os.path.join(ROOT, ".env"))
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat = os.getenv("AUDIT_ALERT_CHAT_ID") or os.getenv("CX_ALERT_CHAT_ID", "")
    if not token or not chat:
        print("  (telegram: TELEGRAM_BOT_TOKEN / chat id .env-də yoxdur)", file=sys.stderr)
        return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text": text, "parse_mode": "HTML",
                                "disable_web_page_preview": True}, timeout=10)
        if not r.ok:
            print(f"  (telegram: {r.status_code} {r.text[:120]})", file=sys.stderr)
        return r.ok
    except Exception as exc:
        print(f"  (telegram error: {exc})", file=sys.stderr)
        return False


def main() -> int:
    quiet = "--quiet" in sys.argv
    a = audit_data()
    c = a["counts"]

    print("=" * 66)
    print("  Marketing OS · xidmət drift auditi")
    print("=" * 66)
    print(f"  Reyestrdə: {c['registered']}  ·  dinləyən: {c['listening']}  ·  "
          f"kodda istinad: {c['referenced']}  ·  aralıq: {c['range'][0]}-{c['range'][1]}")

    if not quiet:
        print("\n  Qeydiyyatlı xidmətlər:")
        for s in a["services"]:
            flag = "🟢" if s["up"] else "⚪"
            print(f"    {flag} {s['port']}  {s['key']:<11} {s['name']}")

    if a["drift"]:
        print("\n  ⚠ REYESTRDƏ OLMAYAN portlar (bu, 8501-tipli boşluqdur!):")
        for d in a["drift"]:
            print(f"     ✗ {d['port']}  ({', '.join(d['why'])}) → services.json-a əlavə et və ya təmizlə")

    if a["missing_dir"]:
        print("\n  ⚠ Reyestrdə var, qovluq yoxdur:")
        for s in a["missing_dir"]:
            print(f"     ✗ {s['key']} → {s['dir']}")

    org = a.get("organs", {})
    if not quiet:
        print(f"\n  Portsuz qabiliyyətlər (vitrin kartı olan): {org.get('capabilities', 0)}")
    if org.get("unaccounted"):
        print("\n  ⚠ VİTRİNSİZ ORQANLAR (sonarzum-tipli boşluq — qovluq var, ön qapıda yeri yox!):")
        for name in org["unaccounted"]:
            print(f"     ✗ {name}/ → services.json: servis, capability və ya audit_ignore_dirs qeydi ver")
    if org.get("missing_home"):
        print("\n  ⚠ Qabiliyyət reyestrdə var, qovluğu yoxdur:")
        for m in org["missing_home"]:
            print(f"     ✗ {m['key']} → {m['home']}")

    # Telegram alert: only on real drift by default; --always = daily heartbeat.
    if "--telegram" in sys.argv and ((not a["ok"]) or "--always" in sys.argv):
        sent = _send_telegram(_telegram_text(a))
        print(f"\n  telegram: {'göndərildi ✓' if sent else 'göndərilmədi ✗'}")

    problems = (len(a["drift"]) + len(a["missing_dir"])
                + len(org.get("unaccounted", [])) + len(org.get("missing_home", [])))
    print("\n" + "=" * 66)
    if problems:
        print(f"  ✗ {problems} uyğunsuzluq — reyestr reallıqla üst-üstə düşmür. Düzəlt.")
        print("=" * 66)
        return 1
    print("  ✓ Reyestr reallıqla tam uyğundur. Boşluq yoxdur.")
    print("=" * 66)
    return 0


if __name__ == "__main__":
    sys.exit(main())

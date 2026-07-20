"""Publisher privacy guard — hold a live publish that may expose a minor or an
identifiable real person until a human explicitly acknowledges it.

Publishing to a public social channel is an outward, hard-to-reverse action. A
client asset that shows a child, a family, or a named testimonial must never go
out on autopilot. This scans the assembled publish plan for such signals and,
when any fires, BLOCKS the live publish and writes a consent checklist instead.
It clears only when the human passes `--privacy-ack` (or PUBLISH_PRIVACY_ACK=1).

Design: the scan is cheap and explainable — no model call, no network. It errs
toward flagging (a false alarm costs one acknowledgement; a missed real minor
costs far more), and on any internal error it FAILS SAFE by flagging rather than
letting content through silently. It reads metadata only and never edits media.

Signals:
  * person-signal words (AZ + EN) in the slug, any caption, or a media filename;
  * a privacy.json sidecar in the media folder — an authoritative human override,
    {"minors": true} or a non-empty "people" list without "consent": true.

Acceptance this satisfies (lab prototype 'publisher-privacy-guard', score 10):
  1. minor/family imagery forces human review before publishing;
  2. the checklist asks for consent, audience scope, necessity, safer substitution;
  3. external-AI editing of minor imagery is blocked unless explicitly approved —
     enforced at publish time here; `minor_edit_allowed()` is the reusable predicate
     media_studio/atelier can adopt at their own edit choke point (separate pass).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Distinctive stems — matched at a word start so inflections are caught
# (uşaq→uşağın via the uşağ stem), but an inner substring is not ("family" is
# not inside "familiar"). re is unicode by default, so \w covers ə ş ç ö ü ğ ı.
_SIGNAL_WORDS = (
    "uşaq", "uşağ", "körpə", "ailə", "ailəvi", "övlad", "məktəbli",   # Azerbaijani
    "child", "baby", "babies", "toddler", "infant", "family", "families",  # English
    "testimonial",
)
# Short / ambiguous tokens — need full word boundaries so "kid" does not fire on
# "kidney" and "minor" does not fire on "minority".
_STRICT_WORDS = ("kid", "kids", "minor", "minors", "ugc")

_SIGNAL_RE = re.compile(r"(?<!\w)(?:" + "|".join(_SIGNAL_WORDS) + r")", re.IGNORECASE)
_STRICT_RE = re.compile(r"(?<!\w)(?:" + "|".join(_STRICT_WORDS) + r")(?!\w)", re.IGNORECASE)

_CHECKLIST = (
    "Written consent on file from every identifiable person "
    "(parent/guardian for a minor)?",
    "Audience scope — is broad public distribution actually necessary here?",
    "Necessity — is showing this real person required, or can the message land without them?",
    "Safer substitution — considered a synthetic, blurred, or illustrated stand-in "
    "instead of a real minor?",
)


def _media_paths(plan: dict) -> list[str]:
    paths = []
    if plan.get("media"):
        paths.append(plan["media"])
    for e in plan.get("entries", []) or []:
        if isinstance(e, dict) and e.get("media"):
            paths.append(e["media"])
    return paths


def _sidecar_reasons(media_path: str) -> list[str]:
    """An authoritative human-authored privacy.json beside the media always wins."""
    cand = Path(media_path).parent / "privacy.json"
    if not cand.is_file():
        return []
    try:
        data = json.loads(cand.read_text(encoding="utf-8"))
    except Exception:
        return ["privacy.json is present but unreadable — treated as sensitive"]
    reasons = []
    if data.get("minors") is True:
        reasons.append("privacy.json declares a minor is present")
    people = data.get("people") or []
    if people and data.get("consent") is not True:
        reasons.append(f"privacy.json lists {len(people)} real person(s) without consent=true")
    return reasons


def scan_plan(plan: dict) -> dict:
    """Inspect the plan; return {flagged, reasons, words}. Never raises for a
    well-formed plan — the enforce() wrapper turns any surprise into a safe flag."""
    hits: set[str] = set()
    texts = [str(plan.get("slug") or "")]
    for e in plan.get("entries", []) or []:
        if isinstance(e, dict):
            texts.append(str(e.get("caption") or ""))
    for mp in _media_paths(plan):
        texts.append(Path(mp).name)
    for t in texts:
        hits.update(m.lower() for m in _SIGNAL_RE.findall(t))
        hits.update(m.lower() for m in _STRICT_RE.findall(t))
    reasons = []
    if hits:
        reasons.append("person-signal words: " + ", ".join(sorted(hits)))
    for mp in _media_paths(plan):
        reasons.extend(_sidecar_reasons(mp))
    return {"flagged": bool(reasons), "reasons": reasons, "words": sorted(hits)}


def checklist_path(plan: dict) -> Path:
    return REPO / "output" / "publish" / (str(plan.get("slug") or "post")) / "PRIVACY-CHECKLIST.md"


def write_checklist(plan: dict, scan: dict) -> Path:
    path = checklist_path(plan)
    path.parent.mkdir(parents=True, exist_ok=True)
    asset = plan.get("asset") or plan.get("slug") or "<asset>"
    lines = [
        f"# Privacy checklist — {plan.get('slug')}",
        "",
        "This publish was **held** because it may show a minor or an identifiable",
        "real person. Answer all four, then re-run with `--privacy-ack` to release it.",
        "",
        "## Why it was flagged",
    ]
    lines += [f"- {r}" for r in scan["reasons"]]
    lines += ["", "## Before you publish"]
    lines += [f"- [ ] {q}" for q in _CHECKLIST]
    lines += [
        "",
        "> Editing or generating a minor's image with an external AI model is **not",
        "> allowed** without a separate, explicit acknowledgement.",
        "",
        f"Release: `python publisher/run.py {asset} --to <platforms> --privacy-ack`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def minor_edit_allowed(plan: dict, *, ack: bool) -> bool:
    """Reusable predicate for any external-AI edit/generation step (media_studio,
    atelier): return False when the asset is minor/person-flagged and unacked."""
    return ack or not scan_plan(plan)["flagged"]


def enforce(plan: dict, *, ack: bool, dry_run: bool) -> tuple[bool, dict, Path | None]:
    """Gate a plan before it reaches the publisher cascade.
    Returns (allowed, scan, checklist_path_or_None).
      * not flagged            -> allowed, nothing written;
      * flagged + ack          -> allowed (human took responsibility);
      * flagged + dry_run      -> allowed (no network is contacted) but surfaced;
      * flagged + live, no ack -> BLOCKED, checklist written.
    Any scan error fails safe (flagged)."""
    try:
        scan = scan_plan(plan)
    except Exception as exc:  # noqa: BLE001
        scan = {"flagged": True, "words": [],
                "reasons": [f"privacy scan error — held for safety: {exc}"]}
    if not scan["flagged"]:
        return True, scan, None
    checklist = None
    try:
        checklist = write_checklist(plan, scan)
    except Exception:  # noqa: BLE001 — a write failure must not unblock the guard
        pass
    if ack or dry_run:
        return True, scan, checklist
    return False, scan, checklist


def report(plan: dict, scan: dict, checklist: Path | None, allowed: bool) -> None:
    print("\n🔒 Privacy guard")
    for r in scan["reasons"]:
        print(f"   • {r}")
    if checklist:
        print(f"   checklist: {checklist}")
    if allowed:
        print("   → acknowledged / dry-run — proceeding.\n")
    else:
        print("   → LIVE PUBLISH HELD. Review the checklist, then re-run with "
              "--privacy-ack.\n")

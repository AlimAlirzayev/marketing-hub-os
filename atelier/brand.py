"""Brand Brain - reads the brand DNA that already lives in the studios.

Atelier never copies the curated markdown; it reads social-studio + copy-studio
at runtime so those files stay the single source of truth. The only thing
Atelier owns is `brand_state.json`: which DNA is active + the user's house rules
and extra exclusions, which get injected into every Creative Lab prompt.

Editing the canonical DNA prose is intentionally out of MVP scope (it is risky
to overwrite hand-curated files via a textarea). Instead the user steers via
selection + house rules; writing back to markdown is a documented V1 step.
"""

from __future__ import annotations

import json
import os
import re

from . import config

# --------------------------------------------------------------------------
# Markdown parsing helpers
# --------------------------------------------------------------------------
def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _title_and_summary(md: str, fallback: str) -> tuple[str, str]:
    """First H1 becomes the title; first real paragraph becomes the summary."""
    title, summary = fallback, ""
    lines = md.splitlines()
    body_start = 0
    for i, line in enumerate(lines):
        if line.startswith("# "):
            # Strip markdown emphasis/backticks/em-dash noise from the heading.
            raw = line[2:].strip()
            raw = re.sub(r"[`*]", "", raw)
            raw = re.split(r"\s+[—-]\s+", raw, maxsplit=1)
            title = (raw[-1] if len(raw) > 1 else raw[0]).strip() or fallback
            body_start = i + 1
            break
    para: list[str] = []
    for line in lines[body_start:]:
        s = line.strip()
        if not s:
            if para:
                break
            continue
        if s.startswith("#") or s.startswith("```"):
            if para:
                break
            continue
        para.append(re.sub(r"[`*]", "", s))
    summary = " ".join(para).strip()
    if len(summary) > 240:
        summary = summary[:237].rsplit(" ", 1)[0] + "…"
    return title, summary


def _scan_dna(root: str) -> list[dict]:
    """Each immediate sub-folder with a dna.md is one DNA option."""
    out: list[dict] = []
    if not os.path.isdir(root):
        return out
    for key in sorted(os.listdir(root)):
        path = os.path.join(root, key, "dna.md")
        if os.path.isfile(path):
            md = _read(path)
            title, summary = _title_and_summary(md, key)
            out.append({"key": key, "title": title, "summary": summary, "body": md})
    return out


def list_style_dna() -> list[dict]:
    return _scan_dna(config.STYLE_DNA_DIR)


def list_voice_dna() -> list[dict]:
    return _scan_dna(config.VOICE_DNA_DIR)


def list_dialects() -> list[str]:
    root = config.MODEL_DIALECTS_DIR
    if not os.path.isdir(root):
        return ["gpt-image-2"]
    return sorted(
        os.path.splitext(f)[0] for f in os.listdir(root)
        if f.endswith(".md") and not f.upper().startswith("README")
    )


def style_body(key: str) -> str:
    for s in list_style_dna():
        if s["key"] == key:
            return s["body"]
    return ""


def voice_body(key: str) -> str:
    for v in list_voice_dna():
        if v["key"] == key:
            return v["body"]
    return ""


def dialect_body(key: str) -> str:
    return _read(os.path.join(config.MODEL_DIALECTS_DIR, f"{key}.md"))


def ai_tells() -> str:
    return _read(config.AI_TELLS)


def brand_identity() -> str:
    return _read(config.BRAND_MD)


def master_template() -> str:
    return _read(config.MASTER_TEMPLATE)


def legal_phrases() -> str:
    return _read(config.LEGAL_PHRASES)


# --------------------------------------------------------------------------
# Brand state - the one thing Atelier owns
# --------------------------------------------------------------------------
_DEFAULT_STATE = {
    "active_style": "financial-restraint",
    "active_voice": "financial-restraint-az",
    "active_dialect": "gpt-image-2",
    "default_format": "4:5 Feed",
    "default_n": 4,
    "house_rules": "",
    "extra_exclusions": "",
}


def _pick(value: str, options: list[str], fallback_idx: int = 0) -> str:
    return value if value in options else (options[fallback_idx] if options else value)


def get_state() -> dict:
    state = dict(_DEFAULT_STATE)
    if os.path.isfile(config.BRAND_STATE):
        try:
            with open(config.BRAND_STATE, encoding="utf-8") as f:
                state.update(json.load(f))
        except (OSError, json.JSONDecodeError):
            pass
    # Heal stale selections so the UI never points at a deleted DNA folder.
    styles = [s["key"] for s in list_style_dna()]
    voices = [v["key"] for v in list_voice_dna()]
    dialects = list_dialects()
    state["active_style"] = _pick(state["active_style"], styles)
    state["active_voice"] = _pick(state["active_voice"], voices)
    state["active_dialect"] = _pick(state["active_dialect"], dialects)
    if state["default_format"] not in config.FORMATS:
        state["default_format"] = next(iter(config.FORMATS))
    return state


def save_state(patch: dict) -> dict:
    config.ensure_dirs()
    state = get_state()
    for k in _DEFAULT_STATE:
        if k in patch and patch[k] is not None:
            state[k] = patch[k]
    try:
        state["default_n"] = max(1, min(8, int(state["default_n"])))
    except (TypeError, ValueError):
        state["default_n"] = 4
    with open(config.BRAND_STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    return state


def payload() -> dict:
    """Everything the Brand Brain screen needs in one call."""
    return {
        "styles": list_style_dna(),
        "voices": list_voice_dna(),
        "dialects": list_dialects(),
        "formats": list(config.FORMATS.keys()),
        "ai_tells": ai_tells(),
        "brand_identity": brand_identity(),
        "legal": legal_phrases(),
        "state": get_state(),
        "account": config.ACCOUNT_NAME,
        "tagline": config.ACCOUNT_TAGLINE,
        "brand_colors": config.BRAND,
        "chatgpt_url": config.CHATGPT_URL,
    }

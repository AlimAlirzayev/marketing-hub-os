"""AZ voice call-agent — the scripted qualification engine.

This is the un-Turkish-locked equivalent of Doruk's Freya inbound sales-qualifier
(lab: knowledge/engineering/2026-07-21_az-voice-phone-agent-plan.md). It is the
BRAIN an ElevenLabs Agent's custom-LLM WebSocket calls per turn, plus the
post-call qualification report. It works and is testable WITHOUT a phone — over
text now, over voice.py audio, or over a real ElevenLabs call once the operator
wires a number (the OWNER step: ElevenLabs paid tier + a +994 carrier/SIP trunk).

Two roles:
  * reply(history, scenario)  -> the agent's next line. Real-time, so a FAST model
    (Doruk's rule: a call must answer in <1-2s; a full `claude -p` turn is too slow).
  * report(history, scenario) -> a structured qualification card (qualified? need,
    budget, urgency, next action), written post-call where latency does not matter,
    so it uses the Claude brain (falls to the free floor only if every rung is capped).

The "script / senaryo" Doruk versions by hand IS just `scenario` here — a small
dict rendered into the agent's system prompt. Swap it per use case; no code change.
"""

from __future__ import annotations

import json
import re

from . import brain

# A scenario is the call script. Runtime strings are Azerbaijani (spoken to the
# caller); the code and keys stay English per the repo language policy.
DEFAULT_SCENARIO: dict = {
    "name": "insurance-inbound-qualifier",
    "company": "Xalq Sığorta",
    "role": "gələn zəngləri cavablandıran nəzakətli satış təmsilçisi",
    "goal": "zəng edənin ehtiyacını müəyyən et və zəngi kvalifikasiya et",
    "qualify": [
        "hansı sığorta növü ilə maraqlanır (KASKO, icbari, əmlak, səyahət…)",
        "obyektin dəyəri / təxmini büdcə",
        "nə vaxt lazımdır (təcililik)",
        "qərar verən şəxsdir, ad və əlaqə nömrəsi",
    ],
    "style": "Azərbaycan dilində, qısa, isti və peşəkar; hər dəfə BİR sual ver, "
             "monoloq qurma, zəng edəni dinlə",
    "closing": "uyğun müştəridirsə ad və nömrəni al, mütəxəssisə ötürəcəyini bildir; "
               "uyğun deyilsə nəzakətlə yönləndir",
}


def _system(scenario: dict) -> str:
    """Render the scenario into the agent's system prompt (its 'senaryo')."""
    qs = "\n".join(f"  - {q}" for q in scenario.get("qualify", []))
    return (
        f"Sən {scenario['company']} şirkətinin {scenario['role']}sisən. "
        f"Məqsəd: {scenario['goal']}.\n"
        f"Danışıq tərzi: {scenario['style']}.\n"
        f"Zəng boyu bunları TƏBİİ şəkildə öyrənməyə çalış (hamısını birdən yox):\n{qs}\n"
        f"Bağlanış: {scenario['closing']}.\n\n"
        "Sən AGENT-sən. Yalnız agentin NÖVBƏTİ bir replikasını yaz — qısa, "
        "danışıq dili, bir cümlə, ən çoxu bir sualla. Rol adı, dırnaq və izahat yazma. "
        "Söhbət boşdursa, zəng yeni bağlanıb — salamla və şirkəti təqdim et."
    )


def _render(history: list) -> str:
    """history = [("caller"|"agent", text), ...] -> a plain transcript."""
    label = {"caller": "Müştəri", "agent": "Agent"}
    return "\n".join(f"{label.get(who, who)}: {text}" for who, text in history)


def reply(history: list, scenario: dict | None = None, *, fast: bool = True) -> str:
    """The agent's next line. `fast` uses the free cascade (Gemini flash) for the
    sub-2s latency a live call needs; fast=False routes turns through Claude."""
    scenario = scenario or DEFAULT_SCENARIO
    convo = _render(history)
    prompt = ((convo + "\n") if convo else "") + "Agent:"
    text, _ = brain.answer(prompt, system=_system(scenario),
                           prefer="free" if fast else "claude", timeout=30)
    # strip a stray "Agent:" prefix the model may echo, THEN surrounding quotes
    line = re.sub(r"^\s*(agent|Agent)\s*:\s*", "", (text or "").strip()).strip().strip('"').strip()
    return line or "Bağışlayın, sizi eşitmirəm, təkrar edə bilərsiniz?"


def _parse_json(raw: str) -> dict:
    text = (raw or "").strip()
    if "{" in text and "}" in text:
        text = text[text.index("{"): text.rindex("}") + 1]
    try:
        d = json.loads(text)
        return d if isinstance(d, dict) else {}
    except ValueError:
        return {}


def report(history: list, scenario: dict | None = None) -> dict:
    """Post-call qualification card. Written by the Claude brain (no latency
    pressure once the call is over); guaranteed to return the full key set."""
    scenario = scenario or DEFAULT_SCENARIO
    transcript = _render(history)
    prompt = (
        f"Bu, {scenario['company']} üçün gələn satış zənginin transkriptidir:\n\n"
        f"{transcript}\n\n"
        "Zəngi kvalifikasiya et. YALNIZ JSON qaytar, başqa mətn yox:\n"
        '{"qualified": true/false, "need": "<ehtiyac, qısa>", '
        '"budget": "<büdcə/dəyər və ya bilinmirsə \'bilinmir\'>", '
        '"urgency": "yüksək" | "orta" | "aşağı" | "bilinmir", '
        '"contact": "<ad və nömrə və ya \'yoxdur\'>", '
        '"summary": "<1-2 cümlə Azərbaycanca>", '
        '"next_action": "<bir konkret növbəti addım>"}'
    )
    text, model = brain.answer(prompt, prefer="claude", timeout=60)
    d = _parse_json(text)
    return {
        "qualified": bool(d.get("qualified", False)),
        "need": str(d.get("need", "bilinmir")),
        "budget": str(d.get("budget", "bilinmir")),
        "urgency": str(d.get("urgency", "bilinmir")),
        "contact": str(d.get("contact", "yoxdur")),
        "summary": str(d.get("summary", "")) or transcript[:160],
        "next_action": str(d.get("next_action", "")),
        "by": model,
    }


# --------------------------------------------------------------------------- #
# Demo: drive the engine end-to-end with a scripted caller so the whole loop is
# testable and showable WITHOUT any telephony. `python3 -m gateway.call_agent`.
# --------------------------------------------------------------------------- #
_DEMO_CALLER = [
    "Salam, KASKO sığortası barədə məlumat almaq istəyirdim.",
    "Maşınım 2021 Toyota Camry, dəyəri təxminən 45 min manat.",
    "Bu həftə lazımdır, köhnə sığortam bu günlərdə bitir.",
    "Bəli, qərar verən mənəm. Adım Elvin, nömrəm 0501234567.",
]


def demo(scenario: dict | None = None, caller: list | None = None) -> dict:
    scenario = scenario or DEFAULT_SCENARIO
    caller = caller or _DEMO_CALLER
    history: list = []
    greeting = reply(history, scenario)          # inbound: the agent answers first
    history.append(("agent", greeting))
    print(f"Agent: {greeting}")
    for turn in caller:
        history.append(("caller", turn))
        print(f"Müştəri: {turn}")
        line = reply(history, scenario)
        history.append(("agent", line))
        print(f"Agent: {line}")
    print("\n--- KVALIFIKASIYA HESABATI ---")
    card = report(history, scenario)
    for k in ("qualified", "need", "budget", "urgency", "contact", "summary", "next_action"):
        print(f"  {k}: {card[k]}")
    return card


if __name__ == "__main__":
    demo()

"""'What changed' — finds the biggest movers vs a baseline and writes a
short Azerbaijani narrative (Gemini, with a deterministic fallback).

This is the single 'Insight of the day' style callout best-in-class dashboards
(Benly, Motion) sit at the top of every report. We compute movers locally,
then ask the AI to phrase them with a recommended action.
"""

from __future__ import annotations

from config import CURRENCY_SYMBOL

from . import ai
from .comparison import METRIC_LABEL, is_good


def _money(x: float) -> str:
    return f"{CURRENCY_SYMBOL}{x:,.2f}"


def _fmt_value(metric: str, v: float) -> str:
    if metric in ("spend", "cpl", "cpm", "cpc", "cost_per_message"):
        return _money(v)
    if metric in ("ctr",):
        return f"{v:.2f}%"
    if metric in ("frequency",):
        return f"{v:.2f}x"
    return f"{int(v):,}".replace(",", " ")


def find_movers(deltas: dict, n: int = 3) -> dict:
    """Top N winners and top N losers by absolute % change."""
    valid = [(k, v) for k, v in deltas.items()
             if v.get("change") is not None and abs(v["change"]) >= 1]
    winners = sorted([x for x in valid if is_good(x[0], x[1]["change"])],
                     key=lambda x: abs(x[1]["change"]), reverse=True)[:n]
    losers = sorted([x for x in valid if not is_good(x[0], x[1]["change"])],
                    key=lambda x: abs(x[1]["change"]), reverse=True)[:n]
    return {"winners": winners, "losers": losers}


def _format_movers(movers: list, prefix: str) -> str:
    if not movers:
        return ""
    bits = []
    for metric, d in movers:
        label = METRIC_LABEL.get(metric, metric)
        arrow = "↑" if d["change"] > 0 else "↓"
        bits.append(f"{label} {arrow}{abs(d['change'])}% ({_fmt_value(metric, d['current'])})")
    return prefix + ", ".join(bits)


def narrate(deltas: dict, mode_label: str, report: dict, anomalies: list,
             use_ai: bool = True) -> dict:
    """Build the 'what changed' insight.

    Returns:
        {
          "movers": {"winners": [...], "losers": [...]},
          "headline": "<short AZ headline>",
          "body": "<2-3 sentence AZ paragraph with recommended action>",
          "source": "gemini" | "rule-based"
        }
    """
    movers = find_movers(deltas)
    win_txt = _format_movers(movers["winners"], "Müsbət: ")
    lose_txt = _format_movers(movers["losers"], "Diqqət: ")
    flag_txt = ", ".join(a["title"] for a in anomalies if a["severity"] in ("high", "warn"))

    facts = f"Müqayisə bazası: {mode_label}.\n"
    if win_txt:
        facts += win_txt + ".\n"
    if lose_txt:
        facts += lose_txt + ".\n"
    if flag_txt:
        facts += f"Aktiv xəbərdarlıqlar: {flag_txt}."

    if not (win_txt or lose_txt or flag_txt):
        return {
            "movers": movers, "headline": "Sabit dövr",
            "body": f"{mode_label} ilə müqayisədə əsas göstəricilər sabitdir, ciddi dəyişiklik yoxdur.",
            "source": "rule-based",
        }

    if use_ai:
        try:
            prompt = (
                f"Aşağıdakı 'nə dəyişdi' analizinə əsasən cəmi 2 cümləlik insight yaz. "
                f"Birinci cümlə baş verən əsas dəyişikliyi izah etsin (rəqəmlə). "
                f"İkinci cümlə konkret bir tövsiyə versin. "
                f"İdiomatik Azərbaycanca, marketinq jarqonu yox. "
                f"Hər cümlə üçün heç bir başlıq, yalnız mətn.\n\n{facts}"
            )
            text = ai._gemini(prompt)
            if text:
                lines = [s.strip() for s in text.split("\n") if s.strip()]
                headline = lines[0] if lines else text
                body = " ".join(lines)
                return {"movers": movers, "headline": headline[:180], "body": body, "source": "gemini"}
        except Exception:
            pass

    # Rule-based fallback.
    first_loser = movers["losers"][0] if movers["losers"] else None
    first_winner = movers["winners"][0] if movers["winners"] else None
    if first_loser:
        m, d = first_loser
        label = METRIC_LABEL.get(m, m)
        headline = f"{label} {('↑' if d['change']>0 else '↓')}{abs(d['change'])}% — diqqət lazımdır"
        body = f"{label} əvvəlki dövrlə müqayisədə {abs(d['change'])}% pisləşib. " + (
            "Kreativi yeniləyin və ya hədəfləməni yenidən nəzərdən keçirin.")
    elif first_winner:
        m, d = first_winner
        label = METRIC_LABEL.get(m, m)
        headline = f"{label} {abs(d['change'])}% yaxşılaşıb"
        body = f"{label} əvvəlki dövrlə müqayisədə {abs(d['change'])}% yaxşılaşıb. Bu yanaşmanı saxlayın."
    else:
        headline = "Sabit dövr"
        body = "Əsas göstəricilərdə ciddi dəyişiklik yoxdur."

    return {"movers": movers, "headline": headline, "body": body, "source": "rule-based"}

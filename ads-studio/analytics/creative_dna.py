"""Kreativ DNA — groups ad-level diagnostics by (product line, format) so the
dashboard can answer "what kind of creative actually works" instead of Meta's
generic per-ad Quality/Engagement/Conversion ranking, which says nothing about
messaging strategy. Pure aggregation over data connectors already fetch.
"""

from __future__ import annotations

from . import product_lines


def leaderboard(ads: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str], dict] = {}
    for a in ads:
        tag = product_lines.tag(a.get("ad_name", ""))
        key = (tag["product"], tag["format"])
        g = groups.setdefault(key, {
            "product": tag["product"], "format": tag["format"],
            "spend": 0.0, "leads": 0, "messages": 0, "impressions": 0, "clicks": 0,
            "ad_count": 0, "quality_above": 0, "quality_total": 0,
        })
        g["spend"] += a.get("spend", 0) or 0
        g["leads"] += a.get("leads", 0) or 0
        g["messages"] += a.get("messages", 0) or 0
        g["impressions"] += a.get("impressions", 0) or 0
        g["clicks"] += a.get("clicks", 0) or 0
        g["ad_count"] += 1
        if a.get("quality_ranking"):
            g["quality_total"] += 1
            if a["quality_ranking"] == "ABOVE_AVERAGE":
                g["quality_above"] += 1

    out = []
    for g in groups.values():
        g["spend"] = round(g["spend"], 2)
        g["cpl"] = round(g["spend"] / g["leads"], 2) if g["leads"] else None
        g["ctr"] = round(g["clicks"] / g["impressions"] * 100, 2) if g["impressions"] else 0.0
        g["quality_rate"] = (round(g["quality_above"] / g["quality_total"] * 100)
                              if g["quality_total"] else None)
        out.append(g)
    out.sort(key=lambda g: (g["cpl"] is None, g["cpl"] if g["cpl"] is not None else 0, -g["spend"]))
    return out

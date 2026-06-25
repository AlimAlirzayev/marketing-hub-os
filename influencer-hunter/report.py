"""JSON, Markdown and optional Telegram output for Influencer Hunter."""

from __future__ import annotations

import json
import os
from datetime import datetime

import httpx

import config
import decision
from models import HuntResult


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in text.lower()).strip("-")[:56] or "influencer-hunt"


def to_json(res: HuntResult) -> dict:
    data = res.to_dict()
    data["generated_at"] = config.now_iso()
    data["engines"] = config.engine_status()
    data["decision"] = decision.result_decision(res)
    return data


def to_markdown(res: HuntResult) -> str:
    b = res.brief
    frame = decision.result_decision(res)
    lines = [
        f"# Influencer Hunt - {b.brand or 'Campaign'} / {b.product}",
        f"_Query: `{res.query}` · generated {config.now_iso()}_",
        "",
        "## What This Result Is For",
        frame["purpose"],
        "",
        "## Decision",
        frame["answer"],
        "",
        f"Confidence: **{frame['confidence']}** - {frame['confidence_reason']}",
        "",
        f"Active gate: **{frame['active_gate']}**",
        "",
        f"Next step: {frame['recommended_next_step']}",
        "",
        "## Brief",
        f"- Brand: {b.brand or '-'}",
        f"- Product: {b.product or '-'}",
        f"- Angle: {b.selling_angle or '-'}",
        f"- Audience: {b.audience or '-'}",
        f"- Format: {b.content_format or '-'}",
        f"- Min followers: {res.filters.min_followers:,}",
        "",
    ]
    if res.verdict:
        lines += ["## Verdict", res.verdict, ""]
    lines += [
        "## Top candidates",
        "",
        "| # | Creator | Score | Followers | ER | Why |",
        "|--:|---------|------:|----------:|---:|-----|",
    ]
    for i, c in enumerate(res.shortlist, 1):
        er = f"{c.engagement_rate * 100:.2f}%" if c.engagement_rate else "-"
        cd = decision.candidate_decision(c, i - 1)
        lines.append(
            f"| {i} | @{c.handle} | {c.total_score:.2f}/10 | {c.followers or '-'} | {er} | {cd['decision']}: {'; '.join(cd['why'])} |"
        )
    lines += ["", "## Evidence", ""]
    for idx, c in enumerate(res.shortlist):
        lines.append(f"### @{c.handle} - {c.total_score:.2f}/10")
        cd = decision.candidate_decision(c, idx)
        lines.append(f"Decision: {cd['decision']}")
        lines.append("Why: " + "; ".join(cd["why"]))
        lines.append("Next checks: " + "; ".join(cd["next_checks"]))
        lines.append(
            f"Audience {c.audience_fit:.1f} · Content {c.content_fit:.1f} · "
            f"Engagement {c.engagement_quality:.1f} · Feedback {c.feedback_sentiment:.1f} · "
            f"Safety {c.brand_safety:.1f} · Authenticity {c.authenticity:.1f}"
        )
        if c.flags:
            lines.append("Flags: " + "; ".join(c.flags))
        for e in sorted(c.evidence, key=lambda x: (x.relevance, x.metrics.get("video_views", 0), x.metrics.get("likes", 0)), reverse=True)[:6]:
            metrics = e.metrics or {}
            lines.append(
                f"- {e.kind}: {e.url or '-'} | rel {e.relevance:.1f} | "
                f"likes {metrics.get('likes', 0)} comments {metrics.get('comments', 0)} "
                f"views {metrics.get('video_views', 0)} | {e.text[:160].replace('|', '/')}"
            )
        lines.append("")
    lines += [
        "## Filtered Out",
        "",
        "| Creator | Followers | Reason |",
        "|---------|----------:|--------|",
    ]
    for c in res.filtered_out[:30]:
        lines.append(f"| @{c.handle} | {c.followers or '-'} | {'; '.join(c.flags) or '-'} |")
    lines += [
        "",
        "## Source coverage",
        "",
        "| Source | Status | Note |",
        "|--------|--------|------|",
    ]
    for s in res.source_status:
        lines.append(f"| {s.source} | {s.status} | {s.note} |")
    lines.append("")
    lines.append(
        f"_Seen {res.total_seen} raw items · ranked {len(res.candidates)} · shortlisted {len(res.shortlist)} · rejected {res.rejected}_"
    )
    return "\n".join(lines)


def save(res: HuntResult) -> tuple[str, str]:
    config.ensure_dirs()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = os.path.join(config.REPORT_DIR, f"{_slug(res.query)}-{stamp}")
    jpath, mpath = base + ".json", base + ".md"
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(to_json(res), f, ensure_ascii=False, indent=2)
    with open(mpath, "w", encoding="utf-8") as f:
        f.write(to_markdown(res))
    return jpath, mpath


def telegram(res: HuntResult) -> bool:
    if not (os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("IH_TELEGRAM_CHAT_ID")):
        return False
    head = f"*Influencer Hunter* - {res.brief.product}\n"
    body = "\n".join(
        f"{i+1}. @{c.handle} - {c.total_score:.1f}/10 ({c.proof_summary})"
        for i, c in enumerate(res.shortlist)
    )
    try:
        r = httpx.post(
            f"https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN')}/sendMessage",
            json={
                "chat_id": os.getenv("IH_TELEGRAM_CHAT_ID"),
                "text": (head + "\n" + body)[:3500],
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        return r.status_code == 200
    except Exception:
        return False

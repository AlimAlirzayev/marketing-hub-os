"""Deterministic mentor engine for the Marketing Certification Coach.

The coach is intentionally exam-prep only. It creates plans, original practice
questions, and approval checklists. It never logs in, pays, books, views live
exam screens, or answers live exam questions.
"""

from __future__ import annotations

import copy
import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import __version__


ROOT = Path(__file__).resolve().parent
CATALOG_PATH = ROOT / "data" / "certifications.json"

LEVEL_SCORE = {
    "beginner": 1,
    "foundation": 1,
    "junior": 1,
    "intermediate": 2,
    "mid": 2,
    "advanced": 3,
    "senior": 3,
}

TRACK_ALIASES = {
    "performance": {"performance", "ppc", "paid", "ads", "media", "meta", "google", "tiktok"},
    "analytics": {"analytics", "ga4", "measurement", "tracking", "reporting", "attribution"},
    "content": {"content", "copy", "inbound", "editorial", "brand"},
    "social": {"social", "community", "instagram", "tiktok", "linkedin", "content"},
    "seo": {"seo", "search", "keyword", "serp", "organic", "ai search"},
    "b2b": {"b2b", "linkedin", "corporate", "lead gen", "abm"},
    "strategy": {"strategy", "brand", "full funnel", "planning", "positioning"},
    "growth": {"growth", "cro", "experiment", "experimentation", "funnel", "revenue"},
}


QUESTION_BANK: dict[str, list[dict[str, Any]]] = {
    "google_ads_search": [
        {
            "id": "gas_1",
            "prompt": "A search campaign has broad traffic but low lead quality. What is the strongest first diagnostic move?",
            "choices": [
                "Increase the budget to exit learning faster.",
                "Review search terms, negative keywords, conversion quality, and intent by ad group.",
                "Pause all exact match keywords because they limit scale.",
                "Move every keyword into one ad group to simplify reporting."
            ],
            "answer": 1,
            "rationale": "Quality problems usually require intent, query, and conversion-quality diagnostics before scaling spend."
        },
        {
            "id": "gas_2",
            "prompt": "Which campaign artifact best shows exam-ready search discipline?",
            "choices": [
                "A list of competitor slogans.",
                "A keyword map with intent, match type, negatives, ads, landing page, and KPI per theme.",
                "A single broad match keyword with maximum budget.",
                "A social media calendar."
            ],
            "answer": 1,
            "rationale": "Search competence is visible in structure: intent, matching, negatives, copy, landing page, and measurement."
        }
    ],
    "google_ads_measurement": [
        {
            "id": "gam_1",
            "prompt": "A campaign reports many leads, but sales says most are weak. What should the measurement plan add?",
            "choices": [
                "Only impressions, because upper-funnel reach matters most.",
                "Qualified lead or offline conversion feedback, tied back to campaign/ad signals where possible.",
                "A bigger retargeting audience with no quality filter.",
                "A daily screenshot of the dashboard."
            ],
            "answer": 1,
            "rationale": "Measurement should connect ad events to business quality, not just raw form submissions."
        },
        {
            "id": "gam_2",
            "prompt": "Which question belongs before changing attribution settings?",
            "choices": [
                "Which model makes the report look best?",
                "What decision will this attribution view support, and what data quality limits exist?",
                "Can we remove all assisted conversions?",
                "Can every channel receive exactly the same credit?"
            ],
            "answer": 1,
            "rationale": "Attribution is a decision lens. The right model depends on the decision and data quality."
        }
    ],
    "google_analytics_ga4": [
        {
            "id": "ga4_1",
            "prompt": "A funnel report looks empty after a new landing page launch. What is the best first check?",
            "choices": [
                "Change all traffic source names manually.",
                "Verify event collection, key event configuration, and page path/parameter consistency.",
                "Delete the property and start over.",
                "Assume there were no visitors."
            ],
            "answer": 1,
            "rationale": "Funnel gaps often come from instrumentation or naming mismatches."
        },
        {
            "id": "ga4_2",
            "prompt": "What makes a GA4 learning deliverable stronger than a badge alone?",
            "choices": [
                "A dashboard screenshot with no explanation.",
                "A measurement brief linking events, audiences, reports, and marketing decisions.",
                "A list of every GA4 menu item.",
                "A social post announcing the certificate."
            ],
            "answer": 1,
            "rationale": "A measurement brief proves that the learner can translate GA4 into decisions."
        }
    ],
    "meta_media_buying": [
        {
            "id": "mmb_1",
            "prompt": "A Meta lead campaign exits learning but CPL rises while quality falls. What is the strongest optimization mindset?",
            "choices": [
                "Change every variable at once to find a quick win.",
                "Diagnose objective, event quality, audience/creative fit, delivery, and post-click quality before scaling.",
                "Turn off measurement and optimize only for impressions.",
                "Duplicate the campaign ten times with the same assets."
            ],
            "answer": 1,
            "rationale": "Media buying is systems diagnosis: objective, signal, delivery, creative, and landing experience."
        },
        {
            "id": "mmb_2",
            "prompt": "Why should the coach avoid live Meta certification exam screens?",
            "choices": [
                "Because it makes practice slower.",
                "Because viewing or answering live exam content would violate assessment integrity.",
                "Because Meta Ads has no scenarios.",
                "Because mock tests are always identical to the real exam."
            ],
            "answer": 1,
            "rationale": "The system is built for ethical prep only. Live exam content stays private to the candidate."
        }
    ],
    "linkedin_advertising_fundamentals": [
        {
            "id": "laf_1",
            "prompt": "A B2B lead campaign has a tiny audience after many targeting layers. What is the best first fix?",
            "choices": [
                "Add more layers to make it even smaller.",
                "Relax targeting, validate audience size, and keep only attributes that matter to the objective.",
                "Switch to a consumer-only platform immediately.",
                "Remove the landing page."
            ],
            "answer": 1,
            "rationale": "LinkedIn targeting works best when precision is balanced with enough scale to deliver."
        },
        {
            "id": "laf_2",
            "prompt": "Which artifact best proves LinkedIn Ads readiness?",
            "choices": [
                "A full-funnel B2B campaign plan with audience logic, offer, format, budget, and KPI map.",
                "A random list of job titles.",
                "A single boosted post without objective.",
                "A private note saying the platform is expensive."
            ],
            "answer": 0,
            "rationale": "B2B advertising readiness is visible in objective, audience, creative offer, and measurement alignment."
        }
    ],
    "linkedin_marketing_strategy": [
        {
            "id": "lms_1",
            "prompt": "A LinkedIn strategy has strong lead forms but weak brand trust. What should the plan add?",
            "choices": [
                "Only lower-funnel retargeting forever.",
                "Upper- and mid-funnel proof content, organic thought leadership, and measurement beyond CPL.",
                "Stop all content production.",
                "Use the same creative for every audience."
            ],
            "answer": 1,
            "rationale": "A strategy credential is about the whole funnel, not only capture tactics."
        }
    ],
    "tiktok_media_buying": [
        {
            "id": "ttmb_1",
            "prompt": "A TikTok campaign has acceptable CPM but weak conversion. What should be tested first?",
            "choices": [
                "Only the logo size.",
                "Hook, creator style, offer clarity, landing experience, and event quality.",
                "A longer legal footer in the first second.",
                "Turning off all creative rotation."
            ],
            "answer": 1,
            "rationale": "TikTok performance is creative-led, but post-click and event quality still matter."
        },
        {
            "id": "ttmb_2",
            "prompt": "Why does TikTok certification need a stronger approval checkpoint than a free HubSpot badge?",
            "choices": [
                "It is described as a proctored exam with registration/payment flow.",
                "It has no study guide.",
                "It can be taken without identity checks in all cases.",
                "It is only a blog post."
            ],
            "answer": 0,
            "rationale": "Proctored and paid or scheduled exams require human approval and human participation."
        }
    ],
    "hubspot_content_marketing": [
        {
            "id": "hcm_1",
            "prompt": "Which content plan is strongest for an insurance brand?",
            "choices": [
                "Only product posts with no audience problem.",
                "A calendar mapped to audience pain points, search intent, format, channel, CTA, and measurement.",
                "Posting whenever someone remembers.",
                "Copying competitor articles without differentiation."
            ],
            "answer": 1,
            "rationale": "Content marketing works when audience, intent, format, distribution, and measurement line up."
        }
    ],
    "hubspot_social_media": [
        {
            "id": "hsm_1",
            "prompt": "A social channel has regular posting but weak learning. What should the operator add?",
            "choices": [
                "A monthly performance review with themes, hooks, formats, comments, and next tests.",
                "More random hashtags only.",
                "A rule that every post must be the same length.",
                "No campaign goals."
            ],
            "answer": 0,
            "rationale": "A social operating system learns from content performance and audience response."
        }
    ],
    "semrush_seo_toolkit": [
        {
            "id": "seo_1",
            "prompt": "A keyword has volume but the SERP is full of comparison pages. What should the content brief reflect?",
            "choices": [
                "Ignore search intent and write a brand manifesto.",
                "Match commercial comparison intent while adding a stronger insurance-specific angle and proof.",
                "Use the keyword once and stop.",
                "Avoid competitor analysis."
            ],
            "answer": 1,
            "rationale": "SEO strategy starts with the real SERP intent, then improves on the visible gaps."
        }
    ],
    "cxl_growth_marketing": [
        {
            "id": "cxl_1",
            "prompt": "Which growth backlog item is ready for execution?",
            "choices": [
                "Try something new.",
                "A hypothesis with audience, lever, expected impact, evidence, ICE score, instrumentation, and decision rule.",
                "A vague idea from a meeting.",
                "A campaign with no measurement."
            ],
            "answer": 1,
            "rationale": "Growth work needs disciplined experiments, not random activity."
        }
    ]
}


@lru_cache(maxsize=1)
def _raw_catalog() -> dict[str, Any]:
    with CATALOG_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def catalog() -> dict[str, Any]:
    """Return a JSON-safe copy of the certification catalog."""
    data = copy.deepcopy(_raw_catalog())
    data["service_version"] = __version__
    return data


def certification(cert_id: str) -> dict[str, Any]:
    for cert in _raw_catalog()["certifications"]:
        if cert["id"] == cert_id:
            return copy.deepcopy(cert)
    raise KeyError(f"Unknown certification: {cert_id}")


def _profile_terms(profile: dict[str, Any]) -> set[str]:
    raw: list[str] = []
    for key in ("role", "target_role", "goal", "goals", "focus", "focus_tags"):
        value = profile.get(key)
        if isinstance(value, str):
            raw.extend(value.replace(",", " ").replace("/", " ").split())
            raw.append(value)
        elif isinstance(value, list):
            raw.extend(str(item) for item in value)
    terms = {item.strip().casefold() for item in raw if str(item).strip()}
    expanded = set(terms)
    joined = " ".join(sorted(terms))
    for track, aliases in TRACK_ALIASES.items():
        if track in terms or any(alias in joined for alias in aliases):
            expanded.add(track)
            expanded.update(aliases)
    if not expanded:
        expanded.update({"performance", "analytics", "content"})
    return expanded


def _level(profile: dict[str, Any]) -> int:
    raw = str(profile.get("level") or profile.get("experience") or "foundation").casefold()
    for key, score in LEVEL_SCORE.items():
        if key in raw:
            return score
    return 1


def _weekly_hours(profile: dict[str, Any]) -> int:
    try:
        return max(2, min(30, int(profile.get("weekly_hours") or 6)))
    except (TypeError, ValueError):
        return 6


def _deadline_weeks(profile: dict[str, Any]) -> int | None:
    raw = profile.get("deadline_weeks")
    if raw in ("", None):
        return None
    try:
        return max(2, min(24, int(raw)))
    except (TypeError, ValueError):
        return None


def score_cert(cert: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """Score a certification for this learner profile."""
    terms = _profile_terms(profile)
    level = _level(profile)
    weekly = _weekly_hours(profile)
    deadline = _deadline_weeks(profile) or 8
    budget = str(profile.get("budget") or "free_first").casefold()

    tags = {str(tag).casefold() for tag in cert.get("focus_tags", [])}
    track = str(cert.get("track", "")).casefold()
    matches = sorted(tags & terms)
    if track in terms:
        matches.append(track)

    score = float(cert.get("proof_power", 70)) * 0.62
    score += min(24, len(set(matches)) * 7)

    difficulty = int(cert.get("difficulty", 3))
    if difficulty <= level + 1:
        score += 9
    elif difficulty >= level + 3:
        score -= 10
    else:
        score += 3

    available_hours = weekly * deadline
    estimated = int(cert.get("estimated_hours", 12))
    if estimated <= available_hours:
        score += 8
    elif estimated > available_hours * 1.5:
        score -= 12

    if estimated <= 10:
        score += 4
    if cert.get("proctored") and level < 2:
        score -= 7
    if "no_paid" in budget and cert.get("cost") in {"paid", "exam_fee_likely"}:
        score -= 20
    if "paid_ok" in budget and cert.get("cost") == "paid":
        score += 3

    return {
        "cert": cert,
        "score": round(max(0, min(100, score)), 1),
        "matched_focus": sorted(set(matches))[:6],
        "why": _why(cert, matches, level),
    }


def _why(cert: dict[str, Any], matches: list[str], level: int) -> str:
    pieces: list[str] = []
    if matches:
        pieces.append("matches " + ", ".join(sorted(set(matches))[:3]))
    if cert.get("proof_power", 0) >= 90:
        pieces.append("strong market signal")
    if cert.get("proctored"):
        pieces.append("requires human-only exam checkpoint")
    if int(cert.get("difficulty", 3)) <= level + 1:
        pieces.append("realistic next step")
    return "; ".join(pieces) or "balanced credential for the current profile"


def rank_certifications(profile: dict[str, Any]) -> list[dict[str, Any]]:
    ranked = [score_cert(cert, profile) for cert in _raw_catalog()["certifications"]]
    ranked.sort(key=lambda item: (-item["score"], item["cert"]["estimated_hours"], item["cert"]["title"]))
    return ranked


def build_roadmap(profile: dict[str, Any]) -> dict[str, Any]:
    """Build a mentor-style certification plan."""
    ranked = rank_certifications(profile)
    weekly = _weekly_hours(profile)
    deadline = _deadline_weeks(profile)
    top = ranked[:4]
    core = top[:3]
    total_hours = sum(int(item["cert"]["estimated_hours"]) for item in core)
    weeks = deadline or max(4, min(12, math.ceil(total_hours / weekly)))

    weekly_plan = _weekly_plan(core, weeks, weekly)
    approvals = _approval_rail([item["cert"] for item in top])

    return {
        "profile": {
            "role": profile.get("role") or "Marketing specialist",
            "level": profile.get("level") or "foundation",
            "weekly_hours": weekly,
            "deadline_weeks": weeks,
            "budget": profile.get("budget") or "free_first",
            "focus": sorted(_profile_terms(profile))[:10],
        },
        "catalog_last_checked": _raw_catalog()["last_checked"],
        "ethics_policy": copy.deepcopy(_raw_catalog()["ethics_policy"]),
        "recommended_stack": [
            {
                **copy.deepcopy(item["cert"]),
                "score": item["score"],
                "matched_focus": item["matched_focus"],
                "why": item["why"],
            }
            for item in top
        ],
        "weekly_plan": weekly_plan,
        "approval_rail": approvals,
        "mentor_notes": _mentor_notes(top, weeks, weekly),
        "proof_board": _proof_board(top),
        "next_action": _next_action(top),
    }


def _weekly_plan(core: list[dict[str, Any]], weeks: int, weekly_hours: int) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    if not core:
        return plan
    for index in range(weeks):
        item = core[min(len(core) - 1, index * len(core) // weeks)]
        cert = item["cert"]
        topics = cert.get("prep_topics", [])
        start = (index * 2) % max(1, len(topics))
        focus_topics = [topics[(start + offset) % len(topics)] for offset in range(min(3, len(topics)))] if topics else []
        phase = _phase(index, weeks)
        plan.append(
            {
                "week": index + 1,
                "phase": phase,
                "primary_cert_id": cert["id"],
                "primary_cert": cert["title"],
                "hours": weekly_hours,
                "focus_topics": focus_topics,
                "mentor_drill": _mentor_drill(phase, cert, focus_topics),
                "deliverable": _deliverable(phase, cert),
                "checkpoint": _week_checkpoint(phase, cert),
            }
        )
    return plan


def _phase(index: int, weeks: int) -> str:
    ratio = (index + 1) / max(weeks, 1)
    if index == 0:
        return "diagnose"
    if ratio < 0.45:
        return "learn"
    if ratio < 0.75:
        return "apply"
    if ratio < 0.95:
        return "mock"
    return "exam_ready"


def _mentor_drill(phase: str, cert: dict[str, Any], topics: list[str]) -> str:
    topic_text = ", ".join(topics) if topics else cert["track"]
    if phase == "diagnose":
        return f"Verify official source, skim the outline, and take a cold self-test on {topic_text}."
    if phase == "learn":
        return f"Study {topic_text}, then write five flashcards and one real-world example from Xalq Insurance."
    if phase == "apply":
        return f"Turn {topic_text} into a portfolio artifact: {cert['portfolio_task']}"
    if phase == "mock":
        return f"Take an original mock test, review every wrong answer, and redo weak topics within 48 hours."
    return "Use the official provider checklist. The human takes the exam; the agent stays outside the exam environment."


def _deliverable(phase: str, cert: dict[str, Any]) -> str:
    if phase == "diagnose":
        return "baseline score, source link, and risk checklist"
    if phase == "learn":
        return "flashcards plus one-page concept map"
    if phase == "apply":
        return cert["portfolio_task"]
    if phase == "mock":
        return "mock score, error log, and retake plan"
    return "human-approved exam or badge publishing checklist"


def _week_checkpoint(phase: str, cert: dict[str, Any]) -> str:
    if phase == "exam_ready" and cert.get("proctored"):
        return "Human approval required before booking or launching the proctored exam."
    if phase == "exam_ready":
        return "Human completes the assessment; agent only prepares final review notes."
    if cert.get("cost") in {"paid", "exam_fee_likely"}:
        return "No payment or booking without explicit approval."
    return "Draft-only study work; no risky action."


def _approval_rail(certs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    base = copy.deepcopy(_raw_catalog()["approval_checkpoints"])
    relevant: list[dict[str, Any]] = []
    has_paid = any(cert.get("cost") in {"paid", "exam_fee_likely"} for cert in certs)
    has_proctored = any(cert.get("proctored") for cert in certs)
    for checkpoint in base:
        cid = checkpoint["id"]
        if cid == "paid_enrollment" and not has_paid:
            continue
        if cid in {"exam_booking", "live_exam"} and not has_proctored:
            continue
        item = dict(checkpoint)
        item["status"] = "human_required" if cid in {"paid_enrollment", "exam_booking", "live_exam", "certificate_publish"} else "human_handles_credentials"
        relevant.append(item)
    return relevant


def _mentor_notes(top: list[dict[str, Any]], weeks: int, weekly: int) -> list[str]:
    if not top:
        return ["No certifications available in the catalog."]
    first = top[0]["cert"]
    notes = [
        f"Start with {first['title']} because it has the best fit-to-proof ratio for this profile.",
        f"Plan tempo: {weeks} weeks at about {weekly} hours/week. Protect one review block every week.",
        "Every badge must produce a work artifact; otherwise it is just a logo on a profile.",
        "Live exams are human-only. The coach can train, quiz, and prepare checklists, but it cannot sit inside the exam."
    ]
    if any(item["cert"].get("proctored") for item in top):
        notes.append("Proctored exams are treated as high-integrity checkpoints: booking, launch, ID checks, and answers stay with the human.")
    return notes


def _proof_board(top: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "cert_id": item["cert"]["id"],
            "title": item["cert"]["title"],
            "proof": item["cert"]["portfolio_task"],
            "mentor_move": item["cert"]["mentor_move"],
        }
        for item in top[:4]
    ]


def _next_action(top: list[dict[str, Any]]) -> dict[str, str]:
    cert = top[0]["cert"] if top else {}
    return {
        "label": "Start baseline",
        "detail": f"Open the official source for {cert.get('title', 'the first certification')}, confirm it is still active, then take a 10-question original mock."
    }


def _questions_for(cert_id: str, count: int) -> list[dict[str, Any]]:
    cert = certification(cert_id)
    questions = copy.deepcopy(QUESTION_BANK.get(cert_id, []))
    topics = cert.get("prep_topics", [])
    for index, topic in enumerate(topics):
        questions.append(
            {
                "id": f"{cert_id}_topic_{index}",
                "prompt": f"You are preparing for {cert['title']}. Which output best proves competence in {topic}?",
                "choices": [
                    "A vague note that the topic was reviewed.",
                    "A practical artifact tied to an objective, decision, metric, and next action.",
                    "A copied paragraph from a third-party forum.",
                    "A live exam screenshot."
                ],
                "answer": 1,
                "rationale": "The coach values applied proof and never uses live exam content."
            }
        )
    return questions[: max(1, min(count, len(questions)))]


def mock_exam(cert_id: str, count: int = 6) -> dict[str, Any]:
    cert = certification(cert_id)
    questions = _questions_for(cert_id, count)
    safe_questions = [
        {
            "id": q["id"],
            "prompt": q["prompt"],
            "choices": q["choices"],
        }
        for q in questions
    ]
    return {
        "cert_id": cert_id,
        "title": cert["title"],
        "policy": "Original practice only. No live exam questions, dumps, screenshots, or proctoring assistance.",
        "count": len(safe_questions),
        "questions": safe_questions,
    }


def grade_mock(cert_id: str, answers: dict[str, int], count: int | None = None) -> dict[str, Any]:
    questions = _questions_for(cert_id, count or max(6, len(answers)))
    total = len(questions)
    correct = 0
    review: list[dict[str, Any]] = []
    for q in questions:
        user_answer = answers.get(q["id"])
        ok = user_answer == q["answer"]
        correct += 1 if ok else 0
        review.append(
            {
                "id": q["id"],
                "correct": ok,
                "your_answer": user_answer,
                "correct_answer": q["answer"],
                "rationale": q["rationale"],
            }
        )
    score = round((correct / total) * 100, 1) if total else 0
    if score >= 85:
        verdict = "ready_for_official_practice"
    elif score >= 70:
        verdict = "review_weak_spots"
    else:
        verdict = "rebuild_foundation"
    return {
        "cert_id": cert_id,
        "score": score,
        "correct": correct,
        "total": total,
        "verdict": verdict,
        "review": review,
    }

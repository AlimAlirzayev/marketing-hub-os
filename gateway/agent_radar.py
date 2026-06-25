"""Security-first registry and scoring for external agent/tool candidates.

Agent Radar is deliberately an evaluation layer, not an execution layer. It
helps decide whether a candidate is worth a sandbox trial, while never granting
credentials, network privileges, or production access by itself.
"""

from __future__ import annotations

import argparse
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import security


ROOT_DIR = Path(__file__).resolve().parent.parent
RADAR_DIR = ROOT_DIR / "data" / "agent_radar"
CANDIDATES_PATH = RADAR_DIR / "candidates.jsonl"
SCAN_PATH = RADAR_DIR / "marketing_os_scan.json"
SCAN_REPORT_PATH = ROOT_DIR / "output" / "agent-radar" / "marketing_os_scan.md"


WORLD_REFERENCE_MODULES = [
    {
        "name": "Microsoft Agent 365",
        "pattern": "agent control plane",
        "strength": "Central inventory, identity, access control, observability, and policy for agents.",
        "fit_for_us": "Use the same control-plane idea locally before any external agent gets tools.",
        "source": "https://www.microsoft.com/en-us/microsoft-agent-365",
    },
    {
        "name": "ServiceNow AI Control Tower",
        "pattern": "enterprise AI governance tower",
        "strength": "Discovers agents/models/identities, governs risk, monitors runtime performance, and measures value.",
        "fit_for_us": "Good model for one dashboard that connects value, risk, and ownership.",
        "source": "https://www.servicenow.com/products/ai-control-tower.html",
    },
    {
        "name": "Salesforce Agentforce",
        "pattern": "domain agents for service, sales, and marketing",
        "strength": "CRM-native agents for customer service, pipeline, content, and campaigns.",
        "fit_for_us": "Inspiration for CX and campaign agents, but only after RAMIN OS has strong permissions.",
        "source": "https://www.salesforce.com/news/stories/agentic-marketing-teams-announcement/",
    },
    {
        "name": "UiPath Agentic Automation",
        "pattern": "governed automation plus AI agents",
        "strength": "Combines workflow automation, agent building, audit, and enterprise controls.",
        "fit_for_us": "Useful pattern for sandbox auditions that turn good ideas into repeatable workflows.",
        "source": "https://www.uipath.com/platform/agentic-automation/foundation",
    },
    {
        "name": "OWASP Agentic AI Security and Governance",
        "pattern": "security baseline",
        "strength": "Focuses on autonomous agent risks, identity, supply chain, provenance, and governance.",
        "fit_for_us": "Security baseline for all future agent modules.",
        "source": "https://genai.owasp.org/resource/state-of-agentic-ai-security-and-governance/",
    },
]


@dataclass
class AgentCandidate:
    name: str
    use_case: str
    description: str = ""
    source_url: str = ""
    repository_url: str = ""
    owner: str = ""
    requested_permissions: list[str] = field(default_factory=list)
    claims: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class AgentEvaluation:
    category: str
    benefit_score: int
    risk_score: int
    trust_score: int
    verdict: str
    reasons: list[str]
    required_controls: list[str]


MARKETING_OS_BLUEPRINTS = [
    {
        "candidate": AgentCandidate(
            name="Agent Governance Control Plane",
            use_case="security governance audit policy approval for every Marketing OS agent",
            description=(
                "Automatically maps agents, requested permissions, value, risk, owner, audit trail, "
                "sandbox status, and required human approvals across the Marketing OS."
            ),
            owner="RAMIN OS",
            requested_permissions=["file_read", "database_read", "network"],
            evidence=[
                "gateway/security.py",
                "gateway/agent_radar.py",
                "SECURITY.md",
                "OWASP Agentic AI Security and Governance",
                "Microsoft Agent 365 control-plane pattern",
                "ServiceNow AI Control Tower pattern",
            ],
            notes="Reinforces the current module; should run automatically and approve nothing for production.",
        ),
        "strategic_priority": 96,
        "phase": "P0 - reinforce now",
        "automation_job": "Daily agent-risk and opportunity scan with a board-level summary.",
        "integration_points": ["gateway/security.py", "gateway/executor.py", "services.json", "app.py"],
        "why": "Best professional fit because it makes all later agents safer, measurable, and auditable.",
    },
    {
        "candidate": AgentCandidate(
            name="CX Resolution Agent",
            use_case="customer service ticket triage SLA sentiment response drafting analytics",
            description=(
                "Reads CX signals, clusters complaints, drafts replies, flags SLA risk, and prepares "
                "resolution suggestions without sending messages autonomously."
            ),
            owner="RAMIN OS",
            requested_permissions=["database_read", "customer_data"],
            evidence=[
                "cx-command-center",
                "gateway/database.py",
                "Gartner customer-service agentic AI trend",
                "Salesforce Agentforce service pattern",
            ],
            notes="High business value, but customer data requires redaction and human approval for replies.",
        ),
        "strategic_priority": 91,
        "phase": "P1 - sandbox audition",
        "automation_job": "Daily complaint themes, SLA risks, and draft-response queue.",
        "integration_points": ["cx-command-center", "gateway/database.py", "briefing_panel.py"],
        "why": "Strongest immediate ROI for customer experience, but must stay draft-only first.",
    },
    {
        "candidate": AgentCandidate(
            name="Campaign Operations Agent",
            use_case="marketing automation campaign budget creative pipeline content performance reporting",
            description=(
                "Combines Meta performance, creative output, and publishing plans to recommend next campaign "
                "actions and generate draft tasks for humans."
            ),
            owner="RAMIN OS",
            requested_permissions=["network", "database_read", "file_write"],
            evidence=[
                "ads-studio",
                "creative_studio.py",
                "publisher",
                "Salesforce agentic marketing teams pattern",
                "UiPath governed automation pattern",
            ],
            notes="Useful after the control plane because posting and budget changes need approval gates.",
        ),
        "strategic_priority": 86,
        "phase": "P2 - approval-gated workflow",
        "automation_job": "Weekly campaign action plan with draft briefs, no spend changes without approval.",
        "integration_points": ["ads-studio", "creative_studio.py", "publisher", "meta-capi"],
        "why": "Good marketing leverage, but write/publish paths must stay behind checkpoints.",
    },
    {
        "candidate": AgentCandidate(
            name="Market Intelligence Agent",
            use_case="data analytics competitor pricing influencer trend monitoring KPI report",
            description=(
                "Reads price, influencer, YouTube, web, and ads signals to detect opportunities and risks "
                "for insurance marketing decisions."
            ),
            owner="RAMIN OS",
            requested_permissions=["network", "browser", "scraping", "database_read"],
            evidence=[
                "price-hunter",
                "influencer-hunter",
                "influencer-hunter/youtube_poc.py",
                "Agentic monitoring agent trend",
            ],
            notes="Valuable intelligence module; scraping and browser use require domain allowlists.",
        ),
        "strategic_priority": 83,
        "phase": "P2 - domain-allowlisted scan",
        "automation_job": "Weekly opportunity map: competitors, creators, topics, and pricing anomalies.",
        "integration_points": ["price-hunter", "influencer-hunter", "ads-studio", "gateway/tools/browser.py"],
        "why": "Strong research value, but must be limited to public sources and explicit domain rules.",
    },
]


_CATEGORY_KEYWORDS = {
    "customer_service": (
        "support",
        "customer",
        "ticket",
        "triage",
        "sentiment",
        "sla",
        "chat",
        "review",
        "musteri",
        "sikayet",
        "complaint",
    ),
    "marketing_automation": (
        "marketing",
        "campaign",
        "ads",
        "lead",
        "crm",
        "content",
        "social",
        "email",
        "growth",
        "reklam",
        "kampaniya",
    ),
    "data_analytics": (
        "analytics",
        "data",
        "dashboard",
        "report",
        "forecast",
        "monitor",
        "price",
        "competitor",
        "kpi",
        "analitika",
        "hesabat",
    ),
    "security": (
        "security",
        "audit",
        "compliance",
        "guardrail",
        "risk",
        "policy",
        "privacy",
    ),
}

_PERMISSION_RISK = {
    "network": 8,
    "browser": 10,
    "scraping": 12,
    "file_read": 10,
    "file_write": 15,
    "database_read": 12,
    "database_write": 22,
    "subprocess": 25,
    "customer_data": 25,
    "pii": 30,
    "secrets": 40,
    "admin": 40,
    "local_network": 45,
    "social_posting": 20,
    "email_send": 20,
    "payment": 50,
}

_RISKY_CLAIMS = (
    "fully autonomous",
    "no human",
    "guaranteed",
    "make money",
    "crypto",
    "wallet",
    "payment",
    "private key",
    "bypass",
    "unlimited",
    "delete",
    "root",
    "admin",
    "secret",
    "credential",
)


def _norm(value: str) -> str:
    return (value or "").casefold()


def _split_csv(value: str) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _text(candidate: AgentCandidate) -> str:
    return " ".join(
        [
            candidate.name,
            candidate.use_case,
            candidate.description,
            candidate.owner,
            " ".join(candidate.claims),
            " ".join(candidate.evidence),
            candidate.notes,
        ]
    )


def classify_category(candidate: AgentCandidate) -> str:
    text = _norm(_text(candidate))
    scores: dict[str, int] = {}
    for category, keywords in _CATEGORY_KEYWORDS.items():
        scores[category] = sum(1 for keyword in keywords if keyword in text)
    category, score = max(scores.items(), key=lambda item: item[1])
    return category if score else "general_productivity"


def evaluate_candidate(candidate: AgentCandidate) -> AgentEvaluation:
    """Score a candidate for safe sandbox consideration."""
    category = classify_category(candidate)
    text = _norm(_text(candidate))
    reasons: list[str] = []
    controls: list[str] = [
        "Sandbox only; no production credentials.",
        "Read-only access by default.",
        "All actions must be logged.",
    ]

    benefit = 30
    if category in {"customer_service", "marketing_automation", "data_analytics"}:
        benefit += 25
        reasons.append(f"Relevant business category: {category}.")
    elif category == "security":
        benefit += 15
        reasons.append("Security-related candidate; useful only as a defensive tool.")

    keyword_hits = 0
    for keywords in _CATEGORY_KEYWORDS.values():
        keyword_hits += sum(1 for keyword in keywords if keyword in text)
    benefit += min(keyword_hits * 4, 25)
    if candidate.evidence:
        benefit += min(len(candidate.evidence) * 5, 15)
        reasons.append("Has some external evidence or references.")
    benefit = min(100, benefit)

    risk = 15
    if not candidate.owner:
        risk += 8
        reasons.append("Owner is not identified.")
    if not candidate.repository_url:
        risk += 10
        reasons.append("No public repository or code reference provided.")
    if not candidate.evidence:
        risk += 8
        reasons.append("No evidence, demos, docs, or feedback references provided.")

    for url_label, url in (("source_url", candidate.source_url), ("repository_url", candidate.repository_url)):
        if not url:
            continue
        decision = security.validate_url(url)
        if not decision.allowed:
            risk += 35
            reasons.append(f"{url_label} failed URL safety check: {decision.reason}")
        elif url.casefold().startswith("http://"):
            risk += 10
            reasons.append(f"{url_label} is not HTTPS.")

    for permission in candidate.requested_permissions:
        key = permission.strip().casefold()
        added = _PERMISSION_RISK.get(key, 12)
        risk += added
        reasons.append(f"Permission risk: {key} (+{added}).")
        if key in {"payment", "database_write", "file_write", "social_posting", "email_send"}:
            controls.append("Human approval required for every write/send/payment action.")
        if key in {"pii", "customer_data", "database_read"}:
            controls.append("PII minimization and redaction required before data leaves RAMIN OS.")
        if key in {"secrets", "admin", "local_network"}:
            controls.append("Do not grant this permission without manual security review.")

    risky_claims = [claim for claim in _RISKY_CLAIMS if claim in text]
    if risky_claims:
        added = min(35, len(risky_claims) * 7)
        risk += added
        reasons.append(f"Risky or unverifiable claims detected: {', '.join(risky_claims)}.")

    if candidate.repository_url and "github.com" in candidate.repository_url.casefold():
        risk -= 6
        reasons.append("GitHub repository reference slightly improves auditability.")
    if candidate.owner and candidate.evidence:
        risk -= 5
        reasons.append("Identified owner plus evidence improves trust.")

    risk = max(0, min(100, risk))
    trust = max(0, min(100, 100 - risk + min(len(candidate.evidence) * 4, 12)))

    if risk >= 75:
        verdict = "reject"
    elif risk >= 55:
        verdict = "quarantine"
    elif risk >= 35:
        verdict = "sandbox_review"
    else:
        verdict = "approved_for_sandbox"

    if verdict != "reject":
        controls.append("No autonomous production deployment; pass an audition task first.")
    controls = list(dict.fromkeys(controls))

    return AgentEvaluation(
        category=category,
        benefit_score=benefit,
        risk_score=risk,
        trust_score=trust,
        verdict=verdict,
        reasons=reasons or ["No major signals found; treat as unproven."],
        required_controls=controls,
    )


def _fit_score(evaluation: AgentEvaluation, strategic_priority: int) -> int:
    score = (
        evaluation.benefit_score * 0.40
        + evaluation.trust_score * 0.25
        + strategic_priority * 0.35
        - evaluation.risk_score * 0.20
    )
    return max(0, min(100, round(score)))


def build_marketing_os_scan(now: float | None = None) -> dict:
    """Build the automatic Marketing OS agent-governance and opportunity map."""
    timestamp = time.time() if now is None else now
    records: list[dict] = []

    for blueprint in MARKETING_OS_BLUEPRINTS:
        candidate = blueprint["candidate"]
        evaluation = evaluate_candidate(candidate)
        strategic_priority = int(blueprint["strategic_priority"])
        fit = _fit_score(evaluation, strategic_priority)
        if blueprint["phase"].startswith("P0"):
            fit = min(100, fit + 8)
        if evaluation.verdict == "reject":
            decision = "do_not_build"
        elif blueprint["phase"].startswith("P0"):
            decision = "reinforce_current_module"
        elif evaluation.risk_score >= 55:
            decision = "sandbox_only_after_controls"
        else:
            decision = "sandbox_audition"

        records.append(
            {
                "candidate": asdict(candidate),
                "evaluation": asdict(evaluation),
                "strategic_priority": strategic_priority,
                "fit_score": fit,
                "phase": blueprint["phase"],
                "decision": decision,
                "automation_job": blueprint["automation_job"],
                "integration_points": blueprint["integration_points"],
                "why": blueprint["why"],
            }
        )

    records.sort(key=lambda item: (item["fit_score"], -item["evaluation"]["risk_score"]), reverse=True)
    recommendation = records[0]
    avg_risk = round(sum(item["evaluation"]["risk_score"] for item in records) / len(records), 1)
    avg_fit = round(sum(item["fit_score"] for item in records) / len(records), 1)

    return {
        "id": uuid.uuid4().hex[:12],
        "generated_at": timestamp,
        "generated_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp)),
        "mission": "Automatically map which agent-governance or agent-workflow module is useful for Marketing OS.",
        "operating_principle": "Security first: discover, score, sandbox, audit; never grant production access automatically.",
        "world_reference_modules": WORLD_REFERENCE_MODULES,
        "system_fit_summary": {
            "overall_rating": 88,
            "avg_fit_score": avg_fit,
            "avg_risk_score": avg_risk,
            "best_variant": "Agent Governance Control Plane, not an open agent marketplace.",
            "why_not_marketplace_first": (
                "Open marketplaces create tool, identity, data, and permission risk. Marketing OS needs a "
                "control plane before it needs more agents."
            ),
        },
        "recommendation": {
            "name": recommendation["candidate"]["name"],
            "decision": recommendation["decision"],
            "phase": recommendation["phase"],
            "fit_score": recommendation["fit_score"],
            "risk_score": recommendation["evaluation"]["risk_score"],
            "automation_job": recommendation["automation_job"],
            "why": recommendation["why"],
        },
        "ranked_candidates": records,
        "next_actions": [
            "Run this scan daily and show the result in the dashboard.",
            "Keep external agents blocked from production until they pass a sandbox audition.",
            "Build the first real agent workflow as CX draft-resolution, because it has strong value but controllable risk.",
            "Add per-agent identity and permission manifests before write/send/post actions are enabled.",
        ],
    }


def load_latest_scan() -> dict | None:
    if not SCAN_PATH.exists():
        return None
    with SCAN_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def scan_is_stale(scan: dict | None, max_age_hours: int = 24) -> bool:
    if not scan:
        return True
    generated_at = float(scan.get("generated_at") or 0)
    return (time.time() - generated_at) > (max_age_hours * 3600)


def render_marketing_os_scan_report(scan: dict) -> str:
    lines = [
        "# Marketing OS Agent Governance Scan",
        "",
        f"Generated: {scan['generated_at_iso']}",
        "",
        "## Executive Verdict",
        "",
        f"- Best variant: {scan['system_fit_summary']['best_variant']}",
        f"- Overall rating: {scan['system_fit_summary']['overall_rating']}/100",
        f"- Average fit: {scan['system_fit_summary']['avg_fit_score']}/100",
        f"- Average risk: {scan['system_fit_summary']['avg_risk_score']}/100",
        f"- Recommendation: {scan['recommendation']['name']} ({scan['recommendation']['phase']})",
        f"- Automatic job: {scan['recommendation']['automation_job']}",
        "",
        "## World Comparison",
        "",
    ]
    for module in scan["world_reference_modules"]:
        lines.extend(
            [
                f"### {module['name']}",
                f"- Pattern: {module['pattern']}",
                f"- Strength: {module['strength']}",
                f"- Fit for us: {module['fit_for_us']}",
                f"- Source: {module['source']}",
                "",
            ]
        )

    lines.extend(["## Ranked Marketing OS Modules", ""])
    for item in scan["ranked_candidates"]:
        candidate = item["candidate"]
        evaluation = item["evaluation"]
        lines.extend(
            [
                f"### {candidate['name']}",
                f"- Fit: {item['fit_score']}/100",
                f"- Risk: {evaluation['risk_score']}/100",
                f"- Verdict: {evaluation['verdict']}",
                f"- Decision: {item['decision']}",
                f"- Phase: {item['phase']}",
                f"- Automation job: {item['automation_job']}",
                f"- Why: {item['why']}",
                f"- Integrations: {', '.join(item['integration_points'])}",
                "",
            ]
        )

    lines.extend(["## Next Actions", ""])
    for action in scan["next_actions"]:
        lines.append(f"- {action}")
    return "\n".join(lines).strip() + "\n"


def run_marketing_os_scan() -> dict:
    scan = build_marketing_os_scan()
    RADAR_DIR.mkdir(parents=True, exist_ok=True)
    SCAN_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SCAN_PATH.open("w", encoding="utf-8") as fh:
        json.dump(scan, fh, indent=2, ensure_ascii=True)
    SCAN_REPORT_PATH.write_text(render_marketing_os_scan_report(scan), encoding="utf-8")
    security.audit_event(
        "agent_radar_marketing_os_scan",
        security.allow("agent_radar", "Marketing OS agent-governance scan completed; no execution granted."),
        {
            "recommendation": scan["recommendation"]["name"],
            "decision": scan["recommendation"]["decision"],
            "report": str(SCAN_REPORT_PATH),
        },
    )
    return scan


def add_candidate(candidate: AgentCandidate) -> dict:
    evaluation = evaluate_candidate(candidate)
    record = {
        "id": uuid.uuid4().hex[:12],
        "created_at": time.time(),
        "candidate": asdict(candidate),
        "evaluation": asdict(evaluation),
    }
    RADAR_DIR.mkdir(parents=True, exist_ok=True)
    with CANDIDATES_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=True) + "\n")
    security.audit_event(
        "agent_radar_candidate",
        security.allow("agent_radar", "Candidate evaluated; no execution granted."),
        {"candidate": candidate.name, "verdict": evaluation.verdict},
    )
    return record


def load_records(limit: int | None = None) -> list[dict]:
    if not CANDIDATES_PATH.exists():
        return []
    records: list[dict] = []
    with CANDIDATES_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    records.sort(key=lambda item: item.get("created_at", 0), reverse=True)
    return records[:limit] if limit else records


def _record_summary(record: dict) -> str:
    candidate = record["candidate"]
    evaluation = record["evaluation"]
    return (
        f"{record['id']} | {candidate['name']} | {evaluation['category']} | "
        f"benefit={evaluation['benefit_score']} risk={evaluation['risk_score']} "
        f"trust={evaluation['trust_score']} verdict={evaluation['verdict']}"
    )


def render_report(records: list[dict] | None = None) -> str:
    records = load_records() if records is None else records
    if not records:
        return "Agent Radar has no candidates yet."
    lines = ["# Agent Radar Report", ""]
    for record in records:
        lines.append(f"## {_record_summary(record)}")
        evaluation = record["evaluation"]
        lines.append("")
        lines.append("Required controls:")
        for control in evaluation["required_controls"]:
            lines.append(f"- {control}")
        lines.append("")
        lines.append("Reasons:")
        for reason in evaluation["reasons"][:8]:
            lines.append(f"- {reason}")
        lines.append("")
    return "\n".join(lines).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Security-first agent candidate radar.")
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="Evaluate and store a candidate.")
    add.add_argument("--name", required=True)
    add.add_argument("--use-case", required=True)
    add.add_argument("--description", default="")
    add.add_argument("--source-url", default="")
    add.add_argument("--repository-url", default="")
    add.add_argument("--owner", default="")
    add.add_argument("--permissions", default="", help="Comma-separated permissions.")
    add.add_argument("--claims", default="", help="Comma-separated claims.")
    add.add_argument("--evidence", default="", help="Comma-separated evidence URLs/notes.")
    add.add_argument("--notes", default="")

    sub.add_parser("list", help="List stored candidates.")
    sub.add_parser("report", help="Print a Markdown report.")
    sub.add_parser("autoscan", help="Run the automatic Marketing OS governance scan.")
    sub.add_parser("autoscan-report", help="Print the latest automatic Marketing OS scan report.")

    args = parser.parse_args()
    if args.command == "add":
        record = add_candidate(
            AgentCandidate(
                name=args.name,
                use_case=args.use_case,
                description=args.description,
                source_url=args.source_url,
                repository_url=args.repository_url,
                owner=args.owner,
                requested_permissions=_split_csv(args.permissions),
                claims=_split_csv(args.claims),
                evidence=_split_csv(args.evidence),
                notes=args.notes,
            )
        )
        print(_record_summary(record))
    elif args.command == "list":
        for record in load_records():
            print(_record_summary(record))
    elif args.command == "report":
        print(render_report())
    elif args.command == "autoscan":
        scan = run_marketing_os_scan()
        print(
            f"{scan['id']} | {scan['recommendation']['name']} | "
            f"fit={scan['recommendation']['fit_score']} risk={scan['recommendation']['risk_score']} | "
            f"report={SCAN_REPORT_PATH}"
        )
    elif args.command == "autoscan-report":
        scan = load_latest_scan()
        if scan_is_stale(scan):
            scan = run_marketing_os_scan()
        print(render_marketing_os_scan_report(scan))


if __name__ == "__main__":
    main()

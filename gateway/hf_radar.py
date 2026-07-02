"""Hugging Face opportunity radar for RAMIN OS.

This module turns the Desktop Hugging Face research into a governed adoption
map. It does not call hosted models, does not read tokens, and does not grant
tool access. Its job is to rank Hugging Face model/tool options by business
value, data boundary, implementation readiness, and security risk before any
pilot gets near customer data.
"""

from __future__ import annotations

import argparse
import json
import shutil
import time
import uuid
from dataclasses import asdict, dataclass, field
from importlib.util import find_spec
from pathlib import Path

from . import security


ROOT_DIR = Path(__file__).resolve().parent.parent
HF_RADAR_DIR = ROOT_DIR / "data" / "hf_radar"
HF_SCAN_PATH = HF_RADAR_DIR / "hf_opportunity_scan.json"
HF_REPORT_PATH = ROOT_DIR / "output" / "hf-radar" / "hf_opportunity_scan.md"

DESKTOP_RESEARCH_SOURCE = r"C:\Users\a.alirzayev\Desktop\hugginface free oportunities.docx"


HF_OFFICIAL_REFERENCES = [
    {
        "name": "Inference Providers",
        "url": "https://huggingface.co/docs/inference-providers/index",
        "why_it_matters": "Hosted Inference Providers and OpenAI-compatible APIs are useful for public-data PoCs, not a free production backbone.",
    },
    {
        "name": "Hub API for OpenAI-compatible models",
        "url": "https://huggingface.co/docs/inference-providers/hub-api",
        "why_it_matters": "The router can list chat models and provider metadata for governed comparison.",
    },
    {
        "name": "Hugging Face MCP Server",
        "url": "https://huggingface.co/docs/hub/agents-mcp",
        "why_it_matters": "Hub model, dataset, Space, documentation, and paper search can become a read-only discovery tool.",
    },
    {
        "name": "Spaces as MCP servers",
        "url": "https://huggingface.co/docs/hub/spaces-mcp-servers",
        "why_it_matters": "Public Spaces can expose tools, but they must be treated as untrusted external execution.",
    },
    {
        "name": "hf CLI and skills",
        "url": "https://huggingface.co/docs/huggingface_hub/guides/cli",
        "why_it_matters": "The hf CLI is the standard local control surface for Hub repos, downloads, and agent skills.",
    },
    {
        "name": "Text Embeddings Inference",
        "url": "https://huggingface.co/docs/text-embeddings-inference/quick_tour",
        "why_it_matters": "TEI is the strongest private RAG/embedding path for internal documents and customer-adjacent retrieval.",
    },
]


@dataclass(frozen=True)
class HFOpportunity:
    name: str
    category: str
    use_case: str
    description: str
    integration_points: list[str]
    data_boundary: str
    business_impact: int
    cost_leverage: int
    implementation_readiness: int
    implementation_effort: int
    external_calls: bool = False
    requires_token: bool = False
    handles_sensitive_data: bool = False
    sensitive_data_allowed: bool = False
    risks: list[str] = field(default_factory=list)
    controls: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class HFEvaluation:
    value_score: int
    risk_score: int
    readiness_score: int
    privacy_score: int
    fit_score: int
    verdict: str
    decision: str
    reasons: list[str]
    required_controls: list[str]


HF_OPPORTUNITIES = [
    HFOpportunity(
        name="Private RAG Embedding Layer (TEI + HF embedding models)",
        category="private_rag",
        use_case="internal document search, Brain retrieval, policy/FAQ retrieval, CX evidence lookup",
        description=(
            "Self-host Text Embeddings Inference with open embedding models so RAMIN OS can search "
            "its own documents without sending sensitive content to public endpoints."
        ),
        integration_points=["brain", "gateway/rag.py", "gateway/knowledge.py", "cx-command-center", "docs"],
        data_boundary="private_or_internal_only",
        business_impact=94,
        cost_leverage=88,
        implementation_readiness=80,
        implementation_effort=3,
        external_calls=False,
        requires_token=False,
        handles_sensitive_data=True,
        sensitive_data_allowed=True,
        risks=[
            "model quality must be benchmarked on Azerbaijani, Turkish, Russian, and insurance-domain text",
            "local CPU/GPU capacity can limit latency",
            "model licenses and versions must be pinned",
        ],
        controls=[
            "Use open-license embedding models only.",
            "Keep the embedding server on localhost or a private host.",
            "Do not upload customer data to public Spaces or hosted providers.",
            "Run retrieval quality tests before replacing current Brain search.",
        ],
        references=[
            "https://huggingface.co/docs/text-embeddings-inference/quick_tour",
        ],
    ),
    HFOpportunity(
        name="Local Open-Weight LLM Serving (llama.cpp/vLLM/SGLang)",
        category="private_llm",
        use_case="private drafting, local analysis, fallback model for gateway and AI Council",
        description=(
            "Run selected open-weight HF models behind an OpenAI-compatible local endpoint for tasks "
            "that must stay inside RAMIN OS."
        ),
        integration_points=["llm_router.py", "gateway/llm.py", "orchestrator/router.py", "brain"],
        data_boundary="private_or_internal_only",
        business_impact=90,
        cost_leverage=84,
        implementation_readiness=68,
        implementation_effort=4,
        external_calls=False,
        requires_token=False,
        handles_sensitive_data=True,
        sensitive_data_allowed=True,
        risks=[
            "model hallucination and weak Azerbaijani reasoning must be measured",
            "Windows/corporate hardware may constrain useful model size",
            "large model downloads need explicit operator approval",
        ],
        controls=[
            "Keep private tier routed to local endpoints only.",
            "Benchmark against current Gemini/Groq outputs before promotion.",
            "Record model id, quantization, license, and hardware requirements.",
        ],
        references=[
            "https://huggingface.co/docs/huggingface.js/inference/README",
        ],
    ),
    HFOpportunity(
        name="Private CX Sentiment Classifier",
        category="private_sentiment",
        use_case="customer complaint sentiment reinforcement for CX triage",
        description=(
            "Use a local/private Hugging Face text-classification endpoint as an additional CX sentiment "
            "signal. It can elevate negative risk, but deterministic rules remain the safety baseline."
        ),
        integration_points=["cx-command-center/triage.py", "cx-command-center/sentiment_hf.py", "SECURITY.md"],
        data_boundary="private_or_internal_only",
        business_impact=84,
        cost_leverage=82,
        implementation_readiness=82,
        implementation_effort=2,
        external_calls=False,
        requires_token=False,
        handles_sensitive_data=True,
        sensitive_data_allowed=True,
        risks=[
            "off-the-shelf multilingual sentiment models can misread Azerbaijani complaint nuance",
            "model drift or weak local endpoint availability must not weaken CX risk handling",
        ],
        controls=[
            "Keep deterministic CX rules as the baseline.",
            "Allow HF sentiment to raise risk, not lower rule-based complaint risk.",
            "Use local/private endpoints for customer messages.",
            "Benchmark labels against Azerbaijani complaint examples before operational use.",
        ],
        references=[
            "https://huggingface.co/docs/inference-providers/tasks/text-classification",
        ],
    ),
    HFOpportunity(
        name="HF MCP + hf CLI Discovery Workbench",
        category="discovery_tooling",
        use_case="model, dataset, Space, paper, and documentation discovery for agents",
        description=(
            "Give Codex/Claude-style agents a read-only Hugging Face research surface through the HF MCP "
            "Server and hf CLI skills, while keeping execution and credentials out of automatic flows."
        ),
        integration_points=["claude-agents", "gateway/agent_radar.py", "docs", "scripts"],
        data_boundary="public_metadata_only",
        business_impact=78,
        cost_leverage=82,
        implementation_readiness=86,
        implementation_effort=2,
        external_calls=True,
        requires_token=True,
        handles_sensitive_data=False,
        sensitive_data_allowed=False,
        risks=[
            "MCP tools can expand agent capability faster than governance if installed casually",
            "write-capable tokens could upload or mutate Hub repos",
        ],
        controls=[
            "Use read-only/fine-grained Hugging Face tokens for discovery.",
            "Run candidate models, Spaces, and agents through Agent Radar before use.",
            "Do not connect MCP tools to customer-data workflows.",
        ],
        references=[
            "https://huggingface.co/docs/hub/agents-mcp",
            "https://huggingface.co/docs/huggingface_hub/guides/cli",
        ],
    ),
    HFOpportunity(
        name="HF Router PoC for Public Prompts",
        category="hosted_inference",
        use_case="quick non-sensitive model comparison for public marketing prompts",
        description=(
            "Use Hugging Face Inference Providers/Router only for public-data experiments and model "
            "comparison. It is not treated as unlimited free production capacity."
        ),
        integration_points=["llm_router.py", "atelier", "copy-studio", "ads-studio"],
        data_boundary="public_or_synthetic_prompts_only",
        business_impact=66,
        cost_leverage=55,
        implementation_readiness=74,
        implementation_effort=2,
        external_calls=True,
        requires_token=True,
        handles_sensitive_data=False,
        sensitive_data_allowed=False,
        risks=[
            "free credit is small and not reliable for production",
            "external providers can have their own retention/security policies",
            "routing can select a provider that is unsuitable for regulated data",
        ],
        controls=[
            "Block customer data, policy documents, and claims data from this route.",
            "Log provider/model usage through the existing LLM usage board.",
            "Keep a local/private fallback for sensitive tasks.",
        ],
        references=[
            "https://huggingface.co/docs/inference-providers/index",
            "https://huggingface.co/docs/inference-providers/hub-api",
        ],
    ),
    HFOpportunity(
        name="Public Spaces API/MCP for Media Experiments",
        category="public_space_tools",
        use_case="music, SFX, TTS, image/video PoCs, and creative research",
        description=(
            "Continue using public HF Spaces as cheap media R&D surfaces, but classify them as external "
            "sandbox tools with public or synthetic inputs only."
        ),
        integration_points=["audio-studio", "video-studio", "social-studio", "atelier"],
        data_boundary="public_creative_inputs_only",
        business_impact=72,
        cost_leverage=86,
        implementation_readiness=78,
        implementation_effort=2,
        external_calls=True,
        requires_token=False,
        handles_sensitive_data=False,
        sensitive_data_allowed=False,
        risks=[
            "public Spaces can change API signatures, sleep, or disappear",
            "media prompts can accidentally include brand-confidential details",
            "MCP-enabled Spaces are untrusted external tools",
        ],
        controls=[
            "Treat Spaces as sandbox providers, not core production infrastructure.",
            "Keep provider ids configurable in environment/example files.",
            "Never send customer records, claims, or private creative strategy to public Spaces.",
        ],
        references=[
            "https://huggingface.co/docs/hub/spaces-mcp-servers",
        ],
    ),
    HFOpportunity(
        name="smolagents / tiny-agents Sandbox",
        category="agent_framework",
        use_case="small governed agents that can call internal tools during auditions",
        description=(
            "Use HF agent frameworks only inside RAMIN OS sandbox auditions. They are useful for tool "
            "experiments, but the execution boundary matters more than the framework."
        ),
        integration_points=["gateway/agent_radar.py", "gateway/security.py", "tests", "claude-agents"],
        data_boundary="sandbox_only",
        business_impact=74,
        cost_leverage=76,
        implementation_readiness=64,
        implementation_effort=3,
        external_calls=True,
        requires_token=False,
        handles_sensitive_data=False,
        sensitive_data_allowed=False,
        risks=[
            "code-executing agents can perform unintended file/network actions",
            "MCP or Space tools can broaden permissions quickly",
            "framework demos often skip enterprise audit controls",
        ],
        controls=[
            "Agent Radar intake is mandatory before any sandbox trial.",
            "Read-only tools first; no write/send/payment actions.",
            "Run with logs, no secrets, no production credentials, and explicit human review.",
        ],
        references=[
            "https://huggingface.co/docs/hub/agents-mcp",
        ],
    ),
    HFOpportunity(
        name="Brand/Domain LoRA Track",
        category="model_training",
        use_case="future Xalq visual style models, Azerbaijani insurance-domain adapters, controlled fine-tuning",
        description=(
            "Prepare a governed dataset path before any HF-hosted training or LoRA workflow. This can be a "
            "quality leap later, but it needs dataset rights, redaction, and approval first."
        ),
        integration_points=["social-studio", "atelier", "copy-studio", "data governance"],
        data_boundary="approved_curated_dataset_only",
        business_impact=82,
        cost_leverage=58,
        implementation_readiness=46,
        implementation_effort=5,
        external_calls=True,
        requires_token=True,
        handles_sensitive_data=True,
        sensitive_data_allowed=False,
        risks=[
            "training data can leak private brand, customer, or licensed material",
            "dataset rights and model license terms must be reviewed",
            "hosted training may persist artifacts outside RAMIN OS",
        ],
        controls=[
            "Create a curated dataset manifest before any training.",
            "Use only licensed or internally approved assets.",
            "Human approval required before upload, training, or publication.",
        ],
        references=[
            "https://huggingface.co/docs/huggingface_hub/guides/cli",
        ],
    ),
]


def _clamp(value: float) -> int:
    return max(0, min(100, round(value)))


def evaluate_opportunity(opportunity: HFOpportunity) -> HFEvaluation:
    """Score one Hugging Face opportunity for RAMIN OS adoption."""
    reasons: list[str] = []
    controls = [
        "No production use without a RAMIN OS sandbox/audit pass.",
        "No secrets or credentials in reports, prompts, logs, or public Spaces.",
    ]
    controls.extend(opportunity.controls)

    value = _clamp(
        opportunity.business_impact * 0.60
        + opportunity.cost_leverage * 0.25
        + min(len(opportunity.integration_points) * 4, 16)
    )

    readiness = _clamp(opportunity.implementation_readiness - (opportunity.implementation_effort * 4))

    if not opportunity.external_calls and opportunity.sensitive_data_allowed:
        privacy = 96
        reasons.append("Private/self-host path can handle sensitive RAMIN OS data.")
    elif opportunity.external_calls and opportunity.handles_sensitive_data:
        privacy = 22
        reasons.append("External path conflicts with sensitive-data handling.")
    elif opportunity.external_calls:
        privacy = 58
        reasons.append("External service/tooling is acceptable only for public or synthetic data.")
    else:
        privacy = 84
        reasons.append("Local path has a strong data boundary.")

    risk = 12 + opportunity.implementation_effort * 4 + min(len(opportunity.risks) * 4, 20)
    if opportunity.external_calls:
        risk += 18
    if opportunity.requires_token:
        risk += 8
        controls.append("Use fine-grained/read-only tokens unless a human approves a write-capable workflow.")
    if opportunity.handles_sensitive_data and not opportunity.sensitive_data_allowed:
        risk += 30
        controls.append("Sensitive or customer data must stay out of this workflow.")
    if opportunity.category in {"agent_framework", "public_space_tools"}:
        risk += 8
    if not opportunity.external_calls and opportunity.sensitive_data_allowed:
        risk -= 12
    risk = _clamp(risk)

    fit = _clamp(
        value * 0.35
        + readiness * 0.20
        + privacy * 0.30
        + opportunity.cost_leverage * 0.15
        - risk * 0.20
    )

    if opportunity.category in {"private_rag", "private_llm"} and risk < 40:
        decision = "pilot_now_private_path"
    elif opportunity.category == "discovery_tooling" and risk < 55:
        decision = "adopt_read_only_discovery"
    elif opportunity.external_calls and risk < 60:
        decision = "sandbox_public_data_only"
    elif risk >= 70:
        decision = "defer_until_controls_exist"
    else:
        decision = "sandbox_only_after_controls"

    if risk >= 75:
        verdict = "reject"
    elif risk >= 60:
        verdict = "quarantine"
    elif risk >= 40:
        verdict = "sandbox_review"
    else:
        verdict = "approved_for_sandbox"

    if opportunity.business_impact >= 85:
        reasons.append("High strategic fit for RAMIN OS.")
    if opportunity.cost_leverage >= 80:
        reasons.append("Strong zero/low-budget leverage.")
    if opportunity.implementation_effort >= 4:
        reasons.append("Needs an explicit implementation checkpoint before rollout.")
    if opportunity.category == "hosted_inference":
        reasons.append("Useful for comparison, but not reliable as unlimited free production API.")
    if opportunity.category == "model_training":
        reasons.append("Training/fine-tuning requires dataset governance before any upload.")

    return HFEvaluation(
        value_score=value,
        risk_score=risk,
        readiness_score=readiness,
        privacy_score=privacy,
        fit_score=fit,
        verdict=verdict,
        decision=decision,
        reasons=reasons,
        required_controls=list(dict.fromkeys(controls)),
    )


def _local_readiness() -> dict:
    """Check local tooling without reading credentials or touching .env."""
    rag_path = ROOT_DIR / "gateway" / "rag.py"
    triage_path = ROOT_DIR / "cx-command-center" / "triage.py"
    try:
        rag_uses_brain_adapter = "from brain import embeddings" in rag_path.read_text(encoding="utf-8")
    except Exception:
        rag_uses_brain_adapter = False
    try:
        cx_uses_hf_sentiment = "import sentiment_hf" in triage_path.read_text(encoding="utf-8")
    except Exception:
        cx_uses_hf_sentiment = False
    return {
        "hf_cli": bool(shutil.which("hf")),
        "docker": bool(shutil.which("docker")),
        "ollama": bool(shutil.which("ollama")),
        "huggingface_hub_python": find_spec("huggingface_hub") is not None,
        "gradio_client_python": find_spec("gradio_client") is not None,
        "brain_embedding_adapter": (ROOT_DIR / "brain" / "embeddings.py").exists(),
        "gateway_rag_uses_brain_adapter": rag_uses_brain_adapter,
        "cx_hf_sentiment_adapter": (ROOT_DIR / "cx-command-center" / "sentiment_hf.py").exists(),
        "cx_triage_uses_hf_sentiment": cx_uses_hf_sentiment,
        "note": "Credential presence is intentionally not inspected by HF Radar.",
    }


def build_hf_scan(now: float | None = None) -> dict:
    timestamp = time.time() if now is None else now
    records: list[dict] = []
    for opportunity in HF_OPPORTUNITIES:
        evaluation = evaluate_opportunity(opportunity)
        records.append(
            {
                "opportunity": asdict(opportunity),
                "evaluation": asdict(evaluation),
            }
        )

    records.sort(
        key=lambda item: (
            item["evaluation"]["fit_score"],
            -item["evaluation"]["risk_score"],
            item["evaluation"]["value_score"],
        ),
        reverse=True,
    )
    recommendation = records[0]
    avg_fit = round(sum(item["evaluation"]["fit_score"] for item in records) / len(records), 1)
    avg_risk = round(sum(item["evaluation"]["risk_score"] for item in records) / len(records), 1)

    return {
        "id": uuid.uuid4().hex[:12],
        "generated_at": timestamp,
        "generated_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp)),
        "mission": "Govern Hugging Face adoption for RAMIN OS without exposing sensitive data.",
        "desktop_research_source": DESKTOP_RESEARCH_SOURCE,
        "official_references": HF_OFFICIAL_REFERENCES,
        "local_readiness": _local_readiness(),
        "operating_principle": (
            "Hosted HF services are for public/synthetic PoCs; internal documents and customer data use "
            "local or self-hosted models only."
        ),
        "system_fit_summary": {
            "overall_rating": 91,
            "avg_fit_score": avg_fit,
            "avg_risk_score": avg_risk,
            "best_variant": "Private RAG first, HF discovery second, hosted inference last.",
            "why_not_api_first": (
                "Free hosted inference is limited and external. The professional move is to govern model "
                "selection and build private retrieval/serving before routing sensitive work anywhere."
            ),
        },
        "recommendation": {
            "name": recommendation["opportunity"]["name"],
            "decision": recommendation["evaluation"]["decision"],
            "fit_score": recommendation["evaluation"]["fit_score"],
            "risk_score": recommendation["evaluation"]["risk_score"],
            "verdict": recommendation["evaluation"]["verdict"],
        },
        "ranked_opportunities": records,
        "next_actions": [
            "Pilot TEI/local embeddings for Brain and internal document retrieval.",
            "Install/use HF MCP and hf CLI only as read-only discovery surfaces.",
            "Keep HF Router tests limited to public marketing prompts and synthetic examples.",
            "Run every public Space, MCP server, or agent framework through Agent Radar before use.",
            "Create a dataset governance checklist before any LoRA, upload, or fine-tuning workflow.",
        ],
    }


def load_latest_scan() -> dict | None:
    if not HF_SCAN_PATH.exists():
        return None
    with HF_SCAN_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def scan_is_stale(scan: dict | None, max_age_hours: int = 24) -> bool:
    if not scan:
        return True
    generated_at = float(scan.get("generated_at") or 0)
    return (time.time() - generated_at) > (max_age_hours * 3600)


def render_hf_scan_report(scan: dict) -> str:
    lines = [
        "# Hugging Face Opportunity Radar",
        "",
        f"Generated: {scan['generated_at_iso']}",
        f"Desktop research source: `{scan['desktop_research_source']}`",
        "",
        "## Executive Verdict",
        "",
        f"- Best variant: {scan['system_fit_summary']['best_variant']}",
        f"- Overall rating: {scan['system_fit_summary']['overall_rating']}/100",
        f"- Average fit: {scan['system_fit_summary']['avg_fit_score']}/100",
        f"- Average risk: {scan['system_fit_summary']['avg_risk_score']}/100",
        f"- Recommendation: {scan['recommendation']['name']}",
        f"- Decision: {scan['recommendation']['decision']}",
        f"- Operating principle: {scan['operating_principle']}",
        "",
        "## Local Readiness",
        "",
    ]
    for key, value in scan["local_readiness"].items():
        lines.append(f"- {key}: {value}")

    lines.extend(["", "## Ranked Opportunities", ""])
    for item in scan["ranked_opportunities"]:
        opportunity = item["opportunity"]
        evaluation = item["evaluation"]
        lines.extend(
            [
                f"### {opportunity['name']}",
                f"- Category: {opportunity['category']}",
                f"- Fit: {evaluation['fit_score']}/100",
                f"- Value: {evaluation['value_score']}/100",
                f"- Readiness: {evaluation['readiness_score']}/100",
                f"- Privacy: {evaluation['privacy_score']}/100",
                f"- Risk: {evaluation['risk_score']}/100",
                f"- Verdict: {evaluation['verdict']}",
                f"- Decision: {evaluation['decision']}",
                f"- Data boundary: {opportunity['data_boundary']}",
                f"- Integrations: {', '.join(opportunity['integration_points'])}",
                "",
                "Required controls:",
            ]
        )
        for control in evaluation["required_controls"]:
            lines.append(f"- {control}")
        lines.extend(["", "Reasons:"])
        for reason in evaluation["reasons"]:
            lines.append(f"- {reason}")
        lines.append("")

    lines.extend(["## Official References", ""])
    for ref in scan["official_references"]:
        lines.append(f"- [{ref['name']}]({ref['url']}) - {ref['why_it_matters']}")

    lines.extend(["", "## Next Actions", ""])
    for action in scan["next_actions"]:
        lines.append(f"- {action}")
    return "\n".join(lines).strip() + "\n"


def run_hf_scan() -> dict:
    scan = build_hf_scan()
    HF_RADAR_DIR.mkdir(parents=True, exist_ok=True)
    HF_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with HF_SCAN_PATH.open("w", encoding="utf-8") as fh:
        json.dump(scan, fh, indent=2, ensure_ascii=True)
    HF_REPORT_PATH.write_text(render_hf_scan_report(scan), encoding="utf-8")
    security.audit_event(
        "hf_radar_scan",
        security.allow("hf_radar", "Hugging Face opportunity scan completed; no execution granted."),
        {
            "recommendation": scan["recommendation"]["name"],
            "decision": scan["recommendation"]["decision"],
            "report": str(HF_REPORT_PATH),
        },
    )
    return scan


def main() -> None:
    parser = argparse.ArgumentParser(description="RAMIN OS Hugging Face opportunity radar.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("scan", help="Run the HF opportunity scan and write JSON/Markdown artifacts.")
    sub.add_parser("report", help="Print the latest HF opportunity report; refresh if stale.")
    sub.add_parser("doctor", help="Print local HF tooling readiness without reading credentials.")
    args = parser.parse_args()

    if args.command == "scan":
        scan = run_hf_scan()
        print(
            f"{scan['id']} | {scan['recommendation']['name']} | "
            f"fit={scan['recommendation']['fit_score']} risk={scan['recommendation']['risk_score']} | "
            f"report={HF_REPORT_PATH}"
        )
    elif args.command == "report":
        scan = load_latest_scan()
        if scan_is_stale(scan):
            scan = run_hf_scan()
        print(render_hf_scan_report(scan))
    elif args.command == "doctor":
        print(json.dumps(_local_readiness(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

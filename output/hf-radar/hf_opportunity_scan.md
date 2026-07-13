# Hugging Face Opportunity Radar

Generated: 2026-07-13T12:31:36Z
Desktop research source: `C:\Users\a.alirzayev\Desktop\hugginface free oportunities.docx`

## Executive Verdict

- Best variant: Private RAG first, HF discovery second, hosted inference last.
- Overall rating: 91/100
- Average fit: 62.8/100
- Average risk: 50.0/100
- Recommendation: Private RAG Embedding Layer (TEI + HF embedding models)
- Decision: pilot_now_private_path
- Operating principle: Hosted HF services are for public/synthetic PoCs; internal documents and customer data use local or self-hosted models only.

## Local Readiness

- hf_cli: True
- docker: False
- ollama: False
- huggingface_hub_python: True
- gradio_client_python: True
- brain_embedding_adapter: True
- gateway_rag_uses_brain_adapter: True
- cx_hf_sentiment_adapter: True
- cx_triage_uses_hf_sentiment: True
- note: Credential presence is intentionally not inspected by HF Radar.

## Ranked Opportunities

### Private RAG Embedding Layer (TEI + HF embedding models)
- Category: private_rag
- Fit: 84/100
- Value: 94/100
- Readiness: 68/100
- Privacy: 96/100
- Risk: 24/100
- Verdict: approved_for_sandbox
- Decision: pilot_now_private_path
- Data boundary: private_or_internal_only
- Integrations: brain, gateway/rag.py, gateway/knowledge.py, cx-command-center, docs

Required controls:
- No production use without a RAMIN OS sandbox/audit pass.
- No secrets or credentials in reports, prompts, logs, or public Spaces.
- Use open-license embedding models only.
- Keep the embedding server on localhost or a private host.
- Do not upload customer data to public Spaces or hosted providers.
- Run retrieval quality tests before replacing current Brain search.

Reasons:
- Private/self-host path can handle sensitive RAMIN OS data.
- High strategic fit for RAMIN OS.
- Strong zero/low-budget leverage.

### Private CX Sentiment Classifier
- Category: private_sentiment
- Fit: 82/100
- Value: 83/100
- Readiness: 74/100
- Privacy: 96/100
- Risk: 16/100
- Verdict: approved_for_sandbox
- Decision: sandbox_only_after_controls
- Data boundary: private_or_internal_only
- Integrations: cx-command-center/triage.py, cx-command-center/sentiment_hf.py, SECURITY.md

Required controls:
- No production use without a RAMIN OS sandbox/audit pass.
- No secrets or credentials in reports, prompts, logs, or public Spaces.
- Keep deterministic CX rules as the baseline.
- Allow HF sentiment to raise risk, not lower rule-based complaint risk.
- Use local/private endpoints for customer messages.
- Benchmark labels against Azerbaijani complaint examples before operational use.

Reasons:
- Private/self-host path can handle sensitive RAMIN OS data.
- Strong zero/low-budget leverage.

### Local Open-Weight LLM Serving (llama.cpp/vLLM/SGLang)
- Category: private_llm
- Fit: 78/100
- Value: 91/100
- Readiness: 52/100
- Privacy: 96/100
- Risk: 28/100
- Verdict: approved_for_sandbox
- Decision: pilot_now_private_path
- Data boundary: private_or_internal_only
- Integrations: llm_router.py, gateway/llm.py, orchestrator/router.py, brain

Required controls:
- No production use without a RAMIN OS sandbox/audit pass.
- No secrets or credentials in reports, prompts, logs, or public Spaces.
- Keep private tier routed to local endpoints only.
- Benchmark against current Gemini/Groq outputs before promotion.
- Record model id, quantization, license, and hardware requirements.

Reasons:
- Private/self-host path can handle sensitive RAMIN OS data.
- High strategic fit for RAMIN OS.
- Strong zero/low-budget leverage.
- Needs an explicit implementation checkpoint before rollout.

### HF MCP + hf CLI Discovery Workbench
- Category: discovery_tooling
- Fit: 64/100
- Value: 83/100
- Readiness: 78/100
- Privacy: 58/100
- Risk: 54/100
- Verdict: sandbox_review
- Decision: adopt_read_only_discovery
- Data boundary: public_metadata_only
- Integrations: claude-agents, gateway/agent_radar.py, docs, scripts

Required controls:
- No production use without a RAMIN OS sandbox/audit pass.
- No secrets or credentials in reports, prompts, logs, or public Spaces.
- Use read-only/fine-grained Hugging Face tokens for discovery.
- Run candidate models, Spaces, and agents through Agent Radar before use.
- Do not connect MCP tools to customer-data workflows.
- Use fine-grained/read-only tokens unless a human approves a write-capable workflow.

Reasons:
- External service/tooling is acceptable only for public or synthetic data.
- Strong zero/low-budget leverage.

### Public Spaces API/MCP for Media Experiments
- Category: public_space_tools
- Fit: 61/100
- Value: 81/100
- Readiness: 70/100
- Privacy: 58/100
- Risk: 58/100
- Verdict: sandbox_review
- Decision: sandbox_public_data_only
- Data boundary: public_creative_inputs_only
- Integrations: audio-studio, video-studio, social-studio, atelier

Required controls:
- No production use without a RAMIN OS sandbox/audit pass.
- No secrets or credentials in reports, prompts, logs, or public Spaces.
- Treat Spaces as sandbox providers, not core production infrastructure.
- Keep provider ids configurable in environment/example files.
- Never send customer records, claims, or private creative strategy to public Spaces.

Reasons:
- External service/tooling is acceptable only for public or synthetic data.
- Strong zero/low-budget leverage.

### smolagents / tiny-agents Sandbox
- Category: agent_framework
- Fit: 54/100
- Value: 79/100
- Readiness: 52/100
- Privacy: 58/100
- Risk: 62/100
- Verdict: quarantine
- Decision: sandbox_only_after_controls
- Data boundary: sandbox_only
- Integrations: gateway/agent_radar.py, gateway/security.py, tests, claude-agents

Required controls:
- No production use without a RAMIN OS sandbox/audit pass.
- No secrets or credentials in reports, prompts, logs, or public Spaces.
- Agent Radar intake is mandatory before any sandbox trial.
- Read-only tools first; no write/send/payment actions.
- Run with logs, no secrets, no production credentials, and explicit human review.

Reasons:
- External service/tooling is acceptable only for public or synthetic data.

### HF Router PoC for Public Prompts
- Category: hosted_inference
- Fit: 51/100
- Value: 69/100
- Readiness: 66/100
- Privacy: 58/100
- Risk: 58/100
- Verdict: sandbox_review
- Decision: sandbox_public_data_only
- Data boundary: public_or_synthetic_prompts_only
- Integrations: llm_router.py, atelier, copy-studio, ads-studio

Required controls:
- No production use without a RAMIN OS sandbox/audit pass.
- No secrets or credentials in reports, prompts, logs, or public Spaces.
- Block customer data, policy documents, and claims data from this route.
- Log provider/model usage through the existing LLM usage board.
- Keep a local/private fallback for sensitive tasks.
- Use fine-grained/read-only tokens unless a human approves a write-capable workflow.

Reasons:
- External service/tooling is acceptable only for public or synthetic data.
- Useful for comparison, but not reliable as unlimited free production API.

### Brand/Domain LoRA Track
- Category: model_training
- Fit: 28/100
- Value: 80/100
- Readiness: 26/100
- Privacy: 22/100
- Risk: 100/100
- Verdict: reject
- Decision: defer_until_controls_exist
- Data boundary: approved_curated_dataset_only
- Integrations: social-studio, atelier, copy-studio, data governance

Required controls:
- No production use without a RAMIN OS sandbox/audit pass.
- No secrets or credentials in reports, prompts, logs, or public Spaces.
- Create a curated dataset manifest before any training.
- Use only licensed or internally approved assets.
- Human approval required before upload, training, or publication.
- Use fine-grained/read-only tokens unless a human approves a write-capable workflow.
- Sensitive or customer data must stay out of this workflow.

Reasons:
- External path conflicts with sensitive-data handling.
- Needs an explicit implementation checkpoint before rollout.
- Training/fine-tuning requires dataset governance before any upload.

## Official References

- [Inference Providers](https://huggingface.co/docs/inference-providers/index) - Hosted Inference Providers and OpenAI-compatible APIs are useful for public-data PoCs, not a free production backbone.
- [Hub API for OpenAI-compatible models](https://huggingface.co/docs/inference-providers/hub-api) - The router can list chat models and provider metadata for governed comparison.
- [Hugging Face MCP Server](https://huggingface.co/docs/hub/agents-mcp) - Hub model, dataset, Space, documentation, and paper search can become a read-only discovery tool.
- [Spaces as MCP servers](https://huggingface.co/docs/hub/spaces-mcp-servers) - Public Spaces can expose tools, but they must be treated as untrusted external execution.
- [hf CLI and skills](https://huggingface.co/docs/huggingface_hub/guides/cli) - The hf CLI is the standard local control surface for Hub repos, downloads, and agent skills.
- [Text Embeddings Inference](https://huggingface.co/docs/text-embeddings-inference/quick_tour) - TEI is the strongest private RAG/embedding path for internal documents and customer-adjacent retrieval.

## Next Actions

- Pilot TEI/local embeddings for Brain and internal document retrieval.
- Install/use HF MCP and hf CLI only as read-only discovery surfaces.
- Keep HF Router tests limited to public marketing prompts and synthetic examples.
- Run every public Space, MCP server, or agent framework through Agent Radar before use.
- Create a dataset governance checklist before any LoRA, upload, or fine-tuning workflow.

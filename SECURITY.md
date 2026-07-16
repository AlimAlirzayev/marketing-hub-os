# Security Prime Directive

Security is the highest law in this workspace.

The autonomous gateway must prefer a blocked action over an unsafe action. A
blocked action is a successful safety outcome, not a failure.

## What The Guard Blocks

- Secret exposure: requests to show, print, copy, upload, or send API keys,
  tokens, passwords, cookies, `.env` values, or credentials.
- Destructive changes: broad deletion, wiping, formatting, table drops, or
  irreversible data changes.
- Payments and commitments: buying, paying, checkout, booking, subscribing, or
  sending money.
- Private infrastructure browsing: localhost, private IPs, link-local metadata
  IPs, `.local`, `.lan`, `.internal`, and URLs containing credentials.
- Unknown automation scripts: studio subprocesses can only run explicitly
  allowlisted scripts.

## Where It Lives

- Policy engine: `gateway/security.py`
- Job pre-flight: `gateway/executor.py`
- Browser URL guard: `gateway/tools/browser.py`
- External agent intake: `gateway/agent_radar.py`
- Hugging Face model/tool intake: `gateway/hf_radar.py`
- Agent permission manifest: `config/agent_permissions.json`
- Permission validator: `gateway/permissions.py`
- Security audit log: `data/logs/security_audit.jsonl`
- Tests: `tests/test_security.py`, `tests/test_agent_radar.py`

## External Agent Intake

Outside agents, marketplaces, plugins, and automation tools must pass Agent
Radar before any sandbox trial. Agent Radar scores value, evidence,
permissions, risky claims, and URL safety. Its strongest positive verdict is
`approved_for_sandbox`; it never approves production use, secrets, admin access,
payments, or private network access.

Agent Radar also runs an automatic Marketing OS scan. This compares governance
and workflow-agent patterns against our own modules, ranks the safest next
agent work, and writes a report to `output/agent-radar/marketing_os_scan.md`.
The scan is analysis-only; it does not run outside agents or grant access.

Allowed next step after a good score: a narrow audition task with read-only
access, no production credentials, logging enabled, and human review before any
write/send/payment action.

## Public Signal Radar

Public Signal Radar (`gateway/signal_radar.py`) is approved only as a read-only
public-source intake loop. It may fetch public http(s) sources, extract claims,
attach official-source candidates, write local lab notes, update prototype
backlog items, and produce reports. It must not read `.env`, secrets, customer
data, claims, policies, private strategy, OAuth caches, or private documents.

It must block localhost, private IPs, link-local addresses, `.local`, `.lan`,
`.internal`, and URLs containing credentials. It must not enable providers,
install agents, spend credits, post publicly, send messages, schedule posts,
log in, control browser/desktop/camera/microphone/hardware, or change production
data. Any useful signal that implies those actions becomes a prototype or
approval-gated task first.

## Hugging Face Model And Tool Intake

Hugging Face is treated as an external model/tool ecosystem, not as a trusted
private backend by default. `gateway/hf_radar.py` ranks HF Router, MCP, Spaces,
agent frameworks, local open-weight serving, and TEI/RAG options before any
pilot is attempted.

Public HF Router calls, public Spaces, and external MCP tools are only for
public or synthetic prompts. Customer data, claims, policies, internal
documents, and private strategy must stay on local/self-hosted paths such as
TEI, llama.cpp, vLLM, SGLang, Ollama, or other approved private endpoints.

Brain semantic recall and `gateway.rag` use `brain.embeddings` as the shared
embedding adapter. Local/private TEI or OpenAI-compatible endpoints are allowed;
external embedding endpoints are ignored unless `BRAIN_EMBED_ALLOW_EXTERNAL=1`
is explicitly set. Do not enable external embeddings for customer data, claims,
internal documents, or private strategy.

CX sentiment reinforcement uses `cx-command-center/sentiment_hf.py`. It is off
by default, should point only to a local/private Hugging Face text-classification
endpoint, and may raise complaint risk but must not downgrade deterministic
rule-based CX risk. Do not send customer messages to public hosted sentiment
endpoints.

Every HF Space, MCP server, or agent framework must pass Agent Radar before a
sandbox trial. Tokens must be fine-grained/read-only unless a human explicitly
approves a write-capable workflow.

## Context7 Documentation Grounding

Context7 is allowed only as a read-only documentation grounding layer for
third-party library and API work. It must not receive secrets, customer data,
claims, internal policies, private strategy, or production credentials. Context7
guidance does not override local source inspection, tests, Agent Radar, or this
security policy.

## FLORA Creative MCP

FLORA is allowed only as a sandbox/draft creative MCP for marketing media work.
It may use approved campaign briefs, public or licensed references, approved
brand assets, synthetic prompts, and redacted localization sheets. It must not
receive secrets, customer data, claims, payment data, internal policies,
unredacted private strategy, or unlicensed assets.

FLORA MCP uses OAuth for interactive agent work. Treat the MCP client token
cache like an SSH key. API keys are for explicitly approved server-side
automation only and must stay in local secrets, never tracked MCP settings.

FLORA generations can consume workspace credits. Before any multi-run or
high-cost batch, the agent must inspect and show the expected `run_cost x count`
and wait for human approval. FLORA outputs remain drafts until Video Studio QA
and Publisher dry-run pass; posting or scheduling still requires a human
checkpoint.

## Agent Permission Manifests

Every internal agent, MCP tool category, or workflow that gains meaningful
capability must have an entry in `config/agent_permissions.json`. The manifest
must state allowed inputs, blocked inputs, allowed outputs, blocked actions, and
required controls. Unknown agents fail closed.

## CX Resolution Agent Sandbox

The CX Resolution Agent is approved only as a draft-only sandbox workflow. It
may read already-triaged complaint data, redact evidence previews, group root
causes, and prepare reply drafts. It must not send replies, change statuses,
post publicly, access payment data, or mark complaints resolved without human
approval.

## Run The Safety Tests

```powershell
python -m unittest discover -s tests
```

## Operating Rule

If a useful feature requires a risky action, build a checkpoint first. The
checkpoint must show the exact action, the target, and the risk in plain
language before a human approves it.

## Secret Rotation And Twin Delivery

Shared API keys must be entered only through the machine-local hidden prompt:
`SECURE_KEY.bat KEY_NAME` on Windows or `python3 scripts/secure_key.py KEY_NAME`
on macOS/Linux. The value must never be pasted into an AI chat, Telegram, shell
argument, URL, log, or tracked file. Success requires encrypted-vault commit,
push, and upstream verification. Receiving twins re-apply the vault on every
sync and record only key names plus a vault digest in a private receipt.

Telegram `/setkey` is disabled by default and is not the normal secret path.
Enabling `ALLOW_TELEGRAM_SETKEY=1` is break-glass only because deletion from
chat history is best-effort and cannot prove removal from every provider log.

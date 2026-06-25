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

## Hugging Face Model And Tool Intake

Hugging Face is treated as an external model/tool ecosystem, not as a trusted
private backend by default. `gateway/hf_radar.py` ranks HF Router, MCP, Spaces,
agent frameworks, local open-weight serving, and TEI/RAG options before any
pilot is attempted.

Public HF Router calls, public Spaces, and external MCP tools are only for
public or synthetic prompts. Customer data, claims, policies, internal
documents, and private strategy must stay on local/self-hosted paths such as
TEI, llama.cpp, vLLM, SGLang, Ollama, or other approved private endpoints.

Every HF Space, MCP server, or agent framework must pass Agent Radar before a
sandbox trial. Tokens must be fine-grained/read-only unless a human explicitly
approves a write-capable workflow.

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

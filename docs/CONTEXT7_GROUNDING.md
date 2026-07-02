# Context7 Grounding Layer

Context7 is approved for Ramin-OS as a read-only documentation grounding layer.
It is not an execution engine, publisher, customer-data processor, or production
decision maker.

## What It Adds

- Fresher library and API documentation for Codex, Claude Code, and MCP-capable
  agents.
- Less hallucinated code when touching FastAPI, Streamlit, Playwright, Pydantic,
  Meta/GA4 SDKs, MCP clients, and similar changing libraries.
- A shared docs habit across agents: use current docs before writing code that
  depends on external APIs.

## Operating Rule

Use Context7 when a task involves:

- A third-party library or framework API.
- Setup/configuration steps for a tool, SDK, MCP server, or platform.
- Version-specific behavior that may have changed.
- Debugging code that depends on external package documentation.

Do not use Context7 for:

- `.env`, credentials, tokens, private customer data, claims, policies, or
  internal strategy.
- Sending, posting, payment, deletion, or production write decisions.
- Replacing Ramin-OS source-of-truth docs (`AGENTS.md`, `SECURITY.md`,
  `services.json`, `docs/RAMIN_OS_CONTEXT.md`).

## Priority Libraries

1. FastAPI
2. Streamlit
3. Playwright
4. Pydantic
5. MCP / Model Context Protocol clients and servers
6. Meta Graph / Marketing API
7. Google Analytics Data API / GA4
8. SQLite / Python standard library details
9. Qdrant
10. Hugging Face local/private serving docs

## Security Boundary

- Context7 is read-only docs access.
- API keys are optional and must not be written into tracked files.
- Context7 output is guidance, not authority; critical changes still require
  source inspection, tests, and Ramin-OS security rules.
- Community-contributed docs can be incomplete or stale, so high-risk changes
  need official-source verification.

## Claude/Codex Prompt Rule

When changing code that depends on external libraries, add this intent to the
task:

```text
Use Context7 for current library/API docs before implementing.
```

If Context7 is unavailable, continue with local docs and official sources, then
state the limitation in the final answer.


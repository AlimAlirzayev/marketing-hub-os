# Ramin-OS Notion Agent Tools

This is the Ramin-OS Notion Workers project. It is a Notion-hosted TypeScript
worker for Notion Custom Agents, not a local service and not an MCP server.

The first version exposes two read-only/draft-only tools:

- `screenRaminOsAction` checks whether a proposed action is safe as a draft,
  needs the Ramin-OS approval rail, or is blocked until redacted.
- `prepareRaminOsHandoff` turns a redacted Notion brief into a structured
  handoff for the right Ramin-OS module.

## Security Boundary

- Do not paste secrets, `.env` content, cookies, tokens, customer records,
  claims, policies, payment data, or private strategy into Notion AI or this
  worker.
- These tools do not send, post, publish, spend, delete, deploy, or write
  production data.
- Use `--no-dotenv` for local smoke tests unless you are deliberately testing a
  secret-backed capability after human approval.
- Login, deploy, `ntn workers env set`, real sync triggers, and webhook URL
  handling are credentialed/production-adjacent actions and require a human
  checkpoint.

## Local Commands

Run from the repo root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-notion-workers.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\notion-cli.ps1 --version
```

Run from this folder after setup:

```powershell
npm run check
ntn workers exec screenRaminOsAction --local --no-dotenv -d '{"action":"draft campaign ideas","target":null,"publicFacing":false,"sendsMessage":false,"changesProduction":false,"deletesOrArchives":false,"spendsMoney":false,"containsSecrets":false,"containsCustomerData":false,"containsClaimsOrPolicies":false}'
ntn workers exec prepareRaminOsHandoff --local --no-dotenv -d '{"workType":"campaign","brief":"Draft a safe KASKO campaign handoff.","desiredOutput":"Campaign package","sourceLocation":"Notion brief","deadline":null,"hasSensitiveInputs":false,"needsExternalAction":false,"needsPublishing":false}'
```

On this Windows machine, `ntn 0.18.1` currently fails local worker execution
with `ERR_UNSUPPORTED_ESM_URL_SCHEME` because the beta CLI passes a `C:` path to
the ESM loader. `npm run check` still type-checks the worker locally; use local
`workers exec` again after a CLI update or from a compatible shell/WSL.

## Deployment Checkpoint

Only after review:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\notion-cli.ps1 login
cd notion-workers\ramin-os-agent-tools
ntn workers deploy --name ramin-os-agent-tools
```

After deploy, add the tools to a Notion Custom Agent from the agent tool
configuration. Do not enable write-like behavior or broad permissions without
updating `config/agent_permissions.json` and the Ramin-OS docs first.

## Official Docs

- Notion Workers overview: https://developers.notion.com/workers/get-started/overview
- Quickstart: https://developers.notion.com/workers/get-started/quickstart
- Agent tools: https://developers.notion.com/workers/guides/tools
- Secrets: https://developers.notion.com/workers/guides/secrets
- CLI commands: https://developers.notion.com/cli/reference/commands

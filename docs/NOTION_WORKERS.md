# Notion Workers For Ramin-OS

Notion Workers is a beta platform for small TypeScript programs hosted by
Notion. A worker can expose three capability types:

- **Tools** for Notion Custom Agents
- **Syncs** to pull external data into Notion managed databases
- **Webhooks** to receive HTTP events from external services

Ramin-OS uses the first capability first: safe Custom Agent tools that screen
risk and prepare handoffs. We are intentionally not using syncs or webhooks yet.

## What We Installed

- Repo-local Notion CLI in `.tools/notion-cli` (`ntn 0.18.1` on this machine).
- Wrapper: `scripts/notion-cli.ps1`
- Setup script: `scripts/setup-notion-workers.ps1`
- Worker project: `notion-workers/ramin-os-agent-tools`
- Readiness checker: `python -m gateway.notion_workers doctor`
- Permission manifest entry: `config/agent_permissions.json` -> `notion_workers`

The worker exposes:

- `screenRaminOsAction`: classifies a proposed action as `safe_draft`,
  `approval_required`, or `blocked`.
- `prepareRaminOsHandoff`: turns a redacted Notion brief into a Ramin-OS module
  handoff package.

Both tools are side-effect-free and use `hints: { readOnlyHint: true }`.

## Most Useful Ramin-OS Uses

1. **Notion as planning intake, Ramin-OS as execution spine**
   Notion agents can shape briefs, but execution still enters the gateway,
   module owners, approval rail, and Brain workflow.

2. **Risk screening before work leaves Notion**
   A Notion agent can ask `screenRaminOsAction` before suggesting publish,
   send, spend, delete, deploy, or production-write steps.

3. **Structured handoffs**
   Campaign notes can become Publisher/Atelier handoffs; analytics questions
   can route to Ads/GA4; CX notes can route to CX Command Center with redaction
   reminders.

4. **Future syncs, carefully**
   Notion Workers syncs could later mirror approved, non-sensitive Ramin-OS
   reports into Notion. Any sync must preview before real writes, use pacers,
   and avoid customer data or private strategy.

5. **Future webhooks, only with signatures**
   Webhooks can receive external events, but the URL acts like a secret and
   provider signatures must be verified before processing.

## Security Rules

- Never send secrets, `.env` content, API keys, tokens, cookies, customer data,
  claims, policies, payment data, or private strategy to Notion Workers.
- Local tests use `--no-dotenv` by default.
- `ntn login`, `ntn workers deploy`, `ntn workers env set/push/pull`, OAuth
  start, real sync triggers, and webhook URL listing require a human checkpoint.
- Do not add tools that send, post, publish, spend, delete, deploy, or write
  production data without a new manifest update and approval gate.
- Do not register this in `services.json`; it has no local port and is not a
  Ramin-OS service card.

## Commands

Setup or repair local tooling:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-notion-workers.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\notion-cli.ps1 --version
```

Validate governance:

```powershell
python -m gateway.notion_workers doctor
python -m gateway.notion_workers report
python -m gateway.permissions doctor
```

Type-check:

```powershell
cd notion-workers\ramin-os-agent-tools
npm run check
```

Smoke-test locally without loading `.env`:

```powershell
ntn workers exec screenRaminOsAction --local --no-dotenv -d '{"action":"draft campaign ideas","target":null,"publicFacing":false,"sendsMessage":false,"changesProduction":false,"deletesOrArchives":false,"spendsMoney":false,"containsSecrets":false,"containsCustomerData":false,"containsClaimsOrPolicies":false}'
ntn workers exec prepareRaminOsHandoff --local --no-dotenv -d '{"workType":"campaign","brief":"Draft a safe KASKO campaign handoff.","desiredOutput":"Campaign package","sourceLocation":"Notion brief","deadline":null,"hasSensitiveInputs":false,"needsExternalAction":false,"needsPublishing":false}'
```

Windows note: on this machine, `ntn 0.18.1` reaches the worker runtime but local
`workers exec --local` fails with `ERR_UNSUPPORTED_ESM_URL_SCHEME` because the
beta CLI passes a `C:` path to the Node ESM loader. Keep using `npm run check`
and `python -m gateway.notion_workers doctor`; retry local exec after a Notion
CLI update or from a compatible shell/WSL.

Checkpoint-only activation:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\notion-cli.ps1 login
cd notion-workers\ramin-os-agent-tools
ntn workers deploy --name ramin-os-agent-tools
```

## Official References

- Notion Workers overview: https://developers.notion.com/workers/get-started/overview
- Quickstart: https://developers.notion.com/workers/get-started/quickstart
- Agent tools: https://developers.notion.com/workers/guides/tools
- Secrets: https://developers.notion.com/workers/guides/secrets
- Webhooks: https://developers.notion.com/workers/guides/webhooks
- CLI command reference: https://developers.notion.com/cli/reference/commands

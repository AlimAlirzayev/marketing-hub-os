# Notion Workers Readiness

Generated: 2026-07-07T11:26:40Z

## Verdict

- Status: configured_cli_installed
- Verdict: ready_for_typecheck_and_human_checkpoint
- Decision: activate_after_human_login_deploy_checkpoint
- Overall rating: 86/100
- Best fit: Notion-side briefing, risk screening, and handoff preparation before work enters the Ramin-OS gateway.
- Main risk: Notion-hosted tools can drift into secrets, customer data, publishing, or production writes if not gated.

## Local Checks

- Worker project exists: True
- Package: @ramin-os/notion-agent-tools
- Workers SDK dependency: True
- Source has expected tools: True
- Tools are read-only hinted: True
- Setup script exists: True
- CLI wrapper exists: True
- Repo-local CLI installed: True
- Repo-local CLI available: True
- Portable Node available: True
- Local exec smoke tested by doctor: False
- Local exec note: Doctor does not execute worker tools. On Windows, ntn 0.18.1 local exec can fail with ERR_UNSUPPORTED_ESM_URL_SCHEME.
- Permission manifest has Notion Workers: True
- Manifest status: sandbox_draft_only
- Blocks secrets: True
- Blocks customer data: True
- Blocks public posting: True
- Blocks deploy without approval: True
- Credentials checked: False
- Notion login checked: False
- Note: Credentials, .env files, OAuth token stores, and Notion login state are intentionally not inspected.

## Tools

- `screenRaminOsAction`: True
- `prepareRaminOsHandoff`: True

## Activation

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-notion-workers.ps1
python -m gateway.notion_workers doctor
cd notion-workers\ramin-os-agent-tools
npm run check
```

Human checkpoint before:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\notion-cli.ps1 login
ntn workers deploy --name ramin-os-agent-tools
```

## Safety Controls

- Do not send secrets, .env content, customer data, claims, policies, payment data, or private strategy.
- Keep tools side-effect-free unless a new manifest entry and approval checkpoint authorizes more.
- Use --no-dotenv for local smoke tests by default.
- Treat worker deployment, secrets, OAuth, real sync triggers, and webhook URLs as checkpoint actions.
- Syncs must preview before writing and webhooks must verify provider signatures.

## Official References

- [Notion Workers overview](https://developers.notion.com/workers/get-started/overview) - Explains Workers as Notion-hosted tools, syncs, and webhooks.
- [Quickstart](https://developers.notion.com/workers/get-started/quickstart) - Official CLI, scaffold, local test, deploy, and Custom Agent setup flow.
- [Agent tools](https://developers.notion.com/workers/guides/tools) - Tool schema, execute handlers, output schemas, and read-only hints.
- [Secrets](https://developers.notion.com/workers/guides/secrets) - Worker secret storage and env commands that require human checkpoints.
- [CLI commands](https://developers.notion.com/cli/reference/commands) - Reference for deploy, exec, sync, env, OAuth, and webhook commands.

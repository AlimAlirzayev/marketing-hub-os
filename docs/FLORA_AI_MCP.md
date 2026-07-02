# FLORA AI MCP Integration

FLORA is the approved draft-media bridge for Ramin-OS creative work. It connects
our campaign planning, prompt dialects, Video Studio, and Publisher dry-run
flows to the FLORA creative canvas without storing FLORA credentials in this
repository.

## Current Status

- Local Ramin-OS prompt and video workflows already reference FLORA.
- `scripts/setup-mcp.ps1` registers the official FLORA MCP endpoint through
  `mcp-remote`.
- If global `node`/`npx` is not on PATH, the setup script uses the portable Node
  runtime under `video-studio/tools`.
- `config/agent_permissions.json` contains a fail-closed FLORA permission
  manifest.
- First real use still requires a human OAuth sign-in from the MCP client.

## Official Endpoint

```json
{
  "mcpServers": {
    "flora": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://agents.flora.ai/mcp"]
    }
  }
}
```

FLORA's direct remote HTTP endpoint is:

```text
https://agents.flora.ai/mcp
```

For Claude Code, FLORA also documents the direct command:

```powershell
claude mcp add --transport http flora https://agents.flora.ai/mcp
```

Ramin-OS uses `mcp-remote` in the project settings because the current local
MCP registry is command/args based.

## What It Adds To Ramin-OS

- Discover available FLORA Techniques for a campaign.
- Run thumbnail, image, video, and motion Techniques from an agent.
- Upload approved local assets through FLORA's signed asset flow when the MCP
  client has shell/filesystem access.
- Batch localized creative variants from a CSV or approved sheet.
- Inspect model lists, Technique schemas, run history, and run cost before work.
- Keep generated visuals on a FLORA project canvas for creative review.

## Safety Rules

- Use only approved marketing briefs, public/licensed references, approved brand
  assets, synthetic prompts, and redacted localization sheets.
- Never send secrets, API keys, customer data, claims, payment data, internal
  policies, unredacted private strategy, or unlicensed third-party assets.
- Before a batch, check `run_cost x count` and ask for approval.
- Keep exact logos, legal copy, dates, prices, CTA text, and Azerbaijani text in
  deterministic local overlays. Do not rely on generated pixels for compliance.
- Do not publish from FLORA. Final assets must pass Video Studio QA and Publisher
  dry-run before any posting or scheduling checkpoint.

## Activation Smoke Test

```powershell
.\scripts\setup-mcp.ps1
python -m gateway.flora_ai doctor
```

Then open Claude Code or the MCP client from this repo and ask:

```text
List my FLORA Techniques.
```

The first tool call should open FLORA OAuth. Sign in with the annual
subscription account and choose the right workspace. After OAuth, ask for a
small, low-cost test such as listing Techniques or inspecting one Technique's
inputs before generating media.

## Best First Ramin-OS Workflow

1. Use Atelier/Copy Studio to make a campaign brief and hook options.
2. Compile a FLORA-ready prompt with `scripts/compile_generative_ad.py`.
3. Ask FLORA MCP to inspect available Techniques and cost.
4. Generate one draft still or short motion plate.
5. Review it locally; only then generate a small batch.
6. Finish exact text, logo, legal terms, CTA, captions, and formats in Video
   Studio.
7. Send the final package through Publisher dry-run for approval.

## Official References

- FLORA MCP: https://developer.flora.ai/mcp/
- Claude Code install: https://developer.flora.ai/mcp/install/claude-code/
- Authentication: https://developer.flora.ai/mcp/authentication/
- Tools reference: https://developer.flora.ai/mcp/tools/
- Batch recipe: https://developer.flora.ai/mcp/recipes/batch-with-coding-agent/

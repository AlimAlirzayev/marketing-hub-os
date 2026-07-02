# FLORA AI MCP Readiness

Generated: 2026-07-01T08:52:01Z

## Verdict

- Status: configured_pending_oauth
- Verdict: ready_for_human_oauth
- Decision: activate_with_oauth_checkpoint
- Overall rating: 89/100
- Best fit: Draft creative generation, Technique discovery, thumbnail grids, video plates, and localized batches.
- Main risk: External media generation can consume credits and may receive sensitive briefs if not gated.

## Local Checks

- Settings has FLORA: True
- Settings command: C:\Users\a.alirzayev\ramin-os\video-studio\tools\node-v24.15.0-win-x64\npx.cmd
- Settings command available: True
- Settings transport: stdio_proxy_to_http
- Settings URL: https://agents.flora.ai/mcp
- Official URL match: True
- Setup script has FLORA: True
- Permission manifest has FLORA: True
- Manifest status: sandbox_draft_only
- Blocks customer data: True
- Blocks public posting: True
- Requires cost control: True
- Credentials checked: False
- Note: Credential and OAuth token presence is intentionally not inspected.

## Existing Ramin-OS FLORA Touchpoints

- `video-studio/generative_ads/README.md`
- `video-studio/generative_ads/model_matrix.flora.md`
- `social-studio/prompt_kit/model_dialects/flora-video.md`
- `scripts/compile_generative_ad.py`
- `docs/media-studio-automation-action-plan.md`

## Activation

```powershell
.\scripts\setup-mcp.ps1
python -m gateway.flora_ai doctor
```

Then open the MCP client and ask: `List my FLORA Techniques.` The first tool call should open OAuth.

## Safety Controls

- Do not send secrets, customer data, claims, payment data, internal policies, or unredacted private strategy.
- Check run_cost x count before batches or premium model work.
- Keep exact text, legal copy, logos, dates, prices, and CTA in deterministic local overlays.
- Use FLORA outputs as drafts, then pass final work through Video Studio QA and Publisher dry-run.
- Treat OAuth token caches and output URLs as sensitive operational material.

## Official References

- [FLORA MCP](https://developer.flora.ai/mcp/) - Official remote MCP overview and supported agent workflows.
- [Claude Code install](https://developer.flora.ai/mcp/install/claude-code/) - Official Claude Code command and project-scoped config shape.
- [Authentication](https://developer.flora.ai/mcp/authentication/) - OAuth and API-key boundary for interactive versus server-side use.
- [Tools reference](https://developer.flora.ai/mcp/tools/) - The MCP exposes search_docs and execute over the FLORA SDK.
- [Batch with a coding agent](https://developer.flora.ai/mcp/recipes/batch-with-coding-agent/) - Shows batch creative generation with explicit cost controls.

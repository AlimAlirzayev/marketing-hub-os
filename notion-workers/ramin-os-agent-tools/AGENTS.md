# Ramin-OS Notion Worker Agent Rules

This folder follows the root Ramin-OS charter first. In particular, never read,
print, copy, upload, or summarize `.env`, `.env.bak`, tokens, cookies, or
credentials.

## Purpose

This worker gives Notion Custom Agents safe Ramin-OS helper tools. It is for
read-only screening and draft handoffs, not autonomous execution.

## Allowed Work

- Edit `src/index.ts` to add narrow, side-effect-free tools.
- Use `@notionhq/workers` and `@notionhq/workers/schema-builder`.
- Validate with `npm run check`.
- Smoke-test locally with `ntn workers exec <tool> --local --no-dotenv -d ...`.

## Blocked Without Human Checkpoint

- `ntn login`, `ntn workers deploy`, `ntn workers env set/push/pull`, real sync
  triggers, OAuth start, and webhook URL handling.
- Any tool that sends, posts, publishes, spends, deletes, deploys, or writes
  production data.
- Any use of customer data, claims, policies, payment data, raw secrets, or
  private strategy.

## Development Notes

- Keep capability keys stable and lowerCamelCase.
- Use field descriptions on every tool schema property.
- Mark side-effect-free tools with `hints: { readOnlyHint: true }`.
- Do not add syncs or webhooks until their data source, auth model, preview
  flow, and signature verification are documented.

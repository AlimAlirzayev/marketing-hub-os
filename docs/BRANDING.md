# Branding — one codebase, many deployments

This repo runs as more than one product: the **Xalq Sigorta** corporate build and a
generic **global** build. To keep them as ONE codebase that syncs cleanly over git
(push here → pull there), the brand must live in **config, not in code**.

## The rule

> Never hardcode a brand string (name, system name, site, locale) in code. Read it
> from [`brand.py`](../brand.py). The brand is chosen by one env var, `BRAND`.

```python
from brand import BRAND
title = f"{BRAND.system_name} report"   # not "Xalq Insurance Digital OS report"
```

## Switching a deployment

Set one line in that machine's `.env`:

```
BRAND=xalq     # Xalq Sigorta (corporate) — the default
BRAND=global   # Marketing Hub (generic personal build)
```

Nothing else changes. The work PC keeps `BRAND=xalq`; the personal/global server
sets `BRAND=global`. Same code, different identity → `git pull`/`push` never
collide over branding. Check the active brand any time:

```bash
python brand.py
```

## Adding / editing a profile

Edit `_PROFILES` in [`brand.py`](../brand.py). Identity fields (name, system_name,
industry, website, locale) live there. **Visual + voice DNA** (colors, logo, tone)
stays in each brand's `brand_kit` (e.g. `social-studio/brand_kit`) — `BRAND.brand_kit`
points at it — so curated creative prose has one home and isn't duplicated here.

## Migration status (honest)

Brand strings currently appear in ~557 places across ~215 files (`git grep -i xalq`).
This is migrated **incrementally**, not all at once — most of those are generated
marketing content and curated brand_kit prose, which are legitimately per-deployment
(the global build generates its own). Priority order:

1. **Live-facing identity** — UI titles, report headers, council/agent prompts,
   Telegram replies. Migrate these to `BRAND.*` first.
2. **Configs / service metadata**.
3. Leave generated output and brand_kit creative prose to each deployment's own kit.

When you touch a file that hardcodes the brand, replace it with `BRAND.*` as you go.

# Capability Cascade — the free-tier-aware router

This file is the **router brain** every command reads before it spends a
credit or a dollar. It encodes one principle and three rules.

**Principle — free-first, no silent drops.** Each capability is a cascade of
providers ordered cheapest→best. Try the free local/HF path first. Only climb
to a paid tool's free-but-limited tier when the free path can't do the job —
and only after checking the remaining quota. If the whole cascade is exhausted,
fall back to a **manual handoff** and say so. Never quietly drop the feature.

**Rule 1 — prefer free, on-prem, token-cheap.** Self-hosted (Postiz, Ollama,
local FFmpeg/Whisper) and free HF Spaces beat anything metered. Raw MCP servers
burn tokens; prefer a *skill* or a direct API/`gradio_client` call over piping
a whole MCP transcript through context.

**Rule 2 — a paid tool's free daily tier is a real provider.** Higgsfield
(~150 cr/mo), Blotato (trial/caps), and friends have limited free usage. Treat
that as a quota-bounded provider: **check what's left, use it when it's there,
fall back when it's gone.** The `quota check` column says how.

**Rule 3 — the market moves weekly; keep this file alive.** Every row carries a
`verified` date. When a date is stale (>30 days) or a call fails with a
quota/pricing error, run `/scout` (see bottom) to re-verify and to look for
newer, cheaper providers. Update the rows; don't trust month-old free tiers.

> Tokens-as-budget: the $100 Claude Max plan is worth ~$2,500/mo in API tokens
> *only if* we don't waste them. That's why Rule 1 favors skills + direct calls
> over chatty MCP, and why the local paths come first.

---

## How a command routes (the algorithm)

```
for provider in cascade(capability):          # cheapest → best
    if not provider.configured:  continue     # key/tool missing → skip, note it
    if provider.metered and quota_left(provider) <= 0:  continue
    try:
        return provider.run(job)              # success → stop here
    except QuotaError | AuthError | DownError as e:
        log(e); continue                      # NEVER drop silently — try next
return manual_handoff(job)                     # cascade exhausted → one paste-block
```

State which provider actually ran, and why the ones above it were skipped.

---

## Cascades

### publish — push a finished asset to social platforms  *(Priority 1, see `/publish`)*

| # | Provider | Tier | Free quota | Quota check | How invoked | Notes |
|---|----------|------|-----------|-------------|-------------|-------|
| 1 | **Postiz** (self-host) | free | unlimited (own infra) | n/a | its MCP server / `POSTIZ_API_URL` + key | AGPL-3.0, 20+ networks, n8n nodes. **Default.** |
| 2 | **n8n** workflow | free | unlimited (own infra) | n/a | webhook → platform node | Glue when a network needs custom auth. |
| 3 | **Blotato** | paid | trial only; Starter caps (≈3 TikTok/24h) | plan/usage via Blotato API | MCP (`BLOTATO_API_KEY`) | Only if 1–2 down **and** key set. Respect daily caps. |
| 4 | manual | — | — | — | print ready-to-paste captions + asset paths | Last resort. |

### clip — find + cut viral moments from a long video  *(`/clip`, built + proven)*

| # | Provider | Tier | Free quota | Quota check | How invoked | Notes |
|---|----------|------|-----------|-------------|-------------|-------|
| 1 | **Local clipper** | free | unlimited | n/a | `video-studio/clipper.py` → transcript → free-LLM score → `ffmpeg_ops.cut_clip` | **Built.** Runs on free Gemini/Groq; proven end-to-end (1080×1920 cuts). |
| 2 | **HF Whisper Space** | free | ZeroGPU minutes | HF account ZeroGPU budget | `gradio_client` → `hf-audio/whisper-large-v3` | Transcribe step if local Whisper is blocked (VC++ lockdown). |
| 3 | **Higgsfield** clipper skill | free→paid | ~150 cr/mo, 720p watermark | dashboard / API credit balance | Higgsfield MCP/CLI | Premium "personal clipper". MCP **always** spends credits. |

### video-gen — generate an original short video from a prompt/image

| # | Provider | Tier | Free quota | Quota check | How invoked | Notes |
|---|----------|------|-----------|-------------|-------------|-------|
| 1 | **HF Spaces** | free | ZeroGPU minutes | HF ZeroGPU budget | `gradio_client` → e.g. `alexnasa/ltx-2-TURBO`, `r3gm/wan2-2-*` | Free Seedance-class gen. Authenticated as `raminataxanl`. |
| 2 | **Flora** | metered | per `model_matrix.flora.md` | Flora credits | Flora MCP/SDK | Already wired in `video-studio/generative_ads/`. |
| 3 | **Higgsfield** | free→paid | ~150 cr/mo | credit balance | Higgsfield MCP | Watermarked on free; premium quality. |

### audio-gen — generate music / sound effects / voice from a prompt  *(`/sound`, built + proven)*

The universal "Suno but also SFX and speech" engine. One CLI
(`audio-studio/audio_studio.py`), three sub-cascades. ElevenLabs is the headline
studio engine (one API for music + sfx + tts + voice clone, 10k free cr/mo, official
MCP server `elevenlabs`); free paths run first so we only spend its credits when needed.

**music** — original background beds / songs from a prompt.

| # | Provider | Tier | Free quota | Quota check | How invoked | Notes |
|---|----------|------|-----------|-------------|-------------|-------|
| 1 | **Stable Audio 3** Space | free | ZeroGPU minutes | HF ZeroGPU budget | `audio_studio.py music` → `gradio_client` `/infer` (`AUDIO_HF_MUSIC_SPACE`) | **Proven live.** `small-music` variant. Space ids drift — re-point via `/scout`. |
| 2 | **ElevenLabs** `compose_music` | free→paid | 10k cr/mo | account dashboard | same CLI / `elevenlabs` MCP | Studio-grade, commercially cleared. `--quality` puts it first. |
| 3 | **Lyria 3** (Gemini) | paid | AI-Studio test only | n/a | `AUDIO_ENABLE_LYRIA=1` | Off by default; may bill. |
| 4 | manual | — | — | — | paste prompt → Suno / Udio / ElevenLabs Music | Best song quality lives here. |

**sfx** — short sound effects from a description.

| # | Provider | Tier | Free quota | Quota check | How invoked | Notes |
|---|----------|------|-----------|-------------|-------------|-------|
| 1 | **ElevenLabs** `sound_effect` | free→paid | 10k cr/mo (≈tiny per clip) | dashboard | `audio_studio.py sfx` | The gold standard; cheap enough to lead. |
| 2 | **Stable Audio 3** Space | free | ZeroGPU | HF budget | `audio_studio.py sfx --provider hf` (`small-sfx`) | **Proven live.** Free fallback. |

**tts / voice** — voice-over, dubbing, cloning.

| # | Provider | Tier | Free quota | Quota check | How invoked | Notes |
|---|----------|------|-----------|-------------|-------------|-------|
| 1 | **Edge Neural TTS** | free | unlimited | n/a | `audio_studio.py tts` (`edge-tts`) | **Native Azerbaijani** (`az-AZ-Babek/Banu`). Commercial-safe, unlimited — but robotic to a native ear. |
| 2 | **Gemini 3.1 native-audio TTS** | free* | Gemini quota | key quota | `tts --provider gemini --voice <Kore/Charon/...>` | **Most natural synthetic AZ** (the reel's family). 30+ voices. *free output NOT licensed for commercial use → paid billing for production. |
| 3 | **OmniVoice clone** | free | ZeroGPU (daily) | HF budget | `clone --ref <human clip>` | **Your own voice:** clones a real human (600+ langs incl. AZ). Best identity match; prosody < ElevenLabs. |
| 4 | **ElevenLabs** TTS | **paid** | none on free (402) | dashboard | same CLI / `elevenlabs` MCP | Free API blocks library voices; TTS/clone need a paid plan. |

> Verified live (measured; naturalness is a **human-ear** call, never claimed by the agent):
> **free + working** = Edge AZ, **Gemini 3.1 TTS** (AZ, multi-voice — 2026-06-22), Stable
> Audio 3 music+sfx, ElevenLabs **sfx**, OmniVoice **clone**. **Paid-only** on a free
> ElevenLabs key = music + TTS (402). For natural AZ: try **Gemini 3.1 TTS** (synthetic,
> natural) or **clone** (your voice). **Real-time dubbing/translation** → Gemini Live API
> (`gemini-3.5-live-translate-preview`) is the roadmap for `azdub-extension`.

### image-gen — already implemented in `/post` step 7; mirror its cascade

Codex CLI (subscription) → FLUX.1-dev HF Space (free) → Pollinations FLUX
schnell (free) → manual handoff. This is the canonical example of this pattern.

### transcribe / captions

Groq Whisper (free key, fast) → local faster-whisper (offline; blocked until
IT installs VC++ redist) → HF `whisper-large-v3` Space (free). See
`video-studio/transcribe.py`.

### llm — reasoning, scoring, copy (the "brain" steps)

**20/80 hybrid (the cost rule):** route ~20% — high-level planning, final
synthesis — to a premium model (Claude, this CLI). Offload ~80% — scraping,
parsing, scoring, first drafts, sub-agent grunt work — to a free/cheap model.
This is how a $0 stack does heavy agentic volume.

Free-first cascade (all OpenAI-compatible unless noted):

| # | Provider | Free tier | Notes |
|---|----------|-----------|-------|
| 1 | **Ollama / LM Studio** (local) | unlimited | no key, offline. Qwen3.x / GLM-air / Gemma 4 GGUF. |
| 2 | **Groq** | ~30 req/min | fastest hosted free; Llama / Qwen. |
| 3 | **Cerebras** | free, no card | very fast. |
| 4 | **Gemini 2.5/3.x Flash** | ~1500/day | our live key. Native search grounding. |
| 5 | **GLM-4.7-Flash** (Zhipu) | free outright | GLM-5.2 ≈ Opus quality at ~1/5 cost (pay tier); MIT, on HF+Ollama. |
| 6 | **OpenRouter** free models | 200 req/day/model (1000 after one $10 top-up) | DeepSeek V4, Qwen3.x, GLM, Llama — one key, many models. |
| 7 | **NVIDIA NIM** | free (phone verify) | DeepSeek / Qwen hosted. |
| 8 | **HF Inference** | free | authed as `raminataxanl`. |
| 9 | **Claude** (this CLI) | budget-as-tokens | reserve for the 20%. |

Pick the cheapest model that clears the bar. China labs (DeepSeek, GLM/Zhipu,
Qwen, Kimi, MiniMax) are the value frontier — open-weight, OpenAI-API-shaped,
free or ~5× cheaper.

> **OpenCode — ADOPTED as the free second harness (the executor arm).** Installed
> (v1.17.x) into the portable Node (Docker-free, no admin); default model = free
> **Gemini 2.5-flash** via `opencode.json` (Groq's 12k TPM is too small for the
> ~42k agent context — see [`docs/OPENCODE.md`](../../../docs/OPENCODE.md)). It
> runs the token-heavy 80% (bulk edits, scaffolds, model A/B, offline) on free
> models; Claude Code keeps the 20% (planning, final review). The 20/80 split at
> the *harness* level — complement to `llm_router` (the same split at the API-call
> level). **A council member only when it adds model diversity:** the panel
> already has a Gemini voice, so OpenCode-on-Gemini would be a redundant 2nd Gemini
> (correlated, slower, no new signal). `gateway/council.py` therefore admits it
> *only* when configured with a distinct free model (`OPENCODE_COUNCIL_MODEL=`
> deepseek/qwen via OpenRouter, or force `AI_COUNCIL_OPENCODE=1`); `--agent plan`,
> read-only, and the prompt must lead with the task (a persona wrapper makes it
> just acknowledge). Launch the TUI in a scoped subdir, not the repo root.
> Full coordination map: [`docs/ORCHESTRATION.md`](../../../docs/ORCHESTRATION.md).

**Implementation: `llm_router.py`** (repo root, LiteLLM-backed — the 2026
standard: one OpenAI-compatible gateway, per-request routing + auto fallback).
```python
from llm_router import complete, complete_json
text, model = complete(prompt, tier="cheap")     # 80% grunt → free models
data, model = complete_json(prompt, tier="cheap")
text, model = complete(prompt, tier="smart")      # 20% planning/synthesis
```
`cheap` order = best-free-quality first (Gemini-flash) → Groq/Cerebras (fast
fallback) → OpenRouter/DeepSeek → local Ollama. Skips unconfigured providers,
falls through on any error. `clipper.py` scoring, `scripts/yt_digest.py`, and the
autonomous `gateway/llm.py` all route through it. Add keys in `.env`
(OPENROUTER/DEEPSEEK/CEREBRAS/ZHIPU…) to light up more rungs — no code change.

**Observability** (the managed-gateway feature — openmodel.ai/Portkey — done free
+ local): every served call logs model/tokens/est-cost/latency to
`data/logs/llm_usage.jsonl`.
- `python llm_router.py --probe` — show configured providers + ping.
- `python llm_router.py --usage` — per-model cost/latency summary.

---

## Token hygiene — make the budget last (every command obeys)

The $100 plan ≈ $2,500/mo in tokens *only if* we don't waste them:

- **English everywhere** in backend files/prompts. Non-English (AZ/TR special
  chars) costs **+30–75%** tokens. (User-facing deliverables stay AZ.)
- **Markdown over everything.** HTML +90%, PDF +70%, DOCX +33% vs `.md`.
  Convert inputs with **Docling** (free, pip, no Docker) before feeding an LLM.
- **Pre-digest big inputs with a free LLM**, never raw into context. See
  `scripts/yt_digest.py` (transcript → free-Gemini digest → read the summary).
- **`.claudignore` / ignore globs** for heavy dirs (`output/clips/*.mp4`,
  `.venv`, `tools/`, `node_modules`) so the agent never scans media.
- **Prune context**: `/compact` near 90% full; `/rewind` to drop dead-end loops.
- **Keep CLAUDE.md lean**; let it route to sub-agent `.md` files loaded on demand.
- **Interactive delegation rule (in a live chat the premium model runs the turn —
  there is no automatic offload, so decide deliberately):**
  - *Reasoning, architecture, small edits, final review, the actual conversation*
    → keep on the premium model (this CLI). Offload overhead would cost more than
    it saves, and quality matters here.
  - *Genuinely heavy + mechanical + repetitive batch work* (bulk refactor across
    many files, scaffold N modules, boilerplate, format conversions) → **hand to
    OpenCode + a free model** and supervise the result. This is the 20/80 split
    made real at the harness level.
  - *A huge single input to understand* (long transcript/doc/log) → **pre-digest
    with a free model first** (`scripts/yt_digest.py` pattern); only the summary
    enters premium context — never the raw blob.
  - Default when unsure: do it directly (premium). Delegating a small task is a
    net loss. Announce a delegation when you make one; never offload silently.

---

## `/scout` — keep this file current  *(answers Rule 3)*

A capability is only as good as its freshest row. The scout pass:

1. For every row with a stale `verified` date (or a provider that just failed),
   `WebSearch` the current free tier / daily limit / pricing and correct it.
2. Look for **new** free providers: HF trending
   (`hub_repo_search sort=trendingScore`, `space_search mcp:true`) and a web
   sweep for "open source / free <capability> 2026". Add any that beat an
   existing row.
3. Re-stamp `verified:` dates; summarize what changed.
4. Surface changes in the autonomous layer's Telegram morning report so a
   shrinking free tier never silently breaks a workflow.

Run it on demand, or schedule it monthly via the autonomous layer.

---

_Verified: 2026-06-12. Stale after 2026-07-12 — run `/scout`._

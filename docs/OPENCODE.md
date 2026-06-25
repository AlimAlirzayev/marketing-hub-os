# OpenCode — the free second harness

OpenCode is the leading open-source coding **harness** (≈160K★, 75+ model
providers) — a Claude-Code alternative whose headline is **model freedom**. We
adopted it as a **second, free agent** that runs the token-heavy 80% (iterative
edits, refactors, scaffolding, model A/B tests, offline work) on **free models**,
while Claude Code keeps the 20% (planning, final synthesis). This is the 20/80
hybrid realized at the *harness* level — see
[`claude-agents/.claude/capabilities.md`](../claude-agents/.claude/capabilities.md).

It does **not** replace Claude Code; it runs alongside it. Same repo, same
`AGENTS.md`/`CLAUDE.md` context (wired via `opencode.json` → `instructions`).

## Install (done — Docker-free, no admin)

Installed into the **portable Node** already in the repo (no winget, no admin):

```powershell
$node = "video-studio\tools\node-v24.15.0-win-x64"
$env:Path = "$node;$env:Path"          # postinstall needs node on PATH
& "$node\npm.cmd" install -g opencode-ai
& "$node\opencode.cmd" --version       # -> 1.17.x
```

The `opencode` shim lands in the portable Node dir. To use it anywhere, either
prepend that dir to PATH or call the shim by full path. (The native installer at
`~/.local/bin` — like the Claude CLI — is an alternative if IT ever allows it.)

## Configure for FREE models (done)

[`opencode.json`](../opencode.json) at the repo root sets the **default model to
free Gemini** so OpenCode never reaches for a paid model unless told:

```json
{ "model": "google/gemini-2.5-flash", "small_model": "google/gemini-2.5-flash-lite" }
```

> **Why Gemini, not Groq, as the harness default.** OpenCode's agent system
> prompt (+ tools + auto-loaded `AGENTS.md`) is ~12–40k tokens. **Groq's free tier
> caps at 12,000 tokens/minute**, so the agent loop fails with *"Request too
> large … TPM Limit 12000."* Gemini Flash (1M context, generous free quota)
> handles it; OpenRouter `:free` and local **Ollama** also work. Groq stays great
> for our single-shot `llm_router` calls — just not as an agent-harness brain.

## Use — the wrapper does the setup (no manual env steps)

[`scripts/opencode.ps1`](../scripts/opencode.ps1) prepends the portable Node,
loads the free keys from `.env`, and maps `GEMINI_API_KEY` →
`GOOGLE_GENERATIVE_AI_API_KEY` (what OpenCode's Google provider reads). Just run:

```powershell
# interactive TUI (run inside a scoped subdir, not the repo root — see note)
.\scripts\opencode.ps1 some-subdir\

# non-interactive (scriptable) on a free model
.\scripts\opencode.ps1 run "refactor X to Y"          # uses the Gemini default
.\scripts\opencode.ps1 run "..." -m openrouter/deepseek/deepseek-chat
.\scripts\opencode.ps1 models                          # list providers/models
.\scripts\opencode.ps1 stats                            # token + cost accounting
```

Free providers wired by the wrapper: **Gemini** (default), **Groq**,
**OpenRouter** (DeepSeek/GLM/Qwen incl. `:free`), **DeepSeek**, **Cerebras**, and
**Ollama** (local, offline). `opencode auth login` is an alternative to the env.

When to reach for OpenCode instead of Claude Code:
- **Token-heavy grunt work** (bulk edits, boilerplate, test scaffolds) → free model.
- **Model A/B tests** — same task across Groq vs Gemini vs DeepSeek vs local.
- **Offline / air-gapped** work → Ollama, fully local.
- Keep **Claude Code** for architecture, tricky reasoning, final review (the 20%).

## Gotcha — don't launch in the repo root cold

First launch indexes the project tree. The repo root contains heavy dirs
(`.venv`, `video-studio/tools`, `node_modules`) that make the first run crawl.
Launch OpenCode in a **scoped subdirectory** (the package you're working on), or
ensure those dirs are ignored, so it indexes only what matters.

## VS Code extension

OpenCode ships a VS Code extension (Grok's tip: try it first). Install it from
the VS Code Marketplace ("OpenCode"); it drives the same engine + config, so the
free-model setup above applies. The extension is a per-user IDE add-on you enable
in VS Code — it doesn't need the portable-Node install above, but they coexist.

# Xalq Insurance Digital OS - Jarvis

The personal voice assistant layer, based on [isair/jarvis](https://github.com/isair/jarvis).
Runs fully local: wake-word detection, Whisper STT, and an Ollama model for the
brain - no cloud calls, no per-request cost.

## Install

```powershell
..\scripts\install-jarvis.ps1
```

The script downloads the latest Windows release from
https://github.com/isair/jarvis/releases, extracts it here, and creates
`config.yaml` from `config.yaml.example`.

### Manual fallback

If the script cannot reach the GitHub API:

1. Download a Windows release zip from https://github.com/isair/jarvis/releases
2. Extract its contents into this `jarvis/` folder
3. Copy `config.yaml.example` to `config.yaml`

## Configure

Edit `config.yaml`:

- `wake_word` - the phrase that activates the assistant
- `llm.model` - the Ollama model (pull it first with
  `..\scripts\install-ollama-models.ps1`)
- `skills` - enable or disable capabilities
- `orchestrator_bridge` - when enabled, voice commands can dispatch CrewAI crews
  via `orchestrator/crews/jarvis_bridge.py`

## Files

| File / folder         | Purpose                                      |
|-----------------------|----------------------------------------------|
| `config.yaml.example` | Template config (tracked in git)             |
| `config.yaml`         | Active config (created on install, untracked)|
| `memory.db`           | SQLite conversation memory (untracked)       |
| `skills/`             | Skill modules                                |

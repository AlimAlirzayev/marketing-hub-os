# doit — autonomous credential-acquisition agent

The "force" that **gets the API key itself** instead of telling you to go get it.
It drives a real Chromium browser (Chrome or Edge) under **your own logged-in
session**, opens the provider dashboard, finds the key in the page/network, and
writes it straight into the repo `.env` — then points you at the provider's probe
to confirm what the key unlocks.

It is our in-house equivalent of the "many-armed" browser agents (OpenClaw / the
Hermes archetype), scoped to one honest job: acquire **your own** credentials on
**your own** accounts.

## What it will and won't do (by design)

- ✅ Uses *your* browser session. Two ways to provide one:
  1. **Default** — doit keeps its own persistent profile (`doit/.profile-<browser>`).
     First run opens a visible window, you log in **once**, every later run is autonomous.
  2. **Your real profile** — point `--user-data-dir` at your Chrome/Edge `User Data`
     (that browser must be fully closed) to use the session you're already in.
- ✅ Writes the key into `.env` (create / update / append, comments preserved).
- ✅ Where a live dashboard is unpredictable, it opens visibly and waits for **one**
  human action, then resumes — it never fakes success.
- ❌ Does **not** create fake accounts or defeat CAPTCHA (those are yours to do once).

## Why Chrome by default (not arbitrary)

Chrome and Edge are both Chromium and both verified to drive on this machine.
Default is **Chrome** because a RapidAPI login most commonly lives there; switch
with `--browser edge`. `--browser auto` picks Chrome if installed, else Edge.

## Use

```powershell
# First time: a visible window opens, log into RapidAPI once; doit remembers it.
..\.venv\Scripts\python.exe -m doit rapidapi

# Or use the browser you're ALREADY logged into (close it first):
..\.venv\Scripts\python.exe -m doit rapidapi --browser chrome `
    --user-data-dir "$env:LOCALAPPDATA\Google\Chrome\User Data" --profile-directory Default

# Once the session is saved, run it fully headless:
..\.venv\Scripts\python.exe -m doit rapidapi --headless

# Optionally subscribe to a specific host's free plan in the same run:
..\.venv\Scripts\python.exe -m doit rapidapi --subscribe-url https://rapidapi.com/<api-page>
```

On success it sets `RAPIDAPI_KEY=...` in the repo `.env`, then
`influencer-hunter/rapidapi_probe.py` reports which hosts the key unlocks.

## Architecture

| File | Role |
|---|---|
| `keyscan.py` | **pure** key detectors (RapidAPI `msh…jsn` shape); a provider = one entry in `DETECTORS` |
| `envfile.py` | **pure** `.env` upsert (tested: create/update/append, preserves comments) |
| `agent.py` | Playwright Chrome/Edge agent: session, navigate, scan page+network, human-in-loop fallback |
| `__main__.py` | CLI |

The fragile part (a live JS dashboard DOM) is isolated in `agent.py`; the parts we
can prove (`keyscan`, `envfile`) are pure and unit-tested. Add a provider by
appending a `RECIPES` entry + a `DETECTORS` entry — no new code path.

## Requirements

`playwright` (installed in the repo `.venv`) driving system Chrome/Edge via
`channel=` — **no browser download** needed. Reinstall if missing:

```powershell
..\.venv\Scripts\python.exe -m pip install playwright
```

> The persistent profile under `doit/.profile-*` holds an authenticated session —
> it is git-ignored. Never commit it.

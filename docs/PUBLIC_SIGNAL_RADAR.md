# Public Signal Radar

Public Signal Radar is the autonomous intake loop for fast-moving public AI,
creative, media, privacy, and workflow signals. It exists so the operator does
not have to manually say "check this channel" every time.

It is deliberately not a new hub service. It is a read-only supervisor loop that
feeds the lab and prototype shelves.

## Loop

```text
public source
  -> claim extraction
  -> official-source gate
  -> supervisor/orchestrator-style triage
  -> lab/knowledge note
  -> lab/prototypes backlog item
  -> output/signal-radar report
  -> later sandbox audition in the owning module
```

## Runtime

The always-on supervisor starts the loop automatically:

```powershell
python -m gateway.supervisor
```

The radar checks whether it is due, then fetches configured public sources. By
default it watches the public Telegram mirror for `@perplexity`.

Environment knobs:

| Variable | Default | Purpose |
|---|---:|---|
| `SIGNAL_RADAR_ENABLED` | `1` | Set `0` to disable the loop. |
| `SIGNAL_RADAR_INTERVAL_HOURS` | `24` | Minimum hours between full runs. |
| `SIGNAL_RADAR_TICK_SECONDS` | `3600` | Supervisor wake-up interval. |
| `SIGNAL_RADAR_SOURCES` | built-in Perplexity mirror | JSON list or comma-separated public URLs. |

Manual commands:

```powershell
python -m gateway.signal_radar due
python -m gateway.signal_radar run
python -m gateway.signal_radar status
```

## Outputs

- `lab/knowledge/*.md` - local source-checked research notes.
- `lab/prototypes/backlog.json` - reusable prototype and future-skill backlog.
- `lab/prototypes/*.md` - human-readable prototype specs.
- `data/signal_radar/public_signals.jsonl` - local runtime ledger.
- `output/signal-radar/*.md` - dated reports for panel/operator review.

Runtime `data/` and `output/` files are git-ignored. Prototype specs are
trackable engine material because they represent reusable capability decisions.

## Current Routing

| Signal type | Route |
|---|---|
| ChatGPT Work / workflow products | `gateway`, `workspace_agent`, `panel`, permissions |
| Media model releases such as Muse or Nano Banana | `media_studio` / Media Studio, `atelier`, `mediagen` |
| Child/minor image safety | `publisher`, `atelier`, Media Studio, permissions |
| Sensor or ambient-agent demos | `lab/prototypes`, gateway approval rails, `brain` |
| New coding/agent models | `gateway/agent_radar`, `llm_router` watch only |
| Weak pop-culture trend fit | skip or idea-bank only |

## Hard Boundaries

Public Signal Radar must not:

- read `.env`, keys, cookies, OAuth caches, customer data, claims, policies, or
  private strategy
- fetch localhost, private IPs, `.local`, `.lan`, `.internal`, or URLs with
  credentials
- enable providers, install agents, spend credits, publish, send messages,
  schedule posts, log in, or change production data
- control a browser, desktop app, camera, microphone, serial device, or hardware
  without a later human-approved workflow

Public channel posts are claims. A model, provider, connector, or workflow does
not enter production until the owning module performs an official-source check,
sandbox audition, and approval-gated integration.

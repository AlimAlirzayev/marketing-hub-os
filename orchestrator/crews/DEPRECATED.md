# DEPRECATED — do not revive these skeletons

These CrewAI crews are **unwired skeletons** and are superseded by the live
multi-agent layer.

## Why deprecated
- `crew.kickoff()` is never called (`jarvis_bridge.dispatch_from_jarvis` returns
  `crew_ready`, marked `TODO`). They never execute.
- They depend on **CrewAI**, which is deliberately not installed on this
  locked-down corporate machine (the whole gateway avoids langchain/crewai).
- They duplicate, less capably, what already works.

## What replaces it

The current production operational workforce is
`gateway/studio_crew.py`: an isolated CrewAI hierarchy over the live studios.
The Claude conversational brain acts as model-as-router and calls
`gateway/summon.py`, which enters the explicit `/crew` rail asynchronously;
Claude then synthesizes the worker output for the operator.

`gateway/council.py` still exists only as an explicit legacy subscriber-CLI
consultation rail. It must not be treated as the current default workforce or
enabled in place of the Crew/manager architecture.

## Status
Files are **kept, not deleted** for history. Importing `orchestrator.crews`
emits a `DeprecationWarning`. Do not build new work on them; reinforce the
production `gateway/studio_crew.py` and model-as-router/summon path.

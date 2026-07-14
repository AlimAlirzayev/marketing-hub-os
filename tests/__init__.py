"""Test-session isolation — tests must NEVER write into the LIVE system state.

Why this exists (2026-07-14): the owner's session pulse showed five "recent
events" that never happened — `engine updated -> abc1234`, `rejected non-owner
chat_id=999`, `transcribed via b` — all of them fixtures. Tests that call
`sense.emit()` (e.g. test_supervisor_sync) were appending to the real
`data/logs/system_events.jsonl`, so every test run overwrote the system's actual
recent history with noise, and the advisor/pulse reasoned over fiction.

This lives in `tests/__init__.py` (not conftest.py) deliberately: the package
init is imported by BOTH runners — pytest AND `unittest discover`, which the
post-pull tripwire (gateway/postpull.py) uses. A conftest.py would only cover
pytest and the tripwire would keep polluting.

`setdefault` keeps two freedoms: a test that sets its own path (test_sense,
test_advisor) still wins, and an outer caller can still redirect deliberately.
"""

from __future__ import annotations

import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="ramin-os-tests-")
os.environ.setdefault("SYSTEM_EVENTS_PATH", os.path.join(_tmp, "system_events.jsonl"))
os.environ.setdefault("LLM_USAGE_PATH", os.path.join(_tmp, "llm_usage.jsonl"))

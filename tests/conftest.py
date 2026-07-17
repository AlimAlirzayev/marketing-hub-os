"""Shared test guards.

Isolation of the live event log: sense.emit() appends to
data/logs/system_events.jsonl — the SAME file the pulse/advisor read as system
truth. Tests that exercise bot/queue/stt paths were writing their synthetic
events (chat_id=999, task a/b/c, fake sync summaries...) into it, so the pulse
"SON HADİSƏLƏR" showed test noise as if it were reality. Every test now gets a
throwaway events file; tests that need to assert on events keep working because
they either read the env var or set their own temp path on top of this one.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_system_events(tmp_path, monkeypatch):
    monkeypatch.setenv("SYSTEM_EVENTS_PATH", str(tmp_path / "system_events.jsonl"))

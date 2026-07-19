"""The pulse's BEYİN line must tell the truth about which brain is live.

Regression guard (2026-07-15): the indicator read os.getenv("MIC_BRAIN"), but the
session_pulse hook never calls load_env(), so it always showed 🟡 free even when
.env said claude — a false "the brain is downgraded" alarm. sense.env_value now
reads the .env file directly (like the credential lamps), so the indicator is true
without load_env().
"""

from __future__ import annotations

import os
from unittest import mock

from gateway import sense


def test_env_value_reads_dotenv_without_load_env(tmp_path):
    env = tmp_path / ".env"
    env.write_text("MIC_BRAIN=claude\n", encoding="utf-8")
    # os.environ deliberately does NOT hold MIC_BRAIN — mimic the pulse hook process.
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("MIC_BRAIN", None)
        assert sense.env_value("MIC_BRAIN", "free", env_path=str(env)) == "claude"


def test_pulse_shows_premium_when_dotenv_says_claude(tmp_path):
    env = tmp_path / ".env"
    env.write_text("MIC_BRAIN=claude\n", encoding="utf-8")
    with mock.patch.object(sense, "_dotenv_values",
                           return_value={"MIC_BRAIN": "claude"}):
        board = sense.pulse()
    beyin = [l for l in board.splitlines() if l.startswith("BEYİN")]
    assert beyin and "premium" in beyin[0] and "🟢" in beyin[0]


def test_pulse_shows_claude_when_unset():
    # New default (2026-07-19): with nothing set, the brain is Claude, so the
    # pulse shows the premium line — not the old free/downgrade warning.
    with mock.patch.object(sense, "_dotenv_values", return_value={}), \
         mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("MIC_BRAIN", None)
        board = sense.pulse()
    beyin = [l for l in board.splitlines() if l.startswith("BEYİN")]
    assert beyin and "premium" in beyin[0] and "🟢" in beyin[0]

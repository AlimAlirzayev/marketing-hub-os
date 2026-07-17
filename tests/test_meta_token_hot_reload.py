from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADS = ROOT / "ads-studio"


def _run(code: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", code], cwd=ADS, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=30,
    )


def test_meta_connectors_reload_rotated_tokens_without_restart(tmp_path):
    # META_ACCESS_TOKEN wins when both are set (2026-07-17): it's the only one
    # the encrypted vault sync rotates, so a same-but-separately-set
    # META_GRAPH_ACCESS_TOKEN silently going stale must not shadow it.
    env_file = tmp_path / ".env"
    env_file.write_text(
        "META_ACCESS_TOKEN=fresh-paid-token\nMETA_GRAPH_ACCESS_TOKEN=stale-graph-token\n",
        encoding="utf-8",
    )
    code = """
from connectors import meta, organic
meta._ROOT_ENV = r'ENV_PATH'
organic._ROOT_ENV = r'ENV_PATH'
assert meta._access_token() == 'fresh-paid-token'
assert organic._token() == 'fresh-paid-token'
print('ok')
""".replace("ENV_PATH", str(env_file).replace("\\", "\\\\"))
    proc = _run(code)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "ok"


def test_organic_falls_back_to_graph_token_when_paid_token_unset(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("META_GRAPH_ACCESS_TOKEN=only-graph-token\n", encoding="utf-8")
    code = """
from connectors import organic
organic._ROOT_ENV = r'ENV_PATH'
assert organic._token() == 'only-graph-token'
print('ok')
""".replace("ENV_PATH", str(env_file).replace("\\", "\\\\"))
    proc = _run(code)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "ok"

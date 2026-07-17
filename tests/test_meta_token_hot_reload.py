from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADS = ROOT / "ads-studio"


def test_meta_connectors_reload_rotated_tokens_without_restart(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "META_ACCESS_TOKEN=fresh-paid-token\nMETA_GRAPH_ACCESS_TOKEN=fresh-graph-token\n",
        encoding="utf-8",
    )
    code = """
from connectors import meta, organic
meta._ROOT_ENV = r'ENV_PATH'
organic._ROOT_ENV = r'ENV_PATH'
assert meta._access_token() == 'fresh-paid-token'
assert organic._token() == 'fresh-graph-token'
print('ok')
""".replace("ENV_PATH", str(env_file).replace("\\", "\\\\"))
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=ADS, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "ok"

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("sync_engine_under_test", ROOT / "scripts" / "sync_engine.py")
sync_engine = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(sync_engine)


def test_up_to_date_sync_still_reconciles_vault():
    def fake_git(*args, **kwargs):
        if args[:2] == ("status", "--porcelain"):
            return 0, ""
        if args and args[0] == "merge-base":
            return 0, "abc123"
        return 0, ""

    with mock.patch.object(sync_engine, "_rev", return_value="abc123"), \
         mock.patch.object(sync_engine, "_git", side_effect=fake_git), \
         mock.patch.object(sync_engine, "_apply_vault_keys") as apply:
        out = sync_engine.sync(pull=True, push=False, quiet=True)
    assert "up to date" in out
    apply.assert_called_once()

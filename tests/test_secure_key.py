from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("secure_key", ROOT / "scripts" / "secure_key.py")
secure_key = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(secure_key)


def test_publish_never_places_secret_in_git_arguments():
    calls = []
    responses = iter([
        (0, ""),
        (0, "committed"),
        (0, "abcdef123456\n"),
        (0, "pushed"),
        (0, "abcdef123456\n"),
    ])

    def fake_git(*args):
        calls.append(args)
        return next(responses)

    with mock.patch.object(secure_key, "_preflight_sync"), \
         mock.patch.object(secure_key, "_ensure_master"), \
         mock.patch.object(secure_key.getpass, "getpass", return_value="TOP-SECRET-VALUE"), \
         mock.patch.object(secure_key.keyvault, "set_local", return_value=True) as set_local, \
         mock.patch.object(secure_key.keyvault, "put", return_value=True) as put, \
         mock.patch.object(secure_key.keyvault, "receipt"), \
         mock.patch.object(secure_key, "_git", side_effect=fake_git):
        assert secure_key.publish("META_ACCESS_TOKEN") == "abcdef1"

    assert "TOP-SECRET-VALUE" not in repr(calls)
    set_local.assert_called_once_with("META_ACCESS_TOKEN", "TOP-SECRET-VALUE")
    put.assert_called_once_with("META_ACCESS_TOKEN", "TOP-SECRET-VALUE")


def test_main_rejects_machine_identity_key_without_prompt():
    with mock.patch.object(secure_key.sys, "argv", ["secure_key.py", "TELEGRAM_BOT_TOKEN"]), \
         mock.patch.object(secure_key.getpass, "getpass") as prompt:
        assert secure_key.main() == 2
    prompt.assert_not_called()

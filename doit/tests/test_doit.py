"""Pure-logic tests for doit (no browser, no network)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from unittest import mock  # noqa: E402

from doit import agent, envfile, keyscan  # noqa: E402

# A realistic RapidAPI application key shape (msh ... jsn markers).
_SAMPLE_KEY = "a1b2c3d4e5f6mshAbCdEf123456p1a2b3c4jsn0011223344ff"


def test_keyscan_detects_rapidapi_key_in_html_blob():
    html = f"""<input value="{_SAMPLE_KEY}" readonly/>
        <pre>'X-RapidAPI-Key': '{_SAMPLE_KEY}'</pre>"""
    assert keyscan.first_rapidapi_key(html) == _SAMPLE_KEY
    assert keyscan.detect("rapidapi", html) == [_SAMPLE_KEY]


def test_keyscan_no_false_positive_on_prose():
    text = "This message has nothing to do with json or a mesh of api keys at all."
    assert keyscan.find_rapidapi_keys(text) == []
    assert keyscan.first_rapidapi_key(text) == ""
    assert keyscan.first_rapidapi_key(None) == ""


def test_keyscan_dedupes_multiple_occurrences():
    blob = f"{_SAMPLE_KEY} ... later ... {_SAMPLE_KEY}"
    assert keyscan.find_rapidapi_keys(blob) == [_SAMPLE_KEY]


def test_envfile_create_update_append(tmp_path=None):
    import tempfile
    d = tempfile.mkdtemp()
    path = os.path.join(d, ".env")
    try:
        # created
        assert envfile.upsert(path, "RAPIDAPI_KEY", "k1") == "created"
        assert "RAPIDAPI_KEY=k1" in open(path, encoding="utf-8").read()
        # append a second, unrelated key (preserve the first)
        assert envfile.upsert(path, "OTHER", "o1") == "appended"
        body = open(path, encoding="utf-8").read()
        assert "RAPIDAPI_KEY=k1" in body and "OTHER=o1" in body
        # update existing, leave others + comments intact
        with open(path, "a", encoding="utf-8") as f:
            f.write("# a comment\nKEEP=yes\n")
        assert envfile.upsert(path, "RAPIDAPI_KEY", "k2") == "updated"
        body = open(path, encoding="utf-8").read()
        assert "RAPIDAPI_KEY=k2" in body
        assert "RAPIDAPI_KEY=k1" not in body
        assert "# a comment" in body and "KEEP=yes" in body and "OTHER=o1" in body
    finally:
        try:
            os.remove(path)
            os.rmdir(d)
        except OSError:
            pass


def test_channel_resolves_browser_choice():
    from doit import agent
    assert agent._channel("edge") == "msedge"
    assert agent._channel("chrome") == "chrome"
    assert agent._channel("auto") in ("chrome", "msedge")


def test_unknown_provider_is_handled_cleanly():
    from doit import agent
    res = agent.acquire("nonsense")
    assert res["ok"] is False
    assert "provider" in res["error"]


# --- doctor: report the ONE precondition instead of failing a browser run ----

def test_doctor_reports_a_borrowable_session():
    with mock.patch.object(agent.profiles, "user_data_root", return_value="/fake"), \
         mock.patch.object(agent.profiles, "find_profile",
                           return_value=("/fake", "Profile 3", 12)):
        diag = agent.doctor("rapidapi")
    assert diag["ok"] is True
    assert "Profile 3" in diag["message"]


def test_doctor_names_the_one_human_step_when_no_session():
    def _find(domain, channel):
        # Google is signed in; the provider is not — the real-world case.
        return ("/fake", "Profile 3", 67) if "google" in domain else None

    with mock.patch.object(agent.profiles, "user_data_root", return_value="/fake"), \
         mock.patch.object(agent.profiles, "find_profile", side_effect=_find):
        diag = agent.doctor("rapidapi")
    assert diag["ok"] is False
    assert "sessiya YOXDUR" in diag["message"]
    assert "Sign in with Google" in diag["message"]   # the password-free path


def test_acquire_fails_fast_without_a_session_and_never_opens_a_browser():
    with mock.patch.object(agent.profiles, "user_data_root", return_value="/fake"), \
         mock.patch.object(agent.profiles, "find_profile", return_value=None), \
         mock.patch.object(agent.profiles, "snapshot") as snap:
        res = agent.acquire("rapidapi")
    assert res["ok"] is False
    assert res["needs_login"] is True
    snap.assert_not_called()          # no browser work attempted

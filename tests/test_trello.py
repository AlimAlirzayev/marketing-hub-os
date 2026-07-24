import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gateway import permissions, trello


class _Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


class TrelloConnectorTests(unittest.TestCase):
    def test_board_allowlist_accepts_only_xalq_board(self):
        self.assertEqual(trello.board_ref(trello.DEFAULT_BOARD_URL), "RRlLCaSG")
        with self.assertRaises(trello.TrelloError):
            trello.board_ref("https://trello.com/b/another/board")

    def test_doctor_does_not_inspect_credentials_or_live_board(self):
        status = trello.build_status(now=1_800_000_000)
        self.assertEqual(trello.doctor_errors(status), [])
        ready = status["local_readiness"]
        self.assertFalse(ready["credential_presence_checked"])
        self.assertFalse(ready["board_access_checked"])

    def test_manifest_blocks_high_risk_actions(self):
        agent = permissions.get_agent("trello_work_board")
        self.assertIsNotNone(agent)
        blocked = {item.casefold() for item in agent["blocked_actions"]}
        self.assertIn("delete cards, lists, or boards", blocked)
        self.assertIn("invite or remove members", blocked)
        self.assertIn("approval_required", agent["permissions"])

    def test_plan_code_changes_when_write_changes(self):
        first = trello.build_write_plan("move_card", "card-1", {"idList": "list-a"})
        second = trello.build_write_plan("move_card", "card-1", {"idList": "list-b"})
        self.assertNotEqual(first["approval_code"], second["approval_code"])

    def test_blocked_write_types_and_fields_fail_closed(self):
        with self.assertRaises(trello.TrelloError):
            trello.build_write_plan("delete_card", "card-1", {})
        with self.assertRaises(trello.TrelloError):
            trello.build_write_plan("update_card", "card-1", {"closed": True})

    def test_apply_requires_exact_approval_and_keeps_secrets_out_of_audit(self):
        calls = []

        def opener(request, timeout):
            calls.append((request, timeout))
            return _Response({"id": "card-1", "name": "Task"})

        client = trello.TrelloClient("secret-key", "secret-token", opener=opener)
        plan = trello.build_write_plan("move_card", "card-1", {"idList": "list-a"})
        with self.assertRaises(trello.TrelloError):
            trello.apply_plan(client, plan, "wrong")
        self.assertEqual(calls, [])

        original_audit = trello.security.audit_event
        audit_calls = []
        trello.security.audit_event = lambda *args: audit_calls.append(args)
        try:
            result = trello.apply_plan(client, plan, plan["approval_code"])
        finally:
            trello.security.audit_event = original_audit
        self.assertEqual(result["id"], "card-1")
        self.assertEqual(len(calls), 1)
        audit_text = repr(audit_calls)
        self.assertNotIn("secret-key", audit_text)
        self.assertNotIn("secret-token", audit_text)

    def test_snapshot_uses_read_method(self):
        calls = []

        def opener(request, timeout):
            calls.append(request)
            return _Response({"id": "board", "lists": [], "cards": []})

        result = trello.TrelloClient("k", "t", opener=opener).snapshot()
        self.assertEqual(result["id"], "board")
        self.assertEqual(calls[0].method, "GET")

    def test_credentials_use_authorization_header_not_url(self):
        calls = []

        def opener(request, timeout):
            calls.append(request)
            return _Response({"id": "member"})

        trello.TrelloClient("secret-key", "secret-token", opener=opener).request(
            "GET", "/members/me", {"fields": "id"}
        )
        request = calls[0]
        self.assertNotIn("secret-key", request.full_url)
        self.assertNotIn("secret-token", request.full_url)
        self.assertIn('oauth_consumer_key="secret-key"', request.get_header("Authorization"))
        self.assertIn('oauth_token="secret-token"', request.get_header("Authorization"))

    def test_connection_status_waits_without_credentials_and_opens_no_browser(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            status = trello.build_connection_status(now=1_800_000_000)
        self.assertEqual(status["state"], "waiting_for_human_authorization")
        self.assertTrue(status["credential_presence_checked"])
        self.assertFalse(status["browser_opened"])
        self.assertFalse(status["board_write_attempted"])
        self.assertNotIn("secret-key", json.dumps(status))
        self.assertNotIn("secret-token", json.dumps(status))

    def test_offline_status_does_not_inspect_environment(self):
        with mock.patch.object(trello.os, "getenv", side_effect=AssertionError("environment inspected")):
            status = trello.build_connection_status(
                now=1_800_000_000,
                inspect_environment=False,
            )
        self.assertEqual(status["state"], "human_authorization_not_verified")
        self.assertFalse(status["credential_presence_checked"])
        self.assertIsNone(status["credentials_present"])

    def test_connection_probe_reads_identity_and_board_metadata_only(self):
        calls = []

        def opener(request, timeout):
            calls.append(request)
            if request.full_url.endswith("/members/me?fields=id"):
                return _Response({"id": "member"})
            return _Response(
                {
                    "name": "Xalq Insurance",
                    "url": trello.DEFAULT_BOARD_URL,
                    "closed": False,
                    "dateLastActivity": "2026-07-21T10:00:00.000Z",
                }
            )

        client = trello.TrelloClient("k", "t", opener=opener)
        status = trello.build_connection_status(client, now=1_800_000_000)
        self.assertEqual(status["state"], "connected_governed")
        self.assertEqual([request.method for request in calls], ["GET", "GET"])
        self.assertNotIn("cards", " ".join(request.full_url for request in calls))

        with tempfile.TemporaryDirectory() as tmp:
            old_json = trello.CONNECTION_STATUS_PATH
            old_report = trello.CONNECTION_REPORT_PATH
            try:
                trello.CONNECTION_STATUS_PATH = Path(tmp) / "status.json"
                trello.CONNECTION_REPORT_PATH = Path(tmp) / "status.md"
                json_path, report_path = trello.save_connection_status(status)
                rendered = json_path.read_text(encoding="utf-8") + report_path.read_text(encoding="utf-8")
            finally:
                trello.CONNECTION_STATUS_PATH = old_json
                trello.CONNECTION_REPORT_PATH = old_report
        self.assertNotIn("oauth_consumer", rendered)
        self.assertNotIn("secret", rendered)


if __name__ == "__main__":
    unittest.main()

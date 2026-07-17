import json
import unittest

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


if __name__ == "__main__":
    unittest.main()

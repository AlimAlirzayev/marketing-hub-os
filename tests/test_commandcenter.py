"""Guards for the live command center (gateway.commandcenter).

flow_state() must turn real sense events into the right lit-up nodes, so the
cockpit map reflects what the OS is actually doing. sense is stubbed — no
services, no network.
"""

import unittest
from unittest.mock import patch

from gateway import commandcenter as cc


class Classify(unittest.TestCase):
    def test_event_kinds_map_to_nodes(self):
        cases = {
            ("mic", "telegram took the mic -> job #1"): "ch_telegram",
            ("mic", "codex took the mic -> job #3"): "ch_codex",
            ("schedule", "due -> job #1"): "ch_schedule",
            ("job", "#1 done (panel)"): "queue",
            ("security", "rejected non-owner"): "checkpoint",
            ("credential", "RAPIDAPI_KEY acquired"): "m_creds",
            ("llm", "fanout:3x->groq"): "m_fanout",
            ("llm", "content:linkedin->groq"): "m_content",
            ("llm", "council:plan"): "m_council",
            ("llm", "browser:gemini"): "m_browser",
            ("llm", "google-search-grounded:gemini"): "m_research",
            ("llm", "chat:gemini:gemini-2.5-flash"): "m_converse",
            ("sync", "engine updated"): "supervisor",
        }
        for (kind, summary), node in cases.items():
            self.assertEqual(cc._classify({"kind": kind, "summary": summary}), node,
                             f"{kind}/{summary}")


class FlowState(unittest.TestCase):
    def _snap(self, **over):
        base = {
            "ts": 1000, "env": {"RAPIDAPI_KEY": "SET (len=50)"},
            "queue": {"queued": 1, "running": 1, "done": 40, "error": 0,
                      "awaiting_approval": 2, "rejected": 0},
            "memory": {"entries": 12}, "schedules": {"active": 3},
            "llm": {"calls_today": 25, "cost_usd_today": 0.0,
                    "by_model": {"groq/llama-3.3-70b-versatile": 24}},
            "git": {"branch": "master", "dirty": False},
            "contradictions": [],
        }
        base.update(over)
        return base

    def test_kpis_and_topology(self):
        import time
        now = time.time()
        events = [
            {"ts": now - 3, "kind": "llm", "summary": "fanout:3x->groq"},
            {"ts": now - 120, "kind": "job", "summary": "#1 done"},
        ]
        with patch.object(cc.sense, "snapshot", return_value=self._snap()), \
             patch.object(cc.sense, "recent", return_value=events):
            d = cc.flow_state()

        self.assertEqual(d["kpis"]["running"], 1)
        self.assertEqual(d["kpis"]["parked"], 2)
        # fanout fired 3s ago -> active; queue fired 120s ago -> idle
        nodes = {n["id"]: n for n in d["nodes"]}
        self.assertEqual(nodes["m_fanout"]["state"], "active")
        self.assertEqual(nodes["queue"]["state"], "idle")
        # 2 parked approvals -> checkpoint warns and operator is needed
        self.assertEqual(nodes["checkpoint"]["state"], "warn")
        self.assertTrue(d["health"]["needs_operator"])
        # every node is present and every edge references real nodes
        ids = set(nodes)
        for a, b in d["edges"]:
            self.assertIn(a, ids)
            self.assertIn(b, ids)

    def test_missing_key_surfaces_on_gateway(self):
        snap = self._snap(env={"RAPIDAPI_KEY": "MISSING"})
        with patch.object(cc.sense, "snapshot", return_value=snap), \
             patch.object(cc.sense, "recent", return_value=[]):
            d = cc.flow_state()
        nodes = {n["id"]: n for n in d["nodes"]}
        self.assertEqual(nodes["gateway"]["state"], "warn")
        self.assertIn("RAPIDAPI_KEY", d["health"]["missing_keys"])


if __name__ == "__main__":
    unittest.main()

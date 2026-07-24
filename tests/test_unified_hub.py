import unittest
from pathlib import Path

from gateway import commandcenter, panel


ROOT = Path(__file__).resolve().parent.parent


class UnifiedHubTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.portal = (ROOT / "hub" / "templates" / "portal.html").read_text(encoding="utf-8")
        cls.hub_app = (ROOT / "hub" / "app.py").read_text(encoding="utf-8")

    def test_hub_exposes_first_class_workdesk_observation_and_council(self):
        self.assertIn("İş masası", (ROOT / "services.json").read_text(encoding="utf-8"))
        self.assertIn('data-key="_observation"', self.portal)
        self.assertIn('data-key="_council"', self.portal)
        self.assertIn("function showObservation", self.portal)
        self.assertIn("function showCouncil", self.portal)
        self.assertIn("/?open=workdesk", self.hub_app)
        self.assertIn("/?open=observation", self.hub_app)
        self.assertIn("/?open=council", self.hub_app)

    def test_council_ui_calls_consultation_api_not_council_command(self):
        self.assertIn("/api/council/runs", self.portal)
        self.assertNotIn("/council ", self.portal)
        self.assertIn("YALNIZ KONSULTASİYA", self.portal)

    def test_panel_has_embedded_mode_without_removing_standalone_ui(self):
        self.assertNotIn('body.embedded .topbar{display:none}', panel._HTML)
        self.assertIn('body.embedded .topbar .brand', panel._HTML)
        self.assertIn('body.embedded .tabs{width:100%', panel._HTML)
        self.assertIn('if(_qs.get("embed")==="1")', panel._HTML)
        self.assertIn('class="topbar"', panel._HTML)

    def test_live_topology_reflects_current_crew_authority(self):
        nodes = {node[0]: node[1] for node in commandcenter._NODES}
        self.assertEqual(nodes["claude_router"], "Claude Brain / Router")
        self.assertEqual(nodes["m_crew"], "CrewAI Workforce")
        self.assertEqual(nodes["synthesis"], "Claude Synthesis")
        self.assertIn(("claude_router", "summon"), commandcenter._EDGES)
        self.assertIn(("summon", "m_crew"), commandcenter._EDGES)
        self.assertIn(("m_crew", "studios"), commandcenter._EDGES)
        self.assertIn(("studios", "synthesis"), commandcenter._EDGES)
        self.assertEqual(commandcenter._classify({"kind": "llm", "summary": "crew"}), "m_crew")

    def test_panel_openapi_schema_builds(self):
        schema = panel.app.openapi()
        self.assertIn("/api/flow", schema["paths"])


if __name__ == "__main__":
    unittest.main()

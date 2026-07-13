"""The 8501 Streamlit monolith is retired — its 3 modules must live on.

Migration map (2026-07-13):
  Gündəlik Hesabat  → ads-studio  /briefing (+ /api/briefing*)
  Agent Radar       → gateway.panel /api/radar (Mühərrik tab section)
  Bilik Bazası (RAG)→ gateway.rag_server, own service on 8895

These tests pin each new home so a regression cannot quietly undo the move,
and pin the retirement itself (no hq service, no root Streamlit entrypoint).
"""

import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


class RagServiceTests(unittest.TestCase):
    def _mod(self):
        from gateway import rag_server
        return rag_server

    def test_health_reports_doc_count(self):
        h = self._mod().health()
        self.assertTrue(h["ok"])
        self.assertIsInstance(h["docs"], int)

    def test_empty_document_rejected(self):
        m = self._mod()
        resp = m.add_doc(m.NewDoc(title="x", text="   "))
        self.assertEqual(resp.status_code, 400)

    def test_docs_listing_shape(self):
        docs = json.loads(self._mod().list_docs().body)
        self.assertIsInstance(docs, list)
        for d in docs:
            self.assertIn("title", d)
            self.assertIn("preview", d)

    def test_ui_is_azerbaijani_knowledge_base(self):
        html = self._mod().index()
        self.assertIn("Bilik Bazas", html)
        self.assertIn("/api/ask", html)

    def test_registered_as_service_8895(self):
        with open(os.path.join(ROOT, "services.json"), encoding="utf-8") as f:
            reg = json.load(f)
        rag = next(s for s in reg["services"] if s["key"] == "rag")
        self.assertEqual(rag["port"], 8895)
        self.assertEqual(rag["target"], "gateway.rag_server:app")
        self.assertTrue(rag["hub_show"])


class PanelRadarTests(unittest.TestCase):
    def test_radar_endpoint_returns_both_scans(self):
        from gateway import panel
        body = json.loads(panel.radar(refresh=0).body)
        self.assertIn("scan", body)
        self.assertIn("hf", body)
        self.assertIn("system_fit_summary", body["scan"])
        self.assertIn("ranked_opportunities", body["hf"])

    def test_panel_ui_has_radar_section(self):
        from gateway import panel
        self.assertIn('id="radar"', panel._HTML)
        self.assertIn("loadRadar", panel._HTML)


class BriefingMigrationTests(unittest.TestCase):
    def test_view_model_survives_dead_sources(self):
        """Collectors may all fail — the view model must still render honestly
        (ƏLÇATMAZ badges), never crash, never invent numbers."""
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import daily_briefing as briefing
        dead = {"status": "error", "detail": "test"}
        vm = briefing.build_view_model(dict(dead), dict(dead), dict(dead))
        for key in ("sources", "kpis", "actions", "markdown", "generated_label"):
            self.assertIn(key, vm)
        self.assertTrue(all(s["status"] in ("live", "demo", "missing", "error")
                            for s in vm["sources"]))

    def test_collectors_prefer_each_apps_venv(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import daily_briefing as briefing
        py = briefing._app_python(briefing.ADS_DIR)
        self.assertTrue(py.endswith(("python.exe", "python")) or py == sys.executable)

    def test_ads_studio_serves_briefing(self):
        src = open(os.path.join(ROOT, "ads-studio", "app.py"), encoding="utf-8").read()
        for route in ("/briefing", "/api/briefing", "/api/briefing/save", "/api/briefing/archive"):
            self.assertIn(f'"{route}', src, f"ads-studio route itib: {route}")
        self.assertTrue(os.path.isfile(
            os.path.join(ROOT, "ads-studio", "templates", "briefing.html")))


class RetirementTests(unittest.TestCase):
    def test_hq_service_is_gone(self):
        with open(os.path.join(ROOT, "services.json"), encoding="utf-8") as f:
            reg = json.load(f)
        self.assertNotIn("hq", {s["key"] for s in reg["services"]})
        self.assertNotIn(8501, {s["port"] for s in reg["services"]})

    def test_streamlit_monolith_files_removed(self):
        for name in ("app.py", "briefing_panel.py", "creative_studio.py"):
            self.assertFalse(os.path.exists(os.path.join(ROOT, name)),
                             f"{name} qayıdıb — 8501 monoliti təqaüdə göndərilib!")


if __name__ == "__main__":
    unittest.main()

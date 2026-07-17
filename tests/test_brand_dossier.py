"""Offline tests for the Brand Dossier engine (scripts/brand_dossier.py).

Everything here runs on the bundled DEMO fixtures or pure render functions —
no network, no keys. Live behavior is covered only through mocks (the
opportunity synthesis must ride the smart tier, radar-style).
"""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import brand_dossier as bd

_TITLES = ["BREND MÖVQEYİ", "RƏQİB HƏRƏKƏTLƏRİ", "BAZAR YENİLİKLƏRİ", "FÜRSƏT BUCAQLARI"]
_LABELS = {"CANLI", "DEMO", "ƏLÇATMAZ"}


def _dry_run(out: Path) -> dict:
    return bd.run(dry_run=True, out_dir=out)


class DryRunPipeline(unittest.TestCase):
    def test_writes_all_three_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            summary = _dry_run(out)
            self.assertTrue((out / ("dossier_%s.md" % summary["generated"])).exists())
            self.assertTrue((out / "dossier_latest.json").exists())
            self.assertTrue((out / "canvas_paste.txt").exists())
            self.assertEqual(summary["mode"], "dry-run")

    def test_dry_run_touches_no_network(self):
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(bd, "_gemini_grounded") as grounded, \
                 mock.patch.object(bd, "_fetch_site") as fetch, \
                 mock.patch.object(bd.requests, "get") as rget, \
                 mock.patch.object(bd.requests, "post") as rpost:
                _dry_run(Path(td))
            grounded.assert_not_called()
            fetch.assert_not_called()
            rget.assert_not_called()
            rpost.assert_not_called()

    def test_dry_run_is_labeled_demo_never_canli(self):
        # Fixtures are synthetic: claiming CANLI would be fabricated data.
        with tempfile.TemporaryDirectory() as td:
            summary = _dry_run(Path(td))
            for _title, status in summary["sections"]:
                self.assertEqual(status, "DEMO")
            canvas = (Path(td) / "canvas_paste.txt").read_text(encoding="utf-8")
            self.assertIn("DEMO", canvas)
            self.assertNotIn("rejim: CANLI", canvas)


class ExportSchema(unittest.TestCase):
    """dossier_latest.json is a stable contract (docs/BRAND_DOSSIER.md, v1)."""

    def _export(self) -> dict:
        with tempfile.TemporaryDirectory() as td:
            _dry_run(Path(td))
            raw = (Path(td) / "dossier_latest.json").read_text(encoding="utf-8")
        return json.loads(raw)

    def test_top_level_contract(self):
        data = self._export()
        for key in ("schema_version", "generated_at", "mode", "brand", "competitors",
                    "models", "section_status", "brand_position", "competitor_moves",
                    "market_news", "opportunity_angles", "sources", "failures"):
            self.assertIn(key, data, key)
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["brand"], "Xalq Sığorta")
        self.assertRegex(data["generated_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")

    def test_section_shapes(self):
        data = self._export()
        # brand_position is an object with items + summary; the rest are arrays.
        self.assertIsInstance(data["brand_position"], dict)
        self.assertIn("items", data["brand_position"])
        self.assertIn("summary", data["brand_position"])
        for field in ("competitor_moves", "market_news", "opportunity_angles"):
            self.assertIsInstance(data[field], list)
            self.assertTrue(data[field], "%s must not be empty in demo mode" % field)
        all_items = (data["brand_position"]["items"] + data["competitor_moves"]
                     + data["market_news"] + data["opportunity_angles"])
        for item in all_items:
            for key in ("text", "source", "date", "label"):
                self.assertIn(key, item)
            self.assertIn(item["label"], _LABELS)

    def test_sources_flat_list_has_section_and_url(self):
        data = self._export()
        self.assertTrue(data["sources"])
        for src in data["sources"]:
            self.assertTrue(src["url"].startswith("https://"))
            self.assertIn(src["section"], ("brand_position", "competitor_moves",
                                           "market_news", "opportunity_angles"))
            self.assertIn("date", src)

    def test_status_values_are_honest_labels(self):
        data = self._export()
        for status in data["section_status"].values():
            self.assertIn(status, _LABELS)


class FactItemParsing(unittest.TestCase):
    def test_source_and_date_extracted(self):
        items = bd._parse_items(
            "- Kampaniya elan olunub (mənbə: xalqsigorta.az, 2026-07-08)\n"
            "- ƏLÇATMAZ: heç nə tapılmadı", "CANLI")
        self.assertEqual(items[0]["source"], "xalqsigorta.az")
        self.assertEqual(items[0]["date"], "2026-07-08")
        self.assertIsNone(items[1]["source"])
        self.assertIn("ƏLÇATMAZ", items[1]["text"])

    def test_every_demo_fact_carries_source_or_unavailable_mark(self):
        for key, fix in bd._DEMO_SECTIONS.items():
            for line in fix["body"].splitlines():
                if not line.strip().startswith("- "):
                    continue
                self.assertTrue(
                    "(mənbə:" in line or "ƏLÇATMAZ" in line or "(siqnal:" in line,
                    "unlabeled demo fact in %s: %r" % (key, line))


class MarkdownDossier(unittest.TestCase):
    def test_markdown_structure_and_labels(self):
        with tempfile.TemporaryDirectory() as td:
            summary = _dry_run(Path(td))
            md = (Path(td) / ("dossier_%s.md" % summary["generated"])).read_text(encoding="utf-8")
        self.assertIn("# Brend Dosyesi — Xalq Sığorta", md)
        for title in _TITLES:
            self.assertIn(title, md)
        self.assertIn("[DEMO]", md)
        self.assertIn("Mənbələr", md)
        self.assertRegex(md, r"\d{4}-\d{2}-\d{2}")
        self.assertIn("ƏLÇATMAZ", md)  # honesty escape hatch present


class CanvasSummaryBlock(unittest.TestCase):
    def test_within_limit_and_has_all_sections(self):
        with tempfile.TemporaryDirectory() as td:
            _dry_run(Path(td))
            canvas = (Path(td) / "canvas_paste.txt").read_text(encoding="utf-8")
        self.assertLessEqual(len(canvas), 2500)
        for title in _TITLES:
            self.assertIn(title, canvas)
        self.assertRegex(canvas, r"\d{4}-\d{2}-\d{2}")

    def test_oversized_input_is_trimmed_to_limit(self):
        huge = "\n".join("- çox uzun fakt %d " % i + "x" * 300 for i in range(40))
        dossier = {
            "generated": "2026-07-16", "mode": "live", "brand": bd.BRAND,
            "sections": [{"key": k, "title": t, "status": "CANLI",
                          "body": huge, "sources": []}
                         for k, t in zip(("brand", "competitors", "market", "opportunities"),
                                         _TITLES)],
        }
        canvas = bd.build_canvas_paste(dossier)
        self.assertLessEqual(len(canvas), 2500)
        for title in _TITLES:
            self.assertIn(title, canvas)


class LiveGuards(unittest.TestCase):
    def test_ground_rules_forbid_fabrication_and_allow_unavailable(self):
        rules = bd._GROUND_RULES
        self.assertIn("UYDURMA", rules.upper())
        self.assertIn("ƏLÇATMAZ", rules)
        self.assertIn("mənbə", rules)

    def test_opportunity_prompt_forbids_fabrication(self):
        self.assertIn("uydurma", bd._OPPORTUNITY_SYSTEM)

    def test_opportunity_synthesis_uses_smart_tier(self):
        # Judgement work rides the smart tier (Claude-first) — radar pattern.
        sections = [{"key": "brand", "title": "BREND MÖVQEYİ", "status": "CANLI",
                     "body": "- fakt (mənbə: x.az, 2026-07-01)", "sources": []}]
        with mock.patch("llm_router.complete",
                        return_value=("- bucaq (siqnal: BREND MÖVQEYİ)", "claude")) as rc:
            body, model = bd._synthesize_opportunities(sections)
        self.assertEqual(rc.call_args.kwargs.get("tier"), "smart")
        self.assertEqual(model, "claude")
        self.assertTrue(body.startswith("- "))

    def test_collection_helpers_use_no_llm_router(self):
        # Mechanical collection must never spend the premium brain.
        import inspect
        for name in ("_fetch_site", "_collect_site_signals", "_gemini_grounded"):
            src = inspect.getsource(getattr(bd, name))
            self.assertNotIn("llm_router", src, "%s must not call llm_router" % name)

    def test_gemini_key_travels_in_header_not_url(self):
        # The key must never appear in a URL (URLs leak into error messages/logs).
        import inspect
        src = inspect.getsource(bd._gemini_grounded)
        self.assertIn("x-goog-api-key", src)
        self.assertNotIn("?key=", src)


if __name__ == "__main__":
    unittest.main()

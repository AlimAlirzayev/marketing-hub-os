"""Tests for MediaForge — the creative-director brain and pipeline.

These run fully offline (use_llm=False) so they are deterministic and never
depend on an LLM key or network. The pipeline test redirects output into a temp
directory so it never pollutes the real campaigns folder.
"""

import json
import tempfile
import unittest
from pathlib import Path

from mediaforge import director, knowledge, models, pipeline


class ParseTests(unittest.TestCase):
    def test_extracts_model_duration_category_platform(self):
        r = director.parse_request(
            "mənə seedance 2.5 modeli ilə 10 saniyəlik səyahət sığortası üçün promo video hazırla"
        )
        self.assertIn("seedance", (r["model_phrase"] or "").casefold())
        self.assertEqual(r["duration_s"], 10)
        self.assertEqual(r["category"], "travel")
        self.assertEqual(r["platform"], "meta")
        self.assertEqual(r["aspect"], "9:16")
        self.assertEqual(r["language"], "az")

    def test_platform_and_category_variants(self):
        r = director.parse_request("kling ilə 8 saniyəlik KASKO promosu tiktok üçün")
        self.assertEqual(r["category"], "auto")
        self.assertEqual(r["platform"], "tiktok")
        self.assertEqual(r["duration_s"], 8)


class ModelResolverTests(unittest.TestCase):
    def test_seedance_2_5_maps_to_real_model_with_note(self):
        res = models.resolve("seedance 2.5", want_duration=10)
        self.assertEqual(res["model_id"], "i2v-seedance-2-0-reference-i2v-enhancor")
        self.assertTrue(any("2.5" in n for n in res["notes"]))  # substitution surfaced
        self.assertEqual(res["duration_s"], 10)

    def test_unsupported_duration_is_snapped_and_flagged(self):
        res = models.resolve("sora", want_duration=10)  # sora supports 4,8,12
        self.assertIn(res["duration_s"], (8, 12))
        self.assertTrue(any("dəstəkləmir" in n for n in res["notes"]))

    def test_unknown_alias_defaults_and_notes(self):
        res = models.resolve("banana-cam", want_duration=10)
        self.assertEqual(res["model_id"], "i2v-seedance-2-0-reference-i2v-enhancor")
        self.assertTrue(res["notes"])

    def test_second_variant_is_a_different_real_model(self):
        res = models.resolve("seedance 2.5")
        self.assertIn(res["partner_id"], models.CATALOG)
        self.assertNotEqual(res["partner_id"], res["model_id"])


class DirectorTests(unittest.TestCase):
    def test_deterministic_brief_is_schema_valid(self):
        out = director.direct(
            "seedance 2.5 ilə 10 saniyəlik səyahət sığortası promo", use_llm=False
        )
        self.assertEqual(out["meta"]["engine"], "deterministic")
        self.assertTrue(out["meta"]["valid"])
        self.assertEqual(out["meta"]["validation_errors"], [])
        brief = out["brief"]
        # brand DNA is reused, not invented
        self.assertEqual(brief["brand"]["name"], "Xalq Sigorta")
        self.assertEqual(brief["format"]["aspect"], "9:16")
        self.assertEqual(len(brief["storyboard"]), 4)
        # no invented prices/dates leak into offer
        self.assertEqual(brief["offer"]["terms"], [])
        self.assertIn("təsdiq", brief["offer"]["dates"])

    def test_validate_brief_catches_missing_keys(self):
        errors = director.validate_brief({"version": "1"})
        self.assertTrue(errors)
        self.assertTrue(any("missing top-level key" in e for e in errors))

    def test_matches_schema_required_keys(self):
        schema_path = (
            Path(__file__).resolve().parent.parent
            / "video-studio" / "generative_ads" / "brief.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        out = director.direct("kling ilə 5 saniyəlik ev sığortası promo", use_llm=False)
        for key in schema["required"]:
            self.assertIn(key, out["brief"], f"brief missing required schema key: {key}")


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_campaigns = pipeline.CAMPAIGNS
        self._orig_log = pipeline.RUN_LOG
        pipeline.CAMPAIGNS = Path(self._tmp.name) / "campaigns"
        pipeline.RUN_LOG = Path(self._tmp.name) / "runs.jsonl"

    def tearDown(self):
        pipeline.CAMPAIGNS = self._orig_campaigns
        pipeline.RUN_LOG = self._orig_log
        self._tmp.cleanup()

    def test_pipeline_writes_full_package(self):
        pkg = pipeline.create(
            "seedance 2.5 ilə 10 saniyəlik səyahət sığortası promo", use_llm=False
        )
        folder = pipeline.CAMPAIGNS / pkg["slug"]
        self.assertTrue((folder / "brief.json").exists())
        self.assertTrue((folder / "prompts" / "compiled-flora-prompt.md").exists())
        self.assertTrue((folder / "storyboard-board.svg").exists())
        self.assertTrue((folder / "package.json").exists())
        # governance: never auto-fire, credits not spent silently
        self.assertFalse(pkg["generation"]["can_autofire"])
        self.assertEqual(pkg["generation"]["status"], "ready_for_generation")
        self.assertTrue(pkg["artifacts"]["compiled_ok"])
        # board is real SVG
        svg = (folder / "storyboard-board.svg").read_text(encoding="utf-8")
        self.assertIn("<svg", svg)
        self.assertIn("OVERLAY", svg)

    def test_compiled_prompt_contains_model_and_no_fake_price(self):
        pkg = pipeline.create("runway ilə 10s sağlamlıq sığortası promo", use_llm=False)
        compiled = (
            pipeline.CAMPAIGNS / pkg["slug"] / "prompts" / "compiled-flora-prompt.md"
        ).read_text(encoding="utf-8")
        self.assertIn("i2v-runway-gen-4.5", compiled)


class KnowledgeTests(unittest.TestCase):
    def test_category_resolution(self):
        self.assertEqual(knowledge.category_for("səyahət sığortası"), "travel")
        self.assertEqual(knowledge.category_for("kasko avtomobil"), "auto")
        self.assertEqual(knowledge.category_for("tamamilə naməlum şey"), "generic")

    def test_director_prompt_injects_framework_and_technique(self):
        prompt = knowledge.director_system_prompt("travel")
        self.assertIn("Before — After — Bridge", prompt)
        self.assertIn("camera", prompt.casefold())
        self.assertIn("overlay", prompt.casefold())


if __name__ == "__main__":
    unittest.main()

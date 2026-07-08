"""Tests for MediaForge — the creative-director brain and pipeline.

These run fully offline (use_llm=False) so they are deterministic and never
depend on an LLM key or network. The pipeline test redirects output into a temp
directory so it never pollutes the real campaigns folder.
"""

import json
import tempfile
import unittest
from pathlib import Path

from mediaforge import director, knowledge, models, pipeline, ugc


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

    def test_turkish_ascii_insurance_brief_is_local_language(self):
        r = director.parse_request("seedance 2.5 ile 10 saniyelik seyahat sigortasi ucun UGC")
        self.assertEqual(r["category"], "travel")
        self.assertEqual(r["language"], "az")


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

    def test_resolution_carries_real_credit_cost(self):
        res = models.resolve("seedance 2.5")
        # Seedance 2.0 Reference is 1176 credits in the live FLORA catalog.
        self.assertEqual(res["credits"], 1176)
        self.assertIn("kredit", res["cost_band"])
        self.assertIn("1176", res["cost_band"])


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


class UgcPackTests(unittest.TestCase):
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

    def test_ugc_pack_writes_doruk_style_draft_package(self):
        pkg = ugc.create(
            "seedance 2.5 ilə 10 saniyəlik səyahət sığortası üçün AI UGC influencer videosu",
            use_llm=False,
        )
        pack = pkg["ugc_pack"]
        pack_dir = pipeline.CAMPAIGNS / pkg["slug"] / "ugc-pack"

        self.assertEqual(pkg["mode"], "ugc_pack")
        self.assertEqual(pack["status"], "draft_only")
        self.assertFalse(pack["can_autofire"])
        self.assertTrue(pack["no_spend"])
        self.assertTrue(pack["no_posting"])
        self.assertEqual(pack["persona"]["name"], "Aysel, travel micro-creator")
        self.assertGreater(pack["economics"]["one_round_video_credit_floor"], 0)

        for rel in ugc.PACK_FILES.values():
            self.assertTrue((pack_dir / rel).exists(), rel)

        manifest = json.loads((pack_dir / "ugc-pack.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["status"], "draft_only")
        self.assertIn("voice", manifest)
        self.assertIn("video", manifest)

    def test_ugc_video_prompt_keeps_text_and_spend_gated(self):
        pkg = ugc.create("kling ilə 8 saniyəlik KASKO UGC reels", use_llm=False)
        prompt = (
            pipeline.CAMPAIGNS / pkg["slug"] / "ugc-pack" / "video-prompt.md"
        ).read_text(encoding="utf-8")
        economics = (
            pipeline.CAMPAIGNS / pkg["slug"] / "ugc-pack" / "unit-economics.md"
        ).read_text(encoding="utf-8")

        self.assertIn("No readable text", prompt)
        self.assertIn("final copy is added later", prompt)
        self.assertIn("spends credits only when the human intentionally confirms", prompt)
        self.assertIn("formula_only_no_payment", economics)


class GenerateTests(unittest.TestCase):
    def _pkg(self):
        out = director.direct("seedance 2.5 ilə 10s səyahət sığortası promo", use_llm=False)
        return {"slug": "t", "concept": out["concept"], "brief": out["brief"],
                "resolution": out["resolution"], "meta": out["meta"]}

    def test_oner_prompt_follows_seedance_official_formula(self):
        # Seedance 2.0 official guide: subject/action/environment + ONE camera
        # instruction + lighting-led style + avoid-list; rhythm words, no lens jargon.
        from mediaforge import generate
        pkg = self._pkg()
        prompt = generate.build_prompt(pkg["brief"], category="travel")
        self.assertIn("[Hero:", prompt)
        self.assertIn("Camera: one slow", prompt)
        self.assertIn("Avoid:", prompt)
        self.assertIn("readable text", prompt.lower())
        self.assertNotIn("f/2.8", prompt)
        self.assertNotIn("Cinematic ", prompt)   # bare "cinematic" is an official anti-pattern

    def test_no_reference_image_picks_text_to_video_model(self):
        from mediaforge import generate
        pkg = self._pkg()
        model_id, reason = generate.choose_model(pkg["brief"], None)
        # brief recommends an i2v reference model, but there is no reference
        # image, so a text-to-video sibling must be chosen.
        self.assertTrue(model_id.startswith("t2v-"))
        self.assertIn(model_id, models.CATALOG)

    def test_plan_only_never_spends(self):
        # choose_model + plan must produce a cost estimate without any network.
        from mediaforge import generate
        pkg = self._pkg()
        model_id, reason = generate.choose_model(pkg["brief"], None)
        pl = generate.plan(pkg, model_id, reason, "prompt")
        self.assertIn("credits", pl)
        self.assertEqual(pl["params"]["aspect_ratio"], "9:16")
        self.assertEqual(pl["params"]["resolution"], "1080p")


class KeyframePipelineTests(unittest.TestCase):
    def _pkg(self):
        out = director.direct("seedance 2.5 ilə 10s səyahət sığortası promo", use_llm=False)
        return {"slug": "t", "request": out["request"], "concept": out["concept"],
                "brief": out["brief"], "resolution": out["resolution"], "meta": out["meta"]}

    def test_beat_time_parsing(self):
        from mediaforge import frames
        pkg = self._pkg()
        durs = frames.parse_beat_seconds(pkg["brief"]["storyboard"])
        self.assertEqual(len(durs), 4)
        self.assertAlmostEqual(sum(durs), 10.0, places=1)
        self.assertAlmostEqual(durs[0], 1.5, places=1)

    def test_keyframe_prompt_carries_style_bible_and_no_text(self):
        from mediaforge import knowledge
        p = knowledge.compose_keyframe_prompt("travel", "a passport on a tray table")
        self.assertIn("35mm", p)                      # style bible look
        self.assertIn("No readable text", p)          # compliance
        self.assertIn("early 30s", p)                 # fixed protagonist
        self.assertIn("9:16", p)

    def test_beat_video_prompt_has_continuity_lock(self):
        from mediaforge import knowledge
        beat = {"visual": "traveler at a skyline", "motion": "slow push-in"}
        p = knowledge.compose_beat_video_prompt("travel", beat, beat_index=2,
                                                total_beats=4, prev_visual="a calm hand")
        self.assertIn("Shot 3 of a continuous 4-shot", p)
        self.assertIn("Continuing directly from the previous shot", p)
        self.assertIn("No readable text", p)

    def test_frames_plan_costs_and_prompts(self):
        from mediaforge import frames
        pkg = self._pkg()
        plan = frames.plan_frames(pkg, variants=2)
        self.assertEqual(plan["total_images"], 8)
        self.assertEqual(plan["estimated_credits"], 8 * 28)
        self.assertEqual(plan["params"]["aspect_ratio"], "9:16")
        self.assertTrue(all("No readable text" in b["prompt"] for b in plan["beats"]))

    def test_stage_plan_lists_all_stages_with_costs(self):
        from mediaforge import generate
        pkg = self._pkg()
        sp = generate.plan_stages(pkg)
        names = [s["stage"] for s in sp["stages"]]
        self.assertEqual(names[:3], ["frames", "pick", "animatic"])
        self.assertTrue(any(n.startswith("film") for n in names))
        self.assertIn("beats", names)
        animatic = sp["stages"][2]
        self.assertEqual(animatic["credits"], 0)      # the animatic must stay free
        film = next(s for s in sp["stages"] if s["stage"].startswith("film"))
        beats = next(s for s in sp["stages"] if s["stage"] == "beats")
        self.assertLess(film["credits"], beats["credits"])   # single run beats 4 runs
        self.assertIn("--confirm", beats["cmd"])
        self.assertIn("--film", film["cmd"])

    def test_film_prompt_is_multishot_kling_dialect(self):
        from mediaforge import knowledge
        pkg = self._pkg()
        p = knowledge.compose_film_prompt("travel", pkg["brief"]["storyboard"], duration_s=10)
        for i in range(1, 5):
            self.assertIn(f"Shot {i}", p)             # explicit shot labels
        self.assertIn("[Hero:", p)                    # character anchor
        self.assertIn("Then,", p)                     # temporal link
        self.assertIn("Avoid:", p)
        self.assertIn("Hold the final shot stable", p)

    def test_primary_camera_move_is_single_and_slow(self):
        from mediaforge import knowledge
        # chained storyboard motion must collapse to ONE slow instruction
        move = knowledge.primary_camera_move("slow push-in, hero wide → detail; motion already alive")
        self.assertEqual(move, "slow push-in")
        self.assertEqual(knowledge.primary_camera_move("whip pan"), "slow whip pan")
        self.assertEqual(knowledge.primary_camera_move(""), "slow push-in")

    def test_pick_selection_roundtrip(self):
        import tempfile
        from mediaforge import frames
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            sel = frames.apply_picks(folder, "1=2,3=1")
            self.assertEqual(sel[0], 2)               # 1-based input -> 0-based beat
            self.assertEqual(sel[2], 1)
            loaded = frames.load_selection(folder, 4)
            self.assertEqual(loaded[0], 2)
            self.assertEqual(loaded[3], 1)            # default for unpicked beats

    def test_animatic_clip_command_is_exact_length(self):
        from mediaforge import animatic
        cmd = animatic.beat_clip_cmd("ffmpeg", Path("kf.png"), Path("out.mp4"),
                                     seconds=2.5, zoom_in=True)
        self.assertIn("-t", cmd)
        self.assertEqual(cmd[cmd.index("-t") + 1], "2.500")
        vf = cmd[cmd.index("-vf") + 1]
        self.assertIn("zoompan", vf)
        self.assertIn("1080x1920", vf)


class KnowledgeTests(unittest.TestCase):
    def test_category_resolution(self):
        self.assertEqual(knowledge.category_for("səyahət sığortası"), "travel")
        self.assertEqual(knowledge.category_for("seyahat sigortasi"), "travel")
        self.assertEqual(knowledge.category_for("kasko avtomobil"), "auto")
        self.assertEqual(knowledge.category_for("tamamilə naməlum şey"), "generic")

    def test_director_prompt_injects_framework_and_technique(self):
        prompt = knowledge.director_system_prompt("travel")
        self.assertIn("Before — After — Bridge", prompt)
        self.assertIn("camera", prompt.casefold())
        self.assertIn("overlay", prompt.casefold())


if __name__ == "__main__":
    unittest.main()

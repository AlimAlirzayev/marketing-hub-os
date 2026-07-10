"""Tests for mediaforge.finish — the free deterministic finishing layer.

Kept in a separate file from test_mediaforge.py on purpose: finishing is its
own layer, and the main test file is under active parallel development.

Pure-logic tests only (no ffmpeg execution, no network): overlay planning from
the brief, filtergraph assembly, path escaping, canvas resolution, master
picking. The one integration test runs only if the portable ffmpeg exists.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mediaforge import finish  # noqa: E402


def _brief(overlays: list[str] | None = None, aspect: str = "9:16") -> dict:
    """A minimal brief with the fields finish.py consumes."""
    ovs = overlays if overlays is not None else ["", "", "Sığorta yanındadır", "Xalq Sığorta · Ətraflı bax"]
    times = ["0.0-1.5s", "1.5-4.0s", "4.0-7.5s", "7.5-10.0s"]
    return {
        "format": {"aspect": aspect, "duration_s": 10},
        "offer": {"cta": "Ətraflı bax", "headline": "Səyahət et, qalanını bizə burax"},
        "brand": {"palette": ["#E31E24", "#2B2A29", "#FFFFFF"]},
        "storyboard": [
            {"time": t, "beat": f"b{i}", "visual": "v", "motion": "m", "overlay": o}
            for i, (t, o) in enumerate(zip(times, ovs))
        ],
    }


class OverlayPlanTests(unittest.TestCase):
    def test_only_director_curated_beats_get_text(self):
        events = finish.plan_overlays(_brief(), duration=10.0)
        # 2 storyboard lines with text; the last one doubles as the CTA.
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["role"], "line")
        self.assertEqual(events[1]["role"], "cta")

    def test_events_use_storyboard_time_windows(self):
        events = finish.plan_overlays(_brief(), duration=10.0)
        self.assertAlmostEqual(events[0]["start"], 4.0)
        self.assertAlmostEqual(events[0]["end"], 7.5)

    def test_cta_holds_to_the_end(self):
        events = finish.plan_overlays(_brief(), duration=10.0)
        self.assertAlmostEqual(events[-1]["end"], 10.0)

    def test_cta_guaranteed_when_brief_has_no_overlays(self):
        events = finish.plan_overlays(_brief(overlays=["", "", "", ""]), duration=10.0)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["role"], "cta")
        self.assertEqual(events[0]["text"], "Ətraflı bax")
        self.assertAlmostEqual(events[0]["end"], 10.0)

    def test_events_clamped_to_duration(self):
        # 10s storyboard finished onto an 8.2s master must not overrun.
        events = finish.plan_overlays(_brief(), duration=8.2)
        for ev in events:
            self.assertLessEqual(ev["end"], 8.2)


class FiltergraphTests(unittest.TestCase):
    def _graph(self, *, with_logo: bool, brief=None) -> str:
        brief = brief or _brief()
        events = finish.plan_overlays(brief, duration=10.0)
        with tempfile.TemporaryDirectory() as td:
            graph, extra = finish.build_filtergraph(
                brief, events, Path(td), 1080, 1920,
                with_logo=with_logo, duration=10.0)
            self._extra = extra
            return graph

    def test_graph_upscales_with_lanczos_and_ends_in_vout(self):
        graph = self._graph(with_logo=False)
        self.assertIn("scale=1080:1920", graph)
        self.assertIn("lanczos", graph)
        self.assertIn("[vout]", graph)

    def test_az_text_goes_through_sidecar_files_not_inline(self):
        graph = self._graph(with_logo=False)
        # The AZ copy must never be embedded raw in the filtergraph.
        self.assertNotIn("Ətraflı", graph)
        self.assertIn("textfile=", graph)

    def test_logo_adds_bug_and_endcard_overlays(self):
        if not finish.LOGO_WHITE.exists():
            self.skipTest("brand logo asset missing")
        graph = self._graph(with_logo=True)
        self.assertEqual(graph.count("overlay="), 2)  # corner bug + end-card lockup
        self.assertEqual(self._extra[0], "-i")

    def test_no_logo_graph_has_no_overlay_inputs(self):
        graph = self._graph(with_logo=False)
        self.assertNotIn("overlay=", graph)
        self.assertEqual(self._extra, [])

    def test_windows_paths_are_ffmpeg_escaped(self):
        escaped = finish._ff_path(r"C:\Windows\Fonts\segoeuib.ttf")
        self.assertNotIn("\\W", escaped)
        self.assertIn(r"C\:", escaped)


class HelperTests(unittest.TestCase):
    def test_canvas_follows_brief_aspect(self):
        self.assertEqual(finish.target_canvas(_brief(aspect="9:16")), (1080, 1920))
        self.assertEqual(finish.target_canvas(_brief(aspect="1:1")), (1080, 1080))

    def test_canvas_override_wins(self):
        self.assertEqual(finish.target_canvas(_brief(), "16:9"), (1920, 1080))

    def test_time_window_parse_and_fallback(self):
        self.assertEqual(finish.parse_time_window("4.0-7.5s", (0, 1)), (4.0, 7.5))
        self.assertEqual(finish.parse_time_window("qeyri-müəyyən", (2.0, 3.0)), (2.0, 3.0))

    def test_pick_master_prefers_film_then_beats_then_any(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            self.assertIsNone(finish.pick_master(folder))
            (folder / "promo-t2v-old.mp4").write_bytes(b"x")
            self.assertEqual(finish.pick_master(folder).name, "promo-t2v-old.mp4")
            (folder / "promo-beats-master.mp4").write_bytes(b"x")
            self.assertEqual(finish.pick_master(folder).name, "promo-beats-master.mp4")
            (folder / "promo-film-master.mp4").write_bytes(b"x")
            self.assertEqual(finish.pick_master(folder).name, "promo-film-master.mp4")

    def test_alpha_expr_is_trapezoid(self):
        expr = finish._alpha_expr(2.0, 5.0)
        self.assertIn("lt(t,2.000)", expr)
        self.assertIn("lt(t,5.000)", expr)


class FinishGuardTests(unittest.TestCase):
    def test_missing_master_is_a_clean_error(self):
        with tempfile.TemporaryDirectory() as td:
            res = finish.finish_master(
                Path(td) / "yoxdur.mp4", _brief(), Path(td) / "out.mp4")
            self.assertFalse(res["ok"])
            self.assertIn("tapılmadı", res["error"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

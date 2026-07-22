"""Experiment Arena ("Paralel Gələcəklər" v0): the decision path must rank on real
metrics, refuse to name a winner inside the noise floor, measure a crashing variant
instead of raising, learn from the loser, and NEVER auto-apply the winner.
"""

import unittest
from unittest import mock

from gateway import arena


def _agg(name, quality, reliability, latency, cost):
    """A raw aggregate as run_arena would emit, for testing rank/decide directly."""
    return {"variant": name, "trials": 5, "passed": int(reliability * 5),
            "reliability": reliability, "quality": quality, "latency_s": latency,
            "cost_usd": cost, "errors": []}


class Aggregate(unittest.TestCase):
    def test_quality_averages_only_over_successful_trials(self):
        trials = [arena.Trial("a", True, 0.1, 0.0, 1.0),
                  arena.Trial("b", True, 0.1, 0.0, 0.0),
                  arena.Trial("c", False, 0.1, 0.0, 0.0, "boom")]
        a = arena.aggregate("v", trials)
        self.assertEqual(a["passed"], 2)
        self.assertAlmostEqual(a["reliability"], 2 / 3, places=3)
        self.assertAlmostEqual(a["quality"], 0.5, places=3)  # (1+0)/2, failure excluded

    def test_cost_sums_across_all_trials(self):
        trials = [arena.Trial("a", True, 0.1, 0.002, 1.0),
                  arena.Trial("b", True, 0.1, 0.003, 1.0)]
        self.assertAlmostEqual(arena.aggregate("v", trials)["cost_usd"], 0.005, places=6)


class RankAndDecide(unittest.TestCase):
    def test_higher_quality_wins(self):
        v = arena.decide("t", [_agg("A", 0.9, 1.0, 0.1, 0.0),
                                _agg("B", 0.5, 1.0, 0.1, 0.0)])
        self.assertEqual(v.status, "decided")
        self.assertEqual(v.winner, "A")
        self.assertGreater(v.margin, 0)

    def test_noise_margin_is_inconclusive(self):
        v = arena.decide("t", [_agg("A", 0.80, 1.0, 0.1, 0.0),
                                _agg("B", 0.79, 1.0, 0.1, 0.0)])
        self.assertEqual(v.status, "inconclusive")
        self.assertIsNone(v.winner)
        self.assertEqual(v.postmortems, [])  # no luck-promotion, no lessons

    def test_single_variant_has_no_shootout(self):
        v = arena.decide("t", [_agg("solo", 1.0, 1.0, 0.1, 0.0)])
        self.assertEqual(v.status, "single")
        self.assertEqual(v.winner, "solo")
        self.assertEqual(v.margin, 0.0)

    def test_speed_and_cost_normalised_across_variants(self):
        # equal quality+reliability: the faster, cheaper variant must win on tie-breakers
        v = arena.decide("t", [_agg("fast", 0.8, 1.0, 0.10, 0.0),
                                _agg("slow", 0.8, 1.0, 1.00, 0.0)])
        self.assertEqual(v.winner, "fast")

    def test_all_equal_speed_does_not_penalise(self):
        ranked = arena.rank([_agg("A", 0.9, 1.0, 0.5, 0.0),
                             _agg("B", 0.4, 1.0, 0.5, 0.0)])
        self.assertTrue(all(a["speed_score"] == 1.0 for a in ranked))


class Postmortems(unittest.TestCase):
    def test_loser_produces_a_structured_lesson(self):
        v = arena.decide("normalizasiya", [_agg("good", 1.0, 1.0, 0.1, 0.0),
                                            _agg("bad", 0.2, 1.0, 0.1, 0.0)])
        self.assertEqual(len(v.postmortems), 1)
        pm = v.postmortems[0]
        self.assertIn("bad", pm["title"])
        self.assertIn("arena", pm["tags"])
        self.assertIn("keyfiyyət", pm["body"])  # names the dimension it lost on

    def test_inconclusive_files_no_lessons(self):
        v = arena.decide("t", [_agg("A", 0.80, 1.0, 0.1, 0.0),
                                _agg("B", 0.79, 1.0, 0.1, 0.0)])
        self.assertEqual(arena.file_postmortems(v), 0)


class RunArena(unittest.TestCase):
    def test_crashing_variant_is_measured_not_raised(self):
        def boom(_):
            raise RuntimeError("kaboom")
        cases = [arena.ReplayCase("c1", "x", "x")]
        v = arena.run_arena("t", [arena.Variant("ok", lambda s: s),
                                  arena.Variant("crash", boom)], cases)
        agg = {a["variant"]: a for a in v.ranking}
        self.assertEqual(agg["ok"]["reliability"], 1.0)
        self.assertEqual(agg["crash"]["reliability"], 0.0)
        self.assertEqual(v.winner, "ok")

    def test_outcome_wrapper_reports_cost(self):
        cases = [arena.ReplayCase("c1", "x", "x")]
        v = arena.run_arena(
            "t",
            [arena.Variant("free", lambda s: s),
             arena.Variant("paid", lambda s: arena.Outcome(s, cost_usd=0.01))],
            cases,
        )
        agg = {a["variant"]: a for a in v.ranking}
        self.assertEqual(agg["paid"]["cost_usd"], 0.01)
        self.assertEqual(agg["free"]["cost_usd"], 0.0)

    def test_demo_is_decided_and_strict_wins(self):
        v = arena._demo_verdict()
        self.assertEqual(v.status, "decided")
        self.assertEqual(v.winner, "strict-normalizer")
        self.assertEqual(len(v.postmortems), 1)


class ProposeNeverApplies(unittest.TestCase):
    def test_propose_emits_but_never_applies(self):
        v = arena.decide("t", [_agg("A", 0.9, 1.0, 0.1, 0.0),
                                _agg("B", 0.5, 1.0, 0.1, 0.0)])
        with mock.patch("gateway.sense.emit") as emit:
            out = arena.propose(v)
        emit.assert_called_once()
        self.assertFalse(out["applied"])
        self.assertFalse(out["auto_apply"])
        self.assertEqual(out["winner"], "A")

    def test_propose_never_raises_without_sense(self):
        v = arena.decide("t", [_agg("A", 0.9, 1.0, 0.1, 0.0)])
        with mock.patch("gateway.sense.emit", side_effect=RuntimeError("no bus")):
            out = arena.propose(v)  # must not raise
        self.assertFalse(out["applied"])


class Render(unittest.TestCase):
    def test_format_is_azerbaijani_and_flags_no_autoapply(self):
        text = arena.format(arena._demo_verdict())
        self.assertIn("PARALEL GƏLƏCƏKLƏR", text)
        self.assertIn("avtomatik tətbiq edilmir", text)
        self.assertNotIn("None", text)


if __name__ == "__main__":
    unittest.main()

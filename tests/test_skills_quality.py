"""Guards for the skill outcome loop (Karpathy layer 4 in gateway.skills):
injections are logged, job outcomes pay wins/losses to the injected cards,
proven cards outrank unproven ones, and never-winning cards are retired."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from gateway import skills

TASK = "bizim üçün yeni landing sayt qur zəhmət olmasa"


def _write_card(slug: str, title: str, triggers: str) -> None:
    (skills._DIR / f"{slug}.md").write_text(
        f"# {title}\n\n**Triggers:** {triggers}\n\n**Steps:**\n- do the thing\n",
        encoding="utf-8")


class OutcomeLedger(unittest.TestCase):
    def setUp(self):
        self._orig = skills._DIR
        skills._DIR = Path(tempfile.mkdtemp()) / "skills"
        skills._DIR.mkdir(parents=True)

    def tearDown(self):
        skills._DIR = self._orig

    def _card(self, *a, **k):
        return {"title": "Build a landing page",
                "triggers": ["landing", "sayt", "html"],
                "steps": ["Author DESIGN.md first", "Build to the palette"]}

    def test_injection_recorded(self):
        _write_card("landing-page", "Landing craft", "landing, sayt")
        self.assertIn("Landing craft", skills.relevant(TASK))
        rec = skills.stats_snapshot()["landing-page"]
        self.assertEqual(rec["uses"], 1)
        self.assertIn(skills._task_key(TASK), skills._load_stats()["pending"])

    def test_win_credited_on_success(self):
        _write_card("landing-page", "Landing craft", "landing, sayt")
        skills.relevant(TASK)
        with patch.object(skills, "_distill", self._card):
            skills.learn_from_job(TASK, "_[agentic-tools:x]_\n\nSayt hazırdır.")
        rec = skills.stats_snapshot()["landing-page"]
        self.assertEqual((rec["wins"], rec["losses"]), (1, 0))
        self.assertNotIn(skills._task_key(TASK), skills._load_stats()["pending"])

    def test_loss_credited_on_soft_failure_and_no_new_card(self):
        _write_card("landing-page", "Landing craft", "landing, sayt")
        skills.relevant(TASK)
        distill = MagicMock()
        with patch.object(skills, "_distill", distill):
            out = skills.learn_from_job(TASK, "_[agentic-tools:x]_\n\n❌ İcra xətası")
        self.assertIsNone(out)
        distill.assert_not_called()  # a failure never becomes a card
        self.assertEqual(skills.stats_snapshot()["landing-page"]["losses"], 1)

    def test_agentic_usage_limit_dump_is_a_loss_not_learned(self):
        # Regression: job 158 (2026-07-21) shipped a raw Codex usage-limit dump
        # as a "result"; it must count as a LOSS and never distill a card.
        _write_card("landing-page", "Landing craft", "landing, sayt")
        skills.relevant(TASK)
        distill = MagicMock()
        dump = ("_[agentic-tools:codex]_\n\nERROR: You've hit your usage limit. "
                "Upgrade to Plus to continue using Codex.")
        with patch.object(skills, "_distill", distill):
            out = skills.learn_from_job(TASK, dump)
        self.assertIsNone(out)
        distill.assert_not_called()
        self.assertEqual(skills.stats_snapshot()["landing-page"]["losses"], 1)

    def test_card_that_never_wins_is_retired(self):
        _write_card("landing-page", "Landing craft", "landing, sayt")
        distill = MagicMock()
        with patch.object(skills, "_distill", distill):
            for _ in range(skills._RETIRE_LOSSES):
                skills.relevant(TASK)
                skills.learn_from_job(TASK, "_[agentic-tools:x]_\n\n❌ İcra xətası")
        self.assertFalse((skills._DIR / "landing-page.md").exists())
        self.assertNotIn("landing-page", skills.stats_snapshot())

    def test_proven_card_outranks_unproven_on_equal_overlap(self):
        _write_card("rookie", "Rookie approach", "landing, sayt")
        _write_card("veteran", "Veteran approach", "landing, sayt")
        stats = skills._load_stats()
        stats["cards"]["veteran"] = {"uses": 3, "wins": 3, "losses": 0}
        skills._save_stats(stats)
        self.assertIn("Veteran approach", skills.relevant(TASK, k=1))

    def test_prune_drops_weakest_first(self):
        _write_card("weak", "Weak approach", "alpha")
        _write_card("strong", "Strong approach", "beta")
        stats = skills._load_stats()
        stats["cards"]["weak"] = {"uses": 2, "wins": 0, "losses": 2}
        stats["cards"]["strong"] = {"uses": 2, "wins": 2, "losses": 0}
        skills._save_stats(stats)
        with patch.object(skills, "_MAX_SKILLS", 1):
            skills._prune()
        self.assertFalse((skills._DIR / "weak.md").exists())
        self.assertTrue((skills._DIR / "strong.md").exists())


if __name__ == "__main__":
    unittest.main()

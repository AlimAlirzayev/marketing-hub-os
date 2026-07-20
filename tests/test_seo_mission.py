"""Guards for the SEO-mission execution rail (gateway.executor).

The rail turns "why aren't we ranking — find it and FIX it" into a REAL run of
the seo/ engine (live audit + SERP gap → execution-ready fix pack), not a
talk-only essay. Tests are pure routing/planning + one mocked integration; the
single LLM seam (keyword extraction) is stubbed, and no network is touched.
"""

import os
import types
import unittest
from unittest.mock import patch

from gateway import executor
from gateway.queue import Job


def _job(task: str) -> Job:
    import time
    return Job(id=0, source="cli", chat_id=None, task=task, status="running",
               result=None, error=None, artifacts=[], created_at=time.time(),
               started_at=None, finished_at=None)


class SeoMissionTrigger(unittest.TestCase):
    def test_ranking_ask_triggers(self):
        self.assertTrue(executor._is_seo_mission(
            "Saytımız üçün texniki SEO analiz et, niyə sıralanmırıq tap və düzəlt"))

    def test_front_page_phrase_triggers(self):
        # the operator's real SAT ask shape — no literal "seo" word at all
        self.assertTrue(executor._is_seo_mission(
            "Niyə biz SAT üzrə ön səhifədə çıxa bilmirik səbəbini tap"))

    def test_casual_seo_question_not_hijacked(self):
        self.assertFalse(executor._is_seo_mission("salam, seo nədir ümumiyyətlə?"))

    def test_ordinary_chat_not_hijacked(self):
        self.assertFalse(executor._is_seo_mission("bugün işlər necə gedir?"))


class SeoMissionPlan(unittest.TestCase):
    def _plan(self, task):
        # stub the one LLM seam so planning is deterministic + offline
        with patch("llm_router.complete_json",
                   return_value=({"keywords": ["sat kursu"]}, "stub")):
            return executor._seo_plan(task)

    def test_explicit_domain_wins(self):
        p = self._plan("edudistance.az saytında niyə sıralanmırıq")
        self.assertEqual(p["url"].lower().replace("https://", ""), "edudistance.az")

    def test_falls_back_to_brand_site(self):
        # no domain in the text -> the active brand's own website
        p = self._plan("saytımızın SEO-sunu analiz et")
        self.assertTrue(p["url"])

    def test_keywords_from_llm(self):
        self.assertEqual(self._plan("SAT kursu üçün ön səhifəyə çıxaq")["keywords"],
                         ["sat kursu"])

    def test_keywords_empty_when_llm_down(self):
        # complete_json failing must never sink the mission — keywords degrade to []
        with patch("llm_router.complete_json", side_effect=RuntimeError("down")):
            self.assertEqual(executor._seo_plan("edudistance.az sıralanma")["keywords"], [])


class SeoMissionPrecedence(unittest.TestCase):
    def test_seo_rail_beats_the_planner(self):
        # The SAT ask contains "sonra" (a planner cue) AND ranking intent. The SEO
        # rail must win — otherwise the task is hijacked into a talk-only research
        # essay (the exact bug this rail fixes). Prove the order inside execute().
        task = "Əvvəlcə dərin analiz, sonra niyə ön səhifədə çıxa bilmirik tap və düzəlt"
        self.assertTrue(executor._is_seo_mission(task))
        self.assertTrue(executor._wants_plan(task))  # both match; order must decide

        allow = types.SimpleNamespace(allowed=True, category="ok")
        with patch.object(executor.mic, "thread_for", return_value="t"), \
             patch.object(executor.knowledge, "set_current_thread"), \
             patch.object(executor.security, "evaluate_task", return_value=allow), \
             patch.object(executor.security, "audit_event"), \
             patch.object(executor, "_save_artifact", return_value="art"), \
             patch.object(executor, "_seo_mission",
                          return_value=("SENTINEL_SEO_PACK", [])) as seo, \
             patch.object(executor, "_plan_and_run",
                          side_effect=AssertionError("planner must not be reached")):
            out = executor.execute(_job(task))

        seo.assert_called_once()
        self.assertIn("SENTINEL_SEO_PACK", out["result"])
        self.assertIn("seo-mission", out["result"])


if __name__ == "__main__":
    unittest.main()

"""Guards for the crew auto-route (gateway.executor).

Routing contract as of 2026-07-20 ("the model is the router"):
- premium brain on (MIC_BRAIN=claude) → the keyword auto-route NEVER fires;
  the bridge brain itself summons the crew via gateway/summon.py.
- free floor (MIC_BRAIN=free) → the keyword auto-route survives as fallback,
  with the 2026-07-19 negative guards (jobs #124/#125 regressions).
- explicit /crew summon works everywhere.
No LLM calls — pure routing.
"""

import os
import unittest
from unittest.mock import patch

from gateway import executor

HEAVY = ("Q3 üçün tam reklam kampaniya strategiyası hazırla, "
         "büdcə bölgüsü ilə birlikdə")


class HeavyOperationalGuards(unittest.TestCase):
    def test_premium_brain_is_the_router(self):
        # "The model is the router" (2026-07-20): with claude on the mic the
        # keyword auto-route must never hijack — the brain summons the crew itself.
        with patch.dict(os.environ, {"MIC_BRAIN": "claude"}):
            self.assertFalse(executor._is_heavy_operational(HEAVY))

    def test_free_floor_keeps_the_keyword_fallback(self):
        with patch.dict(os.environ, {"MIC_BRAIN": "free"}):
            self.assertTrue(executor._is_heavy_operational(HEAVY))

    def test_greeting_opener_stays_conversational(self):
        # job #125: a greeting-wrapped report ask was hijacked by the crew and
        # answered without conversation memory ("no data, empty report")
        with patch.dict(os.environ, {"MIC_BRAIN": "free"}):
            self.assertFalse(executor._is_heavy_operational(
                "Salam, necəsən? İndi də görüm mənə səyahət sığortası üzrə "
                "bu ayın hesabatını verə bilərsən?"))

    def test_system_directed_ask_stays_conversational(self):
        # job #124: "unfinished work" meant SYSTEM tasks; the crew read it as
        # funnel abandonment and produced an off-target GA4 essay
        with patch.dict(os.environ, {"MIC_BRAIN": "free"}):
            self.assertFalse(executor._is_heavy_operational(
                "Yarımçıq qalan işləri analiz et və plan qur və hamısını icra et."))

    def test_short_ask_never_crew(self):
        with patch.dict(os.environ, {"MIC_BRAIN": "free"}):
            self.assertFalse(executor._is_heavy_operational("hesabat ver"))

    def test_kill_switch(self):
        with patch.dict(os.environ, {"MIC_BRAIN": "free"}), \
             patch.object(executor, "_CREW_ENABLED", False):
            self.assertFalse(executor._is_heavy_operational(HEAVY))

    def test_explicit_summon_still_works(self):
        self.assertTrue(executor._wants_crew("/crew bazar araşdırması apar"))


if __name__ == "__main__":
    unittest.main()

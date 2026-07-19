"""Guards for the crew auto-route (gateway.executor).

The crew is a marketing workforce with no conversation memory and no system
awareness. These tests pin the 2026-07-19 routing contract: real heavy marketing
deliverables go to the crew; conversational and system-directed turns never do
(jobs #124/#125 regression guards). No LLM calls — pure routing.
"""

import unittest
from unittest.mock import patch

from gateway import executor

HEAVY = ("Q3 üçün tam reklam kampaniya strategiyası hazırla, "
         "büdcə bölgüsü ilə birlikdə")


class HeavyOperationalGuards(unittest.TestCase):
    def test_real_heavy_ask_routes_to_crew(self):
        self.assertTrue(executor._is_heavy_operational(HEAVY))

    def test_greeting_opener_stays_conversational(self):
        # job #125: a greeting-wrapped report ask was hijacked by the crew and
        # answered without conversation memory ("no data, empty report") while
        # the chat brain had answered the same ask with real numbers a day earlier
        self.assertFalse(executor._is_heavy_operational(
            "Salam, necəsən? İndi də görüm mənə səyahət sığortası üzrə "
            "bu ayın hesabatını verə bilərsən?"))

    def test_system_directed_ask_stays_conversational(self):
        # job #124: "unfinished work" meant SYSTEM tasks; the crew read it as
        # funnel abandonment and produced an off-target GA4 essay
        self.assertFalse(executor._is_heavy_operational(
            "Yarımçıq qalan işləri analiz et və plan qur və hamısını icra et."))

    def test_short_ask_never_crew(self):
        self.assertFalse(executor._is_heavy_operational("hesabat ver"))

    def test_kill_switch(self):
        with patch.object(executor, "_CREW_ENABLED", False):
            self.assertFalse(executor._is_heavy_operational(HEAVY))

    def test_explicit_summon_still_works(self):
        self.assertTrue(executor._wants_crew("/crew bazar araşdırması apar"))


if __name__ == "__main__":
    unittest.main()

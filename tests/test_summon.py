"""Guards for the brain's async crew summon door (gateway.summon).

"The model is the router" (2026-07-20): the bridge brain enqueues heavy work
via this door instead of keyword lists hijacking turns. No LLM, no queue I/O —
mic.speak is mocked.
"""

import unittest
from unittest.mock import patch

from gateway import summon

GOAL = "Q4 səyahət sığortası kampaniya strategiyası, büdcə bölgüsü ilə"
OWNER_ENV = {"TELEGRAM_OWNER_CHAT_ID": "12345"}


class SummonDoor(unittest.TestCase):
    def test_enqueues_on_the_explicit_crew_rail(self):
        with patch.dict("os.environ", OWNER_ENV), \
             patch("gateway.mic.speak", return_value=77) as spoke:
            rc = summon.main(["crew", GOAL])
        self.assertEqual(rc, 0)
        spoke.assert_called_once_with(f"/crew {GOAL}", source="telegram", chat_id="12345")

    def test_dry_run_never_enqueues(self):
        with patch.dict("os.environ", OWNER_ENV), \
             patch("gateway.mic.speak") as spoke:
            rc = summon.main(["crew", GOAL, "--dry-run"])
        self.assertEqual(rc, 0)
        spoke.assert_not_called()

    def test_short_goal_refused(self):
        with patch.dict("os.environ", OWNER_ENV), \
             patch("gateway.mic.speak") as spoke:
            rc = summon.main(["crew", "qısa"])
        self.assertEqual(rc, 2)
        spoke.assert_not_called()

    def test_unknown_kind_refused(self):
        with patch.dict("os.environ", OWNER_ENV):
            self.assertEqual(summon.main(["fanout", GOAL]), 2)

    def test_missing_owner_refused(self):
        with patch.dict("os.environ",
                        {"TELEGRAM_OWNER_CHAT_ID": "", "GATEWAY_OWNER_ID": ""}), \
             patch("gateway.mic.speak") as spoke:
            rc = summon.main(["crew", GOAL])
        self.assertEqual(rc, 2)
        spoke.assert_not_called()


if __name__ == "__main__":
    unittest.main()

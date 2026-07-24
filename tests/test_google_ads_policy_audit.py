from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


MODULE_PATH = Path(__file__).resolve().parents[1] / "ads-studio" / "google_ads_policy_audit.py"
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("google_ads_policy_audit", MODULE_PATH)
AUDIT = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(AUDIT)


class EnumValue:
    def __init__(self, name: str):
        self.name = name


class Obj:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def test_masked_customer_id_keeps_only_last_four_digits():
    assert AUDIT._masked_customer_id("123-456-7890") == "******7890"


def test_recommendation_maps_destination_failure():
    topics = [{"topic": "DESTINATION_NOT_WORKING", "type": "PROHIBITED"}]
    assert AUDIT._recommendation(topics).startswith("Landing page status")


def test_audit_filters_clean_ads_and_keeps_disapproved_ads():
    clean = _row("APPROVED", "ELIGIBLE", [])
    bad = _row(
        "DISAPPROVED",
        "NOT_ELIGIBLE",
        [Obj(topic="DESTINATION_NOT_WORKING", type_=EnumValue("PROHIBITED"))],
    )
    service = Obj(search=lambda **_: [clean, bad])
    client = Obj(get_service=lambda _: service)

    report = AUDIT.audit_account(client, "1234567890")

    assert report["ads_scanned"] == 2
    assert report["problem_ads"] == 1
    assert report["write_actions_performed"] == 0
    assert report["findings"][0]["policy_topics"][0]["topic"] == "DESTINATION_NOT_WORKING"


def _row(approval: str, primary: str, topics: list[Obj]) -> Obj:
    return Obj(
        customer=Obj(descriptive_name="Xalq", currency_code="AZN", time_zone="Asia/Baku"),
        campaign=Obj(id=1, name="Campaign", status=EnumValue("ENABLED")),
        ad_group=Obj(id=2, name="Ad group", status=EnumValue("ENABLED")),
        ad_group_ad=Obj(
            status=EnumValue("ENABLED"),
            primary_status=EnumValue(primary),
            primary_status_reasons=[EnumValue("AD_GROUP_AD_DISAPPROVED")],
            policy_summary=Obj(
                approval_status=EnumValue(approval),
                review_status=EnumValue("REVIEWED"),
                policy_topic_entries=topics,
            ),
            ad=Obj(id=3, type_=EnumValue("RESPONSIVE_SEARCH_AD"), final_urls=["https://xalqinsurance.az/"]),
        ),
    )

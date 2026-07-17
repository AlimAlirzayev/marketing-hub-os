from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "travel_reporting", ROOT / "ads-studio" / "travel_reporting.py")
travel = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(travel)


def test_travel_classifier_handles_azerbaijani_and_campaign_variants():
    assert travel.is_travel("Səyahət sığortası · yay")
    assert travel.is_travel("Travel_insurance_story")
    assert travel.is_travel("Gurcustan sale")
    assert not travel.is_travel("KASKO website conversion")


def test_travel_row_uses_adset_and_avoids_misassigned_creative():
    assert travel.is_travel_row({
        "campaign_name": "Sale",
        "adset_name": "Sale_travel_insurance_story",
        "ad_name": "Gurcustan sale post",
    })
    assert not travel.is_travel_row({
        "campaign_name": "Sale",
        "adset_name": "PlyusKasko_eventbase_Desktop",
        "ad_name": "Gurcustan Story - apply now",
    })
    assert travel.is_travel_row({
        "campaign_name": "Sale",
        "adset_name": "Instagram Post",
        "ad_name": "Travel insurance summer",
    })


def test_purchase_metrics_and_derived_efficiency():
    row = {
        "spend": "100", "impressions": "10000", "clicks": "250", "reach": "7000",
        "actions": [{"action_type": "purchase", "value": "5"}],
        "action_values": [{"action_type": "purchase", "value": "450"}],
    }
    total = travel._sum_metrics([travel._metrics(row)])
    assert total["purchases"] == 5
    assert total["revenue"] == 450
    assert total["ctr"] == 2.5
    assert total["cpa"] == 20
    assert total["roas"] == 4.5


def test_segment_filters_non_travel_rows():
    rows = [
        {"campaign_name": "Sale", "adset_name": "Travel", "region": "Baku", "spend": "10", "impressions": "1000", "clicks": "20"},
        {"campaign_name": "Sale", "adset_name": "KASKO", "region": "Baku", "spend": "999", "impressions": "1000", "clicks": "20"},
    ]
    out = travel._segment(rows, ("region",))
    assert len(out) == 1
    assert out[0]["label"] == "Baku"
    assert out[0]["spend"] == 10

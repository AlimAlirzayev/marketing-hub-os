from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "ads-studio" / "google_ads_az_language_request.py"
SPEC = importlib.util.spec_from_file_location("google_ads_az_language_request", MODULE_PATH)
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MOD)


def test_editor_export_inventory_detects_azerbaijani_rows():
    text = (
        "Campaign\tAd group\tType\tHeadline\n"
        "Travel\tAZ\tResponsive search ad\tSəyahət sığortası\n"
        "Travel\tEN\tResponsive search ad\tTravel insurance\n"
    )
    rows = MOD._rows(text)
    result = MOD.inventory(rows)
    assert result["rows_scanned"] == 2
    assert result["affected_rows"] == 1
    assert result["affected_campaigns"] == 1
    assert result["campaign_counts"] == {"Travel": 1}


def test_request_redacts_customer_id_and_never_claims_submission():
    data = {
        "rows_scanned": 1,
        "affected_rows": 1,
        "affected_campaigns": 1,
        "campaign_counts": {"123-456-7890 Campaign": 1},
    }
    report = MOD.render_request(
        data,
        "export-1234567890.csv",
        observed_ads=4,
        observed_asset_groups=1,
        observed_extensions=9,
    )
    assert "123-456-7890" not in report
    assert "1234567890" not in report
    assert "manual owner checkpoint" in report
    assert "does not submit appeals" in report
    assert "Ads marked `Unsupported language`: 4" in report
    assert "Asset groups marked `Unsupported language`: 1" in report
    assert "Extensions/assets marked `Unsupported language`: 9" in report


def test_inventory_counts_generator_rows_without_consumption_bug():
    rows = (
        row
        for row in [
            {"Campaign": "Travel", "Headline": "Səyahət sığortası"},
            {"Campaign": "Travel", "Headline": "Travel insurance"},
        ]
    )
    result = MOD.inventory(rows)
    assert result["rows_scanned"] == 2
    assert result["affected_rows"] == 1

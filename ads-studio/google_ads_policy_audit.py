"""Read-only Google Ads policy audit for Xalq Sigorta.

This tool never mutates campaigns, ads, assets, budgets, or appeal state. It
reads the Google Ads policy summary and writes a reviewable local report. Live
fixes and appeals remain separate, human-approved actions.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from connectors.google_ads import _customer_id, build_client


DEFAULT_OUTPUT = (
    Path(__file__).resolve().parent.parent
    / "output"
    / "google-ads"
    / "policy_audit.json"
)

_PROBLEM_APPROVALS = {"DISAPPROVED", "APPROVED_LIMITED", "AREA_OF_INTEREST_ONLY"}
_PROBLEM_PRIMARY = {"NOT_ELIGIBLE", "LIMITED"}


def _name(value: Any) -> str:
    """Return an enum-like value as a stable printable name."""
    return getattr(value, "name", str(value))


def _topic(entry: Any) -> dict[str, str]:
    return {
        "topic": str(getattr(entry, "topic", "")),
        "type": _name(getattr(entry, "type_", "")),
    }


def _masked_customer_id(customer_id: str) -> str:
    digits = "".join(ch for ch in customer_id if ch.isdigit())
    return ("*" * max(0, len(digits) - 4)) + digits[-4:]


def _recommendation(topics: list[dict[str, str]]) -> str:
    joined = " ".join(item["topic"].lower().replace("_", " ") for item in topics)
    if any(key in joined for key in ("destination not working", "destination experience")):
        return "Landing page status, redirects, mobile access, robots and DNS must be fixed before review."
    if any(key in joined for key in ("malicious", "compromised", "unwanted software")):
        return "Quarantine the destination and complete a security scan; do not appeal before the site is clean."
    if "misrepresentation" in joined:
        return "Align ad claims with the landing page and make the legal entity, product terms and contact details explicit."
    if any(key in joined for key in ("financial services", "financial products")):
        return "Verify whether Google advertiser/financial-services verification is required for the target market."
    if any(key in joined for key in ("trademark", "copyright")):
        return "Confirm brand rights and remove or document any third-party protected material."
    if any(key in joined for key in ("editorial", "punctuation", "spelling")):
        return "Correct the flagged copy/formatting and save the ad for a new review."
    return "Open the exact policy topic in Policy Manager, correct the ad or destination, then request one targeted review."


def audit_account(client: Any, customer_id: str) -> dict[str, Any]:
    service = client.get_service("GoogleAdsService")
    query = """
        SELECT
          customer.descriptive_name,
          customer.currency_code,
          customer.time_zone,
          campaign.id,
          campaign.name,
          campaign.status,
          ad_group.id,
          ad_group.name,
          ad_group.status,
          ad_group_ad.ad.id,
          ad_group_ad.ad.type,
          ad_group_ad.ad.final_urls,
          ad_group_ad.status,
          ad_group_ad.primary_status,
          ad_group_ad.primary_status_reasons,
          ad_group_ad.policy_summary.approval_status,
          ad_group_ad.policy_summary.review_status,
          ad_group_ad.policy_summary.policy_topic_entries
        FROM ad_group_ad
        WHERE campaign.status != 'REMOVED'
          AND ad_group.status != 'REMOVED'
          AND ad_group_ad.status != 'REMOVED'
    """

    findings: list[dict[str, Any]] = []
    account: dict[str, str] = {}
    scanned = 0
    for row in service.search(customer_id=customer_id, query=query):
        scanned += 1
        if not account:
            account = {
                "name": row.customer.descriptive_name,
                "currency": row.customer.currency_code,
                "time_zone": row.customer.time_zone,
            }
        approval = _name(row.ad_group_ad.policy_summary.approval_status)
        primary = _name(row.ad_group_ad.primary_status)
        topics = [_topic(item) for item in row.ad_group_ad.policy_summary.policy_topic_entries]
        if approval not in _PROBLEM_APPROVALS and primary not in _PROBLEM_PRIMARY and not topics:
            continue
        findings.append(
            {
                "campaign": {
                    "id": str(row.campaign.id),
                    "name": row.campaign.name,
                    "status": _name(row.campaign.status),
                },
                "ad_group": {
                    "id": str(row.ad_group.id),
                    "name": row.ad_group.name,
                    "status": _name(row.ad_group.status),
                },
                "ad": {
                    "id": str(row.ad_group_ad.ad.id),
                    "type": _name(row.ad_group_ad.ad.type_),
                    "status": _name(row.ad_group_ad.status),
                    "primary_status": primary,
                    "primary_status_reasons": [
                        _name(item) for item in row.ad_group_ad.primary_status_reasons
                    ],
                    "approval_status": approval,
                    "review_status": _name(row.ad_group_ad.policy_summary.review_status),
                    "final_urls": list(row.ad_group_ad.ad.final_urls),
                },
                "policy_topics": topics,
                "recommended_next_step": _recommendation(topics),
            }
        )

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "live_read_only",
        "customer_id_masked": _masked_customer_id(customer_id),
        "account": account,
        "ads_scanned": scanned,
        "problem_ads": len(findings),
        "findings": findings,
        "write_actions_performed": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Google Ads policy audit")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--stdout", action="store_true", help="also print the report JSON"
    )
    args = parser.parse_args()

    client = build_client()
    report = audit_account(client, _customer_id())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"Google Ads policy audit complete: {report['ads_scanned']} ads scanned, "
        f"{report['problem_ads']} problem ads. Report: {args.output}"
    )
    if args.stdout:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

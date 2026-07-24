"""Build a legitimate Azerbaijani-language support request for Google Ads.

The Google Ads API and Google Ads Editor cannot enable an unsupported ad
language. This tool therefore does not mutate an account or attempt to bypass
policy review. It inventories Azerbaijani content from a Google Ads Editor CSV
export and produces a redacted, evidence-based request for official support.
"""

from __future__ import annotations

import argparse
import csv
import io
import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Iterable


DEFAULT_OUTPUT = (
    Path(__file__).resolve().parent.parent
    / "output"
    / "google-ads"
    / "az_language_support_request.md"
)

OFFICIAL_LANGUAGE_LIST = "https://support.google.com/google-ads/answer/6333734"
OFFICIAL_SUPPORT = "https://support.google.com/google-ads/gethelp"
OFFICIAL_EDITOR_HELP = "https://support.google.com/google-ads/editor/"

# Strong Azerbaijani Latin-script signals. Several characters overlap Turkish;
# ə/Ə is weighted separately and all matching remains an audit heuristic.
AZ_CHARS = set("əƏğĞıİöÖüÜşŞçÇ")
STRONG_AZ_CHARS = set("əƏ")
ID_PATTERN = re.compile(r"\b\d{3}-\d{3}-\d{4}\b|\b\d{10}\b")


def _read_export(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-16", "utf-8-sig", "utf-8"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Editor export must be UTF-16 or UTF-8 text")


def _rows(text: str) -> list[dict[str, str]]:
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters="\t,;")
    except csv.Error:
        dialect = csv.excel_tab if "\t" in sample else csv.excel
    return [
        {str(k or "").strip(): str(v or "").strip() for k, v in row.items()}
        for row in csv.DictReader(io.StringIO(text), dialect=dialect)
    ]


def _az_score(values: Iterable[str]) -> tuple[int, bool]:
    chars = set(" ".join(values))
    return len(chars & AZ_CHARS), bool(chars & STRONG_AZ_CHARS)


def inventory(rows: Iterable[dict[str, str]]) -> dict:
    rows = list(rows)
    affected: list[dict[str, str]] = []
    campaigns: Counter[str] = Counter()
    for row in rows:
        score, strong = _az_score(row.values())
        if not score:
            continue
        campaign = row.get("Campaign") or row.get("Campaign name") or "(unknown)"
        ad_group = row.get("Ad group") or row.get("Ad group name") or "(unknown)"
        row_type = row.get("Type") or row.get("Ad type") or row.get("Asset type") or "(unknown)"
        affected.append(
            {
                "campaign": campaign,
                "ad_group": ad_group,
                "type": row_type,
                "strong_az_signal": "yes" if strong else "no",
                "signal_count": str(score),
            }
        )
        campaigns[campaign] += 1
    return {
        "rows_scanned": len(rows),
        "affected_rows": len(affected),
        "affected_campaigns": len(campaigns),
        "campaign_counts": dict(campaigns.most_common()),
        "affected": affected,
    }


def _redact(value: str) -> str:
    return ID_PATTERN.sub("[ACCOUNT ID REDACTED]", value)


def render_request(
    data: dict,
    source_name: str,
    observed_ads: int = 0,
    observed_asset_groups: int = 0,
    observed_extensions: int = 0,
) -> str:
    campaign_lines = "\n".join(
        f"- `{_redact(name)}`: {count} Azerbaijani-signalled rows"
        for name, count in data["campaign_counts"].items()
    ) or "- No Editor export evidence supplied yet."
    return f"""# Request: add Azerbaijani as a supported Google Ads language

Generated: {date.today().isoformat()}
Submission mode: manual owner checkpoint through official Google Ads Support
Source: `{_redact(source_name)}`

## Request to Google Ads Support

Hello Google Ads Support,

We are a verified advertiser in Azerbaijan and request product/policy escalation
for Azerbaijani (`az`, Latin script) to become a supported Google Ads ad language
and language-targeting option. Azerbaijani is the primary customer language for
our local insurance communications, but it is not present in the current official
Ads Language Targeting list. Compliant Azerbaijani creatives are consequently
classified as Unsupported language.

We are not asking for an account-specific policy bypass. Please route this as a
product-language support request and confirm whether a formal pilot, allowlist,
or language expansion intake exists for verified advertisers in Azerbaijan.

## Export evidence

- Rows scanned: {data['rows_scanned']}
- Azerbaijani-signalled rows: {data['affected_rows']}
- Affected campaigns: {data['affected_campaigns']}

{campaign_lines}

## Live Policy Manager evidence

- Ads marked `Unsupported language`: {observed_ads}
- Asset groups marked `Unsupported language`: {observed_asset_groups}
- Extensions/assets marked `Unsupported language`: {observed_extensions}

These counts are operator-observed summary evidence from Google Ads Policy
Manager. They contain no customer ID, ad text, personal data, or credentials.

Detection is a local heuristic based on Azerbaijani Latin characters. The source
export should be attached to the support case only after an owner reviews it for
confidential fields.

## Required Google response

1. Confirm whether Azerbaijani ad-language support is on the product roadmap.
2. Confirm whether verified Azerbaijani advertisers have an escalation, pilot,
   or allowlist process.
3. Confirm the compliant interim configuration for Azerbaijani search queries
   without mislabeling Azerbaijani creative as another language.
4. Provide a support case ID and escalation owner/team.

## Official references

- Supported Ads languages: {OFFICIAL_LANGUAGE_LIST}
- Google Ads Support: {OFFICIAL_SUPPORT}
- Google Ads Editor Help: {OFFICIAL_EDITOR_HELP}

## Safety boundary

This package does not submit appeals, upload ads, change language targeting,
mislabel Azerbaijani content, or attempt to bypass policy enforcement. Google Ads
Editor and the Google Ads API remain server-policy constrained.
"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a redacted official-support dossier for Azerbaijani Ads language support"
    )
    parser.add_argument("--editor-csv", type=Path, help="Google Ads Editor CSV/TSV export")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--observed-ads", type=int, default=0)
    parser.add_argument("--observed-asset-groups", type=int, default=0)
    parser.add_argument("--observed-extensions", type=int, default=0)
    args = parser.parse_args()

    observed = (args.observed_ads, args.observed_asset_groups, args.observed_extensions)
    if any(value < 0 for value in observed):
        parser.error("observed policy counts cannot be negative")

    if args.editor_csv:
        parsed = _rows(_read_export(args.editor_csv))
        data = inventory(parsed)
        source_name = args.editor_csv.name
    else:
        data = inventory([])
        source_name = "Editor export not supplied"

    report = render_request(
        data,
        source_name,
        observed_ads=args.observed_ads,
        observed_asset_groups=args.observed_asset_groups,
        observed_extensions=args.observed_extensions,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(f"Azerbaijani language-support dossier written: {args.output}")
    print(f"Affected rows: {data['affected_rows']}; account writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

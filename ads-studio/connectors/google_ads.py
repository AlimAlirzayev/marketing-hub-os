"""Google Ads connector — programmatic campaign creation for Ads Studio.

Why this exists: the screenshot-by-screenshot browser flow is slow and needs a
human babysitting permissions. The Google Ads API builds the same campaign in
seconds, headless, and is re-runnable — the right substrate for the Xalq Insurance Digital OS
autonomous layer.

Design choices (mirror gateway/tools/browser.py):
- The **checkpoint principle**: campaigns are created ``PAUSED``. Nothing here
  ever spends money on its own. Enabling (= starting spend) is a separate,
  explicit ``enable_campaign`` call a human triggers after review.
- Thin SDK only (``google-ads``); credentials come from the repo-root ``.env``
  so we reuse the same secrets store as the rest of Xalq Insurance Digital OS.
- Functions raise ``GoogleAdsNotConfigured`` (recoverable) when creds are
  missing, so callers can degrade instead of crashing.

Requires: ``pip install google-ads`` and the six GOOGLE_ADS_* vars in .env
(see ads-studio/GOOGLE_ADS_SETUP.md).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Reuse the repo-root .env (one level up from ads-studio/), same as config.py.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_REPO_ROOT / ".env")

_API_VERSION = "v24"  # pin so library upgrades don't silently change behaviour
# google-ads 31.x supports v21-v24; bump in lockstep when upgrading the package.


class GoogleAdsNotConfigured(RuntimeError):
    """Raised when Google Ads credentials are missing/incomplete. Recoverable."""


def _env(name: str) -> str:
    val = os.getenv(name, "").strip()
    return val


def build_client():
    """Build a GoogleAdsClient from the six GOOGLE_ADS_* env vars.

    Raises GoogleAdsNotConfigured with the exact missing keys so setup is
    self-explaining.
    """
    required = {
        "developer_token": _env("GOOGLE_ADS_DEVELOPER_TOKEN"),
        "client_id": _env("GOOGLE_ADS_CLIENT_ID"),
        "client_secret": _env("GOOGLE_ADS_CLIENT_SECRET"),
        "refresh_token": _env("GOOGLE_ADS_REFRESH_TOKEN"),
        "login_customer_id": _env("GOOGLE_ADS_LOGIN_CUSTOMER_ID"),
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise GoogleAdsNotConfigured(
            "Missing Google Ads credentials: "
            + ", ".join("GOOGLE_ADS_" + m.upper() for m in missing)
            + " — see ads-studio/GOOGLE_ADS_SETUP.md"
        )

    try:
        from google.ads.googleads.client import GoogleAdsClient
    except ImportError as exc:  # pragma: no cover - environment hint
        raise GoogleAdsNotConfigured(
            "google-ads not installed. Run: pip install google-ads"
        ) from exc

    cfg = {
        "developer_token": required["developer_token"],
        "client_id": required["client_id"],
        "client_secret": required["client_secret"],
        "refresh_token": required["refresh_token"],
        "login_customer_id": required["login_customer_id"].replace("-", ""),
        "use_proto_plus": True,
    }
    return GoogleAdsClient.load_from_dict(cfg, version=_API_VERSION)


def _customer_id() -> str:
    cid = _env("GOOGLE_ADS_CUSTOMER_ID") or _env("GOOGLE_ADS_LOGIN_CUSTOMER_ID")
    if not cid:
        raise GoogleAdsNotConfigured("GOOGLE_ADS_CUSTOMER_ID not set")
    return cid.replace("-", "")


def _micros(amount: float) -> int:
    """Currency units -> micros (Google's money unit). $10 -> 10_000_000."""
    return int(round(amount * 1_000_000))


# --------------------------------------------------------------------------
# Lookups — resolve names to resource names at runtime (robust vs hardcoding).
# --------------------------------------------------------------------------
def resolve_geo_target(client, customer_id: str, location_name: str) -> str:
    """'Azerbaijan' -> geoTargetConstants/<id> resource name."""
    svc = client.get_service("GeoTargetConstantService")
    req = client.get_type("SuggestGeoTargetConstantsRequest")
    req.locale = "en"
    req.location_names.names.append(location_name)
    resp = svc.suggest_geo_target_constants(req)
    for s in resp.geo_target_constant_suggestions:
        if s.geo_target_constant.country_code:  # first country-level match
            return s.geo_target_constant.resource_name
    raise ValueError(f"No geo target found for {location_name!r}")


def resolve_language(client, code: str) -> str:
    """ISO language code (e.g. 'az', 'ru') -> languageConstants/<id>."""
    ga = client.get_service("GoogleAdsService")
    query = (
        "SELECT language_constant.resource_name, language_constant.code "
        f"FROM language_constant WHERE language_constant.code = '{code}'"
    )
    for row in ga.search(customer_id=_customer_id(), query=query):
        return row.language_constant.resource_name
    raise ValueError(f"No language constant for code {code!r}")


def find_user_interests(client, customer_id: str, terms: list[str]) -> list[dict]:
    """Search in-market / affinity audiences by name fragment.

    Returns [{id, name, taxonomy}] — feed the ids into the spec's
    ``audience_user_interest_ids`` after eyeballing them. Kept as a helper so
    audience selection stays auditable rather than guessing criterion ids.
    """
    ga = client.get_service("GoogleAdsService")
    out: list[dict] = []
    for term in terms:
        q = (
            "SELECT user_interest.user_interest_id, user_interest.name, "
            "user_interest.taxonomy_type FROM user_interest "
            f"WHERE user_interest.name LIKE '%{term}%' "
            "AND user_interest.taxonomy_type IN ('IN_MARKET', 'AFFINITY_CATEGORY') "
            "LIMIT 25"
        )
        for row in ga.search(customer_id=customer_id, query=q):
            ui = row.user_interest
            out.append(
                {
                    "id": ui.user_interest_id,
                    "name": ui.name,
                    "taxonomy": ui.taxonomy_type.name,
                }
            )
    return out


# --------------------------------------------------------------------------
# Campaign spec + creation
# --------------------------------------------------------------------------
@dataclass
class DisplayCampaignSpec:
    name: str
    final_url: str                       # where clicks go (the IG post)
    daily_budget: float                  # currency units, e.g. 10.0
    location_name: str = "Azerbaijan"
    language_codes: list[str] = field(default_factory=lambda: ["az", "ru"])
    age_min: int = 25
    age_max: int = 60
    business_name: str = "Xalq Sigorta"
    headlines: list[str] = field(default_factory=list)        # <=30 chars each
    long_headline: str = ""                                   # <=90 chars
    descriptions: list[str] = field(default_factory=list)     # <=90 chars each
    square_image: str = ""               # path, 1:1
    landscape_image: str = ""            # path, 1.91:1
    logo_image: str = ""                 # path, 1:1
    audience_user_interest_ids: list[int] = field(default_factory=list)
    start_date: str = ""                 # 'YYYYMMDD'; '' = today
    end_date: str = ""                   # 'YYYYMMDD'; '' = no end


def _upload_image_asset(client, customer_id: str, path: str, name: str) -> str:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(
            f"Missing image asset: {path} (see GOOGLE_ADS_SETUP.md 'creative')"
        )
    asset_service = client.get_service("AssetService")
    op = client.get_type("AssetOperation")
    asset = op.create
    asset.name = name
    asset.type_ = client.enums.AssetTypeEnum.IMAGE
    asset.image_asset.data = p.read_bytes()
    resp = asset_service.mutate_assets(customer_id=customer_id, operations=[op])
    return resp.results[0].resource_name


def create_display_campaign(spec: DisplayCampaignSpec) -> dict:
    """Create a PAUSED Display campaign + ad group + responsive display ad.

    Returns a dict of the created resource names. PAUSED on purpose: review in
    the UI (or call enable_campaign) before any spend. No money moves here.
    """
    client = build_client()
    customer_id = _customer_id()

    # 1) Daily budget (non-shared).
    budget_service = client.get_service("CampaignBudgetService")
    b_op = client.get_type("CampaignBudgetOperation")
    budget = b_op.create
    budget.name = f"{spec.name} — budget"
    budget.amount_micros = _micros(spec.daily_budget)
    budget.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD
    budget.explicitly_shared = False
    budget_res = budget_service.mutate_campaign_budgets(
        customer_id=customer_id, operations=[b_op]
    ).results[0].resource_name

    # 2) Campaign — Display, PAUSED, Maximize Clicks (target_spend).
    campaign_service = client.get_service("CampaignService")
    c_op = client.get_type("CampaignOperation")
    camp = c_op.create
    camp.name = spec.name
    camp.advertising_channel_type = client.enums.AdvertisingChannelTypeEnum.DISPLAY
    camp.status = client.enums.CampaignStatusEnum.PAUSED  # checkpoint
    camp.campaign_budget = budget_res
    camp.target_spend = client.get_type("TargetSpend")    # = Maximize clicks
    camp.network_settings.target_google_search = False
    camp.network_settings.target_search_network = False
    camp.network_settings.target_content_network = True
    camp.network_settings.target_partner_search_network = False
    if spec.start_date:
        camp.start_date = spec.start_date
    if spec.end_date:
        camp.end_date = spec.end_date
    campaign_res = campaign_service.mutate_campaigns(
        customer_id=customer_id, operations=[c_op]
    ).results[0].resource_name

    # 3) Campaign criteria — location + languages.
    cc_service = client.get_service("CampaignCriterionService")
    cc_ops = []
    geo_res = resolve_geo_target(client, customer_id, spec.location_name)
    geo_op = client.get_type("CampaignCriterionOperation")
    geo_op.create.campaign = campaign_res
    geo_op.create.location.geo_target_constant = geo_res
    cc_ops.append(geo_op)
    for code in spec.language_codes:
        lang_op = client.get_type("CampaignCriterionOperation")
        lang_op.create.campaign = campaign_res
        lang_op.create.language.language_constant = resolve_language(client, code)
        cc_ops.append(lang_op)
    cc_service.mutate_campaign_criteria(customer_id=customer_id, operations=cc_ops)

    # 4) Ad group.
    ag_service = client.get_service("AdGroupService")
    ag_op = client.get_type("AdGroupOperation")
    ag = ag_op.create
    ag.name = f"{spec.name} — ad group"
    ag.campaign = campaign_res
    ag.type_ = client.enums.AdGroupTypeEnum.DISPLAY_STANDARD
    ag.status = client.enums.AdGroupStatusEnum.ENABLED  # gated by PAUSED campaign
    ag_res = ag_service.mutate_ad_groups(
        customer_id=customer_id, operations=[ag_op]
    ).results[0].resource_name

    # 5) Ad group criteria — age range + audiences (in-market / affinity).
    agc_service = client.get_service("AdGroupCriterionService")
    agc_ops = []
    age_enum = client.enums.AgeRangeTypeEnum
    for label in _age_range_labels(spec.age_min, spec.age_max):
        a_op = client.get_type("AdGroupCriterionOperation")
        a_op.create.ad_group = ag_res
        a_op.create.age_range.type_ = getattr(age_enum, label)
        agc_ops.append(a_op)
    for ui_id in spec.audience_user_interest_ids:
        u_op = client.get_type("AdGroupCriterionOperation")
        u_op.create.ad_group = ag_res
        u_op.create.user_interest.user_interest_category = (
            f"customers/{customer_id}/userInterests/{ui_id}"
        )
        agc_ops.append(u_op)
    if agc_ops:
        agc_service.mutate_ad_group_criteria(
            customer_id=customer_id, operations=agc_ops
        )

    # 6) Responsive display ad.
    square = _upload_image_asset(client, customer_id, spec.square_image, f"{spec.name} sq")
    landscape = _upload_image_asset(client, customer_id, spec.landscape_image, f"{spec.name} ls")
    logo = _upload_image_asset(client, customer_id, spec.logo_image, f"{spec.name} logo")

    aga_service = client.get_service("AdGroupAdService")
    aga_op = client.get_type("AdGroupAdOperation")
    aga = aga_op.create
    aga.ad_group = ag_res
    aga.status = client.enums.AdGroupAdStatusEnum.ENABLED
    ad = aga.ad
    ad.final_urls.append(spec.final_url)
    rda = ad.responsive_display_ad
    for text in spec.headlines:
        h = client.get_type("AdTextAsset")
        h.text = text
        rda.headlines.append(h)
    rda.long_headline.text = spec.long_headline
    for text in spec.descriptions:
        d = client.get_type("AdTextAsset")
        d.text = text
        rda.descriptions.append(d)
    rda.business_name = spec.business_name
    _attach_image(client, rda.marketing_images, landscape)
    _attach_image(client, rda.square_marketing_images, square)
    _attach_image(client, rda.logo_images, logo)
    ad_res = aga_service.mutate_ad_group_ads(
        customer_id=customer_id, operations=[aga_op]
    ).results[0].resource_name

    return {
        "status": "PAUSED — review then enable (no spend yet)",
        "campaign": campaign_res,
        "budget": budget_res,
        "ad_group": ag_res,
        "ad": ad_res,
    }


def _attach_image(client, collection, asset_resource: str) -> None:
    img = client.get_type("AdImageAsset")
    img.asset = asset_resource
    collection.append(img)


def _age_range_labels(age_min: int, age_max: int) -> list[str]:
    """Map a min/max to Google's fixed age-range enum buckets."""
    buckets = [
        (18, 24, "AGE_RANGE_18_24"),
        (25, 34, "AGE_RANGE_25_34"),
        (35, 44, "AGE_RANGE_35_44"),
        (45, 54, "AGE_RANGE_45_54"),
        (55, 64, "AGE_RANGE_55_64"),
        (65, 200, "AGE_RANGE_65_UP"),
    ]
    return [lbl for lo, hi, lbl in buckets if hi >= age_min and lo <= age_max]


def enable_campaign(campaign_resource: str) -> str:
    """Flip a PAUSED campaign to ENABLED. This is the spend checkpoint —
    only call after a human has reviewed and approved."""
    client = build_client()
    service = client.get_service("CampaignService")
    op = client.get_type("CampaignOperation")
    op.update.resource_name = campaign_resource
    op.update.status = client.enums.CampaignStatusEnum.ENABLED
    client.copy_from(
        op.update_mask,
        client.get_type("FieldMask")(paths=["status"]),
    )
    res = service.mutate_campaigns(customer_id=_customer_id(), operations=[op])
    return res.results[0].resource_name

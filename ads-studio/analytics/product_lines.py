"""Product-line + creative-format classifier.

Meta campaign/ad names are not tagged by product line in any structured field —
Xalq Sığorta's naming is a human-readable mix ("Kasko - website conversion",
"Travel_insurance_story", "Gurcustan sale post", "Sığorta Maariflənməsi 2-ci
rüb"). This is a best-effort keyword classifier so downstream features (the
narrative report, the Kreativ DNA leaderboard) can group ad-level performance
by product and creative format without a manual tagging step. It is a heuristic,
not ground truth — an ad landing in "Digər" just means no keyword matched.
"""

from __future__ import annotations

PRODUCT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "KASKO": ("kasko",),
    "Səyahət": ("travel", "səyahət", "seyahet", "gurcustan", "gürcüstan"),
    "Həyat": ("həyat", "hayat", "life"),
    "Əmlak": ("əmlak", "emlak", "daşınmaz", "dasinmaz", "mənzil", "menzil"),
    "Tibbi": ("tibbi", "sağlamlıq", "saglamliq", "health"),
    "Maarifləndirmə": ("maarif", "awareness"),
}

FORMAT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Story": ("story", "stories"),
    "Post": ("post",),
    "Video": ("video", "reels"),
}


def classify_product(name: str) -> str:
    n = (name or "").lower()
    for product, keywords in PRODUCT_KEYWORDS.items():
        if any(kw in n for kw in keywords):
            return product
    return "Digər"


def classify_format(name: str) -> str:
    n = (name or "").lower()
    for fmt, keywords in FORMAT_KEYWORDS.items():
        if any(kw in n for kw in keywords):
            return fmt
    return "Qarışıq"


def tag(name: str) -> dict:
    return {"product": classify_product(name), "format": classify_format(name)}

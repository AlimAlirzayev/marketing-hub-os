"""Central brand identity — the ONE place the system's brand lives.

Why this exists: brand strings (name, system name, site) are hardcoded across the
codebase (~557 spots in 215 files). That makes a second deployment — e.g. a generic
"global" build vs the Xalq Sigorta build — fight the corporate one on every
`git pull`. The fix (12-factor: config out of code): choose the brand with ONE env
var, `BRAND`, and read every brand value from here. Same code on every machine;
only the BRAND value differs per deployment → clean bidirectional git sync.

Usage:
    from brand import BRAND
    BRAND.name         # "Xalq Sigorta"
    BRAND.system_name  # "Xalq Insurance Digital OS"

Switch a deployment (e.g. on the global server): set  BRAND=global  in its .env.
Visual DNA (colors, logo, voice) stays in each brand's brand_kit — `BRAND.brand_kit`
points at it — so this file owns identity, not curated creative prose.

Migrate hardcoded strings to BRAND.* incrementally; see docs/BRANDING.md.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Brand:
    key: str            # profile slug, matches the BRAND env value
    name: str           # marketing / company name
    system_name: str    # the OS product name shown in UI, prompts, reports
    industry: str
    website: str        # "" when not applicable
    locale: str         # default user-facing language (az / en / ...)
    brand_kit: str      # path to this brand's visual+voice DNA (single source)


# Add or curate a deployment by adding a profile here. Keep keys lowercase.
_PROFILES: dict[str, Brand] = {
    "xalq": Brand(
        key="xalq",
        name="Xalq Sigorta",
        system_name="Xalq Insurance Digital OS",
        industry="insurance",
        website="xalqsigorta.az",
        locale="az",
        brand_kit="social-studio/brand_kit",
    ),
    "global": Brand(
        key="global",
        name="Marketing Hub",
        system_name="Marketing Hub OS",
        industry="marketing",
        website="",
        locale="en",
        brand_kit="social-studio/brand_kit",  # point at a global kit once curated
    ),
}

DEFAULT_BRAND = "xalq"


def active() -> Brand:
    """The brand selected by the BRAND env var (default: xalq). Unknown → default."""
    key = (os.getenv("BRAND") or DEFAULT_BRAND).strip().lower()
    return _PROFILES.get(key, _PROFILES[DEFAULT_BRAND])


# Import-and-use singleton: `from brand import BRAND`.
BRAND = active()


if __name__ == "__main__":
    b = BRAND
    print(f"Active BRAND={b.key}")
    print(f"  name        : {b.name}")
    print(f"  system_name : {b.system_name}")
    print(f"  industry    : {b.industry}")
    print(f"  website     : {b.website or '(none)'}")
    print(f"  locale      : {b.locale}")
    print(f"  brand_kit   : {b.brand_kit}")
    print(f"Available profiles: {', '.join(_PROFILES)}")

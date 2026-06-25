"""Pure key detectors — no browser, no network, fully unit-testable.

The browser agent dumps page HTML / input values / network bodies here and asks
"is there a credential in this blob?". Keeping detection pure means the fragile
part (a live, JS-heavy dashboard DOM) is isolated from the part we can prove.

RapidAPI application keys carry two very characteristic markers — an ``msh``
segment followed later by a ``jsn`` segment inside one alphanumeric run
(e.g. ``...mshAbC123...p1...jsn00112233...``). Anchoring on both markers makes the
match specific enough to never fire on ordinary prose.
"""

from __future__ import annotations

import re

# msh ... jsn inside a single alphanumeric run = RapidAPI application key shape.
_RAPIDAPI_KEY = re.compile(r"[A-Za-z0-9]{6,}msh[A-Za-z0-9]+jsn[A-Za-z0-9]{4,}")


def find_rapidapi_keys(text: str | None) -> list[str]:
    if not text:
        return []
    out: list[str] = []
    for m in _RAPIDAPI_KEY.findall(text):
        if m not in out:
            out.append(m)
    return out


def first_rapidapi_key(text: str | None) -> str:
    keys = find_rapidapi_keys(text)
    return keys[0] if keys else ""


# Registry so new providers (their own key shapes) plug in without new code paths.
DETECTORS = {
    "rapidapi": find_rapidapi_keys,
}


def detect(provider: str, text: str | None) -> list[str]:
    fn = DETECTORS.get(provider)
    return fn(text) if fn else []

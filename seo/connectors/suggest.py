"""Google Autocomplete (Suggest) — free, keyless keyword research.

The single most valuable free SEO data source: Google's own query completions,
localized to Azerbaijan (hl=az, gl=az). We expand a seed three ways —
raw completions, question-prefixed ("nə/necə/niyə ..."), and alphabet-soup
(seed + each letter) — to surface the long-tail the way pro tools do, at zero cost.
"""

from __future__ import annotations

import json
import string
import time
from concurrent.futures import ThreadPoolExecutor

import requests

_ENDPOINT = "https://suggestqueries.google.com/complete/search"
_UA = {"User-Agent": "Mozilla/5.0"}

# Azerbaijani question / modifier seeds that unlock informational + commercial long-tail
AZ_QUESTIONS = ["nə", "nədir", "necə", "niyə", "harada", "hansı", "nə qədər", "kim", "nə vaxt"]
AZ_MODIFIERS = ["qiymət", "qiyməti", "onlayn", "ən ucuz", "kalkulyator", "hesablama",
                "şərtləri", "haqqında", "2026", "bakı"]
AZ_ALPHABET = "abcçdeəfgğhxıijkqlmnoöprsştuüvyz"


def suggest(query: str, hl: str = "az", gl: str = "az") -> list[str]:
    """Raw Google completions for one query. Never raises — [] on failure."""
    try:
        r = requests.get(_ENDPOINT, params={"client": "firefox", "q": query, "hl": hl, "gl": gl},
                         headers=_UA, timeout=8)
        if r.status_code != 200:
            return []
        data = json.loads(r.text)
        return [s for s in data[1] if isinstance(s, str)]
    except (requests.RequestException, ValueError, IndexError):
        return []


def expand(seed: str, *, hl: str = "az", gl: str = "az",
           questions: bool = True, modifiers: bool = True, alphabet: bool = True,
           max_keywords: int = 200) -> list[str]:
    """Fan out a seed into a de-duplicated long-tail keyword list."""
    seed = seed.strip()
    queries = [seed]
    if questions:
        queries += [f"{q} {seed}" for q in AZ_QUESTIONS] + [f"{seed} {q}" for q in AZ_QUESTIONS]
    if modifiers:
        queries += [f"{seed} {m}" for m in AZ_MODIFIERS]
    if alphabet:
        queries += [f"{seed} {c}" for c in AZ_ALPHABET]

    seen: dict[str, None] = {}
    # concurrent fan-out — each call is small and independent
    with ThreadPoolExecutor(max_workers=8) as ex:
        for res in ex.map(lambda q: suggest(q, hl, gl), queries):
            for s in res:
                s = s.strip().lower()
                if s and s not in seen:
                    seen[s] = None
            if len(seen) >= max_keywords:
                break
    # keep the seed's own completions first-ish; simple ordering by length then alpha
    kws = list(seen.keys())
    kws.sort(key=lambda x: (len(x), x))
    return kws[:max_keywords]

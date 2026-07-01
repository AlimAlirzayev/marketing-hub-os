"""Keyword research: Google-Suggest long-tail → LLM clustering + search intent.

Free-first: the keyword harvest is 100% keyless (Google Autocomplete). The LLM
only adds the *intelligence layer* — grouping the long-tail into topic clusters
and tagging each with search intent, so the operator sees a content strategy,
not a word dump. Without an LLM provider it degrades to a clean flat list.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .. import llm
from ..connectors import suggest

INTENTS = {"informational", "commercial", "transactional", "navigational"}
INTENT_AZ = {
    "informational": "Məlumat (öyrənmə)",
    "commercial": "Kommersiya (müqayisə)",
    "transactional": "Alış (konversiya)",
    "navigational": "Naviqasiya (brend)",
}


@dataclass
class Cluster:
    name: str
    intent: str
    primary: str
    keywords: list[str] = field(default_factory=list)

    @property
    def intent_az(self) -> str:
        return INTENT_AZ.get(self.intent, self.intent)


@dataclass
class ResearchResult:
    seed: str
    keywords: list[str]
    clusters: list[Cluster] = field(default_factory=list)
    intelligence: str = "raw"        # "llm" | "raw"
    hl: str = "az"
    gl: str = "az"

    @property
    def total(self) -> int:
        return len(self.keywords)


_CLUSTER_PROMPT = """Aşağıda bir SEO açar sözü ("{seed}") üçün Google Autocomplete-dən çıxarılmış
Azərbaycan dilində uzun-quyruq (long-tail) sorğular var. Onları 4-8 mövzu
klasterinə qrupla. Hər klaster üçün axtarış niyyətini (search intent) təyin et.

Yalnız bu JSON formatında cavab ver:
{{"clusters":[{{"name":"klasterin qısa adı","intent":"informational|commercial|transactional|navigational","primary_keyword":"klasterin ən dəyərli açar sözü","keywords":["...","..."]}}]}}

Açar sözlər:
{kw}
"""


def research_keywords(seed: str, *, hl: str = "az", gl: str = "az",
                      cluster: bool = True, max_keywords: int = 120) -> ResearchResult:
    kws = suggest.expand(seed, hl=hl, gl=gl, max_keywords=max_keywords)
    res = ResearchResult(seed=seed, keywords=kws, hl=hl, gl=gl)
    if not kws or not cluster or not llm.available():
        return res

    data = llm.ask_json(_CLUSTER_PROMPT.format(seed=seed, kw="\n".join(kws)))
    if not data or "clusters" not in data:
        return res
    clusters: list[Cluster] = []
    for c in data.get("clusters", []):
        if not isinstance(c, dict):
            continue
        intent = str(c.get("intent", "")).lower().strip()
        if intent not in INTENTS:
            intent = "informational"
        clusters.append(Cluster(
            name=str(c.get("name", "")).strip() or "Klaster",
            intent=intent,
            primary=str(c.get("primary_keyword", "")).strip(),
            keywords=[str(k).strip() for k in c.get("keywords", []) if str(k).strip()],
        ))
    if clusters:
        res.clusters = clusters
        res.intelligence = "llm"
    return res

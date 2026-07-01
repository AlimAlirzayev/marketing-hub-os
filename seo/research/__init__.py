"""Research engine — keyword discovery, clustering, intent, and SERP gap."""

from .gap import Competitor, GapResult, analyze_gap
from .keywords import Cluster, ResearchResult, research_keywords

__all__ = ["Cluster", "ResearchResult", "research_keywords",
           "Competitor", "GapResult", "analyze_gap"]

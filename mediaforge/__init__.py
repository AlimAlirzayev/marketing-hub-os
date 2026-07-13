"""Media Studio — the creative-director brain of Ramin-OS media production.

One sentence in ("make me a 10s travel-insurance promo with seedance 2.5"),
a full, directed, professional creative package out: brief, storyboard,
emotional arc, cinematic technique plan, model decision, a compiled FLORA
prompt, and a ready-to-fire generation command with a cost gate.

Media Studio does not spend credits or post anything on its own. It thinks like a
senior creative director + producer, assembles everything up to the single paid
generation step, and hands that step to a human/governed OAuth checkpoint.

Layers:
    knowledge.py  — durable creative intelligence (frameworks, emotion arcs,
                    cinematic techniques, insurance-category playbooks).
    models.py     — FLORA video model catalog + honest alias resolver.
    director.py   — the brain: parse a request, then author a validated brief.
    pipeline.py   — orchestrate brief -> compiled prompt -> package -> cost gate.
    server.py     — FastAPI + single-page studio front-end.
"""

from __future__ import annotations

__all__ = ["knowledge", "models", "director", "pipeline", "ugc"]

__version__ = "0.2.0"

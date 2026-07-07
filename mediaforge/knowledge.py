"""Durable creative intelligence for MediaForge.

This is the part that makes the system feel like a marketer's brain lighting up.
When a human creative director hears "travel-insurance promo", scenes,
emotions, and techniques fire instantly from experience. We encode that
experience here as structured, reusable knowledge — not one-off prompt text —
so every job inherits it and the system keeps getting sharper.

Everything here is brand-agnostic craft knowledge plus Xalq Sigorta brand DNA
that already lives in this repo (social-studio/brand_kit, existing briefs). No
prices, dates, or claims are invented here; those stay deterministic overlays
confirmed by a human.
"""

from __future__ import annotations

from typing import Any


# --------------------------------------------------------------------------- #
# 1. COPY / STORY FRAMEWORKS — the skeleton a 10-second ad hangs on.
# --------------------------------------------------------------------------- #
FRAMEWORKS: dict[str, dict[str, Any]] = {
    "pas": {
        "name": "Problem — Agitate — Solve",
        "best_for": "risk, safety, insurance, 'what if it goes wrong' stories",
        "beats": ["name a felt risk", "let it sting for a beat", "arrive as calm relief", "invite action"],
        "why": "Insurance sells peace of mind; PAS earns the relief the brand delivers.",
    },
    "bab": {
        "name": "Before — After — Bridge",
        "best_for": "transformation, freedom, upgrade stories",
        "beats": ["the anxious 'before'", "the liberated 'after'", "the brand as the bridge", "CTA"],
        "why": "Shows the emotional gap the product closes without lecturing.",
    },
    "hso": {
        "name": "Hook — Story — Offer",
        "best_for": "paid social / Reels where the first second decides everything",
        "beats": ["thumb-stopping hook", "a 4-second human moment", "single-minded offer", "CTA settle"],
        "why": "Built for the scroll; front-loads intrigue, ends on one clear ask.",
    },
    "storybrand": {
        "name": "Hero — Guide — Plan — Success",
        "best_for": "brand-led promos where the customer is the hero",
        "beats": ["customer is the hero", "brand is the calm guide", "one simple plan", "life goes right"],
        "why": "Positions the brand as the trusted guardian, never the loud hero.",
    },
    "aida": {
        "name": "Attention — Interest — Desire — Action",
        "best_for": "classic offer pushes with a concrete deal",
        "beats": ["stop the scroll", "make it relevant", "make it wanted", "make it easy"],
        "why": "Reliable spine when there is a real, confirmed offer to push.",
    },
}


# --------------------------------------------------------------------------- #
# 2. EMOTIONAL ARCS — the feeling curve across ~10 seconds. This is the
#    "duyğu / hiss" layer. A promo without an arc is just footage.
# --------------------------------------------------------------------------- #
EMOTION_ARCS: dict[str, dict[str, Any]] = {
    "wonder_to_safety": {
        "name": "Wonder → tiny tension → protected calm",
        "curve": ["awe / freedom", "a small wobble of risk", "invisible safety net", "warm resolve"],
        "curve_az": ["heyranlıq / azadlıq", "kiçik risk titrəyişi", "görünməz təhlükəsizlik", "isti sakitlik"],
        "color_arc": "warm golden open → slightly desaturated tension → warm, clean resolve",
        "best_for": "travel, health, life — 'keep living, we've got the rest'",
    },
    "pride_of_ownership": {
        "name": "Pride → threat → guarded → confident",
        "curve": ["pride in the thing you love", "a hint it could be lost", "shielded", "confidence"],
        "curve_az": ["sevdiyinlə qürur", "itirmə təhlükəsi", "qorunma", "inam"],
        "color_arc": "rich saturated → cool threat flash → stabilized clean",
        "best_for": "auto / KASKO / property",
    },
    "relief_reveal": {
        "name": "Quiet worry → reveal → relief",
        "curve": ["low-key everyday worry", "the reveal that it's handled", "exhale", "smile"],
        "curve_az": ["gündəlik narahatlıq", "hər şeyin həll olduğu an", "rahat nəfəs", "təbəssüm"],
        "color_arc": "muted → brightening → warm",
        "best_for": "family, health, general trust-building",
    },
}


# --------------------------------------------------------------------------- #
# 3. CINEMATIC TECHNIQUE LIBRARY — the "texnika / üslub" layer. These are the
#    concrete craft levers a director pulls. The brief should *choose* from
#    here, not vaguely say "nice motion".
# --------------------------------------------------------------------------- #
TECHNIQUES: dict[str, list[str]] = {
    "shot_types": [
        "extreme close-up on a detail (eyes, hands, a passport stamp)",
        "hero wide establishing the world",
        "over-the-shoulder POV that puts the viewer in the moment",
        "macro texture insert (fabric, water droplet, boarding pass)",
        "clean product/brand-card beauty shot for the end frame",
    ],
    "camera_moves": [
        "slow push-in to build intimacy",
        "gentle parallax / dolly for depth without shake",
        "match cut on motion between two beats",
        "whip-driven transition disguised as a real movement",
        "locked-off stable end frame for the last ~0.8s (CTA readability)",
    ],
    "lighting_color": [
        "golden-hour warmth for freedom / aspiration",
        "soft desaturation on the risk beat, never ugly",
        "clean high-key resolve when the brand arrives as relief",
        "brand-accent color used only as a deliberate punctuation, not a wash",
    ],
    "pacing_10s": [
        "0.0–1.5s hook: one strong image, no clutter, motion already alive",
        "1.5–4.0s story: a single human/emotional moment, not three",
        "4.0–7.5s turn: the brand enters as the calm answer",
        "7.5–10.0s land: stable brand + CTA, hold the last beat",
    ],
    "sound_design": [
        "one rising motif that resolves on the brand beat",
        "a single diegetic accent (shutter, seatbelt click, wave) for realism",
        "leave 'silence' room so the CTA reads even muted (social autoplay)",
    ],
    "editing_tricks": [
        "invisible match cut to compress time",
        "one satisfying motion payoff (a seatbelt clicks, a case zips shut)",
        "negative space held on-screen for the deterministic text overlay",
    ],
}


# --------------------------------------------------------------------------- #
# 4. CATEGORY PLAYBOOKS — domain instinct per insurance line. This is what a
#    seasoned insurance marketer 'sees' the instant they hear the product.
#    Kept message-led and emotional; no invented prices, dates, or terms.
# --------------------------------------------------------------------------- #
CATEGORY_PLAYBOOKS: dict[str, dict[str, Any]] = {
    "travel": {
        "aliases": ["travel", "səyahət", "seyahet", "seyahət", "tourism", "trip", "abroad", "xarici"],
        "product": "Səyahət sığortası (travel insurance)",
        "core_truth": "People buy travel insurance to keep the adventure feeling free — the promise is 'go, enjoy, we carry the risk'.",
        "core_truth_az": "İnsanlar səyahət sığortasını macəranı azad hiss etmək üçün alır — vəd budur: 'get, həzz al, riski biz daşıyırıq'.",
        "hero_emotion": "freedom without fear",
        "recommended_framework": "bab",
        "recommended_arc": "wonder_to_safety",
        "signature_scenes": [
            "a passport / boarding pass and a window seat as the plane lifts",
            "a small 'what if' wobble — a spilled suitcase, a missed connection, a rained-out plan",
            "the invisible safety net moment: a calm hand, a settled breath, the trip continues",
            "a couple/solo traveler smiling at a new skyline, fully present",
        ],
        "risk_moments": ["lost luggage", "a minor slip abroad", "a delayed flight", "sudden illness far from home"],
        "avoid": ["fear-mongering imagery", "hospital gore", "anything that makes travel feel scary rather than free"],
        "single_minded": "Səyahət et, qalanını bizə burax — Xalq Sığorta yanındadır.",
    },
    "auto": {
        "aliases": ["auto", "kasko", "avto", "car", "avtomobil", "casco", "vehicle"],
        "product": "Avtomobil / KASKO sığortası",
        "core_truth": "The car is pride and daily freedom; the fear is losing it to one bad moment.",
        "core_truth_az": "Avtomobil qürur və gündəlik azadlıqdır; qorxu isə onu bir pis anda itirməkdir.",
        "hero_emotion": "pride, protected",
        "recommended_framework": "pas",
        "recommended_arc": "pride_of_ownership",
        "signature_scenes": [
            "the car detailed, loved, catching light",
            "a near-miss suggested, never gory",
            "the shield / calm resolve",
            "driver confident, keys in hand",
        ],
        "risk_moments": ["a parking scrape", "hail", "a sudden stop in traffic"],
        "avoid": ["graphic crashes", "blaming the driver"],
        "single_minded": "Sevdiyin avtomobili bir anlıq bədbəxtlikdən qoru.",
    },
    "health": {
        "aliases": ["health", "saglamliq", "sağlamlıq", "medical", "tibbi"],
        "product": "Sağlamlıq sığortası",
        "core_truth": "Health cover is really about protecting the people you love and the moments with them.",
        "core_truth_az": "Sağlamlıq sığortası əslində sevdiyin insanları və onlarla anları qorumaqdır.",
        "hero_emotion": "reassurance for family",
        "recommended_framework": "storybrand",
        "recommended_arc": "relief_reveal",
        "signature_scenes": [
            "an ordinary tender family moment",
            "a quiet worry surfaces",
            "the reveal that it's handled",
            "the family moment continues, lighter",
        ],
        "risk_moments": ["an unexpected clinic visit", "a child's fever at night"],
        "avoid": ["clinical coldness", "fear of illness over love of family"],
        "single_minded": "Sağlamlığın arxasında dayanan sığorta.",
    },
    "property": {
        "aliases": ["property", "emlak", "əmlak", "home", "ev", "mənzil", "menzil"],
        "product": "Əmlak / ev sığortası",
        "core_truth": "Home is safety itself; insuring it protects the feeling of home, not just walls.",
        "core_truth_az": "Ev təhlükəsizliyin özüdür; onu sığortalamaq divarları yox, ev hissini qoruyur.",
        "hero_emotion": "sanctuary preserved",
        "recommended_framework": "pas",
        "recommended_arc": "relief_reveal",
        "signature_scenes": [
            "warm home details — light through a window, a family table",
            "a hint of a household mishap",
            "calm resolution",
            "home glowing, safe",
        ],
        "risk_moments": ["a burst pipe", "a small fire scare", "a break-in worry"],
        "avoid": ["disaster-movie drama"],
        "single_minded": "Evin — ən qorunmalı yerin.",
    },
    "generic": {
        "aliases": [],
        "product": "Sığorta",
        "core_truth": "Insurance sells calm: the freedom to live because someone carries the risk.",
        "core_truth_az": "Sığorta sakitlik satır: kimsə riski daşıdığı üçün yaşamaq azadlığı.",
        "hero_emotion": "peace of mind",
        "recommended_framework": "hso",
        "recommended_arc": "relief_reveal",
        "signature_scenes": [
            "a real human moment worth protecting",
            "a hint of what could go wrong",
            "the brand as quiet guardian",
            "life continues, confident",
        ],
        "risk_moments": ["an everyday 'what if'"],
        "avoid": ["fear over reassurance", "corporate coldness"],
        "single_minded": "Yaşamağa davam et — qalanını bizə burax.",
    },
}


# --------------------------------------------------------------------------- #
# 5. XALQ SIGORTA BRAND DNA — reused from existing repo briefs, not invented.
# --------------------------------------------------------------------------- #
BRAND_DNA: dict[str, Any] = {
    "name": "Xalq Sigorta",
    "identity_source": "social-studio/brand_kit/brand.md",
    "tone": ["premium", "trust-led", "clear", "human", "not clickbait"],
    "palette": ["#E31E24", "#2B2A29", "#FFFFFF", "#149040"],
    "typography": ["Inter Tight or Manrope for headlines", "Inter for body/legal"],
    "rules": [
        "Xalq Sigorta logo is a deterministic overlay or approved artwork only.",
        "Campaign terms, dates, prices, and CTA must be deterministic overlays.",
        "No AI-generated readable Azerbaijani copy in the foreground.",
        "Keep red as a deliberate accent, not a full wash.",
    ],
}


# --------------------------------------------------------------------------- #
# 6. STYLE BIBLES — the cinematography DNA that keeps every keyframe and every
#    beat in ONE visual world. This is what separates directed film from
#    "AI slop": lens, light, grade, texture and composition are decided once
#    and injected into every single generation.
# --------------------------------------------------------------------------- #
STYLE_BIBLES: dict[str, dict[str, str]] = {
    "golden_hour_premium": {
        "name": "Golden Hour Premium",
        "look": (
            "shot on a cinema camera with a 35mm prime lens, shallow depth of field, "
            "warm golden-hour sunlight with soft practical highlights, gentle film-emulation "
            "color grade with lifted blacks, natural skin tones, subtle grain"
        ),
        "palette": "warm amber and honey light, soft teal-neutral shadows, one deliberate deep-red accent allowed",
        "composition": (
            "clean negative space in the upper third and lower quarter of the frame for later "
            "text overlays, subject anchored on a rule-of-thirds line, uncluttered background"
        ),
        "texture": "real-world tactile detail — fabric weave, paper edges, window reflections",
        "best_for": "travel, relief, family warmth",
    },
    "guarded_luxe": {
        "name": "Guarded Luxe",
        "look": (
            "shot on a cinema camera with a 50mm prime lens, controlled studio-meets-street lighting, "
            "rich contrast with deep clean shadows, polished automotive reflections, crisp specular highlights"
        ),
        "palette": "graphite, silver and charcoal with one deliberate deep-red accent",
        "composition": "low hero angles, symmetric framing, clean negative space in the upper third for overlays",
        "texture": "paint gloss, brushed metal, wet asphalt reflections",
        "best_for": "auto / KASKO, property protection",
    },
    "soft_daylight_docu": {
        "name": "Soft Daylight Documentary",
        "look": (
            "handheld documentary intimacy on a 28mm lens, soft overcast daylight through windows, "
            "airy high-key grade with gentle contrast, honest natural color"
        ),
        "palette": "soft whites, warm wood, sage green accents",
        "composition": "eye-level human framing, breathing room around subjects, negative space kept for overlays",
        "texture": "home textiles, morning light dust, skin detail",
        "best_for": "health, family, trust-building",
    },
}

# Category -> default style bible.
_CATEGORY_STYLE = {
    "travel": "golden_hour_premium",
    "auto": "guarded_luxe",
    "health": "soft_daylight_docu",
    "property": "soft_daylight_docu",
    "generic": "golden_hour_premium",
}

# The universal negative constraints for every generated pixel (keyframe or video).
NO_TEXT_RULES = (
    "No readable text anywhere in the frame, no lettering on documents or signs, "
    "no captions, no subtitles, no logos, no brand marks, no watermark, no UI elements."
)


def style_bible_for(category: str) -> dict[str, str]:
    return STYLE_BIBLES[_CATEGORY_STYLE.get(category, "golden_hour_premium")]


def character_block(category: str) -> str:
    """A fixed protagonist description reused across every keyframe/beat so the
    hero stays the same person through the whole film."""
    blocks = {
        "travel": (
            "The protagonist: a woman in her early 30s with shoulder-length dark hair, "
            "wearing a cream linen shirt and a light camel coat, calm confident presence"
        ),
        "auto": (
            "The protagonist: a man in his late 30s with short dark hair and a navy "
            "wool coat, composed and self-assured"
        ),
        "health": (
            "The protagonists: a young mother with tied-back dark hair in a soft beige "
            "sweater and her 6-year-old daughter in a mustard cardigan"
        ),
        "property": (
            "The protagonists: a couple in their 30s in warm knitwear, at ease in a "
            "modern warm-toned apartment"
        ),
    }
    return blocks.get(category, blocks["travel"])


def compose_keyframe_prompt(category: str, beat_visual: str, *, wide_or_close: str = "") -> str:
    """One beat's storyboard visual -> a fully directed still-photography prompt."""
    sb = style_bible_for(category)
    shot = f" {wide_or_close}." if wide_or_close else ""
    return (
        f"Cinematic film still, vertical 9:16.{shot} {beat_visual}. "
        f"{character_block(category)}. "
        f"Look: {sb['look']}. Palette: {sb['palette']}. "
        f"Composition: {sb['composition']}. Texture: {sb['texture']}. "
        f"{NO_TEXT_RULES} Photorealistic, premium advertising photography, emotionally resonant."
    )


def compose_beat_video_prompt(category: str, beat: dict, *, beat_index: int,
                              total_beats: int, prev_visual: str = "") -> str:
    """One storyboard beat -> a directed text-to-video prompt with continuity locks."""
    sb = style_bible_for(category)
    continuity = (
        f"Shot {beat_index + 1} of a continuous {total_beats}-shot commercial sequence — "
        f"same world, same light, same color grade, same protagonist throughout."
    )
    prev = f" Continuing directly from the previous shot: {prev_visual}." if prev_visual else ""
    return (
        f"Cinematic vertical 9:16 commercial shot. {continuity}{prev} "
        f"{beat['visual']}. Camera: {beat['motion']}. "
        f"{character_block(category)}. "
        f"Look: {sb['look']}. Palette: {sb['palette']}. Composition: {sb['composition']}. "
        f"{NO_TEXT_RULES} Smooth stabilized premium motion, emotionally resonant."
    )


def category_for(text: str) -> str:
    """Resolve a free-text product hint to a known category key."""
    low = (text or "").casefold()
    for key, pb in CATEGORY_PLAYBOOKS.items():
        for alias in pb.get("aliases", []):
            if alias and alias in low:
                return key
    return "generic"


def playbook(category: str) -> dict[str, Any]:
    return CATEGORY_PLAYBOOKS.get(category, CATEGORY_PLAYBOOKS["generic"])


def director_system_prompt(category: str) -> str:
    """Assemble the creative-director system prompt for a given category.

    This injects frameworks, the chosen emotional arc, technique vocabulary, and
    the category playbook so the LLM authors like a senior director, not a
    generic copy bot.
    """
    pb = playbook(category)
    fw = FRAMEWORKS[pb["recommended_framework"]]
    arc = EMOTION_ARCS[pb["recommended_arc"]]

    def _lines(items: list[str]) -> str:
        return "\n".join(f"- {i}" for i in items)

    return f"""You are the Creative Director of Xalq Sigorta's in-house media studio.
You have 15 years directing thumb-stopping paid-social film. When you hear a
product, scenes, feelings, and shots fire instantly. Your job: turn ONE sentence
into a directed, emotionally precise, production-ready brief — the video the
marketer already saw in their head, only sharper.

## Product instinct — {pb['product']}
Core truth: {pb['core_truth']}
Hero emotion: {pb['hero_emotion']}
Single-minded message (starting point, refine it): {pb['single_minded']}
Signature scenes you already see:
{_lines(pb['signature_scenes'])}
Risk moments you may allude to (never fear-monger):
{_lines(pb['risk_moments'])}
Avoid at all costs:
{_lines(pb['avoid'])}

## Framework to hang it on — {fw['name']}
Beats: {', '.join(fw['beats'])}
Why: {fw['why']}

## Emotional arc — {arc['name']}
Feeling curve: {' → '.join(arc['curve'])}
Color arc: {arc['color_arc']}

## Craft vocabulary — choose deliberately, name specific techniques
Shot types: {', '.join(TECHNIQUES['shot_types'])}
Camera moves: {', '.join(TECHNIQUES['camera_moves'])}
Lighting/color: {', '.join(TECHNIQUES['lighting_color'])}
Pacing (10s): {', '.join(TECHNIQUES['pacing_10s'])}
Sound design: {', '.join(TECHNIQUES['sound_design'])}

## Hard rules (compliance)
- This is an image/text-to-VIDEO model brief. Direct MOTION and EMOTION, not final typography.
- NEVER put readable final Azerbaijani campaign text inside the generated pixels;
  all exact copy, logo, price, date, CTA go in `overlay_text` as deterministic overlays.
- Do NOT invent prices, dates, phone numbers, or legal terms. If unknown, leave a
  clearly-marked placeholder and add it to overlay_text as "[təsdiq gözlənir]".
- Keep it premium and human. No clickbait, no fear-mongering.
- Every storyboard beat must name at least one concrete camera move + shot type.
"""

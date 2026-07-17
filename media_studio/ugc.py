"""AI UGC campaign-pack mode for Media Studio.

This is the Ramin-OS version of the Doruk-style "AI influencer agency" flow:
one brief becomes a synthetic creator persona, a short UGC script, voice route,
video prompts, unit economics, landing-page wireframe, QA, and a final handoff.

It is intentionally draft-only. It does not spend FLORA credits, generate
payments, post anything, or browse credentialed systems. The paid video step
stays behind the existing Media Studio cost gate.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import knowledge, pipeline, resources


PACK_FILES = {
    "persona": "persona.md",
    "script": "script-10s.md",
    "voiceover": "voiceover.md",
    "video_prompt": "video-prompt.md",
    "unit_economics": "unit-economics.md",
    "landing": "landing-wireframe.md",
    "qa": "qa-checklist.md",
    "resources": "resources-readiness.md",
    "handoff": "publish-dry-run.md",
    "manifest": "ugc-pack.json",
}


PERSONAS: dict[str, dict[str, str]] = {
    "travel": {
        "name": "Aysel, travel micro-creator",
        "role": "Azerbaijani travel/lifestyle creator, speaks like a friend before a trip",
        "look": "early 30s, shoulder-length dark hair, cream linen shirt, light camel coat",
        "setting": "airport window seat, hotel mirror, city street, phone-shot travel moments",
        "phone_style": "iPhone-style handheld vertical video, natural daylight, tiny imperfections",
        "promise": "travel can feel free because the risk is handled before leaving",
    },
    "auto": {
        "name": "Murad, car-owner creator",
        "role": "calm car enthusiast explaining one practical protection tip",
        "look": "late 30s, navy coat, clean everyday style, confident but not flashy",
        "setting": "parking lot, car interior, detail shots of keys, mirrors, dashboard",
        "phone_style": "handheld vertical walkaround, realistic reflections, no crash drama",
        "promise": "the car you care about should not depend on one lucky day",
    },
    "health": {
        "name": "Lala, family-life creator",
        "role": "warm family creator talking about one small health worry",
        "look": "young mother in a beige sweater, natural makeup, gentle delivery",
        "setting": "home morning routine, clinic corridor suggestion, child/family detail",
        "phone_style": "soft daylight documentary, gentle handheld, quiet home realism",
        "promise": "health cover protects the calm around the people you love",
    },
    "property": {
        "name": "Nigar, home-life creator",
        "role": "home and lifestyle creator showing why the home feeling matters",
        "look": "early 30s, warm knitwear, relaxed in a real apartment",
        "setting": "kitchen table, window light, hallway, small home details",
        "phone_style": "natural vertical home video, warm textures, no disaster movie tone",
        "promise": "home insurance protects the feeling of home, not only walls",
    },
    "generic": {
        "name": "Rena, everyday-life creator",
        "role": "Azerbaijani lifestyle creator turning one risk into a simple habit",
        "look": "early 30s, understated wardrobe, trustworthy and natural",
        "setting": "real daily-life spaces, phone-shot details, ordinary human moments",
        "phone_style": "authentic handheld vertical video, clean but not overproduced",
        "promise": "life continues more calmly when the risk is carried by the right partner",
    },
}


def create(sentence: str, *, use_llm: bool = True) -> dict[str, Any]:
    """Create a normal Media Studio package and augment it with UGC deliverables."""
    base = pipeline.create(sentence, use_llm=use_llm)
    folder = pipeline.CAMPAIGNS / base["slug"]
    pack_dir = folder / "ugc-pack"
    pack_dir.mkdir(parents=True, exist_ok=True)

    ugc = build_ugc_pack(base, pack_dir)
    base["mode"] = "ugc_pack"
    base["ugc_pack"] = ugc
    (folder / "package.json").write_text(
        json.dumps(base, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return base


def build_ugc_pack(package: dict[str, Any], pack_dir: Path) -> dict[str, Any]:
    request = package["request"]
    category = request["category"]
    brief = package["brief"]
    resolution = package["resolution"]
    persona = PERSONAS.get(category, PERSONAS["generic"])
    playbook = knowledge.playbook(category)
    style = knowledge.style_bible_for(category)

    data = {
        "persona": persona,
        "script": _script(brief, playbook, persona, resolution["duration_s"]),
        "voice": _voice_route(brief, persona),
        "video": _video_prompts(brief, package, persona, style),
        "economics": _unit_economics(package),
        "landing": _landing_wireframe(brief, persona),
        "qa": _qa_checklist(brief),
        "resources": resources.build_status(package),
        "handoff": _handoff(brief, package),
    }

    renderers = {
        "persona": _render_persona,
        "script": _render_script,
        "voiceover": _render_voiceover,
        "video_prompt": _render_video_prompt,
        "unit_economics": _render_unit_economics,
        "landing": _render_landing,
        "qa": _render_qa,
        "resources": _render_resources,
        "handoff": _render_handoff,
    }
    written: dict[str, str] = {}
    for key, renderer in renderers.items():
        path = pack_dir / PACK_FILES[key]
        path.write_text(renderer(data, package), encoding="utf-8")
        written[key] = pipeline._rel(path)

    manifest = {
        "status": "draft_only",
        "source_pattern": "Doruk-style AI UGC agency flow, adapted to Ramin-OS governance",
        "can_autofire": False,
        "no_spend": True,
        "no_posting": True,
        "folder": pipeline._rel(pack_dir),
        "files": written,
        "persona": persona,
        "script": data["script"],
        "voice": data["voice"],
        "video": data["video"],
        "economics": data["economics"],
        "resources": data["resources"],
        "next_human_gate": (
            "Approve the persona, script, voice route, and FLORA cost before any "
            "real generation or external order/payment flow."
        ),
    }
    manifest_path = pack_dir / PACK_FILES["manifest"]
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    written["manifest"] = pipeline._rel(manifest_path)
    manifest["files"] = written
    return manifest


def _script(brief: dict[str, Any], playbook: dict[str, Any],
            persona: dict[str, str], duration_s: int) -> list[dict[str, str]]:
    product = playbook["product"]
    headline = brief["offer"]["headline"]
    cta = brief["offer"]["cta"]
    if brief["campaign"]["language"] == "az":
        return [
            {
                "time": "0.0-1.5s",
                "role": "hook",
                "line": f"{product} barədə bunu səfərdən əvvəl bağlamaq lazımdır.",
                "visual": persona["setting"],
            },
            {
                "time": "1.5-4.0s",
                "role": "human proof",
                "line": "Çünki plan yaxşı gedəndə heç kim risk barədə düşünmür.",
                "visual": "creator speaks to camera, then cuts to a real-life detail",
            },
            {
                "time": "4.0-7.5s",
                "role": "turn",
                "line": playbook["single_minded"],
                "visual": "small risk moment resolves into calm continuation",
            },
            {
                "time": f"7.5-{duration_s}.0s",
                "role": "cta",
                "line": f"{headline}. {cta}.",
                "visual": "stable end frame with deterministic brand overlay",
            },
        ]
    return [
        {
            "time": "0.0-1.5s",
            "role": "hook",
            "line": f"One thing I would sort before trusting any plan: {product}.",
            "visual": persona["setting"],
        },
        {
            "time": "1.5-4.0s",
            "role": "human proof",
            "line": "Because when the day is going well, nobody wants to think about risk.",
            "visual": "creator speaks to camera, then cuts to a real-life detail",
        },
        {
            "time": "4.0-7.5s",
            "role": "turn",
            "line": playbook["core_truth"],
            "visual": "small risk moment resolves into calm continuation",
        },
        {
            "time": f"7.5-{duration_s}.0s",
            "role": "cta",
            "line": f"{headline}. {cta}.",
            "visual": "stable end frame with deterministic brand overlay",
        },
    ]


def _voice_route(brief: dict[str, Any], persona: dict[str, str]) -> dict[str, Any]:
    text = " ".join(part["line"] for part in _script(
        brief, knowledge.playbook(_category_from_brief(brief)), persona, brief["format"]["duration_s"]
    ))
    return {
        "script_text": text,
        "free_draft": (
            "Audio Studio Edge/Gemini TTS for timing drafts; expect robotic AZ and judge by ear."
        ),
        "natural_path": (
            "OmniVoice clone with a consented 20-30s Azerbaijani reference clip under "
            "audio-studio/voices/; generate 2-3 takes and pick manually."
        ),
        "premium_path": (
            "ElevenLabs only after key/credits are intentionally configured and a human approves "
            "the spend. Doruk lesson: local-language voice quality must be ear-tested."
        ),
        "audio_command_template": (
            'python audio-studio\\audio_studio.py clone "<SCRIPT_TEXT>" --lang az'
            "  # defaults to the house voice (AUDIO_DEFAULT_REF -> voices\\ramin_ref.wav);"
            " pass --ref to override"
        ),
    }


def _video_prompts(brief: dict[str, Any], package: dict[str, Any],
                   persona: dict[str, str], style: dict[str, str]) -> dict[str, Any]:
    first_visual = brief["storyboard"][0]["visual"] if brief["storyboard"] else persona["setting"]
    still_prompt = (
        f"Vertical 9:16 UGC reference still. Synthetic creator persona: {persona['look']}. "
        f"Role: {persona['role']}. Scene: {first_visual}. Phone style: {persona['phone_style']}. "
        f"Lighting/look: {style['look']}. Composition: {style['composition']}. "
        f"{knowledge.NO_TEXT_RULES} Realistic, not polished stock, no brand logo in pixels."
    )
    beat_lines = []
    for idx, beat in enumerate(brief["storyboard"]):
        beat_lines.append(
            f"Beat {idx + 1} {beat['time']}: {beat['visual']} | camera: "
            f"{knowledge.primary_camera_move(beat.get('motion', ''))}"
        )
    video_prompt = (
        f"Create a {brief['format']['duration_s']}s vertical AI UGC ad from the approved "
        f"reference still. Keep the same synthetic creator ({persona['look']}) across all shots. "
        f"Style: {persona['phone_style']}. Promise: {persona['promise']}. "
        + " ".join(beat_lines)
        + f" Avoid: {knowledge.VIDEO_AVOID}. No readable text or logos; final copy is added later."
    )
    return {
        "reference_still_prompt": still_prompt,
        "image_to_video_prompt": video_prompt,
        "text_to_video_fallback": knowledge.compose_film_prompt(
            _category_from_brief(brief), brief["storyboard"], duration_s=brief["format"]["duration_s"]
        ),
        "primary_model": package["resolution"]["model_id"],
        "second_variant": package["resolution"]["partner_id"],
        "plan_command": package["generation"]["plan_command"],
        "human_approved_generation": package["generation"]["fire_command"],
    }


def _unit_economics(package: dict[str, Any]) -> dict[str, Any]:
    resolution = package["resolution"]
    duration = resolution["duration_s"]
    primary = int(resolution.get("credits") or 0)
    partner = int(resolution.get("partner_credits") or 0)
    setup = primary + partner
    return {
        "status": "formula_only_no_payment",
        "duration_s": duration,
        "primary_video_credits": primary,
        "second_variant_credits": partner,
        "one_round_video_credit_floor": primary,
        "two_variant_test_credits": setup,
        "voice_cost": "0 for rough Edge/Gemini timing draft; paid/credited if ElevenLabs is approved",
        "finishing_cost": "local FFmpeg/Remotion time; no provider spend",
        "client_price": "[human sets price]",
        "margin_formula": (
            "client_price - (video_generation_credits_to_money + voice_cost + editing_time + revisions)"
        ),
        "doruk_lesson": (
            "Separate one-time setup cost from per-video variable cost; do not price before "
            "voice quality and video redo rate are known."
        ),
    }


def _landing_wireframe(brief: dict[str, Any], persona: dict[str, str]) -> dict[str, Any]:
    return {
        "first_view": [
            brief["offer"]["headline"],
            "Realistic AI UGC videos for campaign testing, built inside Ramin-OS.",
            "Show 3 sample video slots, not stock imagery.",
        ],
        "sections": [
            "Problem: creator videos are slow and expensive to coordinate.",
            "Offer: synthetic UGC drafts for testing hooks before real creator spend.",
            "Process: brief -> persona -> script -> voice -> video -> QA -> dry-run package.",
            "Proof: before/after sample grid and cost-gated generation notes.",
            "Order form: draft request only; payment integration stays disabled until approved.",
        ],
        "cta": "Draft request / manual quote",
        "safety": (
            "No autonomous payment, checkout, or public posting. Human approval required before "
            "generation spend or customer-facing delivery."
        ),
        "persona_signal": persona["name"],
    }


def _qa_checklist(brief: dict[str, Any]) -> list[str]:
    return [
        "The creator looks like a believable synthetic actor, not a glossy avatar.",
        "The first second works muted and tells the product category.",
        "No readable Azerbaijani text, logo, price, or CTA is generated inside pixels.",
        "The voiceover is judged by a native ear; robotic takes are rejected.",
        "The brand appears as the calm solution, not a corporate lecture.",
        "Final legal/CTA/logo overlays are deterministic and reviewed.",
        "No fake testimonials, fake real-person identity, or undisclosed synthetic-person claim.",
        *brief["qa"]["reject_if"],
    ]


def _handoff(brief: dict[str, Any], package: dict[str, Any]) -> dict[str, Any]:
    slug = package["slug"]
    return {
        "when_video_exists": (
            f"Run Publisher dry-run on the final MP4 and campaign caption package for slug {slug}."
        ),
        "manual_command_template": (
            f'python publisher\\run.py "output\\media_studio\\campaigns\\{slug}\\<final>.mp4" '
            "--to instagram,tiktok,linkedin --dry-run"
        ),
        "gates": [
            "Generate only after FLORA cost approval.",
            "Finish exact overlays in Video Studio.",
            "Run QA checklist.",
            "Use dry-run package first; live scheduling remains a separate human checkpoint.",
        ],
        "caption_seed": brief["offer"]["headline"],
    }


def _category_from_brief(brief: dict[str, Any]) -> str:
    return knowledge.category_for(brief["campaign"].get("source_brief", ""))


def _render_persona(data: dict[str, Any], package: dict[str, Any]) -> str:
    p = data["persona"]
    return f"""# Synthetic UGC Persona

Name: {p['name']}
Role: {p['role']}
Look: {p['look']}
Setting: {p['setting']}
Phone style: {p['phone_style']}
Promise: {p['promise']}

## Rules

- This is a synthetic campaign actor, not a real influencer endorsement.
- Do not use a real person's face, voice, name, or likeness without written consent.
- Keep the creator natural: small pauses, handheld framing, real-world detail.
- Final brand text/logo/CTA are deterministic overlays, not generated pixels.
"""


def _render_script(data: dict[str, Any], package: dict[str, Any]) -> str:
    lines = ["# 10s UGC Script", ""]
    for part in data["script"]:
        lines.append(f"## {part['time']} - {part['role']}")
        lines.append(f"Line: {part['line']}")
        lines.append(f"Visual: {part['visual']}")
        lines.append("")
    return "\n".join(lines)


def _render_voiceover(data: dict[str, Any], package: dict[str, Any]) -> str:
    v = data["voice"]
    return f"""# Voiceover Route

## Spoken Script

{v['script_text']}

## Routes

- Free draft: {v['free_draft']}
- Natural path: {v['natural_path']}
- Premium path: {v['premium_path']}

## Command Template

```powershell
{v['audio_command_template']}
```
"""


def _render_video_prompt(data: dict[str, Any], package: dict[str, Any]) -> str:
    v = data["video"]
    return f"""# Video Prompt Pack

Primary model: `{v['primary_model']}`
Second variant: `{v['second_variant']}`

## Reference Still Prompt

{v['reference_still_prompt']}

## Image-To-Video Prompt

{v['image_to_video_prompt']}

## Text-To-Video Fallback

{v['text_to_video_fallback']}

## Cost Gate Commands

```powershell
{v['plan_command']}
{v['human_approved_generation']}
```

The second command spends credits only when the human intentionally confirms it.
"""


def _render_unit_economics(data: dict[str, Any], package: dict[str, Any]) -> str:
    e = data["economics"]
    return f"""# Unit Economics

Status: {e['status']}
Duration: {e['duration_s']}s

| Cost line | Value |
|---|---|
| Primary video | ~{e['primary_video_credits']} FLORA credits |
| Second variant | ~{e['second_variant_credits']} FLORA credits |
| One-round floor | ~{e['one_round_video_credit_floor']} FLORA credits |
| Two-variant test | ~{e['two_variant_test_credits']} FLORA credits |
| Voice | {e['voice_cost']} |
| Finishing | {e['finishing_cost']} |
| Client price | {e['client_price']} |

Formula: `{e['margin_formula']}`

Doruk lesson: {e['doruk_lesson']}
"""


def _render_landing(data: dict[str, Any], package: dict[str, Any]) -> str:
    l = data["landing"]
    sections = "\n".join(f"- {x}" for x in l["sections"])
    first = "\n".join(f"- {x}" for x in l["first_view"])
    return f"""# Landing / Order Wireframe

## First View

{first}

## Sections

{sections}

CTA: {l['cta']}

Safety: {l['safety']}
Persona signal: {l['persona_signal']}
"""


def _render_qa(data: dict[str, Any], package: dict[str, Any]) -> str:
    items = "\n".join(f"- [ ] {x}" for x in data["qa"])
    return f"""# UGC QA Checklist

{items}
"""


def _render_resources(data: dict[str, Any], package: dict[str, Any]) -> str:
    return resources.render_status_report(data["resources"])


def _render_handoff(data: dict[str, Any], package: dict[str, Any]) -> str:
    h = data["handoff"]
    gates = "\n".join(f"- {x}" for x in h["gates"])
    return f"""# Final Packaging Dry-Run

{h['when_video_exists']}

```powershell
{h['manual_command_template']}
```

## Gates

{gates}

Caption seed: {h['caption_seed']}
"""

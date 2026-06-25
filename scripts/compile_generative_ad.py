from __future__ import annotations

import argparse
import json
from pathlib import Path
from textwrap import indent


def bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def storyboard(beats: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for beat in beats:
        lines.append(
            "\n".join(
                [
                    f"{beat['time']}: {beat['beat']}",
                    f"Visual: {beat['visual']}",
                    f"Motion: {beat['motion']}",
                    f"Overlay later: {beat['overlay']}",
                ]
            )
        )
    return "\n\n".join(lines)


def asset_inventory(assets: list[dict[str, object]]) -> str:
    blocks: list[str] = []
    for asset in assets:
        preserve = asset.get("must_preserve") or []
        preserve_text = ", ".join(str(item) for item in preserve) if preserve else "n/a"
        asset_id = asset.get("asset_id")
        asset_id_text = f"\nAsset ID: {asset_id}" if asset_id else ""
        blocks.append(
            "\n".join(
                [
                    f"Role: {asset['role']}",
                    f"Path/URL: {asset['path_or_url']}",
                    f"Usage: {asset['usage']}",
                    f"Must preserve: {preserve_text}",
                    asset_id_text.strip(),
                ]
            ).strip()
        )
    return "\n\n".join(blocks)


def compile_prompt(brief: dict[str, object]) -> str:
    campaign = brief["campaign"]
    platform = brief["platform"]
    fmt = brief["format"]
    objective = brief["objective"]
    brand = brief["brand"]
    offer = brief["offer"]
    text_policy = brief["text_policy"]
    model_strategy = brief["model_strategy"]
    qa = brief["qa"]

    model_commands = []
    for model in model_strategy["recommended"]:
        model_commands.append(
            " ".join(
                [
                    "flora --format json generations create",
                    "--workspace-id <WORKSPACE_ID>",
                    "--project-id <PROJECT_ID>",
                    "--type video",
                    f"--model {model}",
                    '--prompt "<PASTE_COMPILED_PROMPT>"',
                    "--params '{\"image_url\":\"<FLORA_ASSET_URL>\","
                    f"\"aspect_ratio\":\"{fmt['aspect']}\","
                    f"\"duration\":\"{int(fmt['duration_s'])}\"}}'",
                ]
            )
        )

    return f"""# Compiled Generative Ad Prompt

Campaign: {campaign["name"]} (`{campaign["slug"]}`)
Platform: {platform["name"]} / {platform["placement"]}
Format: {fmt["aspect"]}, {fmt["duration_s"]}s, {fmt["resolution"][0]}x{fmt["resolution"][1]}, {fmt["fps"]}fps

## Strategic Objective

Primary: {objective["primary"]}
Audience: {objective["audience"]}
Single-minded message: {objective["single_minded_message"]}
Conversion action: {objective.get("conversion_action", "")}

## Brand Identity

Brand: {brand["name"]}
Identity source: {brand["identity_source"]}
Tone:
{bullets(brand["tone"])}

Palette:
{bullets(brand["palette"])}

Typography:
{bullets(brand["typography"])}

Non-negotiable brand rules:
{bullets(brand["rules"])}

## Offer Copy

Headline: {offer["headline"]}
Subheadline: {offer["subheadline"]}
Dates: {offer["dates"]}
CTA: {offer["cta"]}

Terms:
{bullets(offer["terms"])}

## Asset Inventory

{asset_inventory(brief["assets"])}

## Storyboard

{storyboard(brief["storyboard"])}

## Flora Video Prompt

Create a {fmt["duration_s"]}-second vertical {fmt["aspect"]} paid social ad for {brand["name"]}. Use the provided reference assets for composition, product identity, color, and motion direction. Generate a premium motion plate and social-card animation, not final typography.

Preserve the campaign world and approved assets. The brand tone is {", ".join(brand["tone"])}. The single-minded message is: {objective["single_minded_message"]}

Storyboard:
{indent(storyboard(brief["storyboard"]), "  ")}

Text policy: {text_policy["ai_text_rule"]}

Overlay copy to add after generation:
{bullets(text_policy["overlay_text"])}

Negative constraints:
{bullets(text_policy["forbidden"])}

Reject if:
{bullets(qa["reject_if"])}

Approve if:
{bullets(qa["approve_if"])}

## Model Strategy

Recommended:
{bullets(model_strategy["recommended"])}

Fallbacks:
{bullets(model_strategy["fallbacks"])}

Variant count: {model_strategy["variant_count"]}

Selection criteria:
{bullets(model_strategy["selection_criteria"])}

## Flora CLI Skeletons

Upload the chosen reference image with `flora assets create --source signed-url`,
complete the asset, then replace `<FLORA_ASSET_URL>` below.

```powershell
{chr(10).join(model_commands)}
```
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile a generative ad brief into a Flora-ready prompt.")
    parser.add_argument("brief", type=Path)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    brief = json.loads(args.brief.read_text(encoding="utf-8"))
    compiled = compile_prompt(brief)

    output = args.output
    if output is None:
        slug = brief["campaign"]["slug"]
        output = args.brief.parent / "prompts" / "compiled-flora-prompt.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(compiled, encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()

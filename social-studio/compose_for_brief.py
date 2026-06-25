"""One-shot composer for a given brief — recomposite known-good raw
backgrounds with custom headline/sub/body, then export 1080x1350,
1080x1080 (square), and 1080x1920 (story) variants.

Used by the /post slash command when we have a strong raw background
already and only the brand-locked overlay text changes.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

import render_post as rp  # noqa: E402  (sibling module)

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"


def compose_with_text(
    raw_path: Path,
    out_path: Path,
    *,
    top_tag: str,
    headline: list[str],
    subhead: list[str],
    body: list[str],
) -> Path:
    """Composite using render_post's stages but with overridden text."""
    saved = rp.CAMPAIGN.copy()
    try:
        rp.CAMPAIGN.update({
            "top_tag": top_tag,
            "headline": headline,
            "subhead": subhead,
            "body": body,
        })
        rp.compose(raw_path, out_path)
    finally:
        rp.CAMPAIGN.clear()
        rp.CAMPAIGN.update(saved)
    return out_path


def make_square(src_4x5: Path, out: Path) -> Path:
    """Square crop centered on the headline-and-subject zone."""
    img = Image.open(src_4x5).convert("RGB")
    w, h = img.size  # expect 1080, 1350
    # Drop 135 px equally from top and bottom -> 1080x1080
    top = (h - w) // 2
    sq = img.crop((0, top, w, top + w))
    sq.save(out, "PNG", optimize=True)
    return out


def make_story(src_4x5: Path, out: Path) -> Path:
    """Story 9:16 = 1080x1920: extend the source vertically with a
    blurred copy of itself (so the brand atmosphere keeps flowing)."""
    img = Image.open(src_4x5).convert("RGB")
    w, h = img.size  # 1080, 1350
    target_h = 1920
    canvas = Image.new("RGB", (w, target_h), (10, 12, 18))

    # Blurred top + bottom bars from a scaled-up version of the image
    blur_src = img.resize((int(w * 1.4), int(h * 1.4)), Image.LANCZOS)
    blur_src = blur_src.filter(ImageFilter.GaussianBlur(radius=30))
    # Center the blurred backdrop on the canvas
    bx = (blur_src.width - w) // 2
    by = (blur_src.height - target_h) // 2
    canvas.paste(blur_src.crop((bx, by, bx + w, by + target_h)), (0, 0))

    # Then paste the sharp original centered vertically
    y = (target_h - h) // 2
    canvas.paste(img, (0, y))
    canvas.save(out, "PNG", optimize=True)
    return out


def main() -> int:
    slug = "georgia-train-new-route"
    campaign_out = OUT / slug
    campaign_out.mkdir(parents=True, exist_ok=True)

    # Use our best raws so far — the two GPT Image 2 backgrounds that scored 9/10
    # in master audit (post_codex_1 and post_codex_3). We recomposite them with
    # the NEW topical headline instead of the original travel-insurance one.
    raw_dir = HERE / "experiments"
    raws = [
        ("v1", raw_dir / "raw_codex_1.png"),
        ("v2", raw_dir / "raw_codex_3.png"),
    ]

    top_tag = "BAKI - TBİLİSİ"
    headline = ["Yeni reys başladı."]
    subhead = ["Sığortalı yola çıx."]
    body = [
        "1 yanvar 2026-dan Gürcüstana giriş üçün",
        "səyahət sığortası məcburidir.",
    ]

    delivered: list[Path] = []
    for label, raw in raws:
        if not raw.is_file():
            print(f"  skip {label}: {raw} missing", flush=True)
            continue
        primary = campaign_out / f"{label}-feed-1080x1350.png"
        square = campaign_out / f"{label}-square-1080x1080.png"
        story = campaign_out / f"{label}-story-1080x1920.png"
        print(f"-> {label}: {primary.name}", flush=True)
        compose_with_text(
            raw, primary,
            top_tag=top_tag, headline=headline,
            subhead=subhead, body=body,
        )
        make_square(primary, square)
        make_story(primary, story)
        delivered.extend([primary, square, story])

    print(f"\nDONE - {len(delivered)} files")
    for p in delivered:
        print(f"  {p.relative_to(HERE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

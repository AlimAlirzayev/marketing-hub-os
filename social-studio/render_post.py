"""Xalq Insurance Digital OS Social Studio - render Xalq Sigorta posts.

Pipeline: Pollinations.ai (free FLUX) generates the photographic background;
Pillow composites the brand-locked overlays (top tag, headline, subhead, body)
and the deterministic footer (logo + legal microcopy + contact lockup) from
the Xalq Sigorta brand kit SVG. Output: 1080x1350 production-ready PNG.

Why this split: per brand_kit/brand.md the logo, legal microcopy, and campaign
copy must never be AI-rendered. The image model owns only the photograph;
this Python layer owns everything brand-locked.
"""

from __future__ import annotations

import argparse
import io
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont
from reportlab.graphics import renderPM
from svglib.svglib import svg2rlg

# --- paths ----------------------------------------------------------------
HERE = Path(__file__).resolve().parent
BRAND = HERE / "brand_kit"
OUT = HERE / "experiments"
OUT.mkdir(parents=True, exist_ok=True)

# --- canvas ---------------------------------------------------------------
W, H = 1080, 1350  # 4:5 LinkedIn feed
MARGIN = 72        # safe margin per brand spec

# --- brand colors (from brand_kit/colors.json) ----------------------------
RED = (227, 30, 36)
WHITE = (255, 255, 255)

# --- fonts ----------------------------------------------------------------
# Segoe UI Black ships with Windows; Inter Tight is the brand-correct
# successor and lives in brand_kit later. For now Segoe UI Black is the
# closest legible substitute the corporate machine ships with.
FONT_BLACK = r"C:\Windows\Fonts\seguibl.ttf"   # Segoe UI Black
FONT_BOLD = r"C:\Windows\Fonts\seguisb.ttf"    # Segoe UI Semibold
FONT_REG = r"C:\Windows\Fonts\segoeui.ttf"     # Segoe UI Regular


def _font(path: str, size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


# --- 1. background generation --------------------------------------------

BRIEF = (
    "Ads-marketing final-production photographic background for Xalq Sigorta "
    "Instagram/Facebook campaign. Background only - no headline text, no "
    "logo, no contact text, no fake readable writing. Premium "
    "advertising-grade financial-services photography: crisp edges, realistic "
    "faces and hands, controlled depth of field, refined commercial "
    "retouching. Brand: Xalq Sigorta corporate red #E31E24, white, charcoal "
    "black, restrained premium mood. Subtle red gradient atmosphere at the "
    "edges (not a wash). "
    "Scene: a stylish young Azerbaijani couple seated by the window of a "
    "modern Baku-Tbilisi intercity passenger train. Outside the window: "
    "Caucasus mountains, railway bridge, soft daylight. They hold passports "
    "and a smartphone with abstract red-and-white insurance UI shapes (no "
    "readable text). A red hard-shell suitcase is the brand-color anchor. A "
    "very subtle transparent shield reflection on the window glass - almost "
    "invisible. "
    "Composition: vertical 4:5. Upper-left third left as calm dark negative "
    "space for headline overlay. Bottom 180px clean, no faces or props - "
    "reserved for brand footer overlay. Cinematic corporate daylight, soft "
    "window light, realistic skin tones, modern European/Caucasus travel "
    "aesthetic. "
    "Avoid: fake logos, generated text, random letters, watermarks, "
    "distorted hands, cartoon style, exaggerated shield, oversaturation, "
    "fantasy train."
)


def generate_background(seed: int, out_path: Path) -> Path:
    """Pull a 1080x1350 FLUX background from Pollinations and save it.
    Uses the 'turbo' model (FLUX schnell variant on the free tier) because
    the 'flux' model started returning 402 Payment Required in mid-2026.
    """
    encoded = urllib.parse.quote(BRIEF)
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width={W}&height={H}&model=turbo&seed={seed}&nologo=true&enhance=true"
    )
    print(f"  seed={seed}: requesting Pollinations FLUX ...", flush=True)
    r = requests.get(url, timeout=240)
    r.raise_for_status()
    out_path.write_bytes(r.content)
    print(f"  seed={seed}: got {out_path.stat().st_size // 1024} KB", flush=True)
    return out_path


# --- 2. overlay helpers --------------------------------------------------

def _gradient_mask(w: int, h: int, axis: str, start: int, end: int) -> Image.Image:
    """A grayscale gradient mask of size (w,h) interpolating start->end."""
    if axis == "x":
        line = np.linspace(start, end, w, dtype=np.uint8)
        arr = np.tile(line, (h, 1))
    else:
        col = np.linspace(start, end, h, dtype=np.uint8)
        arr = np.tile(col[:, None], (1, w))
    return Image.fromarray(arr, mode="L")


def _cover_crop(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Resize via cover-crop (preserve aspect, crop excess) instead of stretch.
    Codex / GPT Image 2 outputs are usually 1024x1568 or similar — naive
    resize to 1080x1350 stretches subjects horizontally ~26%. Cover-crop
    preserves anatomy."""
    src_ratio = img.width / img.height
    target_ratio = target_w / target_h
    if abs(src_ratio - target_ratio) < 0.005:
        return img.resize((target_w, target_h), Image.LANCZOS)
    if src_ratio > target_ratio:
        # source is wider → crop equal slices off left and right
        new_w = int(round(img.height * target_ratio))
        left = (img.width - new_w) // 2
        img = img.crop((left, 0, left + new_w, img.height))
    else:
        # source is taller → crop top/bottom (favor keeping subjects centered
        # which sit roughly at the vertical middle of GPT Image 2 outputs)
        new_h = int(round(img.width / target_ratio))
        top = (img.height - new_h) // 2
        img = img.crop((0, top, img.width, top + new_h))
    return img.resize((target_w, target_h), Image.LANCZOS)


def apply_brand_atmosphere(img: Image.Image) -> Image.Image:
    """Smooth organic 2D vignette — no rectangular masks. The top-left zone
    falls off in BOTH axes simultaneously with a smoothstep curve, so there
    is no visible horizontal or vertical seam where the gradient ends.
    The bottom zone fades vertically only but extends far enough up that
    the transition is invisible against typical photo content.
    """
    img = img.convert("RGB")
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)

    # Top-left zone — 2D falloff anchored at (0,0).
    fx_tl = np.clip(1.0 - x / (W * 0.62), 0.0, 1.0)
    fy_tl = np.clip(1.0 - y / (H * 0.42), 0.0, 1.0)
    tl = fx_tl * fy_tl
    tl = tl * tl * (3.0 - 2.0 * tl)              # smoothstep
    tl_alpha = (tl * 165).astype(np.uint8)

    # Bottom zone — smooth vertical fade, starts gently at ~y=H*0.74
    fy_bot = np.clip((y - H * 0.74) / (H * 0.26), 0.0, 1.0)
    bot = fy_bot * fy_bot * (3.0 - 2.0 * fy_bot)  # smoothstep
    bot_alpha = (bot * 200).astype(np.uint8)

    combined = np.maximum(tl_alpha, bot_alpha)
    mask = Image.fromarray(combined, mode="L")

    # Use deep ink rather than pure black — preserves the photo's color story.
    dark = Image.new("RGB", (W, H), (10, 10, 14))
    return Image.composite(dark, img, mask)


def draw_top_tag(draw: ImageDraw.ImageDraw, text: str, x: int, y: int) -> None:
    """The small red rounded badge that sits above the headline."""
    font = _font(FONT_BLACK, 22)
    pad_x, pad_y = 18, 8
    bbox = draw.textbbox((0, 0), text, font=font)
    w = (bbox[2] - bbox[0]) + 2 * pad_x
    h = (bbox[3] - bbox[1]) + 2 * pad_y
    draw.rounded_rectangle(
        [(x, y), (x + w, y + h)], radius=6, fill=RED
    )
    draw.text(
        (x + pad_x, y + pad_y - bbox[1]), text, font=font, fill=WHITE
    )


def draw_text_block(
    draw: ImageDraw.ImageDraw,
    lines: Iterable[str],
    x: int,
    y: int,
    font: ImageFont.ImageFont,
    line_gap: float = 1.05,
) -> int:
    """Draw a multiline block from top-left. Returns the new y cursor."""
    cursor = y
    for line in lines:
        draw.text((x, cursor), line, font=font, fill=WHITE)
        ascent, descent = font.getmetrics()
        cursor += int((ascent + descent) * line_gap)
    return cursor


# --- 3. footer rasterization ---------------------------------------------

def rasterize_footer_svg(svg_path: Path, target_width: int) -> Image.Image:
    """Convert the locked footer SVG to a PNG at the requested width."""
    drawing = svg2rlg(str(svg_path))
    scale = target_width / drawing.width
    drawing.width *= scale
    drawing.height *= scale
    drawing.scale(scale, scale)
    buf = renderPM.drawToString(drawing, fmt="PNG")
    return Image.open(io.BytesIO(buf)).convert("RGBA")


# --- 4. full compose pass -------------------------------------------------

CAMPAIGN = {
    "top_tag": "BAKI - TBİLİSİ",
    "headline": ["Gürcüstana qatarla", "səyahət artıq mümkündür"],
    "subhead": ["Səyahət sığortanı unutma."],
    "body": [
        "1 yanvar 2026-dan Gürcüstana giriş üçün",
        "səyahət sığortası məcburidir.",
    ],
}


def draw_footer(img: Image.Image) -> None:
    """Draw the brand-locked footer onto a photo background using Pillow only.
    Uses a pre-extracted transparent PNG of the logo (slogan-free) instead of
    rasterizing the SVG, which mishandled the brand's gradient definitions.
    """
    draw = ImageDraw.Draw(img)
    # Logo PNG (white on transparent, slogan-free)
    logo_png = Image.open(BRAND / "logo-white.png").convert("RGBA")
    target_w = 240
    ratio = target_w / logo_png.width
    logo = logo_png.resize((target_w, int(logo_png.height * ratio)), Image.LANCZOS)
    logo_x, logo_y = MARGIN, H - 180
    img.paste(logo, (logo_x, logo_y), logo)

    # Legal microcopy under the logo (per brand_kit/brand.md mandatory text).
    legal_font = _font(FONT_REG, 13)
    legal_lines = [
        '*"Xalq Sigorta" ASC Azərbaycan Respublikası Maliyyə Nazirliyinin',
        '29 Aprel 2010-cu il tarixli 000333 saylı lisenziyası əsasında fəaliyyət göstərir.',
        'Ünvan: Bakı şəhəri, Akademik Həsən Əliyev küçəsi 24.',
    ]
    ly = logo_y + logo.height + 18
    for line in legal_lines:
        draw.text((logo_x, ly), line, font=legal_font, fill=(220, 220, 220))
        ascent, descent = legal_font.getmetrics()
        ly += int((ascent + descent) * 1.08)

    # Contact lockup (right-aligned): phone glyph + 183 + | + xalqsigorta.az
    lockup_font = _font(FONT_BLACK, 28)
    contact = "183  |  xalqsigorta.az"
    bbox = draw.textbbox((0, 0), contact, font=lockup_font)
    icon_w = 28
    icon_gap = 14
    cx = W - MARGIN - icon_w - icon_gap - (bbox[2] - bbox[0])
    cy = H - 140
    draw_phone_icon(draw, cx, cy + 6, icon_w, WHITE)
    draw.text((cx + icon_w + icon_gap, cy), contact, font=lockup_font, fill=WHITE)


def draw_phone_icon(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    size: int,
    fill: tuple[int, int, int],
) -> None:
    """Draw a small deterministic phone handset icon.

    Avoid text glyphs here: corporate Windows fonts can render phone symbols as
    missing boxes in final exports.
    """
    s = size
    width = max(3, s // 7)
    points = [
        (x + int(s * 0.26), y + int(s * 0.08)),
        (x + int(s * 0.10), y + int(s * 0.22)),
        (x + int(s * 0.15), y + int(s * 0.44)),
        (x + int(s * 0.30), y + int(s * 0.64)),
        (x + int(s * 0.52), y + int(s * 0.82)),
        (x + int(s * 0.75), y + int(s * 0.88)),
        (x + int(s * 0.91), y + int(s * 0.72)),
    ]
    draw.line(points, fill=fill, width=width, joint="curve")
    draw.line(
        [
            (x + int(s * 0.25), y + int(s * 0.09)),
            (x + int(s * 0.38), y + int(s * 0.23)),
        ],
        fill=fill,
        width=width,
    )
    draw.line(
        [
            (x + int(s * 0.76), y + int(s * 0.87)),
            (x + int(s * 0.91), y + int(s * 0.72)),
        ],
        fill=fill,
        width=width,
    )


def compose(bg_path: Path, out_path: Path) -> Path:
    img = Image.open(bg_path).convert("RGB")
    if img.size != (W, H):
        img = _cover_crop(img, W, H)
    img = apply_brand_atmosphere(img)
    draw = ImageDraw.Draw(img)

    # Top tag
    draw_top_tag(draw, CAMPAIGN["top_tag"], MARGIN, 56)

    # Headline (Segoe UI Black 60pt, white)
    y = 110
    y = draw_text_block(draw, CAMPAIGN["headline"], MARGIN, y, _font(FONT_BLACK, 56))
    # Sub-headline
    y += 18
    y = draw_text_block(draw, CAMPAIGN["subhead"], MARGIN, y, _font(FONT_BLACK, 38))
    # Body
    y += 14
    draw_text_block(draw, CAMPAIGN["body"], MARGIN, y, _font(FONT_REG, 26),
                    line_gap=1.15)

    # Footer (logo SVG + text via Pillow - bypass broken gradient SVG)
    draw_footer(img)

    img.save(out_path, "PNG", optimize=True)
    print(f"  composed -> {out_path.name}", flush=True)
    return out_path


# --- 5. orchestrator ------------------------------------------------------

def _generate_with_retry(seed: int, out_path: Path, retries: int = 3) -> Path | None:
    """Pollinations rate-limits when called in parallel; retry sequentially."""
    import time as _time
    for attempt in range(retries):
        try:
            return generate_background(seed, out_path)
        except Exception as exc:
            wait = 3 * (attempt + 1)
            print(f"  seed={seed} attempt {attempt+1} failed: {exc} "
                  f"(retry in {wait}s)", flush=True)
            _time.sleep(wait)
    print(f"  seed={seed} gave up after {retries} retries", file=sys.stderr)
    return None


def make_variants(seeds: list[int]) -> list[Path]:
    """Generate + compose N variants. Sequential generation to avoid the
    Pollinations free-tier per-IP rate limit; compositing is local and free.
    """
    print(f"generating {len(seeds)} variants via Pollinations + Pillow ...")
    raw = {seed: OUT / f"raw_{seed}.png" for seed in seeds}
    final = {seed: OUT / f"post_variant_{seed}.png" for seed in seeds}

    for seed in seeds:
        result = _generate_with_retry(seed, raw[seed])
        if result is None:
            raw.pop(seed, None)

    print("compositing overlays + brand footer ...")
    for seed, p in raw.items():
        if p.is_file():
            compose(p, final[seed])

    return [final[s] for s in seeds if final[s].is_file()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Render Xalq Sigorta social posts.")
    parser.add_argument(
        "--compose-bg",
        type=Path,
        help="Compose a final post from an existing 1080x1350 background image.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Output PNG path for --compose-bg mode.",
    )
    parser.add_argument(
        "--seeds",
        nargs="*",
        type=int,
        default=[42, 1337, 7890],
        help="Pollinations seeds to generate when not using --compose-bg.",
    )
    args = parser.parse_args()

    if args.compose_bg:
        out = args.out or (OUT / f"{args.compose_bg.stem}_composed.png")
        path = compose(args.compose_bg, out)
        print(f"\nDONE - composed post written:\n  {path}")
        return 0

    paths = make_variants(args.seeds)
    print(f"\nDONE - {len(paths)} variants written:")
    for p in paths:
        print(f"  {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

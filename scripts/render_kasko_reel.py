from __future__ import annotations

import argparse
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont


WIDTH = 1080
HEIGHT = 1920
FPS = 30
DURATION = 10
FRAMES = FPS * DURATION

RED = (226, 28, 40)
GREEN = (20, 144, 64)
DARK = (23, 29, 35)
MUTED = (99, 109, 116)
WHITE = (255, 255, 255)


def font(size: int, bold: bool = False, italic: bool = False) -> ImageFont.FreeTypeFont:
    names = []
    if italic:
        names += ["segoeuii.ttf", "ariali.ttf"]
    elif bold:
        names += ["segoeuib.ttf", "arialbd.ttf"]
    else:
        names += ["segoeui.ttf", "arial.ttf"]

    for name in names:
        path = Path("C:/Windows/Fonts") / name
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


FONTS = {
    "xs": font(28),
    "small": font(34),
    "small_bold": font(34, bold=True),
    "body": font(42),
    "body_bold": font(42, bold=True),
    "card_title": font(54, bold=True),
    "title": font(64, bold=True),
    "hero": font(76, bold=True),
    "hero_italic": font(78, italic=True),
    "mega": font(94, bold=True),
}


def ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def ease_out(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def lerp(a: float, b: float, x: float) -> float:
    return a + (b - a) * x


def fit_cover(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    w, h = image.size
    tw, th = size
    scale = max(tw / w, th / h)
    nw, nh = int(w * scale), int(h * scale)
    resized = image.resize((nw, nh), Image.LANCZOS)
    left = (nw - tw) // 2
    top = (nh - th) // 2
    return resized.crop((left, top, left + tw, top + th))


def fit_contain(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    w, h = image.size
    tw, th = size
    scale = min(tw / w, th / h)
    nw, nh = int(w * scale), int(h * scale)
    return image.resize((nw, nh), Image.LANCZOS)


def rounded_image(image: Image.Image, radius: int) -> Image.Image:
    mask = Image.new("L", image.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, image.size[0], image.size[1]), radius, fill=255)
    out = Image.new("RGBA", image.size, (0, 0, 0, 0))
    out.paste(image.convert("RGBA"), (0, 0), mask)
    return out


def draw_shadowed_round_rect(
    canvas: Image.Image,
    xy: tuple[int, int, int, int],
    radius: int,
    fill: tuple[int, int, int, int],
    shadow_alpha: int = 70,
    shadow_offset: int = 18,
) -> None:
    x1, y1, x2, y2 = xy
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle(
        (x1, y1 + shadow_offset, x2, y2 + shadow_offset),
        radius,
        fill=(0, 0, 0, shadow_alpha),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(24))
    canvas.alpha_composite(shadow)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(xy, radius, fill=fill)


def text_size(draw: ImageDraw.ImageDraw, value: str, text_font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), value, font=text_font)
    return box[2] - box[0], box[3] - box[1]


def wrap_lines(
    draw: ImageDraw.ImageDraw,
    value: str,
    text_font: ImageFont.FreeTypeFont,
    max_width: int,
) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in value.split():
        candidate = f"{current} {word}".strip()
        if text_size(draw, candidate, text_font)[0] <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word
    if current:
        lines.append(current)
    return lines


def draw_wrapped(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    value: str,
    text_font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
    max_width: int,
    line_gap: int = 10,
) -> int:
    x, y = xy
    for line in wrap_lines(draw, value, text_font, max_width):
        draw.text((x, y), line, font=text_font, fill=fill)
        y += text_size(draw, line, text_font)[1] + line_gap
    return y


def paste_centered(base: Image.Image, image: Image.Image, box: tuple[int, int, int, int]) -> None:
    x1, y1, x2, y2 = box
    cx = x1 + (x2 - x1 - image.size[0]) // 2
    cy = y1 + (y2 - y1 - image.size[1]) // 2
    base.alpha_composite(image.convert("RGBA"), (cx, cy))


def draw_pill(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    label: str,
    fill: tuple[int, int, int],
    text_fill: tuple[int, int, int],
    text_font: ImageFont.FreeTypeFont,
    pad_x: int = 28,
    pad_y: int = 16,
) -> tuple[int, int, int, int]:
    x, y = xy
    tw, th = text_size(draw, label, text_font)
    rect = (x, y, x + tw + pad_x * 2, y + th + pad_y * 2)
    draw.rounded_rectangle(rect, radius=(th + pad_y * 2) // 2, fill=fill)
    draw.text((x + pad_x, y + pad_y - 2), label, font=text_font, fill=text_fill)
    return rect


def make_assets(source: Path) -> dict[str, Image.Image]:
    poster = Image.open(source).convert("RGBA")
    bg = fit_cover(poster, (WIDTH, HEIGHT)).filter(ImageFilter.GaussianBlur(26))
    tint = Image.new("RGBA", (WIDTH, HEIGHT), (255, 255, 255, 118))
    bg.alpha_composite(tint)

    vignette = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    v = ImageDraw.Draw(vignette)
    for i in range(42):
        alpha = int(3.2 * i)
        v.rectangle((0, i * 14, WIDTH, HEIGHT - i * 14), outline=(255, 255, 255, alpha))
    bg.alpha_composite(vignette)

    thumb = fit_cover(poster, (852, 1030))
    poster_fit = fit_contain(poster, (894, 1192))
    poster_fill = fit_cover(poster, (920, 1228))

    return {
        "poster": poster,
        "bg": bg,
        "thumb": rounded_image(thumb, 34),
        "poster_fit": rounded_image(poster_fit, 38),
        "poster_fill": rounded_image(poster_fill, 42),
    }


def draw_open_graph_card(canvas: Image.Image, assets: dict[str, Image.Image], t: float) -> None:
    draw = ImageDraw.Draw(canvas)
    intro = ease_out(t / 1.05)
    y = int(lerp(232, 148, intro))
    card_alpha = int(255 * intro)
    card = Image.new("RGBA", (936, 1482), (0, 0, 0, 0))
    draw_shadowed_round_rect(card, (0, 0, 936, 1482), 44, (255, 255, 255, card_alpha), 42, 14)
    cd = ImageDraw.Draw(card)

    cd.ellipse((44, 42, 92, 90), fill=RED + (255,))
    cd.polygon([(55, 66), (78, 50), (69, 66), (81, 86)], fill=(255, 255, 255, 255))
    cd.text((112, 38), "Sponsored", font=FONTS["small_bold"], fill=DARK + (card_alpha,))
    cd.text((112, 76), "Xalq Sığorta", font=FONTS["xs"], fill=MUTED + (card_alpha,))
    draw_pill(cd, (678, 42), "Reels 9:16", (237, 248, 242), GREEN, FONTS["xs"], 20, 12)

    card.alpha_composite(assets["thumb"], (42, 128))
    cd.text((48, 1198), "Qurban bayramına özəl təklif", font=FONTS["body_bold"], fill=GREEN + (255,))
    cd.text((48, 1262), "KASKO al,", font=FONTS["card_title"], fill=RED + (255,))
    cd.text((48, 1322), "yanacaq kartın hədiyyə olsun!", font=FONTS["card_title"], fill=RED + (255,))
    cd.text((48, 1410), "25 may - 5 iyun", font=FONTS["body_bold"], fill=DARK + (255,))
    draw_pill(cd, (610, 1392), "Ətraflı bax", GREEN, WHITE, FONTS["small_bold"], 28, 16)

    canvas.alpha_composite(card, (72, y))


def draw_poster_focus(canvas: Image.Image, assets: dict[str, Image.Image], t: float) -> None:
    draw = ImageDraw.Draw(canvas)
    p = ease((t - 2.35) / 2.75)
    y = int(lerp(420, 300, p))
    scale = lerp(0.92, 1.02, p)
    poster = assets["poster_fit"]
    w = int(poster.size[0] * scale)
    h = int(poster.size[1] * scale)
    poster_scaled = poster.resize((w, h), Image.LANCZOS)

    draw_shadowed_round_rect(
        canvas,
        (84, y - 38, 996, y + h + 38),
        54,
        (255, 255, 255, 238),
        58,
        16,
    )
    canvas.alpha_composite(poster_scaled, ((WIDTH - w) // 2, y))

    top = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    td = ImageDraw.Draw(top)
    alpha = int(255 * ease((t - 2.45) / 0.55))
    td.rounded_rectangle((72, 122, 1008, 270), 36, fill=(255, 255, 255, min(242, alpha)))
    td.text((108, 152), "KASKO al", font=FONTS["title"], fill=RED + (alpha,))
    td.text((420, 158), "yanacaq kartı qazan", font=FONTS["card_title"], fill=GREEN + (alpha,))
    canvas.alpha_composite(top)


def draw_info_scene(canvas: Image.Image, t: float) -> None:
    draw = ImageDraw.Draw(canvas)
    overlay_alpha = int(222 * ease((t - 5.0) / 0.45))
    veil = Image.new("RGBA", (WIDTH, HEIGHT), (255, 255, 255, overlay_alpha))
    canvas.alpha_composite(veil)

    draw.text((84, 142), "Kampaniya şərtləri", font=FONTS["hero"], fill=DARK)
    draw.text((86, 232), "Sosial şəbəkə elanı üçün qısa versiya", font=FONTS["small"], fill=MUTED)

    items = [
        ("25 MAY - 5 İYUN", "KASKO sığortası edənlər üçün"),
        ("750 AZN+", "Sığorta haqqı bu məbləğdən yuxarı olduqda"),
        ("AZPETROL", "Yanacaq kartı hədiyyə"),
    ]

    for index, (title, desc) in enumerate(items):
        local = ease_out((t - 5.2 - index * 0.28) / 0.62)
        x = int(lerp(1320, 84, local))
        y = 390 + index * 306
        draw_shadowed_round_rect(
            canvas,
            (x, y, x + 912, y + 228),
            36,
            (255, 255, 255, 248),
            42,
            12,
        )
        draw.rounded_rectangle((x, y, x + 18, y + 228), 18, fill=GREEN if index != 1 else RED)
        draw.text((x + 56, y + 46), title, font=FONTS["hero"], fill=GREEN if index != 1 else RED)
        draw.text((x + 58, y + 136), desc, font=FONTS["body"], fill=DARK)

    fine = (
        "Təklif yalnız bonus əmsalı 1.0-dan aşağı olan sürücülərə və son 10 il buraxılışlı "
        "minik avtomobillərinə aiddir. Taksi, rent a car və sərnişin daşımaları daxil deyil."
    )
    draw.rounded_rectangle((84, 1366, 996, 1568), 30, fill=(245, 248, 247, 242))
    draw_wrapped(draw, (120, 1402), fine, FONTS["small"], MUTED, 840, 8)


def draw_final_scene(canvas: Image.Image, assets: dict[str, Image.Image], t: float) -> None:
    draw = ImageDraw.Draw(canvas)
    overlay_alpha = int(238 * ease((t - 7.8) / 0.6))
    canvas.alpha_composite(Image.new("RGBA", (WIDTH, HEIGHT), (255, 255, 255, overlay_alpha)))

    p = ease_out((t - 7.92) / 0.72)
    y = int(lerp(420, 236, p))
    draw_shadowed_round_rect(canvas, (72, y, 1008, y + 1190), 52, (255, 255, 255, 250), 52, 16)
    poster = assets["poster_fill"].resize((720, 960), Image.LANCZOS)
    canvas.alpha_composite(poster, (180, y + 60))

    panel_y = y + 1032
    draw.rounded_rectangle((116, panel_y, 964, panel_y + 250), 38, fill=(248, 250, 249, 255))
    draw.text((154, panel_y + 34), "Avtomobilinizi qoruyun", font=FONTS["title"], fill=DARK)
    draw.text((154, panel_y + 106), "yanacaq kartı qazanın", font=FONTS["title"], fill=GREEN)
    draw_pill(draw, (154, panel_y + 184), "25 may - 5 iyun", RED, WHITE, FONTS["small_bold"], 30, 14)
    draw.text((660, panel_y + 188), "Xalq Sığorta × AZPETROL", font=FONTS["small_bold"], fill=DARK)


def frame_at(assets: dict[str, Image.Image], index: int) -> np.ndarray:
    t = index / FPS
    canvas = assets["bg"].copy()

    # Subtle pulse keeps the static poster feeling native to Reels.
    pulse = 1 + math.sin(t * math.pi * 0.8) * 0.012
    bg = fit_cover(assets["poster"], (int(WIDTH * pulse), int(HEIGHT * pulse))).filter(ImageFilter.GaussianBlur(22))
    left = (bg.size[0] - WIDTH) // 2
    top = (bg.size[1] - HEIGHT) // 2
    canvas = bg.crop((left, top, left + WIDTH, top + HEIGHT))
    canvas.alpha_composite(Image.new("RGBA", (WIDTH, HEIGHT), (255, 255, 255, 132)))

    if t < 2.65:
        draw_open_graph_card(canvas, assets, t)
    elif t < 5.2:
        draw_poster_focus(canvas, assets, t)
    elif t < 7.95:
        draw_poster_focus(canvas, assets, 5.2)
        draw_info_scene(canvas, t)
    else:
        draw_final_scene(canvas, assets, t)

    rgb = canvas.convert("RGB")
    return cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2BGR)


def render(source: Path, output: Path) -> None:
    assets = make_assets(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(output), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (WIDTH, HEIGHT))
    if not writer.isOpened():
        raise RuntimeError("Could not open OpenCV MP4 writer with mp4v codec.")
    for index in range(FRAMES):
        writer.write(frame_at(assets, index))
    writer.release()


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a 10-second KASKO Meta Reels ad.")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", default=Path("output/kasko-qurban-reels-10s.mp4"), type=Path)
    args = parser.parse_args()
    render(args.source, args.output)


if __name__ == "__main__":
    main()

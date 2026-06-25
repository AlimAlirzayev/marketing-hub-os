from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

from render_kasko_reel import (
    DURATION,
    FPS,
    FRAMES,
    HEIGHT,
    WIDTH,
    draw_final_scene,
    draw_info_scene,
    draw_open_graph_card,
    draw_poster_focus,
    fit_cover,
    make_assets,
)


def make_video_background(frame: np.ndarray, poster: Image.Image) -> Image.Image:
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    image = Image.fromarray(rgb).convert("RGBA")
    bg = fit_cover(image, (WIDTH, HEIGHT))
    bg = ImageEnhance.Color(bg).enhance(0.72)
    bg = ImageEnhance.Contrast(bg).enhance(0.92)
    bg = bg.filter(ImageFilter.GaussianBlur(18))
    bg.alpha_composite(Image.new("RGBA", (WIDTH, HEIGHT), (255, 255, 255, 116)))

    # Keep a faint campaign-color wash even if the generated background drifts.
    poster_bg = fit_cover(poster, (WIDTH, HEIGHT)).filter(ImageFilter.GaussianBlur(32))
    poster_bg.putalpha(70)
    bg.alpha_composite(poster_bg)
    return bg


class VideoFrameSampler:
    def __init__(self, cap: cv2.VideoCapture, source_fps: float) -> None:
        self.cap = cap
        self.source_fps = source_fps
        self.frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.current_index = -1
        self.current_frame: np.ndarray | None = None

    def at(self, t: float) -> np.ndarray:
        target = min(self.frame_count - 1, max(0, int(t * self.source_fps)))
        while self.current_index < target:
            ok, frame = self.cap.read()
            if not ok:
                break
            self.current_frame = frame
            self.current_index += 1
        if self.current_frame is None:
            raise RuntimeError("Could not read a frame from the Flora video.")
        return self.current_frame


def frame_at(assets: dict[str, Image.Image], sampler: VideoFrameSampler, index: int) -> np.ndarray:
    t = index / FPS
    source_frame = sampler.at(t)
    canvas = make_video_background(source_frame, assets["poster"])

    if t < 2.65:
        draw_open_graph_card(canvas, assets, t)
    elif t < 5.2:
        draw_poster_focus(canvas, assets, t)
    elif t < 7.95:
        draw_poster_focus(canvas, assets, 5.2)
        draw_info_scene(canvas, t)
    else:
        draw_final_scene(canvas, assets, t)

    return cv2.cvtColor(np.array(canvas.convert("RGB")), cv2.COLOR_RGB2BGR)


def render(source: Path, flora_video: Path, output: Path) -> None:
    assets = make_assets(source)
    cap = cv2.VideoCapture(str(flora_video))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open Flora video: {flora_video}")
    source_fps = cap.get(cv2.CAP_PROP_FPS) or 24
    sampler = VideoFrameSampler(cap, source_fps)

    output.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(output), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (WIDTH, HEIGHT))
    if not writer.isOpened():
        raise RuntimeError("Could not open OpenCV MP4 writer with mp4v codec.")

    for index in range(FRAMES):
        writer.write(frame_at(assets, sampler, index))

    writer.release()
    cap.release()


def main() -> None:
    parser = argparse.ArgumentParser(description="Render production-safe KASKO Reels video using Flora motion.")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--flora-video", required=True, type=Path)
    parser.add_argument("--output", default=Path("output/kasko-qurban-flora-hybrid-clean-10s.mp4"), type=Path)
    args = parser.parse_args()
    render(args.source, args.flora_video, args.output)


if __name__ == "__main__":
    main()

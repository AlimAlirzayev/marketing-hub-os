"""Token-saving research helper: digest a YouTube video with a FREE LLM.

Best practice for agent token economy: never pour a raw transcript into the
expensive agent context. Instead fetch the transcript (free, no model) and have
a free LLM (Gemini) pre-digest it into tight English bullets focused on a topic.
The agent then reads only the short digest.

    python scripts/yt_digest.py <url|id> ["focus topic"]

Writes scripts/_digests/<id>.md and prints it. Reused by /scout and research.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DIGESTS = Path(__file__).resolve().parent / "_digests"
DEFAULT_FOCUS = (
    "AI agents, automation, free/open-source/self-hosted tools, social media "
    "publishing, video clipping/shorts, local LLMs, token-saving — anything "
    "actionable for a zero-budget, Docker-free marketing automation system."
)


def _load_env() -> None:
    env = REPO / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _video_id(s: str) -> str:
    m = re.search(r"(?:v=|youtu\.be/|shorts/)([\w-]{11})", s)
    return m.group(1) if m else s


def _transcript(video_id: str) -> str:
    from youtube_transcript_api import YouTubeTranscriptApi

    api = YouTubeTranscriptApi()
    listing = api.list(video_id)
    chosen = None
    for code in ("en", "tr", "az"):
        try:
            chosen = listing.find_transcript([code]); break
        except Exception:
            continue
    if chosen is None:
        for tr in listing:
            chosen = tr; break
    if chosen is None:
        raise RuntimeError(f"no transcript for {video_id}")
    parts = []
    for e in chosen.fetch():
        t = getattr(e, "text", None) or (e.get("text") if isinstance(e, dict) else "")
        if t:
            parts.append(str(t).strip())
    return " ".join(parts)[:60_000]


def _digest(text: str, focus: str) -> str:
    prompt = (
        f"Summarize this video transcript for an engineer. Focus on: {focus}\n\n"
        "Output tight English markdown: (1) one-line what-it-is, (2) 5-10 bullets "
        "of concrete tools/techniques/claims with any names, prices, or repos "
        "mentioned, (3) a 'For us' line — what a zero-budget Docker-free marketing "
        "automation team should steal. Skip filler.\n\nTRANSCRIPT:\n" + text
    )
    # Primary: the unified free-first router (Groq → Gemini → ...).
    try:
        sys.path.insert(0, str(REPO))
        from llm_router import complete
        out, _ = complete(prompt, tier="cheap", temperature=0.3)
        return out
    except Exception:
        pass
    # Fallback: direct Gemini (router/litellm unavailable).
    from google import genai
    from google.genai import types

    key = os.getenv("GEMINI_API_KEY") or os.environ["GOOGLE_API_KEY"]
    model = os.getenv("MODEL_FREE_BULK") or "gemini-2.5-flash"
    client = genai.Client(api_key=key)
    resp = client.models.generate_content(
        model=model, contents=prompt,
        config=types.GenerateContentConfig(temperature=0.3),
    )
    return (resp.text or "").strip()


def main(argv: list[str]) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    if not argv:
        print("usage: python scripts/yt_digest.py <url|id> [\"focus\"]")
        return 2
    _load_env()
    vid = _video_id(argv[0])
    focus = argv[1] if len(argv) > 1 else DEFAULT_FOCUS
    try:
        text = _transcript(vid)
        digest = _digest(text, focus)
    except Exception as e:
        print(f"yt_digest: {e}")
        return 1
    DIGESTS.mkdir(parents=True, exist_ok=True)
    out = DIGESTS / f"{vid}.md"
    out.write_text(f"# Digest {vid}\n\n{digest}\n", encoding="utf-8")
    print(f"[{len(text)} transcript chars → digest] {out}\n")
    print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

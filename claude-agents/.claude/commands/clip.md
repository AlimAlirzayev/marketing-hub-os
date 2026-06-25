---
description: Mine a long video (local file or YouTube URL) for its most viral moments and cut them into platform-ready vertical shorts. Free + local — the in-house "personal clipper".
argument-hint: <video path or YouTube URL> [--n 5] [--aspect 9:16] [--fit cover|contain] [--lang en] [--no-cut]
---

# /clip

The free, local answer to a paid clipper (the one from the Higgsfield video).
Hand it a long video; it finds the moments most likely to go viral, scores them
0-100, and cuts the top ones into 9:16 shorts — all on free infra. The natural
front half of the pipeline: `/clip` makes the shorts, `/publish` ships them.

`$ARGUMENTS` = a local path (under `video-studio/`) or a YouTube URL, plus flags.

## How it works (see `video-studio/clipper.py`)
1. **Transcript** — YouTube URL → caption API (instant, no download); local file
   → Whisper on the audio (free Groq backend).
2. **Score** — the free LLM cascade (Groq → Gemini) picks the top viral windows
   with a one-line reason each. No Higgsfield credits spent.
3. **Cut** — FFmpeg (`ffmpeg_ops.cut_clip`) cuts each to vertical 9:16.
4. Output lands in `video-studio/output/clips/<slug>/` with a `clips.json`.

## Steps
1. **Parse `$ARGUMENTS`** — first token is the source; flags follow.
   `--n` clip count (default 5), `--aspect` (9:16 default, also 1:1/4:5/16:9),
   `--fit` reframe mode — `cover` (crop to fill, best for a talking head) or
   `contain` (whole frame on a blurred backdrop, best for screen-share/slides),
   `--lang` transcript language (default en), `--no-cut` to score only.

2. **Pre-flight.** Confirm a free LLM is available (`GROQ_API_KEY` preferred,
   else `GOOGLE_API_KEY`). If neither, tell the user which free key to add and
   stop — don't reach for a paid tool.

3. **Run it.**
   ```
   python video-studio/clipper.py "<source>" --n 5 --aspect 9:16 --lang en
   ```
   For a YouTube URL with no `yt-dlp` installed, the clipper still returns the
   ranked **plan** (timestamps + scores + reasons) but cuts nothing — surface
   that and offer to cut once the file is local or `yt-dlp` is installed. This is
   a labelled fallback, never a silent drop.

4. **Report** the ranked clips as a table: score · start–end · hook · reason ·
   output path. Call out the strongest one or two; be honest about weak scores
   (a 53/100 is a 53, like in the reference video).

5. **Offer the handoffs.**
   - Polish a clip with motion graphics/captions/music → `/edit-video`.
   - Publish the winners → `/publish <path> --to tiktok,x`.
   - Want premium quality instead of free? Higgsfield is the cascade's paid tier
     in [capabilities.md](../capabilities.md) — only if the free cut isn't enough
     and credits remain.

## Rules
- **Free-first.** The whole default path is free; don't spend a credit the local
  pipeline already covers.
- **No silent drops.** Can't fetch the media? Return the plan and say so.
- **Honest scores.** Report the model's scores straight; don't inflate them.

## Examples
```
/clip https://www.youtube.com/watch?v=uoflzZfJ8kc --n 5
/clip input/webinar-45min.mp4 --n 8 --aspect 9:16
/clip https://youtu.be/abc123 --no-cut          # just the ranked plan
```

# Video Studio

The **video edit & motion-graphics** capability of Xalq Insurance Digital OS — the marketing
domain's answer to "take this clip and turn it into a LinkedIn post".

You hand it a raw recording and a plain-language brief; it returns a finished,
platform-ready video: trimmed, retimed, reformatted, captioned, wrapped in
motion graphics, and scored with a music bed.

## The idea: LLM plans, renderer executes

The LLM never touches the video file — that would be slow and
non-reproducible. Instead the work is split in two:

```
  Brief (you, in Azerbaijani)
      │
      ▼
  LLM  ──writes──▶  edit_spec.json   ◀── validated by edit_spec.schema.json
  (the "brain": what to do)
      │
      ▼
  render.py  ──executes──▶  finished .mp4
  (the "muscle": deterministic FFmpeg + Remotion)
```

`edit_spec.json` is the whole contract. Anything the LLM wants done has to be
expressible in [`edit_spec.schema.json`](edit_spec.schema.json); the renderer
does exactly that and nothing else. Same spec in → same video out, every time.

## Pipeline

`render.py` runs six deterministic stages:

| # | Stage | Tool | What it does |
|---|-------|------|--------------|
| 1 | probe | ffprobe | read duration / resolution / fps |
| 2 | trim | FFmpeg | drop dead head & tail |
| 3 | cuts | FFmpeg | delete inner mistakes / pauses |
| 4 | base | FFmpeg | speed change + aspect/resolution + loudness normalise |
| 5 | captions | Whisper | speech-to-text → word-timed captions (Groq API or local) |
| 6 | compose | Remotion | intro + outro + lower-thirds + animated captions |
| — | music | FFmpeg | mix an energetic electronic bed, ducked under the voice |

## Layout

```
video-studio/
├── generative_ads/        AI ad-generation briefs, model matrix, prompts, QA
├── render.py              pipeline orchestrator (entry point)
├── clipper.py             viral clipper: long video → ranked vertical shorts
├── ffmpeg_ops.py          FFmpeg wrappers: probe, trim, cuts, retime, cut_clip, mix
├── transcribe.py          local Whisper → word-timed captions
├── paths.py               locates the portable Node.js / FFmpeg
├── edit_spec.schema.json  the LLM ↔ renderer contract
├── edit_spec.example.json a worked example
├── requirements.txt       Python deps (faster-whisper, jsonschema)
├── remotion/              Remotion project — motion graphics
│   └── src/components/    Intro, Outro, LowerThird, Captions
├── music/                 royalty-free music library + manifest
├── tools/                 portable Node.js + FFmpeg (git-ignored)
├── input/                 drop raw videos here (git-ignored)
├── output/                finished videos land here (git-ignored)
└── work/                  per-job intermediates (git-ignored)
```

## Setup (one-off)

```powershell
# 1. Portable Node.js + FFmpeg (winget is blocked by Group Policy here)
.\scripts\install-video-tools.ps1

# 2. Python deps
pip install -r video-studio\requirements.txt
```

Remotion's own `node_modules` installs itself automatically on the first
render.

### Captions backend

Captions use Whisper, and there are two backends (see `transcribe.py`):

- **Groq (recommended here).** Set a free `GROQ_API_KEY` and captions just
  work — no native dependency, fast. Get a key at
  https://console.groq.com/keys.
- **Local openai-whisper (offline).** `pip install openai-whisper`. Fully
  offline, no key. **Currently blocked on this machine:** the corporate VC++
  runtime / EDR lockdown stops the PyTorch *and* ctranslate2 native libraries
  from loading (`WinError 1114`). It will work once IT installs the
  **Visual C++ 2015–2022 Redistributable** (`vcruntime140_1.dll` is missing).

If neither is available the renderer simply skips captions and says so — the
rest of the video still renders.

## Usage

### Via Claude Code (the intended way)

Open Claude Code in `claude-agents/` and run:

```
/edit-video input/raw.mp4  LinkedIn üçün, 1.5x sürət, intro + caption, energetik electron musiqi
```

Claude probes the clip, writes an `edit_spec.json`, shows it to you for
approval, then runs `render.py`.

### Directly

```powershell
python video-studio\render.py video-studio\edit_spec.example.json
```

### Generative AI ad campaigns

Use `generative_ads/` when the job is not editing an existing video, but
creating a new ad from brand assets, reference images, storyboard, and Flora
or another AI video model.

```powershell
python scripts\validate_generative_ad.py video-studio\generative_ads\campaigns\kasko-qurban-2026\brief.json
python scripts\compile_generative_ad.py video-studio\generative_ads\campaigns\kasko-qurban-2026\brief.json
```

The compiled prompt is saved under the campaign's `prompts/` folder. Use it
with the model strategy in `generative_ads/model_matrix.flora.md`, then finish
the ad with deterministic overlays for logos, dates, prices, legal copy, and
CTA.

### Viral clipper (long video → vertical shorts)

`clipper.py` is the free, local "personal clipper": hand it a long video and it
finds the most viral moments, scores them 0-100, and cuts the top ones into 9:16
shorts. Same brain/muscle split — an LLM plans, FFmpeg executes.

```powershell
# YouTube URL (captions pulled instantly, no download for the scoring step):
python video-studio\clipper.py "https://www.youtube.com/watch?v=<id>" --n 5

# Local long recording:
python video-studio\clipper.py input\webinar-45min.mp4 --n 8 --aspect 9:16

# Score only, don't cut:
python video-studio\clipper.py "<url>" --no-cut
```

- **Transcript** — YouTube → `youtube-transcript-api` (instant, free); local file
  → Whisper via `transcribe.py` (free Groq backend).
- **Scoring** — free LLM cascade: `GROQ_API_KEY` preferred, else Gemini. No
  Higgsfield credits are spent.
- **Cutting** — needs `yt-dlp` (for URLs) + the portable FFmpeg. Without `yt-dlp`
  the clipper still returns the ranked *plan*; it just doesn't cut.

Output lands in `output/clips/<slug>/` with a `clips.json` manifest. From Claude
Code the intended entry point is `/clip`; the winners then go to `/edit-video`
(polish) or `/publish` (ship).

## Notes

- **Captions.** The local backend runs Whisper in `translate` mode, so even an
  Azerbaijani recording yields English captions. The Groq backend transcribes
  in the spoken language — record in English for English captions there.
- **Music is never bundled.** Drop royalty-free tracks into `music/` and list
  them in `music/manifest.json`; see [music/README.md](music/README.md).
- **Zero budget.** FFmpeg, Node.js, Remotion, and Whisper are all free and run
  locally. Nothing is uploaded; nothing is published automatically.

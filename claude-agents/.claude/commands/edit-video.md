---
description: Edit and montage a raw video into a platform-ready clip via Video Studio
argument-hint: <video path> <plain-language brief>
---

# /edit-video

Turn a raw recording into a finished, platform-ready video using the Xalq Insurance Digital OS
**Video Studio** (`video-studio/`). You plan the edit; `render.py` executes it.

`$ARGUMENTS` = the video path followed by a free-text brief, e.g.

```
/edit-video input/raw.mp4  LinkedIn üçün, 1.5x sürət, intro + outro,
            avtomatik subtitr, energetik electron musiqi
```

## Steps

1. **Parse `$ARGUMENTS`.** The first token is the video path, relative to
   `video-studio/` (e.g. `input/raw.mp4`). The rest is the brief.
   If either is missing, ask the user before continuing.

2. **Probe the clip.** Run
   `python video-studio/paths.py` once to confirm the tools resolve, then
   inspect the source so the spec uses real numbers:
   ```
   python -c "import sys; sys.path.insert(0,'video-studio'); import ffmpeg_ops as f; print(f.probe('video-studio/<path>'))"
   ```
   This gives duration, resolution, fps, and whether the clip has audio.

3. **Write the edit spec.** Translate the brief into an `edit_spec.json` that
   validates against `video-studio/edit_spec.schema.json`. Map the user's
   words to spec fields, e.g.:
   - "LinkedIn" → `job.platform`, and `format.aspect` = `1:1` or `4:5`
   - "1.5x sürət" → `timeline.speed: 1.5`
   - "intro / outro" → `motion_graphics.intro|outro` with drafted copy
   - "subtitr" → `captions.enabled: true` (language stays `en`)
   - "energetik electron musiqi" → `audio.music.mood: "energetic-electronic"`
   Save it as `video-studio/jobs/<slug>.json` (create `jobs/` if needed).

4. **Show the spec and get approval.** Display the JSON and a one-line plain
   summary. Do **not** render until the user approves. Apply any tweaks they
   ask for and re-show.

5. **Render.** On approval, run:
   ```
   python video-studio/render.py video-studio/jobs/<slug>.json
   ```
   Relay the six-stage progress; surface FFmpeg/Remotion errors verbatim.

6. **Report.** Give the user the output path under `video-studio/output/` and
   a short note of what was applied (speed, format, graphics, music track).

## Notes

- The first render also installs Remotion's `node_modules` — it takes a few
  extra minutes once, then never again.
- If `music/` has no track matching the mood, the renderer skips the music bed
  and says so; point the user to `video-studio/music/README.md`.
- Nothing is published. `/edit-video` only produces a file; sharing it on
  LinkedIn is a separate, explicit step.
- Tools missing? Run `scripts/install-video-tools.ps1` first.

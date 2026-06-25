# Music library

Background music beds for Video Studio. **Audio files are git-ignored** — you
download them once into this folder, then describe each one in
[`manifest.json`](manifest.json). `render.py` reads the manifest whenever an
edit spec asks for `music.track = "auto"`: it filters by the `mood` tag and
picks a track.

## How to add a track

1. Download a royalty-free track (see sources below) into this folder.
2. Add an entry to the `tracks` array in `manifest.json`:

   ```json
   {
     "file": "energetic-01.mp3",
     "title": "Neon Drive",
     "moods": ["energetic-electronic"],
     "bpm": 128,
     "source": "https://pixabay.com/music/...",
     "license": "Pixabay Content License - free for commercial use, no attribution"
   }
   ```

3. That's it — the next `auto` render can pick it.

## Where to get royalty-free electronic music (zero budget)

| Source | URL | Notes |
|---|---|---|
| **Pixabay Music** | https://pixabay.com/music/search/electronic/ | Best fit. Free for commercial use, **no attribution required**. Filter by genre "Electronic" / "Dance". |
| YouTube Audio Library | https://studio.youtube.com → Audio Library | Free; some tracks require attribution — check the licence column. |
| Free Music Archive | https://freemusicarchive.org | Mixed licences; pick CC0 or CC-BY tracks only. |
| ccMixter | https://dig.ccmixter.org | CC-licensed; attribution usually required. |

> For a LinkedIn "production-style energetic" feel, look for **electro / future
> bass / tech-house** tracks around **120–130 BPM**. Tag them
> `energetic-electronic` in the manifest.

## Licensing

Keep the `source` and `license` fields filled in for every track — that is your
proof you may use it in published content. Never drop a track in here from an
unknown source; LinkedIn (and your client work) can be hit with copyright
claims for unlicensed music.

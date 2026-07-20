# Post-production spec — the 70%

Track D3 of [MUSIC_ROADMAP.md](MUSIC_ROADMAP.md). The generator is ~30% of a professional
release; selection, mixing and mastering are the rest. This file specs that layer as an
extension of `audio_studio.py` — **not** a new module (repo rule: reinforce, don't fragment).

Status: **mastering is solved and verified. The rest is specced but OPEN.** The D3 research
agent hit a session limit mid-flight; what is proven below is proven, and what is not is
labelled OPEN. Nothing here is assumed.

---

## 1. Mastering — SOLVED, measured (2026-07-12)

Verified on a transient-rich 120 BPM test signal (`music-lab/master_chain.sh`, reproducible).

### The trap
The obvious chain — push loudness up, then limit just under 0 dBFS — **clips after encoding**:

| Chain | master.wav | after 192k mp3 | verdict |
|---|---|---|---|
| `loudnorm I=-7` + `alimiter limit=-0.1dB` | **+0.2 dBTP** | **+0.4 dBTP** | **CLIPS** |
| `loudnorm I=-9` + `alimiter limit=-0.1dB` | -0.3 dBTP | -0.7 dBTP | marginal |
| **two-pass `loudnorm I=-14 TP=-1.0 LRA=11 linear=true`** | **-5.5 dBTP** | **-5.8 dBTP** | **PASS** |

`alimiter` caps **sample** peak. A lossy decoder reconstructs **inter-sample** peaks between
those samples, so a file that measures -0.10 dBTP comes back at +0.40 dBTP and clips on
playback. A better limiter is not the fix.

### The rule
> **Master to -14 LUFS integrated, TP ceiling -1.0 dBTP, two-pass linear `loudnorm`.
> Never chase loudness with a limiter.**

Normalising *down* to -14 LUFS leaves ~5 dB of true-peak headroom by itself — which is why
the ceiling choice barely matters once you stop mastering hot. YouTube and Spotify normalise
to roughly this level anyway: a hot master buys **no** perceived loudness on the platform and
pays for it in clipping. The loudness war is a fight you win by not entering.

### The chain (both passes required; one-pass loudnorm is dynamic and pumps)
```bash
# pass 1 — measure
ffmpeg -i in.wav -af loudnorm=I=-14:TP=-1.0:LRA=11:print_format=json -f null -
# pass 2 — apply the measured values, linear
ffmpeg -i in.wav -af "loudnorm=I=-14:TP=-1.0:LRA=11:\
measured_I=…:measured_TP=…:measured_LRA=…:measured_thresh=…:linear=true,aresample=44100" out.wav
```

### CLI surface
`audio_studio.py master <in> [--out F] [--lufs -14] [--tp -1.0]` → writes the master and a
sidecar JSON with measured in/out LUFS and true peak. The measurement is the receipt; a
master that cannot be measured must fail, never silently pass.

---

## 2. The ffmpeg gap — a real latent hole on the VPS

`ffmpeg` is **not installed on the Hetzner VPS** (verified 2026-07-11; `yt-dlp` is present).
Three code paths already depend on it, all via `shutil.which("ffmpeg")`:

- `audio-studio/audio_studio.py:647`
- `media_studio/animatic.py:26`
- `video-studio/paths.py:34`

Because they probe with `which`, they **do not crash — they silently skip**. So today, on the
VPS, audio post-processing and animatic rendering quietly do nothing while reporting success.
That is worse than a crash. This was built and proven on the Windows work PC, where ffmpeg
exists; nobody re-checked the server.

**Action:** `apt-get install -y ffmpeg` on the VPS, and make the callers *fail loudly* when
ffmpeg is absent rather than skipping.

---

## 3. OPEN — not yet done, do not assume

| Item | Why it matters | Status |
|---|---|---|
| **Music auto-judge** | The existing `--best-of N` judge scores **ASR character-error-rate** — a *speech* metric. It is meaningless for songs. A music rubric needs: hook energy curve, vocal intelligibility, structural coherence, near-duplicate detection across the catalogue. | **OPEN.** ⚠️ Be honest here: an auto-judge that claims to score "musical quality" is snake oil. It can reject *bad* takes (silence, mush, clipping, duplicates); it cannot pick the *good* one. That stays Alim's ear. |
| **Stem separation (Demucs)** | Needed for remixing and clean transitions. | **OPEN** — wall-clock on 4 CPU cores unmeasured. Likely minutes per track. Question its value before building it. |
| **BPM / key detection** | Required for beat-matched, harmonically-correct transitions (Camelot wheel). | **OPEN** — `librosa` proven to install on the Mac; not yet installed or benchmarked on the VPS. |
| **Continuous-mix assembly** | The actual product: 20 tracks → one beat-matched 60-minute set. | **OPEN** — the highest-value unbuilt piece. |

## 4. What cannot be automated

Take *selection* and transition *taste*. The judge can throw out the unusable; it cannot tell
you which track is good. Every plan that pretends otherwise is the plan that produces a
channel indistinguishable from the mass-produced AI content YouTube demonetises — see
[COMPLIANCE.md](COMPLIANCE.md). **The human ear in the loop is not a bottleneck to engineer
away; it is the thing that keeps the channel legal.**

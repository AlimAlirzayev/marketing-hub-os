# Music Engine — build roadmap (2026-07-11)

Twin of [VOICE_ROADMAP.md](VOICE_ROADMAP.md). That one chases a natural **Azerbaijani speaking
voice**; this one chases a **vocal song engine** — "our own Suno" — good enough to ship a
release-grade track.

Reference target (user-supplied): a continuous **Turkish deep-house / trend-pop** YouTube mix
(`youtube.com/watch?v=QoMZT_ieg7g`). That format is the benchmark: vocal songs, one aesthetic,
beat-matched into a 60-minute set.

## The hard truths (verified live on the VPS, 2026-07-11)

1. **We already have the engine shell.** `audio_studio.py` (1022 lines) has the music cascade,
   the provider abstraction, a `--best-of N` judge, and the official `elevenlabs` MCP wired.
   Nothing here needs rebuilding. Do not fragment it with a second module.
2. **The only music rung that runs free is Stable Audio 3 — and it is INSTRUMENTAL ONLY.**
   That single fact is why the system can never produce the reference video. The gap is vocals.
3. **ElevenLabs Music is one paid tier away — but the tier is not the cheap one.** Live probe
   returns `HTTP 402 paid_plan_required: "Music API is not available for free users."` Key
   present, code written, MCP connected. But the *Eleven Music Model-Specific Terms* (26 May
   2026) gate the rights per tier: **`Streaming` — publishing Output to third-party music
   platforms — is Prohibited on Free AND Starter**, so Spotify needs **Creator ($22) minimum**;
   and 44.1 kHz downloads plus usable volume start at **Pro ($99/mo)** — Creator's cap is
   ~62 min/month, less than one 60-minute mix at best-of-4. **Pro is the real floor for the
   channel business.** Full analysis: [COMPLIANCE.md](COMPLIANCE.md).
4. **Training our own music foundation model is out of scope. Permanently.**
   No GPU, cents-per-month budget. ACE-Step took a funded lab thousands of A100-hours.
   We rent the model; we own the pipeline. (Same layer split as MediaForge: we build the
   director, not the camera.)
5. **Turkish is the reachable language; Azerbaijani is the moat.** VOICE_ROADMAP already
   established that no 2026 engine natively supports AZ, and Turkish is the usable Turkic
   neighbour. The reference target is Turkish → in range. AZ vocals stay an open problem,
   and that is precisely where nobody competes.
6. **The model is ~30% of the result.** The reference video's professionalism is mostly
   curation, beat-matched mixing, mastering and packaging. That 70% does not exist yet and
   is CPU-friendly. **That 70% is the actual project.**
7. **Policy, not quality, is the thing most likely to kill this — and the format IS the
   violation.** YouTube's own inauthenticity policy names *"AI-generated content made with
   generic templates giving the impression of mass production"*. A static image over
   continuous AI audio, posted on a schedule, is not adjacent to that example — it is that
   example. Disclosure is mandatory but does not demonetise; **inauthenticity does**.
   Therefore: **automation is the risk and volume is the tell.** Build this pipeline to make
   one human faster, never to make the channel autonomous. Verified detail in
   [COMPLIANCE.md](COMPLIANCE.md); the "DistroKid requires a paid tier at generation time"
   claim that circulates online is **folklore** — the real constraint comes from ElevenLabs'
   per-tier grant, fixed at the moment of generation.
8. **We are not eligible for Content ID and must never register.** It requires *exclusive*
   rights; ElevenLabs expressly disclaims exclusivity. Registering would be a false claim and
   would auto-claim our own mixes.

## The gate (nothing proceeds until this is answered)

**Can a rights-clean engine sing Turkish at the reference video's level?**
Ear-tested by the user. Not measurable by a script.

- **Green** → build the 70% (Phase E1+).
- **Red** → the vocal lane needs Suno (no official API; third-party resellers put commercial
  ownership on sand) or an open model + Turkish/AZ finetune. Both are worse. Know this before
  spending.

## Discovery (kəşf) — run before any building

| # | Track | Who / How | What it must produce |
|---|-------|-----------|----------------------|
| **D1** | **Vocal engine bake-off** — THE gate | User's ear + Claude Code drives generation. Same Turkish deep-house brief through: ElevenLabs Music v2 (paid tier), Lyria 3 (Gemini key already READY — needs `pip install google-genai` + `AUDIO_ENABLE_LYRIA=1`), Suno (manual web, Pro), ACE-Step (rented 4090, ~$0.35/h). Blind A/B. | A ranked verdict on **who sings Turkish well**, with per-track cost and the verbatim commercial-rights clause of the winner. |
| **D2** | **Reference reverse-engineering** — the "master approach" | Claude Code subagent. `yt-dlp` the reference audio → `librosa`/`essentia` for BPM, key, track boundaries; `pyloudnorm` for LUFS; manual listen for hook timing + transition type. | A **sound spec** the generator must hit (BPM band, key rotation, intro/hook/drop timing, LUFS target, transition style) + an **automatic QC rubric** derived from it. |
| **D3** | **Post-production stack** — the 70% | Claude Code subagent. Survey CPU-feasible tooling: Demucs (stems), beat-matched crossfade mixing, `matchering` / ffmpeg `loudnorm` (-14 LUFS for YouTube/Spotify), duplicate/hook detection for the music judge (the existing `--best-of` judge is ASR-CER — speech-only, useless for music). | A build spec for `audio-studio`'s missing post-production layer, with a go/no-go on running each piece on the CPU-only VPS. |
| **D4** | **Rights & monetisation gate** | Claude Code subagent. ElevenLabs self-serve commercial terms verbatim; YouTube July-2025 mass-production rule as enforced; Spotify AI Credits; DistroKid proof-of-rights (it requires you were on a **paid tier at generation time**). | A **compliance gate that blocks publishing**, plus a per-track **rights ledger** schema (engine, plan, timestamp, prompt, human edits) written at generation time — retroactive proof is impossible. |

D1 is sequential and gates everything. D2/D3/D4 run in parallel and are safe to start now —
they cost nothing and stay valid whichever engine wins.

## Execution (icra) — only after the gate is green

- **E0 — Manual proof, ≥1 week** (the user's own standing rule). Three tracks made end-to-end
  by hand on the Mac; one published; watch whether it survives monetisation. No automation
  written until it does.
- **E1 — Vocal rung + music judge.** Light up the paid rung inside the existing cascade. Add a
  **music-specific** auto-judge (hook presence, vocal intelligibility, structure, loudness,
  near-duplicate detection) → generate N takes, keep top-k. This is the hardest piece and the
  one that turns raw output into a catalogue.
- **E2 — Post-production chain.** Stems → tempo/key → beat-matched continuous mix → master to
  -14 LUFS. CPU-only, runs on the VPS. **This is where the reference video's quality actually
  comes from.**
- **E3 — Packaging.** Cover art reuses the established trick: AI background + **text rendered in
  code** (Pillow / HTML→Playwright), which is the only reliable way to get AZ diacritics right.
  Titles, chapters, description, AI disclosure.
- **E4 — Publish.** Surfaced in the panel's *Studiya* tab and Telegram. Publishing is a risky
  outward action → it parks at the existing **human checkpoint** (`/approve N`). The D4
  compliance gate must pass before the approval prompt is even offered.

## Cost model (order of magnitude)

| Lane | Per 3-min track | Rights |
|------|-----------------|--------|
| ElevenLabs Music (API, ~$0.15/min) | ~$0.45 raw; ~$1.80 with 4 takes → 1 keeper | Licensed training data, commercially cleared. Clean. |
| Suno via third-party reseller | $0.014–0.111 | No official API. Ownership proof is shaky → fails DistroKid scrutiny. |
| ACE-Step on rented 4090 (~$0.35/h) | ~$0.01 | Ours outright (Apache). Turkish/AZ vocal quality unproven — likely the weak point. |

A 60-minute mix ≈ 20 keeper tracks ≈ ~240 minutes of generation at best-of-4. That does not
fit Creator's ~62 min/month cap, so the channel business is a **$99/mo Pro subscription**,
not a $22 one — plus whatever generation runs past the included quota. Treat $99/mo as the
standing cost of the clean lane and ask whether one hand-curated mix per week can carry it.
(⚠️ The contract's 62-min cap and the credit math, ~900 credits/min, do not reconcile —
read the true cap off the live account before committing money.)

The open lane (ACE-Step) stays useful as the **draft tier**: generate cheaply, audition, and
spend ElevenLabs minutes only on briefs that already proved themselves. Same tiered logic the
image pipeline already uses (Z-Image draft → FLUX final).

## Kill criteria (say it out loud now, not in month three)

- No rights-clean engine sings Turkish acceptably → the project is a hobby, not a business.
- **The format itself is what YouTube demonetises**, regardless of quality (see truth #7). The
  channel lane only survives as a low-volume, genuinely human-curated craft operation. If the
  goal was passive volume income, **stop here — that business is already dead.**
- The client-work fallback is narrower than assumed: a **bespoke** track for one client is
  permitted, but building a **stock library** of AI tracks to offer clients is Prohibited on
  every self-serve ElevenLabs tier.
- The 70% (mixing/mastering) turns out to need a human ear at every step → it does not automate,
  and there is no platform, only a tool.
- $99/mo cannot be recovered → the clean lane is not affordable, and the only remaining path is
  the open lane with its unproven Turkish/AZ vocals.

## Sources (2026-07-11 sweep)

- Suno has no public API; third-party resellers only — https://sunor.cc/blog/suno-api-pricing-2026
- Udio is a walled garden post-UMG; no export — https://www.billboard.com/pro/umg-udio-ai-deal-faq-artist-payments-user-downloads-lawsuit/
- Eleven Music API, licensed + commercially cleared — https://elevenlabs.io/music-api
- ACE-Step (Apache 2.0, 4 min in 20 s on A100) — https://arxiv.org/abs/2506.00045
- YouTube AI-music monetisation rules — https://musicmake.ai/blog/youtube-ai-generated-music-policy-2026
- DistroKid / Spotify AI disclosure — https://www.rightsdocket.com/insights/ai-music-disclosure-distrokid-spotify-apple-music-2026

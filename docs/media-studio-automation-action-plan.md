# Media Studio Automation Action Plan

Date: 2026-06-17

Goal: one natural-language request should produce a ready social asset; "publish" should schedule or post it through connected channels with no silent failures.

## Executive Summary

The system is not missing intelligence. It is missing three operational bridges:

1. A reliable external video-generation account bridge for Higgsfield / Media Studio.
2. A live publishing bridge through Docker + Postiz + connected social accounts.
3. A standardized campaign pipeline that always performs reference ingestion, transcript extraction, creative packaging, quality audit, and publish routing in the same order.

Several core pieces already work:

- Instagram reference data extraction works through Apify.
- Audio Studio is now ready for Azerbaijani TTS, ElevenLabs, HF, and Gemini.
- Publisher dry-run works and creates paste-ready platform packages.
- Social Studio already has brand kit, image generation cascade, deterministic overlays, and audit structure.
- Existing video pipeline can render/edit videos locally through FFmpeg/Remotion once assets exist.

The main blockers are account/connectivity, not creative capability.

## What Happened In The Xalq Sigorta Reel Test

### 1. Instagram link could not be read by normal browsing

Symptom:

- Direct browser access to the Instagram reel did not expose the actual video/audio.

Root cause:

- Instagram often hides reel media behind login/session/anti-scraping layers.
- A normal browser fetch is not enough for reliable creative reference ingestion.

Resolution:

- Used Apify `apify/instagram-reel-scraper`.
- Extracted caption, video URL, audio URL, duration, metrics, tagged user, and transcript.

Permanent fix:

- Treat Instagram/TikTok references as a first-class ingestion step, not as web pages.
- Default every reel reference job to:
  - scrape metadata
  - include transcript
  - save original caption
  - save tone notes
  - extract hook/structure/CTA

### 2. First voice-over draft was too official

Symptom:

- Initial rewrite sounded like an insurance announcement, not like the reference reel.

Root cause:

- I used caption + official product facts before extracting the real spoken transcript.
- The emotional value of the reference was in the blogger's spoken tone.

Resolution:

- Extracted transcript:
  - "Mayın 26-dan etibarən Bakıdan Tiflisə gedə biləcəksiz..."
  - Tone: creator warning followers, "sonra demədiniz deməyin".
- Rewrote Xalq Sigorta VO as UGC/blogger speech.

Permanent fix:

- In reference-based social jobs, never write the final script until the audio transcript is extracted or the user confirms it is unavailable.
- Store a "tone DNA" before writing variants:
  - speaker role
  - emotional posture
  - sentence length
  - warning level
  - CTA placement

### 3. Higgsfield / Media Studio connector failed

Symptoms:

- `show_marketing_studio(action='fetch')` failed with generic `Something went wrong`.
- `show_marketing_studio(action='create')` failed with generic `Something went wrong`.
- `media_upload` failed with `Upload URL generation failed`.
- `balance` failed with `Error fetching balance`.
- `list_workspaces` failed.
- Direct video generation failed with `User not found`.

Observed request IDs:

- `87442f3d-589c-4b1f-9ba8-aa59bc7c25a4`
- `2cf7cac4-8086-4709-8572-3274a5b8a539`
- `ac3b6d9b-05ff-4260-a0e6-b29f5671c861`
- `ae7faf01-8bb1-4444-b9ab-2f46416b9b45`
- `08740228-0812-4a9d-8962-1fcb3b40fe37`
- `705afbf9-22d1-4aaa-a2cc-7b86b9f00836`
- `230fc5bd-4b2a-436c-80c4-6ee4420164e3`

Root cause:

- The connector can list models, but user/workspace/account endpoints fail.
- Direct generation returns `User not found`, which points to an authentication/workspace mapping issue, not prompt quality.
- This cannot be fixed by local code alone because the failure is inside the external MCP connector/account layer.

Required fix:

- Reconnect or re-authorize Higgsfield / Media Studio connector.
- Ensure the same account has a valid Higgsfield workspace.
- Confirm workspace selection and credit balance.
- Re-run `balance`, `list_workspaces`, then a tiny `get_cost` or 3-second generation test.

Fallback while blocked:

- Use local/other cascade:
  - Apify for reference extraction
  - Audio Studio for VO
  - HF Spaces / Flora / other video model for generation
  - Video Studio + Remotion for captions/overlays
  - Publisher dry-run/manual or Postiz once ready

### 4. Postiz live publishing is not ready

Symptoms:

- `docker` command is not available in PATH.
- `http://localhost:5000` is unreachable.
- `POSTIZ_API_KEY` is not configured.
- Publisher dry-run works, but live publish cannot work yet.

Root cause:

- Docker Desktop is not installed or not available in PATH.
- Postiz container is not running.
- Social accounts are not connected inside Postiz.
- Postiz public API key has not been generated and placed in `.env`.

Resolution so far:

- Verified `publisher/run.py` dry-run works.
- It creates platform-specific paste-ready packages under `output/publish/...`.

Permanent fix:

- Install/start Docker Desktop.
- Run `docker compose up -d postiz`.
- Open `http://localhost:5000`.
- Create Postiz admin account.
- Connect Instagram, LinkedIn, TikTok, Facebook, X as needed.
- Generate public API key.
- Set `POSTIZ_API_KEY` in `.env`.
- Re-run live publish smoke test.

### 5. Audio Studio had missing local dependencies

Symptoms:

- ElevenLabs key was present but SDK was missing.
- Edge TTS was missing.

Root cause:

- `audio-studio/requirements.txt` had not been fully installed on this machine.
- Latest ElevenLabs 2.x package hits Windows Long Path limits on this environment.

Resolution completed:

- Installed `elevenlabs==1.59.0`.
- Installed `edge-tts`.
- Updated `audio-studio/requirements.txt` to `elevenlabs>=1.50.0,<2.0`.
- Re-ran doctor: Audio Studio is now ready.
- Generated sample Xalq Sigorta Azerbaijani VO:
  - `output\xalq-sigorta-georgia-reel-voiceover.mp3\tts_20260617-114408_bir-deqiqe-gurcustana-gedenler-bunu-esit.mp3`

Permanent fix:

- Keep ElevenLabs under 2.x until Windows Long Paths is enabled or package structure changes.
- Add `python audio-studio\audio_studio.py doctor` to every media stack health check.

### 6. Environment key naming must be standardized

Symptom:

- `HF_TOKEN` is configured and Audio Studio reads it.
- `HUGGINGFACE_TOKEN` is not configured.

Root cause:

- Different tools may expect different env variable names.

Permanent fix:

- Use one naming contract in `.env.example`.
- Preferred canonical key: `HF_TOKEN`.
- If a provider expects `HUGGINGFACE_TOKEN`, map it in the loading layer rather than duplicating logic everywhere.

## Current Readiness Matrix

| Layer | Current status | Evidence | Next action |
|---|---|---|---|
| Reference ingestion | Working | Apify extracted Instagram caption + transcript | Make it standard in `/post` and `/video-post` flow |
| Copy/script | Working manually | Blogger-style VO package created | Convert to reusable `tone_dna` step |
| Audio | Ready | Audio doctor green; Azerbaijani VO generated | Add preferred voices and pacing presets |
| Image Social Studio | Mostly ready | Brand kit, render, audit, outputs exist | Keep improving audit + brand LoRA/reference conditioning |
| Generative video | Blocked on Higgsfield auth | `User not found` | Reconnect connector; add fallback video cascade |
| Local video finishing | Built | Video Studio exists with FFmpeg/Remotion contract | Wire generated VO + captions + overlays into a one-command reel flow |
| Publishing dry-run | Working | `publisher/run.py --dry-run` creates packages | Keep as mandatory approval preview |
| Live publishing | Blocked | Docker unavailable, Postiz unreachable, no API key | Install Docker, run Postiz, connect socials |
| Orchestrator | Skeleton | README says CrewAI calls are TODO | Promote only after core pipeline is stable |
| Diagnostics | Added | `scripts/diagnose-media-stack.ps1` | Run before any production session |

## Target Architecture

The final system should have one command path:

```text
User brief
  -> reference ingestion
  -> brand/product facts
  -> creative concept variants
  -> copy + script + captions
  -> asset generation
  -> deterministic brand overlay
  -> audio/VO/music mix
  -> visual + copy + legal audit
  -> publish dry-run
  -> user says "paylaş"
  -> Postiz schedules/posts
  -> logs + archive + learning memory
```

The user-facing experience should be:

```text
"Xalq Sığorta üçün bu Instagram reel kimi, amma daha emosional və blogger tonunda video hazırla."
```

System output:

- final video
- thumbnail
- caption AZ/EN
- hashtags
- alt text
- compliance note
- platform variants
- dry-run publish preview

Then:

```text
"Paylaş."
```

System action:

- posts/schedules through Postiz
- if any platform is disconnected, creates a labelled manual block
- never silently drops a channel

## Recommended Production Workflow

### Stage 1: Intake

Inputs:

- user brief
- brand/product
- platform target
- reference URLs/files
- required CTA

Output:

- campaign slug
- product fact sheet
- reference transcript
- tone DNA

Rule:

- If a reference has audio, extract transcript before writing copy.

### Stage 2: Creative

Outputs:

- 3 concepts
- selected concept
- VO script
- screen captions
- shot list
- caption package

Audit:

- Does it sound like a human?
- Is the hook visible in 1 second?
- Does the brand arrive as a solution, not as a lecture?

### Stage 3: Generation

Preferred cascade:

1. Higgsfield / Media Studio once auth is fixed.
2. HF Spaces / Flora / other configured video provider.
3. Local deterministic Remotion template using stills, VO, captions, motion graphics.
4. Manual handoff.

Rule:

- Always save prompts and model settings in the campaign folder.

### Stage 4: Finish

Use deterministic local tools:

- normalize audio
- burn or overlay captions
- add logo/end card
- export 9:16 / 1:1 / 4:5 if needed
- generate thumbnail

Rule:

- Brand text/logos should be deterministic overlays, not AI-rendered inside the model.

### Stage 5: Audit

Checks:

- brand fidelity
- legal/product accuracy
- tone match
- no competitor names/logos
- caption readability
- platform-safe length
- CTA correct

Rule:

- Insurance content should keep a human approval gate until at least 20 successful posts pass without correction.

### Stage 6: Publish

Default:

- dry-run first.

Live:

- only after user says "paylaş", "publish", or an approved automation policy exists.

Fallback:

- manual package per platform.

## User-Owned Actions

### A. Fix Higgsfield / Media Studio connector

1. Open the environment where the connector/app is authorized.
2. Disconnect Higgsfield / Media Studio if it is already connected.
3. Reconnect it with the correct Higgsfield account.
4. Confirm that the account has a workspace.
5. Confirm the workspace has access to video generation.
6. Confirm credits/balance is visible in the Higgsfield UI.
7. Send me "Higgsfield yenidən qoşuldu" and I will run:
   - balance
   - list workspaces
   - tiny generation cost check
   - Xalq Sigorta reel generation

If support is needed, send them the request IDs listed above and the exact error: `generate_video -> User not found`.

### B. Enable live social publishing through Postiz

1. Install Docker Desktop for Windows.
2. Restart PowerShell so `docker` is available in PATH.
3. In project root, run:

```powershell
docker compose up -d postiz
```

4. Open:

```text
http://localhost:5000
```

5. Create the Postiz account.
6. Connect the social channels:
   - Instagram Business / Creator account
   - Facebook Page connected to Instagram
   - LinkedIn Page
   - TikTok Business if needed
   - X if needed
7. In Postiz, create a Public API key.
8. Put it in `.env`:

```env
POSTIZ_API_KEY=...
```

9. Send me "Postiz hazırdır" and I will run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\diagnose-media-stack.ps1
python publisher\run.py <asset> --to instagram,linkedin --dry-run
python publisher\run.py <asset> --to instagram,linkedin --when now
```

### C. Confirm publishing policy

Choose one:

1. Manual approval for every post.
2. Auto-schedule drafts, manual approve in Postiz.
3. Full auto-publish for low-risk categories only.

Recommendation:

- Use option 2 for the first month.
- Use full auto-publish only for non-legal, non-claim, non-price content.

### D. Confirm brand/legal source of truth

Provide or approve:

- official logo pack
- exact brand colors
- approved slogans
- legal disclaimers by product
- approved phone numbers and URLs
- banned phrases
- competitor mention rules

Current assumed CTA for this campaign:

- `travel.xalqsigorta.az`
- `Xalq Sığorta`
- `Biz varıq!`

## Work Already Completed In This Pass

1. Extracted Instagram reference metadata and transcript through Apify.
2. Built Xalq Sigorta blogger-style reel package:
   - `xalq-sigorta-georgia-reel.md`
3. Fixed Audio Studio local dependencies:
   - installed Edge TTS
   - installed ElevenLabs SDK 1.59.0
   - verified Audio Studio doctor is green
4. Generated Azerbaijani voice-over sample:
   - `output\xalq-sigorta-georgia-reel-voiceover.mp3\tts_20260617-114408_bir-deqiqe-gurcustana-gedenler-bunu-esit.mp3`
5. Updated Audio Studio requirements to avoid Windows Long Path breakage:
   - `audio-studio/requirements.txt`
6. Added reusable health-check script:
   - `scripts/diagnose-media-stack.ps1`
7. Verified Publisher dry-run works:
   - output packages under `output\publish\...`

## Next Implementation Tasks For Me

After Higgsfield and Postiz are fixed:

1. Add a `/video-post` or equivalent campaign flow that standardizes:
   - reference scrape
   - transcript extraction
   - VO script
   - generated video prompt
   - audio generation
   - final export
   - publish package
2. Wire Xalq Sigorta campaign folders for video the same way Social Studio handles images.
3. Add a campaign manifest schema:
   - brand
   - product
   - references
   - transcript
   - tone DNA
   - script
   - media outputs
   - audit status
   - publish status
4. Add a smoke-test command:
   - reference URL in
   - one draft video or fallback storyboard out
5. Add publish confirmation states:
   - draft
   - approved
   - scheduled
   - posted
   - failed/manual

## Definition Of "Ideal"

The media studio is ideal when these are true:

- Any reference URL can be ingested or gracefully reported.
- Any generated output has saved prompts and source facts.
- Audio, visual, caption, and CTA are generated as one package.
- Brand/legal audit runs before publishing.
- User approval is requested only at the right gate.
- "Paylaş" triggers a real publisher, not a manual copy-paste.
- If a provider fails, the cascade moves to the next provider and tells us why.
- Every campaign leaves a reusable memory trail for the next one.

## Immediate Next Command

Run this any time to see current readiness:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\diagnose-media-stack.ps1
```

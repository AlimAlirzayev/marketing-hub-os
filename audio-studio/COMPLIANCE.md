# Rights & Monetisation Gate — D4

Research date: **2026-07-11**. Owner: Alim (individual, Baku, AZ).
Scope: Eleven Music → YouTube continuous mixes → (optional) Spotify via DistroKid.

Every claim below is tagged with its source. Where a primary source could not be found,
the claim is marked **UNVERIFIED** and must not be relied on.
Re-verify this file whenever a vendor updates its terms (ElevenLabs terms are dated
**26 May 2026**; re-check quarterly).

---

## 1. Findings

### 1.1 ElevenLabs — the controlling documents

Three documents stack, in this order of precedence (Music Terms, preamble):
**(A) Model-Specific Terms → (B) Music Terms → (C) Terms of Service.**

| Document | Last updated | URL |
|---|---|---|
| Eleven Music Model-Specific Terms | 26 May 2026 | https://elevenlabs.io/eleven-music-model-specific-terms |
| Music Terms | 26 May 2026 | https://elevenlabs.io/music-terms |
| Terms of Service | 31 March 2026 | https://elevenlabs.io/terms-of-use |

**Ownership.** The Music Terms contain **no ownership grant at all** — ownership comes from the
master ToS, §4(c)(ii): *"Except as expressly set forth herein, as between you and ElevenLabs, you
retain all rights in and to your Output."*
(https://elevenlabs.io/terms-of-use)

**Free tier is non-commercial, full stop.** ToS §1(c) Use Restrictions: *"(i) if you access or use
our Services free of charge (such a user, a "Free User"), you may only use the Services for
non-commercial purposes; (ii) if you access or use our Services through a paid subscription plan
(such a user, a "Paid User"), you may use the Services for commercial purposes…"*
This is the legal counterpart of the `HTTP 402 paid_plan_required` we already see on the API.
(https://elevenlabs.io/terms-of-use)

**No exclusivity — this is the sleeper clause.** Music Terms §3: *"You acknowledge that, due to
the nature of machine learning, Output you generate using Music may not be unique and may be
similar or identical to Output returned to other users. ElevenLabs does not guarantee the
exclusivity of Output, and any responses generated for others shall not be considered your
Output."* Consequences in §1.3 below — it is what disqualifies us from Content ID.
(https://elevenlabs.io/music-terms)

### 1.2 The Music Commercial Rights table (verbatim, Model-Specific Terms)

This is the single most important table in the project. Plan names map to the standard
ElevenLabs plans (Free $0 / Starter $6 / Creator $22 / Pro $99 / Scale $299 / Business $990 —
https://elevenlabs.io/pricing).

| Row | Free | Starter | Creator | Pro | Scale | Business |
|---|---|---|---|---|---|---|
| Eligibility | Individual use only | Individual use only | Individual use only | Individual use only | Individuals / orgs **< 10 employees** | Individuals / orgs **< 50 employees** |
| Monthly generation | 11 min | 17 min | 62 min | 304 min | 1,100 min | 4,800 min |
| Monthly download | **Not permitted** | 30 min | 250 min | 500 min | 1,500 min | 4,000 min |
| **Streaming Rights** | **Prohibited** | **Prohibited** | **Yes** | Yes | Yes | Yes |
| Media Rights | all online + offline commercial use **except film, TV, radio, & Studio Games** | *(same)* | *(same)* | *(same)* | *(same)* | *(same)* |
| Reseller Rights | Prohibited | Prohibited | Prohibited | Prohibited | Prohibited | Prohibited |
| **Music Libraries & Repositories** | **Prohibited** | **Prohibited** | **Prohibited** | **Prohibited** | **Prohibited** | **Prohibited** |
| Attribution | **Required** ("denote Eleven Music when distributing") | None | None | None | None | None |
| **High Quality Downloads** | No | **No** | **No** | **Yes** | Yes | Yes |
| API access (stems, streaming, timestamps) | No | Yes | Yes | Yes | Yes | Yes |

Defined terms (Model-Specific Terms §5):
- ***"Streaming*** means making Output(s) available on third party music streaming platforms."
  → **This is Spotify.** Prohibited on Free **and Starter**.
- ***"Studio Games*** means video games which are commercialised … and made available … through
  more than one platform."
- ***"Music Libraries & Repositories*** means any arrangement in which Customer creates or permits
  others to create a library, catalogue, database, or other repository of Output with the intent of
  licensing it or otherwise making it available to third parties."

**Four corrections to MUSIC_ROADMAP.md follow from this table:**

1. **"A $5–22/mo self-serve plan lights it up" is wrong for this business.**
   Starter ($6) unlocks the API but **prohibits Streaming** → no Spotify. **Creator ($22) is the
   floor for Spotify.**
2. **Pro ($99/mo) is the real floor for release-grade audio.** High Quality Downloads are **No**
   up to and including Creator; the pricing page confirms *"44.1kHz PCM audio output via API"* is a
   **Pro** feature. Below Pro we would be mastering lossy MP3 to −14 LUFS and re-encoding —
   generation loss baked into every release.
3. **Pro is also the volume floor.** One 60-min mix ≈ 20 keeper tracks; at best-of-4 × 3 min that is
   **240 min of generation**. Creator's cap is **62 min/month** — not even one mix. Pro gives 304 min.
   ⚠️ **UNVERIFIED / CONFLICT:** the credit system (Music = 900 credits/min; Creator = 121k credits ≈
   134 min) does not reconcile with the table's 62 min cap. The contract table is what binds us, but
   **the true cap must be read off the live account before any budget is committed.**
4. The media-rights carve-out includes **radio**, which the marketing page
   (https://elevenlabs.io/music-api) omits. That page also claims Eleven Music is *"cleared for
   nearly all commercial uses, from film and television to…"*, which **contradicts the contract**.
   The contract wins. Do not rely on marketing copy.

**Ownership survives cancellation — and this is the legal basis of the rights ledger.**
Model-Specific Terms §2:
- §2(b) *"If you upgrade to a higher-priced plan … all Output in your account at the time of upgrade
  will be subject to the upgraded plan."* (Upgrading is retroactive **in our favour** — a useful
  escape hatch if something was generated on too low a tier **and is still in the account**.)
- §2(c) *"If you terminate your Music account or downgrade to a lower-price plan, Output will remain
  available in your account **subject to the plan in effect when the Output was created**. For
  example, if you terminate your Business plan account, you will continue to have access to and the
  right to use Output you created while a Business plan subscriber…"*

→ **Rights attach at the moment of generation, and are fixed by the tier active at that moment.**
Cancel later and you keep what you made. Generate on the wrong tier and no later payment fixes it
(except the §2(b) upgrade path, while the Output is still in the account).

**Prohibited inputs (Music Terms §2(b)) — mechanically checkable.** No artist's or songwriter's
real/stage name, no song title, no album title, no publisher name, no label name, and no
*"substantial or distinct portion of any song's lyrics such that a reasonable person would determine
the prompt was intended to reference a particular song."*
**Prohibited industries (§2(a)):** firearms, tobacco, pharma/controlled substances, adult, religious
organisations, political advocacy. (Relevant if the engine is ever pointed at client work.)
**Impersonation (§2(d)):** no output mimicking an identifiable recording artist's voice.

### 1.3 YouTube

**Monetisation — the "inauthentic content" policy.** YouTube's own channel monetisation policies page
defines it: *"Inauthentic content refers to mass-produced or repetitive content. This includes content
that looks like it's made with a template with little to no variation across videos, or content that's
easily replicable at scale."* The test it gives for what is still OK: *"If the average viewer can
clearly tell that content on your channel differs from video to video, it's fine to monetize."*
Explicitly listed as **ineligible**: *"AI-generated content made with generic templates giving the
impression of mass production without adding the creator's original, authentic insights or
perspective"* — and separately, *"pitch/speed-altered songs identical to originals."*
(https://support.google.com/youtube/answer/1311392)

There is **no numeric threshold** for "sufficient original input". YouTube deliberately publishes a
qualitative standard ("the average viewer can clearly tell"). Any gate we build is therefore a
**proxy** for a human judgement, not a guarantee. Be honest about that.

**Disclosure is MANDATORY for our content — verified verbatim.** YouTube's GenAI disclosure page:
*"we require creators to disclose content that is generated or meaningfully altered with AI when it
appears realistic"*, and the list *"Examples of content, edits, or video assistance that creators need
to disclose"* begins with **"AI generated music"**.
Field: YouTube Studio → upload → **Attributes → "Altered or synthetic content" / AI use → Yes**.
Penalty: *"Creators who consistently choose not to disclose this information may be subject to manual
application of a label, or penalties from YouTube, including removal of content or suspension from the
YouTube Partner Program."*
(https://support.google.com/youtube/answer/14328491)
Note: disclosure itself does **not** demonetise. The *inauthenticity* does. These are two separate
policies and they are often confused.

**Content ID: we are NOT eligible, and must never register.** YouTube requires *"Copyright owners must
have the exclusive rights to the material that's evaluated"*, and explicitly lists as ineligible
*"music or video that was licensed, but without exclusivity."*
(https://support.google.com/youtube/answer/1311402)
ElevenLabs **expressly disclaims exclusivity** (Music Terms §3, quoted above). Therefore:
- Registering Eleven Music output in Content ID would be a **false assertion of exclusive rights**.
- If DistroKid auto-enrols our releases in Content ID, it would also **claim our own YouTube mixes**
  (same audio) — self-claiming, and a compliance breach at the same time.
- **Action: Content ID / "YouTube Money" must be OFF for every AI release.**
  ⚠️ **UNVERIFIED:** whether DistroKid enrols in Content ID by default. Secondary sources say some
  distributors do. **This must be confirmed in the DistroKid account UI before the first upload.**

**Real enforcement.** That AI-music and templated channels are being demonetised at scale in 2025–26
is consistently reported, but I could **not find a primary/on-the-record source** for the specific
case numbers circulating (e.g. "16 channels, 4.7B views", the "$30k/mo Bible channel"). Those come
from SEO/marketing blogs that cite each other. **Treated as UNVERIFIED.** What is *not* in doubt,
because it is in YouTube's own policy text, is the shape of the target: **templated, low-variation,
mass-produced uploads with no evident human authorship**. The pattern most often described as hit —
**AI audio over a static image, uploaded on a schedule** — is precisely the reference format this
project is copying. Forbes has covered the broader AI-music fraud economy:
https://www.forbes.com/sites/virginieberger/2026/05/05/how-ai-generated-music-became-a-4-billion-fraud-machine/

### 1.4 Spotify

**Policy (primary, 2025-09-25 newsroom).** Three pillars:
1. **Impersonation** — *"Vocal impersonation is only allowed in music on Spotify when the impersonated
   artist has authorized the usage."*
2. **Music spam filter** — targets *"mass uploads, duplicates, SEO hacks, artificially short track
   abuse, and other forms of slop"*; Spotify removed *"over 75 million spammy tracks"* in 12 months.
   Flagged uploaders stop being recommended.
3. **AI disclosure via DDEX** — artists/labels/distributors can declare *"whether that's AI-generated
   vocals, instrumentation, or post-production"*. Spotify: this is *"not about punishing artists who
   use AI responsibly or down-ranking tracks for disclosing"*.
(https://newsroom.spotify.com/2025-09-25/spotify-strengthens-ai-protections/)

**AI Credits beta.** Rolled out **~16 April 2026, DistroKid first**, surfacing AI involvement in the
Song Credits panel, carried from upload to app over DDEX. Sourced to **trade press, not a Spotify
newsroom post I could retrieve** — treat the exact date as trade-press-grade:
https://www.billboard.com/pro/spotify-launches-ai-credits-music/ ·
https://www.musicbusinessworldwide.com/spotify-to-show-ai-tags-in-song-credits-where-artists-have-chosen-to-disclose-through-their-label-or-distributor/

**Who declares:** the **distributor**, on the artist's instruction, at upload. On Spotify's side the
disclosure is **voluntary and non-punitive**. At DistroKid it is **part of the upload flow**.

### 1.5 DistroKid

**Their actual AI policy** (help centre, updated **2026-06-29**) is four rules, quoted in full:
> *"You must own the rights. You must own 100% of the rights, including the legal right to distribute
> music created with any AI tools, samples, lyrics, etc."*
> *"No impersonation. Your music cannot mimic or copy someone else's voice, likeness, or identity
> without permission."*
> *"No mass-generated spam. Music created solely to game streaming algorithms or flood platforms with
> generic content violates streaming services' policies."*
> *"No infringement. Your release cannot infringe on anyone else's rights."*
(https://support.distrokid.com/hc/en-us/articles/41182362733715-Can-I-Upload-Music-Made-With-AI-Tools-to-DistroKid)

**🔴 CORRECTION — the "paid tier at generation time" claim is NOT a DistroKid rule.**
The roadmap says DistroKid *"requires you were on a paid tier at generation time."* I searched
DistroKid's own policy pages and **that language does not appear anywhere in them.** It is an
inference that SEO blogs repeat as if it were quoted policy. **Do not cite it as DistroKid's rule.**

The requirement is nonetheless **real**, by composition:
- DistroKid requires you own **100% of the rights** (their words, above);
- ElevenLabs only grants commercial + streaming rights on **certain paid tiers**, and fixes them by
  **the plan in effect when the Output was created** (Model-Specific Terms §2(c));
- ⇒ if it was generated on Free/Starter, you **do not** hold streaming rights, so you **cannot**
  truthfully attest 100% ownership to DistroKid.

So the rule binds — but it originates in **ElevenLabs' terms**, not DistroKid's. That distinction
matters, because it means **the evidence we need is evidence about our ElevenLabs plan at generation
time**, which only we can produce. Nobody will hand it to us later.

**AI Credits** (help centre, updated **2026-06-29**) — declare when AI *generated* part of the track:
> *"AI-generated audio (vocals, instrumental tracks, etc.) · AI-generated lyrics (not written by a
> human) · AI-generated compositions (melody or arrangement not composed by a human)"*
> *"You don't need AI credits if you just used AI as a tool: Pitch correction, auto-tune, etc. ·
> AI-assisted mixing or mastering · AI-assisted workflows"*
(https://support.distrokid.com/hc/en-us/articles/50784235803411-What-Are-AI-Credits)
→ **Our tracks trigger all three positive categories.** Our post-production (Demucs, matchering,
loudnorm) triggers **none** — that is "AI as a tool" and needs no credit.

**Stream farming / "artificial streaming"** is a **separate** and narrower thing than AI-spam. Their
definition: *"when an artist uses artificial means to increase their stream counts"* — bots, paid
playlist placement, "promo" services. Sanction: *"your music will likely be removed … royalties …
will not be paid. You may also receive a warning from DistroKid and/or your DistroKid account will be
closed."* Their instruction is blunt: **"DO NOT PAY FOR ANY SERVICE THAT OFFERS MORE STREAMS / MORE
FOLLOWERS / PLAYLIST PLACEMENT."** Note it can be triggered **without your knowledge** by a fraudulent
playlist adding your track.
(https://support.distrokid.com/hc/en-us/articles/360013647373-What-is-Artificial-Streaming)
→ Two distinct triggers to defend against: **(a) volume/genericness** = "mass-generated spam";
**(b) fake streams** = artificial streaming, including via third-party "promo".

---

## 2. Publish gate

**All conditions are BLOCKING. A track/mix may be published only if every gate returns PASS.**
Every gate reads from the track's rights-ledger record (§3). A missing field is a **FAIL**, never a
pass — absence of evidence is not evidence of compliance.

### G0 — Ledger integrity
- `ledger` record exists for every source track in the release.
- All required fields present and non-null.
- `output.sha256` recomputed from the audio file == stored value. (Guards against publishing a file
  the ledger does not actually describe.)

### G1 — Plan tier at generation time (per track, per destination)
- `plan.tier_at_generation` ∈ {`starter`,`creator`,`pro`,`scale`,`business`} → else **FAIL** (Free is
  non-commercial and download-prohibited; nothing generated on Free may ever be published).
- Destination `youtube` requires tier ≥ `starter` (online commercial use).
- Destination `spotify` / any streaming DSP requires tier ≥ **`creator`** (Streaming Rights).
- Release-grade master requires tier ≥ **`pro`** (High Quality Downloads / 44.1 kHz PCM).
- If `plan.tier_at_generation` == `free` → check §2(b) upgrade path is *not* available as an excuse:
  a Free-tier generation is non-commercial under the **ToS**, not merely rights-limited. **Hard fail.**

### G2 — Prohibited input scan (run at generation, re-checked at publish)
Reject if `prompt.text` or `lyrics.text` matches any of:
- a known artist / songwriter real or stage name (deny-list + NER on PERSON entities);
- a known song title or album title (deny-list);
- a music label or publisher name (deny-list);
- ≥ N consecutive tokens matching any known song lyric (fuzzy match against a lyrics corpus).
Per Music Terms §2(b). Any hit → **FAIL**, generation is void, do not publish.

### G3 — Prohibited industry / impersonation
- Track is not produced for firearms, tobacco, pharma, adult, religious or political use (§2(a)).
- `impersonation_check.passed` == true — output does not mimic an identifiable artist's voice (§2(d)).

### G4 — Use-case carve-out
- `destination` ∉ {`film`, `tv`, `radio`, `studio_game`} on any self-serve tier.
- `catalogue_intent` == false — we do **not** build a licensable library/repository of Output for third
  parties. **"Music Libraries & Repositories" is Prohibited on every self-serve tier.**
  ⚠️ This directly constrains the roadmap's own fallback plan ("the capability survives as a marketing
  asset — client jingles, ad beds"). A **bespoke** track delivered to one client is ordinary commercial
  use and is fine. A **stock library** of AI tracks offered to clients is **prohibited** without
  Enterprise. Know which one you are building.

### G5 — Eligibility
- If the engine is used on behalf of an entity, not Alim personally: tiers Free→Pro are
  *"For Individual Use Only"*; ≥10 employees requires Scale. `account.entity_size` must be consistent
  with `plan.tier_at_generation`.
  ⚠️ **UNVERIFIED interpretation:** whether freelance client work under a personal Pro plan counts as
  "individual use". Ambiguous in the contract. Low risk for a sole trader; flag before scaling.

### G6 — Attribution
- If `plan.tier_at_generation` == `free` → attribution *"Created in collaboration with ElevenLabs"* is
  **Required**. But G1 already hard-fails Free. Keep this gate so the two can never silently diverge.

### G7 — Disclosure (mandatory, both platforms)
- YouTube: `disclosure.youtube_synthetic_content_label` == true. ("AI generated music" is on YouTube's
  own must-disclose list.) Non-negotiable, checked per **video**.
- DistroKid/Spotify: `disclosure.ai_credits` must set every category that applies —
  `{lyrics: bool, vocals: bool, instrumental: bool, composition: bool}` — with `true` for anything
  AI-*generated*. Post-production (mixing/mastering/loudnorm) is **not** declared.
- **Falsely declaring "no AI"** is the one lie that gets the release pulled. Never do it.

### G8 — Content ID
- `content_id.registered` == false, **always**, for every AI-generated track.
- DistroKid YouTube Content ID / "YouTube Money" toggle must be **OFF** at upload.
- Rationale: Content ID requires **exclusive** rights; ElevenLabs disclaims exclusivity. Registering
  would be a false claim of exclusivity *and* would auto-claim our own mixes.

### G9 — Human creative direction (the YouTube inauthenticity gate)
This is the gate that decides whether the channel lives. It is a **proxy** for a human judgement, so it
must be strict. **All** of:
- `human.curation_ratio` — takes generated ÷ takes published ≥ **3:1** (real selection happened, and it
  is evidenced by the discarded takes still being logged).
- `human.edits[]` — **≥ 1** substantive, logged post-generation human edit per track (arrangement cut,
  re-order, inpaint, lyric rewrite, EQ/level decision). Auto-mastering does **not** count.
- `packaging.artwork_hash` — **unique per video**; must not match any previous release's artwork, and
  must not be a template with only a text layer swapped.
- `packaging.description_hash` + `packaging.title` — unique per video; description is human-written,
  not generated boilerplate.
- `packaging.tracklist_timestamps` — present (chapters). A 60-min mix with no chapters is a
  slideshow-equivalent.
- `packaging.visual_is_static_image` == false → **must have motion / original visuals.**
  🔴 A static image + AI audio is the single most-cited demonetisation pattern. If this is true,
  **FAIL**.
- `human.approval` — human checkpoint (`/approve N`) recorded with a timestamp and an operator ID.

### G10 — Anti-mass-production rate limits
- ≤ **1** mix published per channel per **7 days** (tunable down, never up without a review).
- No two published items share `packaging.artwork_hash` or `packaging.description_hash`.
- Near-duplicate audio check across the published catalogue (chroma/embedding distance above a
  threshold) → block re-releases of substantially the same track.

### G11 — Streaming integrity
- `promotion.paid_services` == false. **Never** buy streams, followers or playlist placement.
- Monitor for unsolicited playlist adds; if an artificial-streaming notice lands, the response is the
  documented DistroKid path (re-upload with the same ISRC), not silence.

**Gate result:** `PASS` only if G0–G11 all pass. Any `FAIL` → the track never reaches the `/approve`
prompt. The gate runs **before** the human checkpoint, not after.

---

## 3. Rights ledger — schema

Written **at generation time**, one record per generated take (**including takes that are discarded** —
the discards are what prove curation under G9). Append-only. Store as JSONL next to the audio, and
back it up off-box; this file *is* the ownership evidence.

```json
{
  "ledger_version": "1.0",
  "track_id": "uuid-v4",
  "batch_id": "uuid-v4",
  "created_at_utc": "2026-07-11T19:32:04Z",

  "engine": {
    "vendor": "elevenlabs",
    "product": "eleven_music",
    "model_version": "v2",
    "endpoint": "https://api.elevenlabs.io/v1/music",
    "request_id": "vendor-side request id from the response headers",
    "terms_version_seen": {
      "model_specific_terms": "2026-05-26",
      "music_terms": "2026-05-26",
      "tos": "2026-03-31"
    }
  },

  "plan": {
    "tier_at_generation": "pro",
    "verified_at_utc": "2026-07-11T19:32:01Z",
    "verification_method": "GET /v1/user/subscription immediately before generation",
    "raw_subscription_response_sha256": "…",
    "subscription_id": "…",
    "entity_size": "individual",
    "rights_implied": {
      "commercial_use": true,
      "streaming_rights": true,
      "hq_download": true,
      "attribution_required": false,
      "excluded_media": ["film", "tv", "radio", "studio_games"]
    }
  },

  "prompt": {
    "text": "verbatim prompt as sent",
    "sha256": "…",
    "style_tags": ["turkish", "deep house", "female vocal"],
    "negative_prompt": null,
    "seed": null
  },

  "lyrics": {
    "authorship": "human | ai | hybrid",
    "author": "Alim | eleven_music | Alim+eleven_music",
    "text": "verbatim lyrics as sent or as returned",
    "sha256": "…",
    "human_rewrite_pct": 0.0
  },

  "prohibited_input_scan": {
    "passed": true,
    "scanned_at_utc": "2026-07-11T19:32:03Z",
    "checks": {
      "artist_or_songwriter_name": "clear",
      "song_or_album_title": "clear",
      "label_or_publisher_name": "clear",
      "substantial_song_lyrics": "clear"
    },
    "scanner_version": "1.0"
  },

  "output": {
    "path": "…/tracks/uuid.wav",
    "sha256": "…",
    "format": "wav",
    "sample_rate_hz": 44100,
    "bit_depth": 16,
    "duration_sec": 182.4,
    "is_hq_download": true,
    "kept": true,
    "discard_reason": null
  },

  "human": {
    "curation_ratio": "4:1",
    "edits": [
      {
        "at_utc": "2026-07-12T09:14:00Z",
        "operator": "alim",
        "type": "arrangement_cut | inpaint | lyric_rewrite | eq | level | reorder",
        "description": "cut 16-bar intro; moved hook 12s earlier",
        "tool": "audio_studio.py --inpaint"
      }
    ],
    "approval": {
      "approved": true,
      "operator": "alim",
      "at_utc": "2026-07-12T10:02:00Z",
      "method": "telegram /approve 3"
    }
  },

  "packaging": {
    "title": "…",
    "artwork_hash": "sha256 of the cover image",
    "description_hash": "sha256 of the video description",
    "tracklist_timestamps": true,
    "visual_is_static_image": false
  },

  "disclosure": {
    "youtube_synthetic_content_label": true,
    "ai_credits": {
      "lyrics": true,
      "vocals": true,
      "instrumental": true,
      "composition": true
    }
  },

  "content_id": {
    "registered": false,
    "distributor_content_id_optout_confirmed": true
  },

  "promotion": {
    "paid_services": false
  },

  "publication": [
    {
      "destination": "youtube",
      "url": "…",
      "published_at_utc": "…",
      "gate_result": "PASS",
      "gate_version": "1.0"
    }
  ],

  "gate": {
    "status": "PASS | FAIL",
    "evaluated_at_utc": "…",
    "failures": []
  }
}
```

### Why retroactive proof is impossible

ElevenLabs binds rights to *"the plan in effect **when the Output was created**"* (Model-Specific Terms
§2(c)). That makes **generation time the only moment at which the facts that determine ownership are
all simultaneously true and observable.** Specifically:

- **The API does not tell you.** The returned audio carries no plan attestation — no tier, no licence
  stamp, no signature. There is nothing in the WAV to inspect later.
- **The audio is not self-dating.** A file's mtime is trivially mutable and proves nothing to a
  distributor or an adjudicator.
- **The account will not remember for you.** Billing history shows *that* you held a tier over a date
  range; it does not bind *this* generation to that tier, and after a downgrade or cancellation the
  usage history may not persist at all. Ironically, §2(c) — the clause that lets you keep your rights
  after cancelling — is also the clause that destroys your ability to *evidence* them, because the
  account you would have queried is gone.
- **The prompt is unrecoverable from the output.** Nothing about the finished track proves it was not
  generated from a prohibited input (an artist name, a lyric quote). Only a contemporaneous log does.
- **Curation cannot be reconstructed after the fact.** G9's proof of human creative direction rests on
  the *discarded* takes and the *sequence* of edits. If you throw the rejects away and log nothing,
  there is no artefact anywhere that distinguishes "we generated 4 and chose 1" from "we published raw
  output" — and that distinction is exactly what YouTube's inauthenticity policy turns on.

So: **if the ledger is not written in the same function call that generates the audio, the evidence does
not exist and cannot be manufactured later without lying.** Write it at generation, append-only, or
accept that every ownership attestation made downstream — to DistroKid, to YouTube, in a Content ID
dispute — is unevidenced.

---

## 4. What would kill this

The lethal fact is that **the exact format this project is copying — a static image over a continuous
bed of AI-generated audio, uploaded on a schedule — is the single most precisely-targeted pattern in
YouTube's inauthentic-content policy.** Not adjacent to it. It *is* the example. YouTube's own
monetisation page names *"AI-generated content made with generic templates giving the impression of mass
production without adding the creator's original, authentic insights or perspective"* as ineligible, and
the enforcement pattern everyone reports is templated audio-over-image channels losing YPP wholesale —
not per-video strikes, but **channel-level demonetisation**. The rights lane is genuinely clean:
ElevenLabs' licence is real, ownership survives cancellation, and Starter/Creator/Pro give us defensible
commercial and streaming rights. **The rights were never the problem. The format is.** And the "70%"
that MUSIC_ROADMAP correctly identifies as the actual project — curation, beat-matching, mastering,
packaging — is *also* the only thing standing between this channel and the demonetisation bucket. That
is a happy coincidence, but it cuts both ways: the moment the pipeline is good enough to run unattended
and start posting daily, it becomes indistinguishable from the slop farms YouTube is killing, and the
better it automates, the more it looks like exactly what the policy targets. **Automation is the risk.
Volume is the tell.** Secondary killers, in order: Spotify's spam filter (mass uploads / duplicates /
"slop") quietly ending recommendation, which is a soft death nobody notifies you about; a Content ID
false-claim war we cannot win because we have **no exclusive rights and therefore no standing to
counter-register**; and the mundane one — Creator's 62-min/month generation cap making the economics
absurd until you are paying Pro at $99/mo before a single view. The honest read: **this is a viable
craft business at low volume with a real human in the loop, and a guaranteed-dead business as an
automated content farm.** The pipeline should be built to make one person faster — not to make the
channel autonomous. If the plan is a mix a week, hand-curated, with real visuals and a written
description, it survives. If the plan is twenty channels posting daily, it is already over; the only
question is the date.

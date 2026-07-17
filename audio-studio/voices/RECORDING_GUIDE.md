# Recording the personal voice corpus (for a true ElevenLabs-class AZ voice)

This is the **one gating step** only you can do. A personal, natural Azerbaijani voice needs
real recorded audio of the target speaker — no public AZ corpus exists. Do this once; then
`prep_dataset.py` + a free Colab finetune turn it into our own voice (VOICE_ROADMAP.md, Phase 3).

## What to record
- **Length:** 30–60 minutes of clean speech (20 min minimum). More = better stress/intonation.
- **One speaker only.** No second voice, no overlap.
- **Clean room:** no background music, TV, traffic, echo, fan. Quiet room, soft furnishings help.
- **Mic:** a decent phone mic 10–20 cm away is fine; avoid pops. Keep the **same mic + distance**
  for the whole session.
- **Delivery — this is what the clone copies, so record the styles you want:**
  - Mostly **natural, calm, conversational** Azerbaijani (the base voice).
  - Include a few minutes of **warm/energetic** (ad tone) and a few of **soft/empathetic**
    (support tone) — so the voice can later cover different purposes.
  - Read **full, varied sentences** (not single words): news, ad copy, explanations, numbers,
    dates, common insurance terms, and Azerbaijani names. Cover ə, x, q, ğ, ö, ü sounds.
- **Format:** wav (best) or m4a/mp3. Any sample rate — we re-encode. One file is easiest.

## Tips for natural result
- Speak as you normally would — don't "announce." The model copies your delivery, flaws and all.
- Short pauses between sentences help the splitter cut clean clips.
- If you misspeak, just pause and redo the sentence — bad clips get dropped in review.

## Then run
```powershell
# drop your recording in audio-studio/voices/  (git-ignored, stays private)
python audio-studio\prep_dataset.py voices\my_recording.wav --speaker ramin
# -> audio-studio/dataset/ramin/  (wavs/ + metadata.csv + report.json)
```
Open `report.json`, skim the transcripts, and delete any clip whose text looks wrong (the
splitter + ASR are good but not perfect). Then upload `dataset/ramin/` to the Colab finetune
notebook (VOICE_ROADMAP.md, Phase 3).

> Consent: only clone a voice you own or have explicit permission to use.

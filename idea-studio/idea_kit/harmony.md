# `harmony.md` — audiovisual unity: why a video FEELS like art

The craft science under every video concept — Eisenstein's montage,
Murch's editing hierarchy, gestalt composition, measured sound-image
congruence, Pixar color scripting — compressed into rules a creative
director (or mediaforge's director brain) can apply to a 15–60s brand
video. This is the layer that turns "generated clips" into the felt
harmony the caring-hand / artful-ugc genres run on.

---

## The laws

- **Cut for emotion above everything (Murch's Rule of Six).** Emotion
  51% → story 23% → rhythm 10% → eye-trace 7% → 2D plane 5% → 3D
  continuity 4%. Sacrifice from the bottom up: "Emotion… is the thing
  that you should try to preserve at all costs."
- **Manage eye-trace.** Know where the viewer's gaze is at the cut;
  place the next shot's point of interest there (smooth) or away
  (deliberate jolt). In prompts: specify subject screen-position across
  consecutive shots.
- **Collision creates the third meaning (Eisenstein).** Two unrelated
  shots butted together force the viewer to synthesize a concept
  contained in neither (ear + door = eavesdropping). One engineered
  collision per short video: product shot + metaphor shot = the claim,
  unsaid.
- **Sound need not illustrate (1928 Statement on Sound).** Deliberate
  sound-image mismatch (contrapuntal) is an expressive device when it
  creates combined meaning — serene music over chaos, silence over the
  loudest visual.
- **Vertical montage.** Each beat is a sound+image *chord*; the sequence
  of beats is a melody with direction. Design both axes.
- **Sync lives at movement ENDPOINTS, not cuts** (PLOS One research):
  viewers perceive synchrony when the hand lands / the object stops
  exactly on the musical beat. Choreograph impact frames to the beat
  grid; skip beats so the edit breathes.
- **Arousal congruence** (JTAER 2025): high-intensity visuals pair with
  high-arousal audio, calm with calm — matched curves measurably lift
  engagement; mismatch only as a designed contrapuntal moment.
- **Color is an arousal dial** (128-year systematic review): red/yellow/
  saturated = arousing; blue/green/grey = calming; valence is
  context-dependent. Don't treat hue as a fixed meaning dictionary.
- **Script color like music (Pixar/Eggleston).** A color script maps the
  emotional arc before production; the palette progression should tell
  the story with no characters at all.
- **Gestalt:** one dominant figure per frame (figure-ground), continuity
  of line/shape/direction across cuts, and closure — suggest, don't
  show; the audience co-authors the meaning.

## Devices (operational — usable as mediaforge prompt/edit instructions)

| Device | Instruction | Proof |
|---|---|---|
| **Beat-anchored impact** | Lay the track first, mark the grid, place each action's IMPACT frame on a beat (not the cut). Skip beats deliberately. | Apple "Bounce" (AirPods) |
| **Collision cut** | One juxtaposition per video: product/user shot + metaphor shot → viewer synthesizes the claim. Place at the concept's spike. | Potemkin's stone lions |
| **Match-on-action invisible cut** | Cut mid-movement to another angle, identical action phase + movement vector at the join. | Continuity grammar |
| **Graphic match transition** | Link shots by shape/composition (round → round, same diagonal) to compress time or scale into one cut. | 2001's bone → satellite |
| **Micro color script (3-beat arc)** | Define 3–4 color beats before generating any shot (cool/desaturated problem → neutral → warm/saturated resolution; brand color owns the final frame). Every shot prompt inherits its beat's palette. | Toy Story colorscripts |
| **Contrapuntal drop** | ONE deliberate sound-image mismatch, then resolve to congruence. | "Dumb Ways to Die"; A Clockwork Orange |
| **Figure-ground lock** | Prompt: "single subject, clean simplified background, strong subject-background contrast"; verify readability at thumbnail size in ~300ms. | Apple product films |
| **Arousal-matched pacing curve** | Draw the arousal curve first (hook high → modulation → pre-climax breath → peak → calm brand close); match cut-rate AND audio energy to it. | JTAER 2025 findings |

## Anti-patterns

```
✗ Cutting on every beat, metronome-style (template content, not craft)
✗ Arousal mismatch by neglect (undesigned incongruence reads as error)
✗ Sacrificing the emotionally right cut to protect spatial continuity
  (inverting Murch: emotion 51% > 3D space 4%)
✗ Busy frames with no figure-ground separation (the shot lives 1-2s)
✗ Per-shot random color — no arc, no felt progression, brand color
  never owns a moment
✗ Mickey-mousing every movement (accent saturation = no accents)
✗ Breaking the motion vector across a mid-action cut
✗ Showing everything — no closure left for the viewer to complete
```

## How mediaforge should consume this

1. Concept locked (via `/idea` + rubric) → draw the **arousal curve**
   and the **3-beat color script** before any generation.
2. Scene prompts inherit: beat palette + figure-ground lock + movement
   vector notes at joins.
3. Sound brief (audio-studio): the track's grid drives impact frames;
   one contrapuntal moment maximum, by design.
4. The edit: match-on-action at joins, one collision cut at the spike,
   endpoints on beats, breathe.

## Sources

- Murch's Rule of Six — https://blogs.ischool.berkeley.edu/i290-viznarr-s12/the-rule-of-six-walter-murch/ ; https://www.studiobinder.com/blog/walter-murch-rule-of-six/
- Eisenstein collision montage — https://darkskiesfilm.com/a-dialectic-approach-to-film-form-by-sergei-eisenstein-summary/ ; vertical montage — https://openjournals.uwaterloo.ca/index.php/kinema/article/download/1152/1394?inline=1
- 1928 Statement on Sound — https://www.britannica.com/topic/Sound-and-Image
- Movement-endpoint sync — https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0221584
- Arousal congruence in short video — https://doi.org/10.3390/jtaer20020069
- Color-emotion systematic review — https://pmc.ncbi.nlm.nih.gov/articles/PMC12325498/
- Color scripts — https://www.studiobinder.com/blog/what-is-a-color-script-definition/
- Gestalt in cinema — https://beverlyboy.com/filmmaking/what-is-gestalt-principles-in-cinema/
- Match on action — https://www.studiobinder.com/blog/what-is-a-match-on-action-cut/

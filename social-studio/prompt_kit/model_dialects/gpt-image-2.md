# Model dialect — GPT Image 2 (via Codex CLI)

How GPT Image 2 prefers the same content phrased. Use this as a
post-processing layer on the master_template output.

## What GPT Image 2 responds to

- **Long, layered instructions.** It can ingest 1500+ word prompts.
- **Hard constraints in opening sentence.** First 100 tokens carry the
  most weight in its attention.
- **Hierarchical structure with headers** (=== SECTION ===) — it
  treats these as priority anchors.
- **Explicit "DO NOT" lists**, particularly for text/letters.
- **Photographer reference names** (Annie Leibovitz, Magnum) trigger
  trained associations.
- **HEX color codes** are honored more reliably than color names.

## What confuses it

- Conflicting directives ("vibrant but restrained" → it picks one).
- Vague qualifiers ("nice", "good", "professional") — meaningless.
- Multi-subject scenes with no spatial anchors.
- Long sentences with three clauses — split into bullets.

## Codex CLI delivery quirk

- Codex saves output to `~/.codex-cli/generated_images/<session>/ig_*.png`,
  not the path you request via `--out`.
- After running, `harvest_codex_images()` in `render_post.py` copies the
  latest ig_*.png into the requested experiments path.
- Each Codex run takes 30 seconds to 7 minutes. Don't time out the
  Python subprocess earlier than 8 minutes.

## Recommended dialect

For master_template content, GPT Image 2 prefers:

1. Open with a single sentence stating output format and what to NOT render.
2. Then 8–10 hard-section headers (=== CAMERA ===, === LIGHTING === ...).
3. End with a numbered exclusion list in priority order.
4. Avoid lyrical prose. The model treats prose as decoration; the
   structured sections as instructions.

## Failure modes specific to GPT Image 2

- Generates an entirely off-brief scene (~33% of runs) when the brief
  leads with style ("premium ad") instead of subject anchor ("ONE
  couple on a train"). Fix: lead with subject + scene.
- Tendency to add "props the agent thinks an ad would have" (extra
  laptop, coffee cup, books). Add to exclusion list if you don't
  want them.
- Strong adherence to negative-text rules, but only if listed FIRST
  in the exclusion list.

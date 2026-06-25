# Flora Video Prompt v1

Target: Meta Reels, 9:16, 10 seconds.

Recommended production models:

- `i2v-seedance-2-0-reference-i2v-enhancor` with `aspect_ratio=9:16`, `duration=10`, `resolution=1080p`
- `i2v-runway-gen-4.5` with `aspect_ratio=9:16`, `duration=10`
- `i2v-sora2-pro` with `aspect_ratio=9:16`, `duration=12`, `resolution=1080p`, then trim to 10 seconds if the best motion lands early

## Prompt

Create a 10-second vertical 9:16 paid Meta Reels ad for Xalq Sigorta's Qurban holiday KASKO campaign. Use the provided campaign key visual and Open Graph start-frame as reference for composition, product identity, colors, and layout. The output should be a premium motion plate and social-card animation, not final typography.

Preserve the campaign world: green Azpetrol fuel pump, clean red passenger car, green gift box with red ribbon, Azpetrol fuel cards, white studio background, green energy sweep, red/green holiday palette, and a polished insurance-ad feeling. The brand tone is premium, trustworthy, clear, and festive without becoming cartoonish.

Storyboard:

0.0-1.5s: A sponsored Open Graph-style social card floats over a soft blurred version of the campaign world. The card has rounded corners, clean white surface, and a subtle mobile Reels feel.

1.5-4.0s: The card expands into the campaign scene: the fuel pump, red car, gift box and fuel cards gain subtle depth. Use controlled 3D parallax, a smooth push-in, and a soft green/red light sweep.

4.0-7.5s: The fuel cards and gift box become the visual focus. Add a subtle glow from the cards, ribbon shimmer, and calm product-ad motion. Keep enough clear space for later overlay cards.

7.5-10.0s: Settle into a clean final brand frame. The last 0.8 seconds should be stable, readable, and suitable for a CTA overlay and Meta thumbnail.

Text policy: Do not generate new readable text, dates, prices, legal terms, CTA labels, or logos. If text from the reference appears as part of the distant card artwork, keep it secondary. Foreground campaign copy will be added later as deterministic overlay. Leave clean zones for vector text and logo lockups.

Motion style: premium paid social, clean product-ad parallax, stable camera, soft shadows, glossy but not plastic, refined green/red light accents, no chaotic zoom, no shaky camera, no scene cut that breaks brand continuity.

Negative constraints: no fake Xalq Sigorta logo, no fake AZPETROL logo, no invented sponsor brand, no malformed Azerbaijani text, no wrong dates, no wrong prices, no people, no extra cars, no distorted car geometry, no melted fuel cards, no warped pump hoses, no random UI controls, no low-resolution blur, no watermark, no stock-video look.

## Overlay Copy to Add After Generation

- Qurban bayramına özəl təklif
- KASKO al, yanacaq kartın hədiyyə olsun!
- 25 may - 5 iyun
- 750 AZN+
- AZPETROL
- Ətraflı bax
- Avtomobilinizi qoruyun, yanacaq kartı qazanın

## QA Reminder

Reject outputs that are visually attractive but require AI-generated text to
carry the message. The final ad must remain understandable with deterministic
overlay copy only.

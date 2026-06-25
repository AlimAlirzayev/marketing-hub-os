# Compiled Generative Ad Prompt

Campaign: Qurban Bayramina KASKO teklifi (`kasko-qurban-2026`)
Platform: meta / instagram-facebook-reels
Format: 9:16, 10s, 1080x1920, 30fps

## Strategic Objective

Primary: Drive KASKO insurance consideration during Qurban holiday campaign.
Audience: Azerbaijani private passenger-car owners eligible for KASKO, excluding taxi, rent-a-car and passenger transport use cases.
Single-minded message: Get KASKO insurance during the campaign and receive an Azpetrol fuel card gift.
Conversion action: Learn more / contact Xalq Sigorta

## Brand Identity

Brand: Xalq Sigorta
Identity source: social-studio/brand_kit/brand.md
Tone:
- premium
- trust-led
- clear
- holiday-positive
- not clickbait

Palette:
- #E31E24
- #2B2A29
- #FFFFFF
- #149040

Typography:
- Inter Tight or Manrope for headlines
- Inter for body/legal

Non-negotiable brand rules:
- Xalq Sigorta logo is deterministic overlay or approved poster artwork only.
- AZPETROL identity must remain green, clean, and recognizable.
- Campaign terms, dates, prices, and CTA must be deterministic overlay.
- No AI-generated new Azerbaijani copy in foreground.

## Offer Copy

Headline: Qurban bayramina ozel teklif
Subheadline: KASKO sigortasi al, yanacaq kartin hediyye olsun!
Dates: 25 may - 5 iyun
CTA: Etrafli bax

Terms:
- Təklif yalnız bonus əmsalı 1.0-dan aşağı olan sürücülərə məxsus minik avtomobillərinə aiddir.
- Taksi, rent a car və sərnişin daşımalarında istifadə olunan avtomobillər kampaniyaya daxil deyil.
- Kampaniya buraxılış ili son 10 ilə qədər olan minik avtomobillərinə şamil olunur.
- Kampaniya sığorta haqqı 750 AZN-dən yuxarı avtomobillər üçün nəzərdə tutulmuşdur.

## Asset Inventory

Role: campaign_key_visual
Path/URL: C:/Users/a.alirzayev/Desktop/Xalq/Logo/bayram kampaniyasi .png
Usage: Approved visual reference: fuel pump, red car, gift box, Azpetrol cards, holiday color system.
Must preserve: red car, Azpetrol fuel pump, gift box, fuel cards, holiday green/red visual language
Asset ID: asset_jd74qh6a2zqckt3gevr685v5xn877nhb

Role: overlay_lockup
Path/URL: output/kasko-flora-og-start.png
Usage: Open Graph-style vertical start-frame reference for composition and hook.
Must preserve: sponsored card structure, rounded card, CTA area, mobile Reels feel
Asset ID: asset_jd7fffw7rs81x62qr5dnvm6etn877w1b

Role: brand_logo
Path/URL: social-studio/brand_kit/xalqsigorta-logo-official.svg
Usage: Final deterministic overlay logo.
Must preserve: exact logo geometry, official color

Role: partner_logo
Path/URL: embedded in approved campaign key visual; request separate vector from marketing when available
Usage: Partner brand reference and final overlay if separate vector is supplied.
Must preserve: AZPETROL green, partner mark integrity

## Storyboard

0.0-1.5s: Open Graph hook
Visual: A clean sponsored social preview card floats over a soft holiday campaign backdrop.
Motion: Gentle card float, slight push-in, soft green-red ambient sweep.
Overlay later: Sponsored / Xalq Sigorta / Reels 9:16 / campaign headline.

1.5-4.0s: Offer reveal
Visual: The card opens into the KASKO campaign world: Azpetrol pump, red car, gift box and cards.
Motion: Controlled 3D parallax, light sweep across the fuel cards, no fast shake.
Overlay later: KASKO al, yanacaq kartı qazan.

4.0-7.5s: Terms made simple
Visual: Three clean offer chips/cards appear over the branded motion plate.
Motion: Staggered slide-in with subtle shadow and settle.
Overlay later: 25 MAY - 5 İYUN / 750 AZN+ / AZPETROL.

7.5-10.0s: CTA settle
Visual: Final clean card with approved campaign visual, logo lockup and CTA.
Motion: Slow settle, stable end frame for last 0.8 seconds.
Overlay later: Avtomobilinizi qoruyun, yanacaq kartı qazanın / 25 may - 5 iyun / Xalq Sigorta x AZPETROL.

## Flora Video Prompt

Create a 10-second vertical 9:16 paid social ad for Xalq Sigorta. Use the provided reference assets for composition, product identity, color, and motion direction. Generate a premium motion plate and social-card animation, not final typography.

Preserve the campaign world and approved assets. The brand tone is premium, trust-led, clear, holiday-positive, not clickbait. The single-minded message is: Get KASKO insurance during the campaign and receive an Azpetrol fuel card gift.

Storyboard:
  0.0-1.5s: Open Graph hook
  Visual: A clean sponsored social preview card floats over a soft holiday campaign backdrop.
  Motion: Gentle card float, slight push-in, soft green-red ambient sweep.
  Overlay later: Sponsored / Xalq Sigorta / Reels 9:16 / campaign headline.

  1.5-4.0s: Offer reveal
  Visual: The card opens into the KASKO campaign world: Azpetrol pump, red car, gift box and cards.
  Motion: Controlled 3D parallax, light sweep across the fuel cards, no fast shake.
  Overlay later: KASKO al, yanacaq kartı qazan.

  4.0-7.5s: Terms made simple
  Visual: Three clean offer chips/cards appear over the branded motion plate.
  Motion: Staggered slide-in with subtle shadow and settle.
  Overlay later: 25 MAY - 5 İYUN / 750 AZN+ / AZPETROL.

  7.5-10.0s: CTA settle
  Visual: Final clean card with approved campaign visual, logo lockup and CTA.
  Motion: Slow settle, stable end frame for last 0.8 seconds.
  Overlay later: Avtomobilinizi qoruyun, yanacaq kartı qazanın / 25 may - 5 iyun / Xalq Sigorta x AZPETROL.

Text policy: Do not generate final readable Azerbaijani campaign copy. Generate motion plate and card movement; exact copy is added as deterministic overlay.

Overlay copy to add after generation:
- Qurban bayramına özəl təklif
- KASKO al, yanacaq kartın hədiyyə olsun!
- 25 may - 5 iyun
- 750 AZN+
- AZPETROL
- Ətraflı bax
- Avtomobilinizi qoruyun, yanacaq kartı qazanın

Negative constraints:
- mutated Azerbaijani text
- invented prices
- wrong dates
- fake Xalq Sigorta logo
- fake AZPETROL logo
- new sponsor brands
- warped UI controls

Reject if:
- Azerbaijani text is generated or visibly malformed in foreground
- Xalq Sigorta or AZPETROL identity is altered
- the red car, fuel pump, gift cards or gift box are deformed
- the offer is not understandable without audio
- the final CTA is not readable for at least the last 0.8 seconds

Approve if:
- the first second reads as a high-quality sponsored social card
- the motion plate supports the approved poster concept
- all final copy is locked as overlay text
- terms are simplified without contradicting the legal brief
- the video is ready for Meta Reels upload

## Model Strategy

Recommended:
- i2v-seedance-2-0-reference-i2v-enhancor
- i2v-runway-gen-4.5
- i2v-sora2-pro

Fallbacks:
- i2v-kling-2.6
- i2v-seedance-1.5-pro
- deterministic-remotion

Variant count: 3

Selection criteria:
- Open Graph hook remains premium and readable
- red car, fuel pump, gift box and fuel cards stay recognizable
- no AI-generated foreground text is required for final comprehension
- motion feels like paid social, not random cinematic drift
- final frame is stable enough for CTA and Meta thumbnail

## Flora CLI Skeletons

Upload the chosen reference image with `flora assets create --source signed-url`,
complete the asset, then replace `<FLORA_ASSET_URL>` below.

```powershell
flora --format json generations create --workspace-id <WORKSPACE_ID> --project-id <PROJECT_ID> --type video --model i2v-seedance-2-0-reference-i2v-enhancor --prompt "<PASTE_COMPILED_PROMPT>" --params '{"image_url":"<FLORA_ASSET_URL>","aspect_ratio":"9:16","duration":"10"}'
flora --format json generations create --workspace-id <WORKSPACE_ID> --project-id <PROJECT_ID> --type video --model i2v-runway-gen-4.5 --prompt "<PASTE_COMPILED_PROMPT>" --params '{"image_url":"<FLORA_ASSET_URL>","aspect_ratio":"9:16","duration":"10"}'
flora --format json generations create --workspace-id <WORKSPACE_ID> --project-id <PROJECT_ID> --type video --model i2v-sora2-pro --prompt "<PASTE_COMPILED_PROMPT>" --params '{"image_url":"<FLORA_ASSET_URL>","aspect_ratio":"9:16","duration":"10"}'
```

# Google Business Profile (Google My Business) — rəy oxu + cavab yaz

Bu bələdçi Xalq Sigorta-nın **Google müştəri rəylərini** CX radara canlı gətirmək
və gələcəkdə **rəylərə cavab yazmağı avtomatlaşdırmaq** üçündür.

> **Niyə service-account bəs etmir?** GA4/Search Console-dan fərqli olaraq rəylər
> (oxu **və** cavab) biznesin **sahiblik datasıdır**. Rəsmi API (`mybusiness.googleapis.com/v4`
> — 2026-da hələ də aktiv rəy səthidir) profili idarə edən **istifadəçi hesabı** ilə
> OAuth (`business.manage` scope) tələb edir. Service-account rəy oxuya/cavab verə bilməz.
> Empirik təsdiq: SA token-i ilə v4 → 404, Account Management API → `SERVICE_DISABLED`.

Kodumuz artıq hazırdır (`connectors/google_reviews.py`): düz endpoint-lər (list +
`updateReply`), OAuth **refresh-token** ilə özü-yenilənən token, dürüst status.
Yalnız aşağıdakı **insan addımları** qalır (yalnız Google hesab sahibi edə bilər).

---

## Addım 1 — Ön şərt (bir dəfə yoxla)

Xalq Sigorta Google Business Profile:
- **təsdiqlənmiş (verified) və aktiv** olmalı, **≥60 gün**,
- profildə **veb-sayt** göstərilməli (xalqsigorta.az),
- profili **sənin idarə etdiyin Google hesabı** ilə idarə olunmalı.

Xalq kimi qurulmuş şirkət üçün bu, demək olar ki, hazırdır.

## Addım 2 — API-yə giriş tələbi (SAAT İŞLƏYİR — indi et)

Bu, əsl darboğazdır (növbə/gözləmə ola bilər), ona görə **ən əvvəl** bunu et:

1. Cloud layihəsi: **`xalq-insure-app`** (nömrə `556481503206`) — GA4 ilə eyni.
2. Giriş formu: <https://developers.google.com/my-business/content/prereqs> →
   *"Request access to the APIs"* → formu doldur.
3. Təsdiq əlaməti: Cloud Console → APIs → *My Business Account Management API* →
   **Quotas**. **0 QPM = hələ təsdiqlənməyib/rədd**, **300 QPM = təsdiqləndi**.

## Addım 3 — API-ləri aktiv et (layihədə)

Cloud Console → *APIs & Services → Enable APIs* üzərində aktiv et:
- **My Business Account Management API** (`mybusinessaccountmanagement.googleapis.com`)
- **My Business Business Information API** (`mybusinessbusinessinformation.googleapis.com`)
- **Google My Business API** (v4 — rəylər burada)

## Addım 4 — OAuth 2.0 Client ID yarat

Cloud Console → *Credentials → Create credentials → OAuth client ID → Desktop app*.
- OAuth consent screen-də scope əlavə et: `https://www.googleapis.com/auth/business.manage`
- `client_secret_....json` faylını yüklə → mənə ver (və ya client_id + client_secret de).

## Addım 5 — Refresh token (bir dəfəlik icazə) — **mən edirəm**

Sən Addım 4-ü bitirən kimi, profili idarə edən hesabla bir dəfəlik consent axını
qururam (OAuth Playground / kiçik helper) və uzunömürlü **refresh_token** alıram.
Sonra bunları şifrəli vault-a yazıram:

```
GOOGLE_BUSINESS_PROFILE_OAUTH_CLIENT_ID
GOOGLE_BUSINESS_PROFILE_OAUTH_CLIENT_SECRET
GOOGLE_BUSINESS_PROFILE_OAUTH_REFRESH_TOKEN
```

## Addım 6 — Hesab + məkan ID-ləri (auto) — **mən edirəm**

Token işləyən kimi `accounts.list` + `locations.list` ilə `GOOGLE_BUSINESS_PROFILE_ACCOUNT_ID`
və `GOOGLE_BUSINESS_PROFILE_LOCATION_IDS`-i özüm tapıb yazıram.

---

## Bundan sonra (avtomatik canlı)

- Rəylər 15-dəqiqəlik fon dövrü ilə CX radara axır (triage → SLA → alert), digər
  kanallarla eyni pipeline.
- **Cavab yazma**: `reply_to_review(...)` (indi `dry_run=True` default) —
  AI-qaralama → insan təsdiqi → `updateReply` ilə göndərmə. Avtomatlaşdırmanı
  təsdiq-qapılı qururuq (heç vaxt icazəsiz göndərmə).

## Alternativ: hazır MCP

`jmdurant/gbp-mcp-server` (5 rəy aləti: list, get_unreplied, generate_reply,
post_reply, delete_reply; **mock mode** dev üçün) — eyni API-ni sarır. Biz **öz
konnektorumuzu** seçdik: CX radarın vahid pipeline-ına (triage/SLA/alert/store)
inteqrasiya olunur, ayrıca silo yaratmır və AI cavabları öz LLM router-imizlə gedir.
Live rejim onun üçün də eyni Google təsdiqini (Addım 2) tələb edir.

## İstinadlar
- Rəy datası ilə işləmə: <https://developers.google.com/my-business/content/review-data>
- Ön şərtlər / giriş: <https://developers.google.com/my-business/content/prereqs>
- `reviews.list`: v4 `GET .../accounts/{acc}/locations/{loc}/reviews` (yalnız verified)
- `reviews.updateReply`: v4 `PUT .../reviews/{id}/reply` body `{"comment": "..."}`

# "NARAHAT OLMA. MƏN XALQ SIĞORTADAYAM." — v2 SPIDER-MAN EDITION
## The AA × Spider-Man spotunun EYNİSİ — yalnız şəhər Bakı, şirkət Xalq Sığorta

> Qayda: orijinala heç nə əlavə edilmir, heç nə çıxarılmır. Hər beat, hər
> replika 10 kadrlıq frame-analizdən + Whisper transkriptindən (CANLI)
> birbaşa köçürülüb. Dəyişən yalnız: şəhər = Bakı, brend = Xalq Sığorta,
> dil = Azərbaycanca.
> Render reli: MediaForge paketi `auto-meta-20260716-155814`.

## Personajlar (continuity)

- **ATA (~40):** Azerbaijani man ~40, short dark hair, stubble, navy
  overshirt over a mustard-yellow shirt (orijinaldakı geyim), holding a
  fork with a bite of food on it — orijinaldakı kimi.
- **OĞUL (~10):** curly dark hair, striped t-shirt, denim jacket
  (orijinaldakı kimi).
- **SPIDER-MAN:** classic red-and-blue suit, web pattern, white eye
  lenses — orijinal obraz, olduğu kimi.
- **MAŞIN:** ailənin sedanı, küçədə park edilib.
- **MƏKAN:** Bakı kafesi — pəncərədən köhnə şəhər küçəsi / Bakı silueti
  görünür; küçə səhnələri İçərişəhər ətrafı daş binalar.

## 30s SSENARİ — 10 plan (orijinalla plan-plan)

| # | TC | Plan (Bakı versiyası) | Orijinalda |
|---|----|------------------------|------------|
| 1 | 0–3s | Bakı kafesi. Ata və oğul stolda burger yeyir. Adi günorta. Küncdə TV yanır. | kafe, ata-oğul burger |
| 2 | 3–6s | TV-də təcili xəbər: aparıcı + helikopter canlı yayımı — **Spider-Man binalar arasında yellənərək təqibdədir**. Alt yazı: "TƏCİLİ XƏBƏR: SPIDER-MAN TƏQİBDƏDİR" | "BREAKING NEWS: SPIDER-MAN IS IN PURSUIT" |
| 3 | 6–9s | GURULTU. İşıq tutulur, pəncərədən nəhəng kölgə keçir, stəkanlar əsir. Ata tikəsi ağzında donub YUXARI baxır. | frame-3: şok baxış |
| 4 | 9–12s | Panika — müştərilər qapıya axışır. Ata əlində çəngəl ayağa qalxır. | frame-4: ata qalxır |
| 5 | 12–15s | KÜÇƏ. Toz çökür. Onların maşını əzilib — dağıntının altında. Siqnalizasiya yanıb-sönür. | frame-6: dağıntı reveal |
| 6 | 15–18s | **SPIDER-MAN əzilmiş maşının üstünə çömbəlmiş halda enir** (klassik poza), ataya tərəf baxır. | frame-7: Spider-Man maşının üstündə |
| 7 | 18–23s | **ANA BEAT.** Oğul: **"Ata, maşın!"** Kimsə: **"Dayan!"** — Ata, əlində hələ də üstündə tikə olan çəngəl, tam sakit: **"Narahat olma. Mən Xalq Sığortadayam."** | "Dad, the car!" / "Wait!" / "It's okay. I'm with the AA." (frame-8: çəngəl əldə) |
| 8 | 23–26s | Spider-Man tor atıb binalar arasına yellənərək uzaqlaşır; arxa fonda partlayış işartısı. | frame-9: swing çıxışı |
| 9 | 26–27s | Ata arxasınca nəzakətlə: **"Sağ ol!"** | "Thank you." |
| 10 | 27–30s | END-CARD: qırmızı fon (#E31E24), iri hərflər: **NARAHAT OLMA. MƏN XALQ SIĞORTADAYAM.** + KASKO + hüquqi sətir. VO: **"Qəzadan sonra da ilk zəngi bizə edin — qalanını Xalq Sığorta həll edir."** | sarı kart: "IT'S OK. I'M WITH THE AA" + "Even after an accident, contact the AA first and we'll take care of everything." |

## Dialoq — transkriptdən birbaşa tərcümə

| Orijinal (Whisper, CANLI) | Bakı versiyası |
|---|---|
| "Breaking news, we are down to live images of Spider-Man." | "Təcili xəbər: Spider-Man-in canlı görüntülərini izləyirsiniz." |
| "Dad, the car!" | "Ata, maşın!" |
| "Wait!" | "Dayan!" |
| "It's okay. I'm with the AA." | "Narahat olma. Mən Xalq Sığortadayam." |
| "Even after an accident, contact the AA first and we'll take care of everything." | "Qəzadan sonra da ilk zəngi bizə edin — qalanını Xalq Sığorta həll edir." |
| "Thank you." | "Sağ ol!" |

## Səs bibliası (orijinalın quruluşu)

kafe ambiyansı → TV xəbər tonu → dərin bas gurultu → panika →
**ANA BEAT-də nisbi sükut** (yalnız atanın sakit səsi) → web-swing
"thwip" + whoosh → VO + son akkord.

## 15s Reels cutdown (paketin render etdiyi — 9:16)

1. 0–2.5s: kafe + TV xəbəri + gurultu başlayır
2. 2.5–5s: panika, ata çəngəllə sakit qalxır
3. 5–8s: əzilmiş maşın + Spider-Man üstünə enir
4. 8–11.5s: "Ata, maşın!" → "Narahat olma. Mən Xalq Sığortadayam." (subtitle)
5. 11.5–13.5s: Spider-Man yellənib gedir, ata: "Sağ ol!"
6. 13.5–15s: end-card + KASKO CTA

## Render reli

| Addım | Əmr | Xərc |
|---|---|---|
| 12 keyframe | `python -m mediaforge.generate auto-meta-20260716-155814 --frames --confirm` | ~$0.30 |
| Animatic | `--animatic` | pulsuz |
| Film (Kling v3 multi-shot) | `--film --confirm` | ~$0.53 |
| Finishing (AZ subtitle+loqo+end-card) | `--finish` | pulsuz |

**İki texniki qeyd (ssenariyə aid deyil):** (1) efir/paylaşım üçün
Sony/Marvel lisenziyası lazımdır — The AA-nın yolu da məhz tərəfdaşlıq
idi; (2) video modelləri lisenziyalı obrazı filtrləyə bilər — render
cəhdində görünəcək; ssenarinin özü bundan asılı deyil.

---
*v2 · 2026-07-16 · Mənbə: 10 kadr frame-analizi + Whisper transkripti.
Konsept sənədi: xs-baku-adaptation.md*

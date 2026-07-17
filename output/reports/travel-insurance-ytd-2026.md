# Səyahət sığortası — 2026 YTD rəhbərlik hesabatı

**Hesabat tarixi:** 16.07.2026  
**Dövr:** 01.01.2026–16.07.2026  
**Status:** Data tamamlanması tələb olunur

## İcra xülasəsi

Hazırkı sistem vəziyyətində səyahət sığortası üzrə real satış sayı və reklam
performansını rəhbərliyə etibarlı rəqəmlərlə təqdim etmək mümkün deyil. Səbəb
hesablama deyil, iki əsas mənbənin hazırkı statusudur:

- CRM-in 2026 üzrə verilmiş səyahət polisləri ixracı sistemdə yoxdur.
- Meta Ads bağlantısı konfiqurasiya olunub, lakin sessiya təhlükəsizlik/parol
  dəyişikliyindən sonra etibarsızlaşdırılıb (`code 190`, `subcode 460`).
- GA4 canlı property qoşulmayıb və demo rejimindədir; demo rəqəmlər bu hesabatdan
  qəsdən çıxarılıb.

Bu səbəbdən satış, premium, CPA, ROAS və məhsul seqmentləri üçün rəqəm
uydurulmayıb. Yeni Səyahət YTD dashboardu mənbələr bərpa edilən kimi aşağıdakı
göstəriciləri avtomatik formalaşdırır.

## Rəhbərlik üçün KPI çərçivəsi

| KPI | Əsas mənbə | Hazırkı status |
|---|---|---|
| Verilmiş polis sayı | CRM | CSV ixracı tələb olunur |
| Yığılmış premium | CRM | CSV ixracı tələb olunur |
| Orta premium | CRM | CSV ixracı tələb olunur |
| Reklam xərci, reach, impression, klik, CTR, CPC | Meta Ads | Token yenilənməlidir |
| Meta-attributed Purchase, CPA, gəlir, ROAS | Meta Ads + CAPI | Token yenilənməlidir |
| Yaş × cins, region, placement, cihaz | Meta Ads | Token yenilənməlidir |
| Landing page sessiyası, conversion rate, funnel drop-off | GA4 | Canlı property qoşulmalıdır |

## Qərar üçün tövsiyə edilən seqmentasiyalar

1. Yaş × cins üzrə satış və CPA.
2. Bakı/region və səfər istiqaməti üzrə polis sayı, premium və orta çek.
3. Facebook/Instagram, Feed/Stories/Reels üzrə CTR, CPA və ROAS.
4. Yeni/təkrar müştəri və fərdi/ailə paketi üzrə satış dəyəri.
5. Mobil/desktop üzrə landing conversion rate və funnel itkisi.
6. Aylıq trend və mövsümi piklər üzrə büdcə payı.

## İstifadə qaydası

1. `http://localhost:8800/travel-report` ünvanını açın.
2. CRM-dən 2026 üzrə səyahət sığortası polislərini CSV UTF-8 kimi ixrac edin.
3. Faylı “CRM CSV-ni seçin” sahəsinə verin. Fayl serverə göndərilmir; polis sayı
   və premium yalnız brauzerdə lokal hesablanır.
4. Meta tokeni yeniləndikdən sonra səhifəni refresh edin: kampaniya nəticələri və
   seqmentlər avtomatik gələcək.
5. `PDF / Çap` düyməsi ilə rəhbərlik versiyasını saxlayın.

## Data bərpası üçün minimum addımlar

- Meta: daimi System User token və `ads_read` icazəsi ilə mövcud tokeni yeniləmək.
- CRM: 2026 YTD səyahət məhsulu ixracında ən azı `Polis №`, `Premium/Məbləğ`,
  `Valyuta`, `Məhsul`, `Tarix` sahələrini saxlamaq.
- GA4: service account-u property-yə Viewer kimi əlavə edib property ID-ni
  Ramin-OS konfiqurasiyasına daxil etmək.

---

_Rəqəmlər yalnız canlı mənbədən və ya istifadəçinin lokal CRM ixracından
formalaşır; demo data rəhbərlik nəticəsinə daxil edilmir._

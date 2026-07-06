# SITE-CRAFT — sayt/landing quruculuğunun doktrinası

> Mənbə: şəxsi sistemdə sınaqdan çıxmış üsul (2026-06). Bu sənəd mühərrikin bir orqanıdır —
> hər iki maşındakı hər agent sayt/landing/HTML işinə başlamazdan ƏVVƏL bunu oxumalıdır.

## Qayda bir cümlədə

**Bir sətir HTML yazmazdan əvvəl həmin layihənin öz `DESIGN.md`-i müəllif olunur —
sayt sonra ona tabe tikilir.** Design sistemi olmayan sayt = "AI saytı" görkəmi.

## Niyə

LLM-lər default olaraq eyni saytı çıxarır: bənövşəyi qradiyent hero, mərkəzlənmiş hər şey,
emoji-bullet-lər, glassmorphism kartlar, Inter şrifti, "Get Started" düyməsi. Bu görkəm
istifadəçiyə "şablon" siqnalı verir və brendi ucuzlaşdırır. Çıxış yolu üslub "seçmək" deyil —
layihəyə məxsus design sistemini ƏVVƏLCƏDƏN yazıb ona tabe olmaqdır.

## DESIGN.md-in məcburi bölmələri

1. **Konsept adı + əhval** — bir başlıq, 2-3 cümlə dünya-hissi (məs. "editorial-noir:
   gecə jurnalı kimi — mürəkkəb qara, kağız ağı, bir damla qan qırmızısı").
2. **Palitra** — dəqiq HEX-lərlə 4-6 rəng: fon / mətn / vurğu / səth / xətt. Hər rəngin
   İŞİ yazılır ("vurğu yalnız CTA və aktiv vəziyyət üçün").
3. **Tipoqrafiya** — display + body cütlüyü (adları ilə), ölçü şkalası (px/rem pilləkəni),
   sətir hündürlüyü, hərf-araları. Default şriftlə qalmaq qadağandır.
4. **Boşluq ritmi** — baza vahidi (məs. 8px) və bölmə aralarının qaydası.
5. **İmza motivləri** — bu saytı BAŞQA heç kimin saytına oxşatmayan 2-3 detal
   (kəsik künc, nömrələnmiş bölmələr, xətt-altı işarələr, asimmetrik grid...).
6. **Qadağalar siyahısı** — generik-AI əlamətlərinin açıq inkarı: bənövşəyi qradiyent,
   emoji-bullet, glassmorphism, hamısı-mərkəzdə düzülüş, stok "hero illustration",
   səbəbsiz dairəvi künclər. Layihəyə görə genişləndirilir.
7. **İnteraksiya dili** — hover/focus/keçid davranışının bir abzaslıq təsviri
   (sürət, yumşaqlıq, nə qədər hərəkət "çox"dur).

## İş axını

1. Brif → `DESIGN.md` müəllifliyi (yuxarıdakı 7 bölmə, konkret dəyərlərlə).
2. Sahibdən bir dəfə təsdiq (əhval düzgündürmü) — sonra dəyişməz qanundur.
3. Tikinti: hər komponent DESIGN.md-ə istinadla. Kənara çıxmaq lazımdırsa —
   əvvəl DESIGN.md-ə düzəliş, sonra kod.
4. Yekun yoxlama: saytı aç və soruş — "bu, qadağalar siyahısındakı hansısa əlaməti
   daşıyırmı?" Daşıyırsa, bitməyib.

## Uygulama qeydi

Bu doktrina statik landing-dən tutmuş studio UI-larına qədər hər vizual səthə aiddir.
Kiçik daxili alət üçün belə minimum: palitra + tipoqrafiya + qadağalar (3 bölmə).

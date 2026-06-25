"""Meta connection checker for Ads Studio.

Run this after putting a token in .env. It confirms the token works, shows the
real account name/currency, and lists which months actually have spend - so we
know the dashboard will show live data before flipping the server to live.

    .venv\\Scripts\\python.exe verify_meta.py
"""

from __future__ import annotations

import sys

import config


def _explain_how_to_get_token() -> None:
    print("\n  Token yoxdur. Real datanı görmək üçün ən sürətli yol (~1 dəqiqə):")
    print("  ┌─ MÜVƏQQƏTİ TOKEN (dərhal görmək üçün) ─────────────────────────")
    print("  │ 1. https://developers.facebook.com/tools/explorer")
    print("  │ 2. Yuxarı sağda 'Meta App' seç (yoxdursa 'Create App' → Business).")
    print("  │ 3. 'Permissions' → 'ads_read' əlavə et.")
    print("  │ 4. 'Generate Access Token' → Meta hesabınla təsdiqlə.")
    print("  │ 5. Token-i kopyala, .env-də META_ACCESS_TOKEN= sətrinə yapışdır.")
    print("  └────────────────────────────────────────────────────────────────")
    print("  (Bu token ~1-2 saatlıqdır — sadəcə görmək üçün. Daimi üçün sonra")
    print("   System User token qurarıq.)\n")


def main() -> int:
    print("=" * 64)
    print("  Ads Studio · Meta bağlantı yoxlaması")
    print("=" * 64)
    print(f"  Ad account : {config.META_AD_ACCOUNT_ID or '(yoxdur)'}")
    print(f"  Data mode  : {config.DATA_MODE}")

    if not config.META_ACCESS_TOKEN:
        _explain_how_to_get_token()
        return 1
    if not config.META_AD_ACCOUNT_ID:
        print("\n  META_AD_ACCOUNT_ID .env-də yoxdur (act_... formatında).\n")
        return 1

    from connectors import meta

    # 1) Account identity
    try:
        info = meta.account_info()
    except Exception as exc:
        print(f"\n  ✗ Hesab məlumatı alınmadı: {exc}\n")
        print("  İpucu: token bitib (kod 190) ola bilər, ya da ads_read icazəsi /")
        print("  bu ad account-a çıxış yoxdur (kod 200/10). Yenidən token yarat.\n")
        return 2
    print(f"\n  ✓ Bağlantı OK")
    print(f"    Hesab adı  : {info['name']}")
    print(f"    Valyuta    : {info['currency']}   (lazım olsa .env-də ADS_CURRENCY={info['currency']})")
    print(f"    Status     : {info.get('status')}   Saat qurşağı: {info.get('timezone')}")

    # 2) Which recent months actually have data?
    print("\n  Son aylarda real data:")
    found_any = False
    now = config.today()
    y, m = now.year, now.month
    for _ in range(config.HISTORY_MONTHS):
        ym = f"{y}-{m:02d}"
        try:
            rep = meta.build_report(ym, "all")
            t = rep["combined_totals"]
            has = t["spend"] > 0 or t["impressions"] > 0
            found_any = found_any or has
            flag = "✓" if has else "·"
            print(f"    {flag} {config.month_label(ym):<14} xərc={t['spend']:>10}  "
                  f"göstərilmə={t['impressions']:>8}  lead={t['leads']:>5}  mesaj={t['messages']:>5}")
        except Exception as exc:
            print(f"    ! {config.month_label(ym):<14} xəta: {exc}")
        m -= 1
        if m == 0:
            m, y = 12, y - 1

    print("\n" + "=" * 64)
    if found_any:
        print("  ✓ HAZIR — real data var. Serveri restart et, panel CANLI olacaq.")
    else:
        print("  ⚠ Token işləyir, amma bu aylarda xərc/göstərilmə tapılmadı")
        print("    (kampaniya yeni/draft ola bilər). Panel açılır, sadəcə rəqəmlər 0.")
    print("=" * 64 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

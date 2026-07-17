"""Meta token rotasiyasından SONRA bir komandalı uçuş yoxlaması.

Token `SECURE_KEY.bat META_ACCESS_TOKEN` ilə yeniləndikdən sonra bu skript
üç cəbhəni bir dəfəyə, YALNIZ OXUMA rejimində yoxlayır:

  1. Token sağlamlığı  — /me + reklam hesabı (ads_read işləyirmi)
  2. KASKO cəbhəsi     — kampaniya/draft siyahısı, publish-ə nə qalıb
  3. CAPI cəbhəsi      — offline dataset görünürmü (göndəriş YOX)
  4. Travel cəbhəsi    — YTD hesabatın canlı KPI-ları dolurmu

Heç nə publish etmir, heç bir event göndərmir — yalnız vəziyyəti çıxarır və
növbəti dəqiq komandaları yazır. İstifadə:

    python scripts/meta_relaunch.py
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

from gateway._bootstrap import load_env  # noqa: E402

load_env()

import os  # noqa: E402

TOKEN = os.getenv("META_ACCESS_TOKEN", "")
ACT = os.getenv("META_AD_ACCOUNT_ID", "")
DATASET = os.getenv("META_OFFLINE_DATASET_ID", "")
VER = os.getenv("META_GRAPH_API_VERSION") or os.getenv("META_API_VERSION") or "v21.0"
KASKO_HINTS = ("kasko", "bayram", "azpetrol")


def _get(path: str, **params) -> dict:
    params["access_token"] = TOKEN
    url = f"https://graph.facebook.com/{VER}/{path}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        try:
            return {"error": json.loads(exc.read().decode()).get("error", {})}
        except Exception:  # noqa: BLE001
            return {"error": {"message": f"HTTP {exc.code}"}}
    except Exception as exc:  # noqa: BLE001
        return {"error": {"message": str(exc)}}


def _fail(err: dict) -> str:
    return f"code={err.get('code')} — {str(err.get('message', ''))[:110]}"


def main() -> int:
    print("=" * 64)
    print("  META YENİDƏN UÇUŞ — oxuma rejimli tam yoxlama")
    print("=" * 64)

    if not TOKEN:
        print("\n✗ META_ACCESS_TOKEN boşdur. Əvvəlcə: SECURE_KEY.bat META_ACCESS_TOKEN")
        return 1

    # 1) Token
    me = _get("me", fields="id,name")
    if "error" in me:
        print(f"\n✗ Token hələ də işləmir: {_fail(me['error'])}")
        print("  → Yeni token System User-dan ads_read icazəsi ilə yaradılmalıdır.")
        return 1
    print(f"\n✓ Token sağlamdır — {me.get('name')} (id={me.get('id')})")

    acc = _get(ACT, fields="name,account_status,currency,amount_spent")
    if "error" in acc:
        print(f"✗ Reklam hesabı oxunmur ({ACT}): {_fail(acc['error'])}")
        print("  → Tokenin System User-ına bu ad account təyin olunmalıdır (ads_read).")
    else:
        print(f"✓ Hesab: {acc.get('name')} | status={acc.get('account_status')} "
              f"| xərc={acc.get('amount_spent')} {acc.get('currency')}")

    # 2) KASKO — kampaniyalar + draftlar
    print("\n--- KASKO cəbhəsi ---")
    camps = _get(f"{ACT}/campaigns",
                 fields="id,name,status,effective_status,objective,start_time",
                 limit=50)
    kasko_found = False
    for c in camps.get("data", []):
        mark = "→" if any(h in c.get("name", "").lower() for h in KASKO_HINTS) else " "
        if mark == "→":
            kasko_found = True
        print(f" {mark} [{c.get('effective_status')}] {c.get('name')} ({c.get('id')})")
    if "error" in camps:
        print(f"✗ Kampaniyalar oxunmadı: {_fail(camps['error'])}")
    drafts = _get(f"{ACT}/addrafts", fields="id,name,status")
    for d in drafts.get("data", []):
        kasko_found = True
        print(f" → [DRAFT] {d.get('name')} ({d.get('id')})")
    if not kasko_found and "error" not in camps:
        print("  KASKO adına kampaniya/draft görünmədi — draft Ads Manager UI-də "
              "qala bilər (API-yə düşməyən UI draftı). Publish UI-dən gedəcək.")
    print("  Publish qərarı insandadır: Azpetrol təsdiqi + Ads Manager-də 'Publish'.")

    # 3) CAPI — dataset görünürlüyü (göndəriş YOXDUR)
    print("\n--- CAPI cəbhəsi ---")
    if not DATASET:
        print("✗ META_OFFLINE_DATASET_ID boşdur.")
    else:
        ds = _get(DATASET, fields="id,name")
        if "error" in ds:
            print(f"✗ Dataset oxunmur: {_fail(ds['error'])}")
        else:
            print(f"✓ Dataset görünür: {ds.get('name')} ({ds.get('id')})")
            print("  İlk canlı göndəriş (PII → sən işlədirsən):")
            print("    meta-capi\\POLIS_SATISLARI_GONDER.bat")

    # 4) Travel hesabatı
    print("\n--- Travel cəbhəsi ---")
    sys.path.insert(0, str(ROOT / "ads-studio"))
    try:
        from travel_reporting import build_ytd_report  # noqa: PLC0415
        report = build_ytd_report()
        meta_block = report.get("meta") or {}
        status = meta_block.get("status", "?")
        print(f"  Meta bloku statusu: {status}")
        if status in {"ok", "live"}:
            print("✓ Travel YTD hesabatı canlı doldu → http://localhost:8800/travel-report")
        else:
            print(f"  Qeyd: {str(meta_block.get('note', ''))[:140]}")
    except Exception as exc:  # noqa: BLE001
        print(f"✗ travel_reporting işləmədi: {exc}")

    print("\n" + "=" * 64)
    print("  Yekun: yuxarıdakı ✓/✗-lərə bax; ✗ qalırsa səbəb yanındadır.")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

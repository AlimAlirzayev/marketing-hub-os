"""Safest supported API-key rotation: hidden prompt -> vault -> verified push."""

from __future__ import annotations

import argparse
import getpass
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from gateway import keyvault  # noqa: E402
from gateway.secret_store import migrate_legacy_env, store_master  # noqa: E402

KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,80}$")


def _git(*args: str) -> tuple[int, str]:
    proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=60)
    return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()


def _ensure_master() -> None:
    migrate_legacy_env(keyvault.ENV_PATH)
    if keyvault.enabled():
        return
    first = getpass.getpass("Vault master parolu (yalnız bu maşında saxlanacaq): ")
    second = getpass.getpass("Təkrar daxil edin: ")
    if not first or first != second:
        raise RuntimeError("Master parollar uyğun gəlmir")
    store_master(first)
    os.environ.pop("KEY_VAULT_SECRET", None)
    if not keyvault.enabled():
        raise RuntimeError("OS secret store açıla bilmədi")


def _preflight_sync() -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "sync_engine.py"), "--pull-only", "--quiet"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    output = ((proc.stdout or "") + (proc.stderr or "")).casefold()
    if any(flag in output for flag in ("blocked", "diverged", "could not reach", "manual review")):
        raise RuntimeError("Git preflight təhlükəsiz tamamlanmadı; açar qəbul edilmədi")


def publish(key: str) -> str:
    _preflight_sync()
    _ensure_master()
    value = getpass.getpass(f"{key} dəyərini yapışdırın (görünməyəcək): ").strip()
    if not value:
        raise RuntimeError("Boş dəyər qəbul edilmir")
    keyvault.set_local(key, value)
    if not keyvault.put(key, value):
        raise RuntimeError("Şifrəli vault-a yazılmadı")
    del value
    if _git("add", "--", "secrets/keys.vault")[0]:
        raise RuntimeError("Vault stage edilmədi")
    code, out = _git("commit", "-m", f"chore(keys): rotate {key} in encrypted vault", "--", "secrets/keys.vault")
    if code:
        raise RuntimeError("Vault commit edilmədi")
    head = _git("rev-parse", "HEAD")[1].splitlines()[0]
    if _git("push", "origin", "HEAD")[0]:
        raise RuntimeError(f"Şifrəli commit yaradıldı ({head[:7]}), amma push alınmadı")
    remote = _git("rev-parse", "@{u}")[1].splitlines()[0]
    if remote != head:
        raise RuntimeError("Upstream təsdiqi uyğun gəlmədi")
    keyvault.receipt([key])
    return head[:7]


def main() -> int:
    parser = argparse.ArgumentParser(description="API açarını twin-lərə təhlükəsiz çatdır")
    parser.add_argument("key", nargs="?", help="məs. META_ACCESS_TOKEN")
    args = parser.parse_args()
    key = (args.key or input("Açar adı (məs. META_ACCESS_TOKEN): ")).strip().upper()
    if not KEY_RE.fullmatch(key) or not keyvault.syncable(key):
        print("Xəta: bu açar adı paylaşım üçün icazəli deyil.")
        return 2
    try:
        commit = publish(key)
    except Exception as exc:
        print(f"Xəta: {exc}")
        return 1
    print(f"Hazırdır: {key} lokal yazıldı, şifrələndi və upstream təsdiqləndi ({commit}).")
    print("Digər twin növbəti avtomatik sync-də qəbul qəbzi yaradacaq.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

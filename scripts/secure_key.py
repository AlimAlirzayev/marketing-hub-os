"""Safest supported API-key rotation: hidden prompt -> isolated vault push."""

from __future__ import annotations

import argparse
import getpass
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from gateway import keyvault  # noqa: E402
from gateway.secret_store import migrate_legacy_env, store_master  # noqa: E402

KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,80}$")


def _git(*args: str, cwd: Path = ROOT, timeout: int = 60) -> tuple[int, str]:
    proc = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout,
    )
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


def _upstream() -> tuple[str, str]:
    """Return (remote ref, remote branch), without inspecting the dirty tree."""
    code, ref = _git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    ref = ref.splitlines()[0].strip() if not code and ref else "origin/master"
    if "/" not in ref:
        raise RuntimeError("Git upstream tapılmadı")
    remote, branch = ref.split("/", 1)
    if remote != "origin" or not branch:
        raise RuntimeError("Yalnız origin upstream dəstəklənir")
    return ref, branch


def _publish_isolated(key: str, value: str) -> str:
    """Publish only ciphertext from a clean detached worktree.

    The user's current checkout may be dirty or divergent. It is never staged,
    merged, reset, or otherwise modified by this operation.
    """
    upstream, branch = _upstream()
    code, output = _git("fetch", "origin", "--prune", timeout=120)
    if code:
        raise RuntimeError(f"GitHub-a təhlükəsiz bağlantı alınmadı: {output[-180:]}")

    temp_root = Path(tempfile.mkdtemp(prefix="ramin-keyvault-"))
    worktree = temp_root / "repo"
    original_vault = keyvault.VAULT_PATH
    added = False
    try:
        code, output = _git("worktree", "add", "--detach", str(worktree), upstream, timeout=120)
        if code:
            raise RuntimeError(f"Təmiz vault sahəsi yaradıla bilmədi: {output[-180:]}")
        added = True

        keyvault.VAULT_PATH = worktree / "secrets" / "keys.vault"
        if not keyvault.put(key, value):
            raise RuntimeError("Şifrəli vault-a yazılmadı")

        if _git("add", "--", "secrets/keys.vault", cwd=worktree)[0]:
            raise RuntimeError("Vault stage edilmədi")
        code, output = _git(
            "commit", "-m", f"chore(keys): rotate {key} in encrypted vault",
            "--", "secrets/keys.vault", cwd=worktree,
        )
        if code:
            raise RuntimeError(f"Vault commit edilmədi: {output[-180:]}")
        head = _git("rev-parse", "HEAD", cwd=worktree)[1].splitlines()[0]

        code, output = _git("push", "origin", f"HEAD:{branch}", cwd=worktree, timeout=120)
        if code:
            raise RuntimeError(f"Şifrəli vault push edilmədi: {output[-180:]}")
        code, remote = _git("ls-remote", "origin", f"refs/heads/{branch}", cwd=worktree)
        remote_head = remote.split()[0] if not code and remote else ""
        if remote_head != head:
            raise RuntimeError("GitHub təsdiqi uyğun gəlmədi")
        return head[:7]
    finally:
        keyvault.VAULT_PATH = original_vault
        if added:
            _git("worktree", "remove", "--force", str(worktree), timeout=120)
        try:
            temp_root.rmdir()
        except OSError:
            pass


def publish(key: str) -> str:
    _ensure_master()
    value = getpass.getpass(f"{key} dəyərini yapışdırın (görünməyəcək): ").strip()
    if not value:
        raise RuntimeError("Boş dəyər qəbul edilmir")

    # Push first. A failed remote publication must not look globally complete.
    head = _publish_isolated(key, value)
    keyvault.set_local(key, value)
    del value
    keyvault.receipt([key])
    return head


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
    print(f"Hazırdır: {key} lokal yazıldı, şifrələndi və GitHub-da təsdiqləndi ({commit}).")
    print("Digər twin növbəti avtomatik sync-də açarı qəbul edəcək.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

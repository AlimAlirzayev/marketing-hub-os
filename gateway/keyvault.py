"""Encrypted key vault — let API keys travel between the two friend-systems
SAFELY, the way SOPS / git-crypt / ansible-vault do it: the SECRET VALUES are
encrypted at rest and the ciphertext rides the same git "post office" as the
engine, while the master passphrase that unlocks them NEVER touches git.

The rule this refines: *plaintext* keys never travel via git (that is a real
leak). *Encrypted-at-rest* keys can — ciphertext without the master key is not
a secret. Whoever can read the repo sees only an opaque blob.

  secrets/keys.vault   git-TRACKED ciphertext (Fernet, AES-128-CBC + HMAC).
  KEY_VAULT_SECRET     the master passphrase, in each machine's .env only —
                       set ONCE per machine (same value on both). Never stored
                       in the vault, never committed, never echoed.

Bootstrap = one owner action per machine:  /setkey KEY_VAULT_SECRET <passphrase>
After that, every /setkey travels automatically: the value is encrypted into the
vault, pushed, and the other friend applies it to its own .env on the next sync.

Machine-identity keys never travel (each friend has its OWN Telegram bot and the
master passphrase is per-machine by definition) — see _NEVER_SYNC.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from ._bootstrap import load_env

load_env()  # standalone CLI (`python -m gateway.keyvault`) must see .env too

ROOT = Path(__file__).resolve().parent.parent
VAULT_PATH = ROOT / "secrets" / "keys.vault"
ENV_PATH = ROOT / ".env"

# Keys that are intrinsically per-machine and must NOT be shared, even by /setkey.
# The master passphrase can never live inside the thing it encrypts; each friend
# runs its own Telegram bot; the owner-chat pairing stays local too.
_NEVER_SYNC = {"KEY_VAULT_SECRET", "TELEGRAM_BOT_TOKEN", "TELEGRAM_OWNER_CHAT_ID"}

_SCRYPT = dict(n=2**15, r=8, p=1, dklen=32, maxmem=64 * 1024 * 1024)


def _secret() -> str | None:
    val = (os.getenv("KEY_VAULT_SECRET") or "").strip()
    if not val:
        try:
            from .secret_store import load_master
            val = (load_master() or "").strip()
        except Exception:
            val = ""
    return val or None


def enabled() -> bool:
    """True once the owner has set the master passphrase on this machine."""
    return _secret() is not None


def syncable(key: str) -> bool:
    return key not in _NEVER_SYNC and bool(key)


def _fernet(salt: bytes):
    from cryptography.fernet import Fernet
    derived = hashlib.scrypt((_secret() or "").encode("utf-8"), salt=salt, **_SCRYPT)
    return Fernet(base64.urlsafe_b64encode(derived))


def load() -> dict[str, dict]:
    """Decrypt the vault -> {KEY: {"v": value, "ts": iso}}. {} if empty/locked."""
    if not enabled() or not VAULT_PATH.exists():
        return {}
    try:
        env = json.loads(VAULT_PATH.read_text(encoding="utf-8"))
        salt = base64.b64decode(env["salt"])
        blob = _fernet(salt).decrypt(env["blob"].encode("utf-8"))
        return json.loads(blob.decode("utf-8")).get("keys", {})
    except Exception:
        # Wrong passphrase or corrupt file: fail closed (never crash), no values.
        return {}


def _save(keys: dict[str, dict]) -> None:
    salt = os.urandom(16)
    blob = _fernet(salt).encrypt(json.dumps({"keys": keys}).encode("utf-8"))
    VAULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    VAULT_PATH.write_text(
        json.dumps({"v": 1, "salt": base64.b64encode(salt).decode(), "blob": blob.decode()},
                   indent=0),
        encoding="utf-8",
    )


def put(key: str, value: str) -> bool:
    """Add/update one key in the encrypted vault so it travels. Returns False if
    the vault is locked (no master passphrase) or the key is non-syncable."""
    if not enabled() or not syncable(key):
        return False
    keys = load()
    keys[key] = {"v": value, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
    _save(keys)
    return True


def names() -> list[str]:
    """Key NAMES held in the vault (never the values)."""
    return sorted(load().keys())


def drop(key: str) -> bool:
    """Remove one key from the vault (e.g. a poisoned/stale entry). Returns True
    if it was present. The caller decides whether to commit_and_push."""
    if not enabled():
        return False
    keys = load()
    if key not in keys:
        return False
    del keys[key]
    _save(keys)
    return True


# --- applying arrived keys into this machine's .env -------------------------

def _read_env_lines() -> list[str]:
    return ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []


def _env_value(lines: list[str], key: str) -> str | None:
    prefix = f"{key}="
    for line in lines:
        if line.strip().startswith(prefix):
            return line.split("=", 1)[1]
    return None


def _write_env(key: str, value: str, lines: list[str]) -> list[str]:
    prefix = f"{key}="
    for i, line in enumerate(lines):
        if line.strip().startswith(prefix):
            lines[i] = f"{key}={value}"
            return lines
    lines.append(f"{key}={value}")
    return lines


def apply_to_env() -> list[str]:
    """Merge vault keys the other friend added into this machine's .env. Only
    adds or updates (never deletes local keys); skips values already identical.
    Returns the NAMES applied (for a masked announcement)."""
    keys = load()
    if not keys:
        return []
    lines = _read_env_lines()
    applied: list[str] = []
    for key, rec in keys.items():
        if not syncable(key):
            continue
        value = rec.get("v", "")
        if _env_value(lines, key) == value:
            continue
        lines = _write_env(key, value, lines)
        os.environ[key] = value
        applied.append(key)
    if applied:
        ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return applied


def set_local(key: str, value: str) -> bool:
    """Write one key locally without printing or returning its value."""
    if not syncable(key):
        return False
    lines = _read_env_lines()
    previous = _env_value(lines, key)
    lines = _write_env(key, value, lines)
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ[key] = value
    return previous != value


def receipt(applied: list[str]) -> None:
    """Write machine-private proof that a vault version was checked/applied."""
    try:
        digest = hashlib.sha256(VAULT_PATH.read_bytes()).hexdigest() if VAULT_PATH.exists() else None
        path = ROOT / "data" / "private_context" / "keyvault_receipt.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "vault_sha256": digest,
            "applied_names": sorted(applied),
            "available_names": names(),
        }, indent=2), encoding="utf-8")
    except Exception:
        pass


# --- pushing the vault into the post office (git) ---------------------------

def commit_and_push() -> bool:
    """Commit ONLY the vault file and push it, so the other friend gets the new
    encrypted key on its next sync. Best-effort; never raises."""
    rel = str(VAULT_PATH.relative_to(ROOT))
    try:
        subprocess.run(["git", "add", rel], cwd=str(ROOT), check=True,
                       capture_output=True, timeout=30)
        subprocess.run(["git", "commit", rel, "-m", "chore(keys): update encrypted key vault"],
                       cwd=str(ROOT), check=True, capture_output=True, timeout=30)
        subprocess.run(["git", "push", "origin", "HEAD"], cwd=str(ROOT), check=True,
                       capture_output=True, timeout=60)
        local = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT), check=True,
                               capture_output=True, text=True, timeout=15,
                               encoding="utf-8", errors="replace").stdout.strip()
        remote = subprocess.run(["git", "rev-parse", "@{u}"], cwd=str(ROOT), check=True,
                                capture_output=True, text=True, timeout=15,
                                encoding="utf-8", errors="replace").stdout.strip()
        return bool(local and local == remote)
    except Exception:
        return False


if __name__ == "__main__":  # tiny CLI for the SessionStart hook + manual use
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "apply":
        try:
            from .secret_store import migrate_legacy_env
            migrated = migrate_legacy_env(ENV_PATH)
        except Exception:
            migrated = False
        applied = apply_to_env()
        receipt(applied)
        print(f"[keyvault] applied {len(applied)} key(s): {', '.join(applied) or '—'}")
        if migrated:
            print("[keyvault] master secret moved from .env to the OS-local secret store")
    elif cmd == "status":
        if not enabled():
            print("[keyvault] locked (set KEY_VAULT_SECRET to enable)")
        else:
            print(f"[keyvault] {len(names())} synced key(s): {', '.join(names()) or '—'}")
    elif cmd == "drop" and len(sys.argv) > 2:
        ok = drop(sys.argv[2])
        print(f"[keyvault] {'dropped' if ok else 'not found'}: {sys.argv[2]}")
    else:
        print("usage: python -m gateway.keyvault [apply|status|drop KEY]")

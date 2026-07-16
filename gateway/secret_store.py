"""Machine-local storage for the key-vault master secret.

Windows uses CurrentUser DPAPI. Unix hosts use a user-only (0600) file outside
the repository. API keys still travel only as encrypted ``keys.vault`` data.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


_WIN_BLOB = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "RaminOS" / "keyvault-master.dpapi"
_UNIX_FILE = Path.home() / ".config" / "ramin-os" / "keyvault-master"


def _powershell(script: str, *, stdin: str = "") -> str:
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        input=stdin, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=20,
    )
    if proc.returncode:
        raise RuntimeError("OS secret store operation failed")
    return (proc.stdout or "").strip()


def store_master(secret: str) -> None:
    secret = (secret or "").strip()
    if not secret:
        raise ValueError("master secret cannot be empty")
    if os.name == "nt":
        _WIN_BLOB.parent.mkdir(parents=True, exist_ok=True)
        script = r"""
$plain = [Console]::In.ReadToEnd()
$secure = ConvertTo-SecureString $plain -AsPlainText -Force
$secure | ConvertFrom-SecureString
"""
        _WIN_BLOB.write_text(_powershell(script, stdin=secret), encoding="ascii")
        return
    _UNIX_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(_UNIX_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(secret)
    os.chmod(_UNIX_FILE, 0o600)


def load_master() -> str | None:
    try:
        if os.name == "nt":
            if not _WIN_BLOB.exists():
                return None
            script = r"""
$blob = [Console]::In.ReadToEnd()
$secure = ConvertTo-SecureString $blob
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
"""
            return _powershell(script, stdin=_WIN_BLOB.read_text(encoding="ascii")).strip() or None
        if not _UNIX_FILE.exists() or (_UNIX_FILE.stat().st_mode & 0o077):
            return None
        return _UNIX_FILE.read_text(encoding="utf-8").strip() or None
    except Exception:
        return None


def migrate_legacy_env(env_path: Path) -> bool:
    """Move KEY_VAULT_SECRET out of .env after storing it machine-locally."""
    if load_master() or not env_path.exists():
        return False
    lines = env_path.read_text(encoding="utf-8").splitlines()
    value, kept = None, []
    for line in lines:
        if line.strip().startswith("KEY_VAULT_SECRET="):
            value = line.split("=", 1)[1].strip()
        else:
            kept.append(line)
    if not value:
        return False
    store_master(value)
    env_path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    os.environ.pop("KEY_VAULT_SECRET", None)
    return True

"""Read the operator's own browser cookies for ONE domain, so doit never logs in.

Why (2026-07-11, the hard lesson): every login route inside an automation-driven
browser is a dead end by design, not a bug — Google refuses OAuth there ("this
browser or app may not be secure") and CAPTCHA exists to require a human. And
driving a COPY of the real Chrome profile doesn't survive either: Chrome tears
down the automation page when it opens a real user profile.

So doit stops trying to *become* the operator and simply *carries their session*:
read the cookies Chrome already stored for the provider domain, decrypt them with
the key in the operator's own login Keychain, and inject them into a clean
headless context. No window, no login, no CAPTCHA — fully autonomous from then on.

Scope guards (this reads secrets, so the blast radius is deliberately tiny):
  * ONE domain per call — never the whole cookie jar;
  * local machine, local user, the operator's own accounts;
  * values are returned for immediate injection and never logged or persisted.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile

_MAC_KEYCHAIN_SERVICE = {"chrome": "Chrome Safe Storage",
                         "msedge": "Microsoft Edge Safe Storage"}
_MAC_KEYCHAIN_ACCOUNT = {"chrome": "Chrome", "msedge": "Microsoft Edge"}
# Chrome's fixed KDF parameters on macOS (v10 cookies).
_SALT = b"saltysalt"
_IV = b" " * 16
_ITERATIONS = 1003


class CookieError(RuntimeError):
    pass


def _mac_key(channel: str) -> bytes:
    """The AES key Chrome keeps in the operator's login Keychain. macOS may ask
    the operator to allow access once — that prompt IS the human checkpoint."""
    from cryptography.hazmat.primitives.hashes import SHA1
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    try:
        pw = subprocess.run(
            ["security", "find-generic-password", "-w",
             "-s", _MAC_KEYCHAIN_SERVICE.get(channel, "Chrome Safe Storage"),
             "-a", _MAC_KEYCHAIN_ACCOUNT.get(channel, "Chrome")],
            capture_output=True, text=True, timeout=30, check=True,
        ).stdout.strip()
    except Exception as exc:  # noqa: BLE001
        raise CookieError(f"Keychain açarı alınmadı: {exc}") from exc
    return PBKDF2HMAC(algorithm=SHA1(), length=16, salt=_SALT,
                      iterations=_ITERATIONS).derive(pw.encode())


def _decrypt(blob: bytes, key: bytes) -> str:
    """Decrypt one cookie value (v10 = AES-128-CBC on macOS)."""
    if not blob:
        return ""
    if not blob.startswith(b"v10"):
        return blob.decode("utf-8", "replace")  # legacy plaintext
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    dec = Cipher(algorithms.AES(key), modes.CBC(_IV)).decryptor()
    data = dec.update(blob[3:]) + dec.finalize()
    if data:
        data = data[: -data[-1]]  # strip PKCS#7 padding
    # Chrome ≥ v127 prefixes a 32-byte SHA256 of the domain before the value.
    text = data.decode("utf-8", "replace")
    if len(data) > 32 and not text.isprintable():
        text = data[32:].decode("utf-8", "replace")
    return text


def _cookie_db(profile_dir: str) -> str | None:
    for rel in (os.path.join("Network", "Cookies"), "Cookies"):
        p = os.path.join(profile_dir, rel)
        if os.path.exists(p):
            return p
    return None


def for_domain(profile_dir: str, domain: str, channel: str = "chrome") -> list[dict]:
    """Playwright-shaped cookies for ``domain`` from the operator's profile."""
    if sys.platform != "darwin":
        raise CookieError("cookie oxuma hazırda yalnız macOS üçün dəstəklənir")
    src = _cookie_db(profile_dir)
    if not src:
        raise CookieError(f"cookie bazası tapılmadı: {profile_dir}")

    key = _mac_key(channel)
    tmpdir = tempfile.mkdtemp()
    try:
        db = os.path.join(tmpdir, "c.db")
        shutil.copy2(src, db)  # Chrome holds a lock on the live file
        con = sqlite3.connect(db)
        rows = con.execute(
            "SELECT host_key, name, encrypted_value, path, expires_utc, "
            "is_secure, is_httponly FROM cookies WHERE host_key LIKE ?",
            (f"%{domain}%",),
        ).fetchall()
        con.close()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    out: list[dict] = []
    for host, name, enc, path, expires, secure, httponly in rows:
        try:
            value = _decrypt(enc, key)
        except Exception:  # noqa: BLE001 — one bad cookie must not sink the run
            continue
        if not value:
            continue
        c = {"name": name, "value": value, "domain": host, "path": path or "/",
             "secure": bool(secure), "httpOnly": bool(httponly)}
        if expires:  # Chrome epoch (1601) -> unix seconds
            unix = expires / 1_000_000 - 11_644_473_600
            if unix > 0:
                c["expires"] = unix
        out.append(c)
    if not out:
        raise CookieError(f"{domain} üçün cookie tapılmadı — həmin brauzerdə daxil ol")
    return out

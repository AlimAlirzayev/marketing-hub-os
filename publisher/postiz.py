"""Xalq Insurance Digital OS Publisher - Postiz public-API client.

Thin wrapper over Postiz's public API (the self-hosted, free publisher):
list channels, upload media, create/schedule a post. Built to the documented
shape at https://docs.postiz.com/public-api :

    base:   {POSTIZ_API_URL}/api/public/v1   (self-host)   override: POSTIZ_API_BASE
    auth:   Authorization: <api-key>
    GET  /integrations         list connected channels
    POST /upload               multipart 'file' -> {id, path}
    POST /posts                {type, date, posts:[{integration, value, settings}]}

The router only calls this when POSTIZ_API_KEY is set; if Postiz is unreachable
it raises PostizError and the router falls back to a manual handoff - never a
silent drop.
"""

from __future__ import annotations

import os
from pathlib import Path

import requests


class PostizError(RuntimeError):
    """Postiz is unconfigured or unreachable. Recoverable -> manual fallback."""


class Postiz:
    def __init__(self, *, timeout: int = 60) -> None:
        key = os.getenv("POSTIZ_API_KEY")
        if not key:
            raise PostizError("POSTIZ_API_KEY not set")
        base = os.getenv("POSTIZ_API_BASE")
        if not base:
            url = (os.getenv("POSTIZ_API_URL") or "http://localhost:5000").rstrip("/")
            base = f"{url}/api/public/v1"
        self.base = base.rstrip("/")
        self.timeout = timeout
        self._headers = {"Authorization": key}

    # -- low level -------------------------------------------------------- #

    def _get(self, path: str):
        try:
            r = requests.get(self.base + path, headers=self._headers, timeout=self.timeout)
        except requests.RequestException as e:
            raise PostizError(f"cannot reach Postiz at {self.base} ({e})") from e
        if r.status_code >= 400:
            raise PostizError(f"GET {path} -> {r.status_code}: {r.text[:300]}")
        return r.json()

    def _post(self, path: str, *, json=None, files=None, data=None):
        try:
            r = requests.post(self.base + path, headers=self._headers, json=json,
                              files=files, data=data, timeout=self.timeout)
        except requests.RequestException as e:
            raise PostizError(f"cannot reach Postiz at {self.base} ({e})") from e
        if r.status_code >= 400:
            raise PostizError(f"POST {path} -> {r.status_code}: {r.text[:300]}")
        return r.json() if r.content else {}

    # -- operations ------------------------------------------------------- #

    def list_integrations(self) -> list[dict]:
        """Connected channels. Normalised to {id, name, provider}."""
        raw = self._get("/integrations")
        items = raw if isinstance(raw, list) else raw.get("integrations", raw.get("data", []))
        out = []
        for it in items:
            provider = (it.get("identifier") or it.get("providerIdentifier")
                        or it.get("provider") or it.get("type") or "").lower()
            out.append({"id": it.get("id"), "name": it.get("name", ""), "provider": provider})
        return out

    def upload(self, media: Path) -> dict:
        """Upload a media file. Returns the Postiz media object ({id, path})."""
        with open(media, "rb") as fh:
            res = self._post("/upload", files={"file": (Path(media).name, fh)})
        if isinstance(res, list):
            res = res[0] if res else {}
        if "id" not in res:
            raise PostizError(f"upload returned no id: {str(res)[:200]}")
        return res

    def create_post(self, *, integration_id, content: str, media: dict | None,
                    provider: str, post_type: str, date_iso: str) -> dict:
        """Create or schedule one post on one channel."""
        value = {"content": content}
        if media:
            value["image"] = [{"id": media.get("id"), "path": media.get("path")}]
        body = {
            "type": post_type,
            "date": date_iso,
            "shortLink": False,
            "tags": [],
            "posts": [{
                "integration": {"id": integration_id},
                "value": [value],
                "settings": {"__type": provider},
            }],
        }
        return self._post("/posts", json=body)

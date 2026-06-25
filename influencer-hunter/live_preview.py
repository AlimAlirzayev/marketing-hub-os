"""Render a LIVE YouTube hunt result into the real frontend (for a screenshot).

Runs the full pipeline against the live YouTube Data API, bakes the real payload
into static/index.html, and writes data/reports/LIVE-youtube.html.
"""
from __future__ import annotations

import json
import os
import sys

import hunt as hunt_mod
import server

BASE = os.path.dirname(os.path.abspath(__file__))
QUERY = sys.argv[1] if len(sys.argv) > 1 else (
    "Xalq Sigorta üçün səyahət sığortası barədə emosional video canlandıracaq "
    "Azərbaycanlı travel/lifestyle YouTube creator lazımdır."
)

SEEDS = [s for s in (os.getenv("IH_PREVIEW_SEEDS", "").split(",")) if s.strip()]
res = hunt_mod._run_pipeline(QUERY, source="youtube", top_n=3, min_followers=10000, seed_handles=SEEDS or None)
payload = server._payload(res)

banner = ('<div style="background:#0f6e2e;color:#fff;text-align:center;padding:9px 14px;'
          'font:700 13px/1.4 -apple-system,Segoe UI,Arial;letter-spacing:.03em">'
          '✅ CANLI YouTube NƏTİCƏSİ — real data, pulsuz rəsmi API (YouTube Data API v3), ban riski yoxdur'
          '</div>')

html = open(os.path.join(BASE, "static", "index.html"), encoding="utf-8").read()
inject = ("<script>\n"
          f"const LIVE_PAYLOAD = {json.dumps(payload, ensure_ascii=False)};\n"
          "document.body.insertAdjacentHTML('afterbegin', " + json.dumps(banner) + ");\n"
          "window.fetch = async () => ({ json: async () => ({}) });\n"
          "document.getElementById('engtxt').textContent = 'CANLI YouTube Data API v3';\n"
          "document.getElementById('source').value='youtube';\n"
          "render(LIVE_PAYLOAD);\n</script>\n")
html = html.replace("health();\n</script>", "/* */\n</script>").replace("</body>", inject + "</body>")

out = os.path.join(BASE, "data", "reports", "LIVE-youtube.html")
open(out, "w", encoding="utf-8").write(html)
print("shortlist:", [(c["handle"], c.get("country"), c["scores"]["total"]) for c in payload["shortlist"]])
print("filtered:", [(c["handle"], c.get("country"), (c["flags"] or ["-"])[0]) for c in payload["filtered_out"][:8]])
print("written:", out)

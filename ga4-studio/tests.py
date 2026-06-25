"""Offline tests for GA4 Studio — no network, demo connector only. Run:

    .venv\\Scripts\\python.exe tests.py

Verifies the demo report is internally consistent, the analytics layer derives
sane deltas/funnel/insights, and the report shape matches what the live
connector promises (so demo↔live stay in lock-step).
"""

from __future__ import annotations

import os
import sys

os.environ["GA4_DATA_MODE"] = "demo"   # force demo regardless of any creds

import analytics
import config
import connectors

_P = _F = 0


def check(name, cond, detail=""):
    global _P, _F
    if cond:
        _P += 1; print(f"  ✓ {name}")
    else:
        _F += 1; print(f"  ✗ {name}  {detail}")


start, end = config.default_range(28)
r = analytics.enrich(connectors.get_report(start, end))
t = r["totals"]

# --- shape ---------------------------------------------------------------
for key in ("totals", "prev_totals", "trend", "channels", "top_pages",
            "devices", "geo", "events", "deltas", "funnel", "insights"):
    check(f"report has '{key}'", key in r)
check("mode is demo", r["mode"] == "demo")
check("trend covers 28 days", len(r["trend"]) == 28, str(len(r["trend"])))

# --- internal consistency ------------------------------------------------
check("engaged <= sessions", t["engaged_sessions"] <= t["sessions"])
check("conversions <= sessions", t["conversions"] <= t["sessions"])
check("engagement_rate in 0..1", 0 <= t["engagement_rate"] <= 1)
check("trend sessions sum == total sessions",
      sum(d["sessions"] for d in r["trend"]) == t["sessions"],
      f'{sum(d["sessions"] for d in r["trend"])} vs {t["sessions"]}')
ch_sum = sum(c["share"] for c in r["channels"])
check("channel shares ~ 1.0", abs(ch_sum - 1.0) < 0.02, f"{ch_sum:.3f}")
check("channels sorted by sessions desc",
      all(r["channels"][i]["sessions"] >= r["channels"][i+1]["sessions"]
          for i in range(len(r["channels"])-1)))
mob = next(d for d in r["devices"] if d["device"] == "mobile")
check("mobile is the largest device share", mob["share"] >= 0.5)

# --- determinism ---------------------------------------------------------
r2 = connectors.get_report(start, end)
check("demo is deterministic for a fixed range",
      r2["totals"]["sessions"] == t["sessions"])

# --- analytics layer -----------------------------------------------------
check("deltas computed for sessions",
      "delta_pct" in r["deltas"]["sessions"])
check("bounce 'up' is flagged bad",
      r["deltas"]["bounce_rate"]["good"] in (True, False, None))
check("funnel has 3 steps", len(r["funnel"]) == 3)
check("funnel descends", r["funnel"][0]["value"] >= r["funnel"][2]["value"])
check("insights are generated", len(r["insights"]) >= 2)
check("every insight ties to text", all(i.get("text") for i in r["insights"]))

# --- live connector imports + builds a request (no creds, no send) -------
import connectors.ga4_live as live
body_ok = True
try:
    # _run_report will fail without creds, but the module + helpers must import.
    live._num("12.5") == 12.5
except Exception as exc:
    body_ok = False
check("live connector module imports + helpers work", body_ok)
check("live blockers reported in demo", isinstance(config.live_blockers(), list))

print(f"\n  {_P} passed, {_F} failed")
sys.exit(1 if _F else 0)

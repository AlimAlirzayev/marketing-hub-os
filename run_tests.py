"""Ramin-OS — the one command that runs EVERY test suite in the repo.

Why this exists (2026-07-14): there was no way to answer "is the system green?".
A bare `pytest` at the root exploded with 27 collection errors, so the honest
answer was unknown — and "unknown" silently reads as "broken". The cause was
never a real bug: this repo holds eight different modules named `config.py` and a
`meta-capi/gateway.py` that shadows the root `gateway/` package. Put them in one
interpreter and they overwrite each other in sys.modules; the first one imported
wins and everything else fails on an attribute that was never missing.

The fix is not a refactor — the sub-projects are intentionally standalone tools,
each rooted in its own directory. The fix is process isolation: give every suite
its own interpreter, with the cwd and sys.path IT was written for. That is what
this runner does, and why it is the only command that can honestly report green.

    python run_tests.py           # everything, one summary
    python run_tests.py seo doit  # only the named suites
    python run_tests.py --quiet   # only failures + the summary line

Exit code 0 = every suite green. Non-zero = the number of failing suites.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 — a console that can't do UTF-8 is not fatal
        pass

ROOT = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable

# Each suite records the invocation it ACTUALLY needs — verified, not assumed.
#
#   cwd     : sys.path[0] under `python -m`, so it decides which module wins a
#             name collision. meta-capi MUST run from its own dir or the root
#             `gateway/` package shadows its `gateway.py`.
#   script  : run as a plain script instead of under pytest (meta-capi/test_capi.py
#             is a self-running harness that calls sys.exit() at module scope —
#             that hard-kills pytest collection with an INTERNALERROR).
#   pythonpath: only where the tests don't already bootstrap their own sys.path.
#             influencer-hunter / price-hunter / doit each do their own
#             sys.path.insert(), so they need nothing from us.
SUITES: list[dict] = [
    {"name": "tests", "target": "tests", "cwd": ROOT, "pythonpath": ROOT,
     "about": "nüvə: gateway, hub, brain, panel, security"},
    {"name": "seo", "target": "seo", "cwd": ROOT, "pythonpath": ROOT,
     "about": "SEO Engine (audit + research + content)"},
    {"name": "doit", "target": "doit", "cwd": ROOT, "pythonpath": ROOT,
     "about": "kredensial agenti"},
    {"name": "influencer-hunter", "target": "influencer-hunter", "cwd": ROOT,
     "about": "influencer uyğunluq motoru"},
    {"name": "price-hunter", "target": "price-hunter", "cwd": ROOT,
     "about": "AZ qiymət kəşfiyyatı"},
    {"name": "meta-capi", "script": "test_capi.py",
     "cwd": os.path.join(ROOT, "meta-capi"),
     "about": "Conversions API göndərici"},
]

# "403 passed, 1 skipped, 2 warnings in 17.97s"  /  "22 passed, 0 failed"
_COUNT = re.compile(r"(\d+)\s+(passed|failed|error|errors|skipped)")


def _tally(output: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for n, word in _COUNT.findall(output):
        key = "error" if word.startswith("error") else word
        counts[key] = counts.get(key, 0) + int(n)
    return counts


def _run(suite: dict, quiet: bool) -> dict:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    # A stale PYTHONPATH from the caller's shell is exactly the shadowing bug this
    # runner exists to prevent — so we set it explicitly, or clear it.
    if suite.get("pythonpath"):
        env["PYTHONPATH"] = suite["pythonpath"]
    else:
        env.pop("PYTHONPATH", None)

    if suite.get("script"):
        cmd = [PYTHON, suite["script"]]
    else:
        cmd = [PYTHON, "-m", "pytest", suite["target"], "-q",
               "--import-mode=importlib", "-p", "no:cacheprovider"]

    started = time.time()
    proc = subprocess.run(cmd, cwd=suite["cwd"], env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    output = (proc.stdout or "") + (proc.stderr or "")
    result = {
        "name": suite["name"], "about": suite["about"], "rc": proc.returncode,
        "ok": proc.returncode == 0, "seconds": time.time() - started,
        "output": output, **_tally(output),
    }

    mark = "✓" if result["ok"] else "✗"
    bits = [f"{result.get(k, 0)} {label}"
            for k, label in (("passed", "keçdi"), ("failed", "uğursuz"),
                             ("error", "xəta"), ("skipped", "ötürüldü"))
            if result.get(k)]
    if not quiet or not result["ok"]:
        print(f"  {mark} {result['name']:<18} {', '.join(bits) or 'nəticə oxunmadı':<34} "
              f"{result['seconds']:5.1f}s  · {result['about']}")
    if not result["ok"]:
        print("    " + "-" * 62)
        for line in output.strip().splitlines()[-15:]:
            print(f"    | {line}")
        print("    " + "-" * 62)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Bütün test dəstlərini qaçır (hər biri öz prosesində).")
    ap.add_argument("suites", nargs="*", help="yalnız adı çəkilənlər (boş = hamısı)")
    ap.add_argument("--quiet", action="store_true", help="yalnız uğursuzları göstər")
    args = ap.parse_args()

    chosen = SUITES
    if args.suites:
        want = {s.strip().lower() for s in args.suites}
        chosen = [s for s in SUITES if s["name"].lower() in want]
        unknown = want - {s["name"].lower() for s in SUITES}
        if unknown:
            print(f"Tanınmayan dəst: {', '.join(sorted(unknown))}", file=sys.stderr)
            print(f"Mövcud: {', '.join(s['name'] for s in SUITES)}", file=sys.stderr)
            return 2

    print("=" * 78)
    print("  Ramin-OS · tam test auditi  (hər dəst ayrı prosesdə — ad toqquşmasına qarşı)")
    print("=" * 78)

    started = time.time()
    results = [_run(s, args.quiet) for s in chosen]
    failed = [r for r in results if not r["ok"]]
    total_passed = sum(r.get("passed", 0) for r in results)
    total_failed = sum(r.get("failed", 0) + r.get("error", 0) for r in results)
    total_skipped = sum(r.get("skipped", 0) for r in results)

    print("=" * 78)
    line = f"  {len(results) - len(failed)}/{len(results)} dəst yaşıl  ·  {total_passed} test keçdi"
    if total_failed:
        line += f"  ·  {total_failed} uğursuz"
    if total_skipped:
        line += f"  ·  {total_skipped} ötürüldü"
    print(f"{line}  ·  {time.time() - started:.1f}s")
    if failed:
        print(f"  ✗ UĞURSUZ: {', '.join(r['name'] for r in failed)}")
    else:
        print("  ✓ Bütün dəstlər yaşıldır.")
    print("=" * 78)
    return len(failed)


if __name__ == "__main__":
    sys.exit(main())

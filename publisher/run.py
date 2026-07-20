"""Xalq Insurance Digital OS Publisher - CLI entry point.

    python publisher/run.py <asset|slug> --to tiktok,x [--when now|ISO]
                            [--caption "text"] [--stagger 30] [--dry-run]

Assembles the per-platform publish package and routes it through the cascade
(Postiz → manual). `--dry-run` contacts no network and just writes the package.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow `python publisher/run.py` to import the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from publisher import manual, privacy_guard, router  # noqa: E402
from publisher.package import PackageError, build_plan  # noqa: E402


def _load_env() -> None:
    env = Path(__file__).resolve().parent.parent / ".env"
    if not env.exists():
        return
    import os
    for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    if not argv or argv[0] in ("-h", "--help"):
        print("usage: python publisher/run.py <asset|slug> --to tiktok,x "
              "[--when now|ISO] [--caption \"text\"] [--stagger 30] [--dry-run]")
        return 2

    _load_env()
    asset = argv[0]
    opts = argv[1:]

    def _opt(name, default=None):
        return opts[opts.index(name) + 1] if name in opts else default

    platforms = [p.strip() for p in (_opt("--to", "") or "").split(",") if p.strip()]
    if not platforms:
        print("publisher: --to is required (e.g. --to tiktok,x,instagram)")
        return 2

    try:
        plan = build_plan(
            asset, platforms,
            when=_opt("--when", "now"),
            caption_override=_opt("--caption"),
            stagger_min=int(_opt("--stagger", "0")),
        )
    except PackageError as e:
        print(f"publisher: {e}")
        return 1

    # Privacy guard: a publish that may show a minor or an identifiable real
    # person is HELD until the human passes --privacy-ack. Fail-safe by design.
    ack = "--privacy-ack" in opts or os.getenv("PUBLISH_PRIVACY_ACK") == "1"
    allowed, scan, checklist = privacy_guard.enforce(
        plan, ack=ack, dry_run="--dry-run" in opts)
    if scan["flagged"]:
        privacy_guard.report(plan, scan, checklist, allowed)
    if not allowed:
        return 3

    result = router.publish(plan, dry_run="--dry-run" in opts)
    _report(plan, result)
    return 0


def _report(plan: dict, result: dict) -> None:
    icon = {"posted": "✅", "scheduled": "⏰", "planned": "📝", "manual": "✋"}
    print(f"\nPublish · {plan['slug']} · via {result['provider']} · "
          f"{plan['type']} · media={'yes' if plan['media'] else 'none'}\n")
    for r in result["results"]:
        print(f"  {icon.get(r['state'], '•')} {r['platform']:<10} {r['state']:<10} {r['detail']}")
    if result.get("manual_dir"):
        print(f"\n  paste-ready blocks: {result['manual_dir']}")
    print()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

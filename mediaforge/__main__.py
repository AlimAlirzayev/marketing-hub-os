"""Media Studio CLI.

    python -m mediaforge "mənə seedance 2.5 ilə 10 saniyəlik səyahət sığortası promo videosu hazırla"
    python -m mediaforge --no-llm "..."      # deterministic only (offline)
    python -m mediaforge --json "..."         # machine-readable package
"""

from __future__ import annotations

import argparse
import json
import sys

from . import pipeline, resources, ugc


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to cp1252 and choke on emoji/AZ letters.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass

    parser = argparse.ArgumentParser(
        prog="mediaforge",
        description="Media Studio: one sentence -> a directed, production-ready media package.",
    )
    parser.add_argument("sentence", nargs="*", help="Natural-language request (AZ or EN).")
    parser.add_argument("--no-llm", action="store_true", help="Deterministic brain only (no LLM call).")
    parser.add_argument("--json", action="store_true", help="Print the full package as JSON.")
    parser.add_argument(
        "--ugc",
        action="store_true",
        help="Build a Doruk-style AI UGC campaign pack (persona, script, voice, prompts, economics).",
    )
    parser.add_argument(
        "--resources",
        action="store_true",
        help="Show safe local readiness for real Doruk-style video generation.",
    )
    args = parser.parse_args(argv)

    if args.resources and not args.sentence:
        status = resources.build_status()
        if args.json:
            print(json.dumps(status, ensure_ascii=False, indent=2))
        else:
            print(resources.render_status_report(status))
        return 0

    if not args.sentence:
        parser.error("sentence is required unless --resources is used")

    sentence = " ".join(args.sentence)
    pkg = ugc.create(sentence, use_llm=not args.no_llm) if args.ugc else pipeline.create(
        sentence, use_llm=not args.no_llm
    )

    if args.json:
        print(json.dumps(pkg, ensure_ascii=False, indent=2))
        return 0

    c, r, g = pkg["concept"], pkg["resolution"], pkg["generation"]
    print("=" * 70)
    print(f"🎬  {c.get('name', '')}")
    print("=" * 70)
    print(f"Sorğu     : {sentence}")
    print(f"Böyük ideya: {c.get('big_idea', '')}")
    print(f"Emosional qövs: {c.get('emotional_arc', '')}")
    print(f"Framework : {c.get('framework', '')}")
    print()
    print(f"Model     : {r['label']} ({r['model_id']}) · {r['duration_s']}s · {r['tier']} · xərc: {r['cost_band']}")
    print(f"2-ci variant: {r['partner_label']} ({r['partner_id']})")
    for note in r.get("notes", []):
        print(f"  ⚠ {note}")
    print()
    print("Storyboard:")
    for b in pkg["brief"]["storyboard"]:
        print(f"  [{b['time']}] {b['beat']}")
        print(f"      görüntü: {b['visual']}")
        print(f"      hərəkət: {b['motion']}")
        if b["overlay"]:
            print(f"      overlay: {b['overlay']}")
    print()
    print(f"Mühərrik  : {pkg['meta']['engine']}"
          + (f" ({pkg['meta']['llm_model']})" if pkg['meta'].get('llm_model') else ""))
    print(f"Paket     : {pkg['artifacts']['folder']}")
    print(f"Board (SVG): {pkg['artifacts']['board_svg']}")
    if args.ugc and pkg.get("ugc_pack"):
        up = pkg["ugc_pack"]
        print(f"UGC pack  : {up['folder']}")
        print(f"Persona   : {up['persona']['name']}")
        print(f"Variable cost floor: ~{up['economics']['one_round_video_credit_floor']} FLORA kredit")
        print(f"Resources : {up['resources']['status']}")
    print()
    print("İşə salmağa hazır (cost gate — kredit avtomatik xərclənmir):")
    print(f"  plan (xərcsiz): {g.get('plan_command','')}")
    print(f"  real generasiya: {g.get('fire_command','')}   (~{g.get('credits','?')} kredit)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""MediaForge CLI.

    python -m mediaforge "mənə seedance 2.5 ilə 10 saniyəlik səyahət sığortası promo videosu hazırla"
    python -m mediaforge --no-llm "..."      # deterministic only (offline)
    python -m mediaforge --json "..."         # machine-readable package
"""

from __future__ import annotations

import argparse
import json
import sys

from . import pipeline


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to cp1252 and choke on emoji/AZ letters.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass

    parser = argparse.ArgumentParser(
        prog="mediaforge",
        description="One sentence -> a directed, production-ready promo video package.",
    )
    parser.add_argument("sentence", nargs="+", help="Natural-language request (AZ or EN).")
    parser.add_argument("--no-llm", action="store_true", help="Deterministic brain only (no LLM call).")
    parser.add_argument("--json", action="store_true", help="Print the full package as JSON.")
    args = parser.parse_args(argv)

    sentence = " ".join(args.sentence)
    pkg = pipeline.create(sentence, use_llm=not args.no_llm)

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
    print()
    print("İşə salmağa hazır (cost gate — kredit avtomatik xərclənmir):")
    print(f"  → {g['mcp_instruction']}")
    print(f"  qapı: {g['gate_reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

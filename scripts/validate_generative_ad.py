from __future__ import annotations

import argparse
import json
from pathlib import Path

from jsonschema import Draft7Validator


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a generative ad brief against the local schema.")
    parser.add_argument("brief", type=Path)
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path("video-studio/generative_ads/brief.schema.json"),
    )
    args = parser.parse_args()

    brief = json.loads(args.brief.read_text(encoding="utf-8"))
    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    validator = Draft7Validator(schema)
    errors = sorted(validator.iter_errors(brief), key=lambda error: list(error.path))

    if errors:
        for error in errors:
            path = ".".join(str(part) for part in error.path) or "<root>"
            print(f"{path}: {error.message}")
        raise SystemExit(1)

    print(f"valid: {args.brief}")


if __name__ == "__main__":
    main()

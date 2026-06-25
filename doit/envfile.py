"""Pure .env upsert — create / update / append one key, preserving everything else.

No third-party dotenv writer: comments, ordering and unrelated keys must survive
untouched, so this does a careful line-wise rewrite that is trivial to unit-test.
"""

from __future__ import annotations

import os


def upsert(path: str, key: str, value: str) -> str:
    """Set ``key=value`` in the env file. Returns 'created' | 'updated' | 'appended'."""
    line = f"{key}={value}"
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(line + "\n")
        return "created"

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    out: list[str] = []
    replaced = False
    for raw in content.splitlines():
        stripped = raw.lstrip()
        if stripped and not stripped.startswith("#") and "=" in raw:
            existing_key = raw.split("=", 1)[0].strip()
            if existing_key == key:
                out.append(line)
                replaced = True
                continue
        out.append(raw)
    if not replaced:
        out.append(line)

    new_content = "\n".join(out)
    if content.endswith("\n"):
        new_content += "\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)
    return "updated" if replaced else "appended"

"""The knowledge store: human-readable markdown is the source of truth.

Every piece of institutional knowledge (a decision we made, a lesson we learned,
a reusable playbook) is one markdown file under ``data/memory/`` with a small
frontmatter header. Plain files mean nothing is ever locked inside a binary blob:
they are git-trackable, greppable, and editable by hand. Embeddings (see
``brain.embeddings``) are only an accelerator layered on top -- never the truth.

This module deliberately has **zero third-party dependencies** (no PyYAML), so it
works on the locked-down corporate machine and inside the gateway worker without
pulling anything heavy.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import re
from pathlib import Path
from typing import Iterable

# data/memory/ is the home the README already reserves for "memory".
STORE_DIR = Path(__file__).resolve().parent.parent / "data" / "memory"
PENDING_DIR = STORE_DIR / "_pending"
INDEX_FILE = STORE_DIR / "INDEX.md"

# The kinds of knowledge the system accumulates. Kept small on purpose.
TYPES = ("decision", "lesson", "playbook", "pattern", "glossary", "preference")
CONFIDENCE = ("high", "medium", "low")

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


def _today() -> str:
    return _dt.date.today().isoformat()


def slugify(text: str, maxlen: int = 60) -> str:
    """A filesystem-safe, stable id derived from a title."""
    s = _SLUG_RE.sub("-", text.lower()).strip("-")
    return (s[:maxlen].strip("-")) or "entry"


@dataclasses.dataclass
class Entry:
    """One unit of knowledge. Maps 1:1 to a markdown file."""

    id: str
    type: str
    title: str
    body: str
    tags: list[str] = dataclasses.field(default_factory=list)
    source: str = "manual"
    confidence: str = "medium"
    created: str = dataclasses.field(default_factory=_today)
    updated: str = dataclasses.field(default_factory=_today)
    related: list[str] = dataclasses.field(default_factory=list)

    # ---- serialization -------------------------------------------------

    def to_markdown(self) -> str:
        tags = ", ".join(self.tags)
        related = ", ".join(self.related)
        lines = [
            "---",
            f"id: {self.id}",
            f"type: {self.type}",
            f"title: {self.title}",
            f"tags: [{tags}]",
            f"source: {self.source}",
            f"confidence: {self.confidence}",
            f"created: {self.created}",
            f"updated: {self.updated}",
            f"related: [{related}]",
            "---",
            "",
            self.body.strip(),
            "",
        ]
        return "\n".join(lines)

    @property
    def text(self) -> str:
        """Full searchable text (title weighted by repetition upstream)."""
        return f"{self.title}\n{', '.join(self.tags)}\n{self.body}"

    @classmethod
    def from_markdown(cls, text: str, fallback_id: str) -> "Entry":
        m = _FRONTMATTER_RE.match(text.lstrip("﻿"))
        if not m:
            # No frontmatter -> treat the whole file as a freeform lesson body.
            return cls(id=fallback_id, type="lesson", title=fallback_id, body=text.strip())
        meta = _parse_frontmatter(m.group(1))
        body = m.group(2).strip()
        return cls(
            id=meta.get("id", fallback_id),
            type=meta.get("type", "lesson"),
            title=meta.get("title", fallback_id),
            body=body,
            tags=_parse_list(meta.get("tags", "")),
            source=meta.get("source", "manual"),
            confidence=meta.get("confidence", "medium"),
            created=meta.get("created", _today()),
            updated=meta.get("updated", _today()),
            related=_parse_list(meta.get("related", "")),
        )


def _parse_frontmatter(block: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, val = line.partition(":")
        out[key.strip()] = val.strip()
    return out


def _parse_list(val: str) -> list[str]:
    val = val.strip()
    if val.startswith("[") and val.endswith("]"):
        val = val[1:-1]
    return [p.strip() for p in val.split(",") if p.strip()]


# ---- store operations --------------------------------------------------


def _ensure_dirs() -> None:
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    PENDING_DIR.mkdir(parents=True, exist_ok=True)


def _path_for(entry_id: str) -> Path:
    return STORE_DIR / f"{entry_id}.md"


def all_entries() -> list[Entry]:
    """Load every committed entry (ignores _pending and INDEX)."""
    if not STORE_DIR.exists():
        return []
    entries: list[Entry] = []
    for path in sorted(STORE_DIR.glob("*.md")):
        if path.name == INDEX_FILE.name:
            continue
        try:
            entries.append(Entry.from_markdown(path.read_text(encoding="utf-8"), path.stem))
        except Exception:
            # A single malformed file must never break recall for the rest.
            continue
    return entries


def get(entry_id: str) -> Entry | None:
    path = _path_for(entry_id)
    if not path.exists():
        return None
    return Entry.from_markdown(path.read_text(encoding="utf-8"), entry_id)


def save(entry: Entry, *, rebuild_index: bool = True) -> Path:
    """Create or update an entry. Returns the file path."""
    _ensure_dirs()
    entry.updated = _today()
    path = _path_for(entry.id)
    path.write_text(entry.to_markdown(), encoding="utf-8")
    if rebuild_index:
        rebuild_index_file()
    return path


def remember(
    title: str,
    body: str,
    *,
    type: str = "lesson",
    tags: Iterable[str] | None = None,
    source: str = "manual",
    confidence: str = "medium",
    entry_id: str | None = None,
    related: Iterable[str] | None = None,
) -> Entry:
    """Add (or overwrite by id) a knowledge entry. The everyday capture path."""
    if type not in TYPES:
        type = "lesson"
    if confidence not in CONFIDENCE:
        confidence = "medium"
    eid = entry_id or slugify(f"{type}-{title}")
    existing = get(eid)
    created = existing.created if existing else _today()
    entry = Entry(
        id=eid,
        type=type,
        title=title.strip(),
        body=body.strip(),
        tags=sorted({t.strip().lower() for t in (tags or []) if t.strip()}),
        source=source,
        confidence=confidence,
        created=created,
        related=list(related or []),
    )
    save(entry)
    return entry


def delete(entry_id: str) -> bool:
    path = _path_for(entry_id)
    if path.exists():
        path.unlink()
        rebuild_index_file()
        return True
    return False


# ---- pending (auto-reflected suggestions awaiting human approval) ------


def add_pending(entry: Entry) -> Path:
    """Write a *suggested* entry to the review queue, never to the live store.

    Auto-reflection must not pollute the trusted knowledge base. A human (or an
    explicit ``brain review approve``) promotes a suggestion into a real entry.
    """
    _ensure_dirs()
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = PENDING_DIR / f"{stamp}-{entry.id}.md"
    path.write_text(entry.to_markdown(), encoding="utf-8")
    return path


def list_pending() -> list[tuple[Path, Entry]]:
    if not PENDING_DIR.exists():
        return []
    out: list[tuple[Path, Entry]] = []
    for path in sorted(PENDING_DIR.glob("*.md")):
        try:
            out.append((path, Entry.from_markdown(path.read_text(encoding="utf-8"), path.stem)))
        except Exception:
            continue
    return out


def approve_pending(path: Path) -> Entry:
    entry = Entry.from_markdown(Path(path).read_text(encoding="utf-8"), Path(path).stem)
    entry.source = entry.source or "reflect"
    save(entry)
    Path(path).unlink(missing_ok=True)
    return entry


def reject_pending(path: Path) -> None:
    Path(path).unlink(missing_ok=True)


# ---- index -------------------------------------------------------------


def rebuild_index_file() -> Path:
    """Regenerate the human-readable INDEX.md (one line per entry, by type)."""
    _ensure_dirs()
    entries = all_entries()
    by_type: dict[str, list[Entry]] = {}
    for e in entries:
        by_type.setdefault(e.type, []).append(e)

    lines = [
        "# RAMIN OS — Knowledge Core index",
        "",
        f"_{len(entries)} entries · auto-generated by `brain` · do not edit by hand._",
        "",
    ]
    for t in TYPES:
        bucket = by_type.get(t, [])
        if not bucket:
            continue
        lines.append(f"## {t} ({len(bucket)})")
        lines.append("")
        for e in sorted(bucket, key=lambda x: x.updated, reverse=True):
            tags = f" · _{', '.join(e.tags)}_" if e.tags else ""
            lines.append(f"- [{e.title}]({e.id}.md) — {e.confidence}{tags}")
        lines.append("")
    INDEX_FILE.write_text("\n".join(lines), encoding="utf-8")
    return INDEX_FILE


def stats() -> dict:
    entries = all_entries()
    by_type: dict[str, int] = {}
    for e in entries:
        by_type[e.type] = by_type.get(e.type, 0) + 1
    return {
        "total": len(entries),
        "by_type": by_type,
        "pending": len(list_pending()),
        "store_dir": str(STORE_DIR),
    }

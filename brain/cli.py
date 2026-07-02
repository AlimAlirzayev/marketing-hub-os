"""Command line for the Knowledge Core.

    python -m brain remember "title" --type lesson --tags a,b --body "..."
    python -m brain recall "how do we build report PDFs"
    python -m brain list [--type lesson]
    python -m brain show <id>
    python -m brain reflect --task "..." --result-file output/jobs/job-12.md
    python -m brain review                 # show the pending queue
    python -m brain review approve <n|file>
    python -m brain review reject  <n|file>
    python -m brain stats
    python -m brain reindex
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import capture, embeddings, retrieval, store


def _read_body(args) -> str:
    if getattr(args, "body", None):
        return args.body
    if getattr(args, "body_file", None):
        return Path(args.body_file).read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        data = sys.stdin.read().strip()
        if data:
            return data
    return ""


def _cmd_remember(args) -> int:
    body = _read_body(args)
    if not body:
        print("error: provide a body via --body, --body-file, or stdin", file=sys.stderr)
        return 2
    tags = [t for t in (args.tags or "").split(",") if t.strip()]
    entry = store.remember(
        args.title,
        body,
        type=args.type,
        tags=tags,
        source=args.source,
        confidence=args.confidence,
        entry_id=args.id,
    )
    print(f"saved: {entry.id} ({entry.type}) -> {store._path_for(entry.id)}")
    return 0


def _cmd_recall(args) -> int:
    if args.block:
        block = retrieval.recall_block(args.query, k=args.k)
        print(block or "(no relevant knowledge)")
        return 0
    hits = retrieval.recall(args.query, k=args.k)
    if not hits:
        print("(no relevant knowledge)")
        return 0
    for h in hits:
        e = h.entry
        print(f"[{h.score:.2f}] ({e.type}) {e.title}  #{e.id}")
        print(f"        {e.body.strip().splitlines()[0][:120]}")
    return 0


def _cmd_list(args) -> int:
    entries = store.all_entries()
    if args.type:
        entries = [e for e in entries if e.type == args.type]
    entries.sort(key=lambda e: e.updated, reverse=True)
    if not entries:
        print("(empty)")
        return 0
    for e in entries:
        tags = f"  #{', '.join(e.tags)}" if e.tags else ""
        print(f"{e.updated}  ({e.type:9}) {e.title}{tags}   [{e.id}]")
    return 0


def _cmd_show(args) -> int:
    entry = store.get(args.id)
    if not entry:
        print(f"not found: {args.id}", file=sys.stderr)
        return 1
    print(entry.to_markdown())
    return 0


def _cmd_reflect(args) -> int:
    result = ""
    task = args.task or ""
    if args.job is not None:
        artifact = store.STORE_DIR.parent.parent / "output" / "jobs" / f"job-{args.job}.md"
        if artifact.exists():
            result = artifact.read_text(encoding="utf-8")
        else:
            print(f"artifact not found: {artifact}", file=sys.stderr)
            return 1
        if not task:
            task = _task_from_queue(args.job) or f"(job {args.job})"
    elif args.result_file:
        result = Path(args.result_file).read_text(encoding="utf-8")
    elif args.result:
        result = args.result
    if not result:
        print("error: provide --result, --result-file, or --job", file=sys.stderr)
        return 2

    entries = capture.reflect(task, result, commit=args.commit)
    if not entries:
        print("reflect: nothing worth remembering (or LLM unavailable).")
        return 0
    where = "committed" if args.commit else "queued for review"
    print(f"reflect: {len(entries)} lesson(s) {where}:")
    for e in entries:
        print(f"  - ({e.type}) {e.title}")
    return 0


def _task_from_queue(job_id: int) -> str | None:
    """Best-effort: pull the original task text from the gateway queue DB."""
    try:
        import sqlite3

        db = store.STORE_DIR.parent / "jobs.sqlite"
        if not db.exists():
            return None
        con = sqlite3.connect(str(db))
        row = con.execute("SELECT task FROM jobs WHERE id = ?", (job_id,)).fetchone()
        con.close()
        return row[0] if row else None
    except Exception:
        return None


def _cmd_review(args) -> int:
    pending = store.list_pending()
    if args.action == "list" or args.action is None:
        if not pending:
            print("(no pending suggestions)")
            return 0
        for i, (path, e) in enumerate(pending, 1):
            print(f"{i}. ({e.type}) {e.title}  [{e.confidence}]  <{path.name}>")
            print(f"     {e.body.strip().splitlines()[0][:120]}")
        print("\napprove/reject with: python -m brain review approve <n>")
        return 0

    target = _resolve_pending(pending, args.ref)
    if target is None:
        print(f"no pending item matches {args.ref!r}", file=sys.stderr)
        return 1
    path, entry = target
    if args.action == "approve":
        e = store.approve_pending(path)
        print(f"approved -> {e.id}")
    else:
        store.reject_pending(path)
        print(f"rejected -> {path.name}")
    return 0


def _resolve_pending(pending, ref: str):
    if ref is None:
        return None
    if ref.isdigit():
        idx = int(ref) - 1
        return pending[idx] if 0 <= idx < len(pending) else None
    for path, e in pending:
        if ref in path.name or ref == e.id:
            return (path, e)
    return None


def _cmd_stats(args) -> int:
    s = store.stats()
    print(f"entries: {s['total']}   pending: {s['pending']}")
    for t, n in sorted(s["by_type"].items()):
        print(f"  {t:10} {n}")
    print(f"store: {s['store_dir']}")
    return 0


def _cmd_reindex(args) -> int:
    path = store.rebuild_index_file()
    print(f"index rebuilt -> {path}")
    return 0


def _cmd_embeddings(args) -> int:
    info = embeddings.provider_info()
    print("Brain embeddings:")
    for key in ("enabled", "provider", "model", "endpoint", "endpoint_private", "external_allowed", "cache_file"):
        print(f"  {key}: {info.get(key)}")
    print("No network call was made.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="brain", description="RAMIN OS Knowledge Core")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("remember", help="add a knowledge entry")
    r.add_argument("title")
    r.add_argument("--body")
    r.add_argument("--body-file")
    r.add_argument("--type", default="lesson", choices=store.TYPES)
    r.add_argument("--tags", default="")
    r.add_argument("--source", default="manual")
    r.add_argument("--confidence", default="medium", choices=store.CONFIDENCE)
    r.add_argument("--id", default=None)
    r.set_defaults(func=_cmd_remember)

    rc = sub.add_parser("recall", help="find relevant knowledge")
    rc.add_argument("query")
    rc.add_argument("-k", type=int, default=5)
    rc.add_argument("--block", action="store_true", help="print the prompt-injection block")
    rc.set_defaults(func=_cmd_recall)

    ls = sub.add_parser("list", help="list entries")
    ls.add_argument("--type", default=None, choices=store.TYPES)
    ls.set_defaults(func=_cmd_list)

    sh = sub.add_parser("show", help="print one entry")
    sh.add_argument("id")
    sh.set_defaults(func=_cmd_show)

    rf = sub.add_parser("reflect", help="distill a job into lessons")
    rf.add_argument("--task", default="")
    rf.add_argument("--result")
    rf.add_argument("--result-file")
    rf.add_argument("--job", type=int, default=None, help="read output/jobs/job-<id>.md")
    rf.add_argument("--commit", action="store_true", help="save directly instead of queueing")
    rf.set_defaults(func=_cmd_reflect)

    rv = sub.add_parser("review", help="review pending suggestions")
    rv.add_argument("action", nargs="?", choices=["list", "approve", "reject"], default="list")
    rv.add_argument("ref", nargs="?", default=None, help="index number or filename/id")
    rv.set_defaults(func=_cmd_review)

    sub.add_parser("stats", help="store statistics").set_defaults(func=_cmd_stats)
    sub.add_parser("reindex", help="rebuild INDEX.md").set_defaults(func=_cmd_reindex)
    sub.add_parser("embeddings", help="show embedding provider status without network calls").set_defaults(func=_cmd_embeddings)
    return p


def main(argv: list[str] | None = None) -> int:
    # The corporate console defaults to cp1252, which can't encode Azerbaijani
    # characters (ə, ö, ...). Force UTF-8 so CLI output never crashes on them.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

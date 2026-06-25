"""CLI front-end: throw a task at the background worker, or inspect jobs.

This works today with zero external setup -- no Telegram token needed -- so you
can prove background execution immediately.

    python -m gateway.submit "research 3 fresh marketing trends for car insurance"
    python -m gateway.submit --list
    python -m gateway.submit --status 4
"""

from __future__ import annotations

import sys

from ._bootstrap import load_env
from . import queue

load_env()


def _print_job(job: queue.Job) -> None:
    print(f"#{job.id} [{job.status}] ({job.source}) {job.task[:70]}")
    if job.status == "done" and job.result:
        print("-" * 60)
        print(job.result)
        if job.artifacts:
            print("\nartifacts:", ", ".join(job.artifacts))
    elif job.status == "error" and job.error:
        print("-" * 60)
        print(job.error.splitlines()[0])


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return

    if args[0] == "--list":
        for job in queue.list_jobs():
            print(f"#{job.id} [{job.status}] {job.task[:70]}")
        return

    if args[0] == "--status":
        if len(args) < 2 or not args[1].isdigit():
            print("usage: --status <job_id>")
            return
        job = queue.get(int(args[1]))
        if job is None:
            print("no such job")
        else:
            _print_job(job)
        return

    task = " ".join(args)
    job_id = queue.submit(task, source="cli")
    print(f"queued job #{job_id}. Run the worker to execute it:")
    print("    python -m gateway.worker")
    print(f"Then check: python -m gateway.submit --status {job_id}")


if __name__ == "__main__":
    main()

"""Workspace agent — the executor's real hands: sandboxed shell + file IO.

This is what makes a Telegram task equal to a keyboard task for CREATE/BUILD
work: the background agent can author files, scaffold and build a whole site,
run python/node, generate media — anything reversible — freely, but confined to
a per-job workspace so it can NEVER touch the live engine, .env, secrets, or
infrastructure.

Two enforcement layers (belt AND suspenders):

  1. bubblewrap sandbox (hard, kernel-level): the whole filesystem is mounted
     READ-ONLY; only the job workspace and /tmp are writable; .env, secrets/,
     the key vault, ~/.ssh and every /opt/*/.env are MASKED (unreadable). So
     even a command the classifier misses physically cannot modify the engine
     or read a secret. If bwrap is unavailable the agent runs in a strict
     refuse-by-default mode instead.

  2. intent classifier (soft, explains itself): every command is tiered
       SAFE      -> runs, sandboxed.
       RISKY     -> outward/irreversible (push, deploy, publish, external POST).
                    Refused UNLESS the owner already /approved THIS job.
       PROTECTED -> infra/secret surgery (systemctl, docker, package installs,
                    firewall, git remote/config, secret paths). HARD-blocked
                    always — even an approved job. That surgery stays keyboard-
                    only (the architect does it, from here, with a human).

Kill switch:  touch <repo>/workspace/KILL   (or WORKSPACE_AGENT_DISABLED=1)
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import queue, sense

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = REPO_ROOT / "workspace"
_KILL = WORKSPACE_ROOT / "KILL"

_CMD_TIMEOUT = int(os.getenv("WORKSPACE_CMD_TIMEOUT", "300"))
_OUT_LIMIT = 8000          # chars of stdout/stderr returned to the model
_CMD_CAP = int(os.getenv("WORKSPACE_CMD_CAP", "80"))  # commands per job, anti-runaway
_HAVE_BWRAP = shutil.which("bwrap") is not None

# Secrets/infra masked inside the sandbox so even a read cannot exfiltrate them.
_MASK_FILES = [REPO_ROOT / ".env"] + list(Path("/opt").glob("*/.env"))
_MASK_DIRS = [
    REPO_ROOT / "secrets",
    REPO_ROOT / "data" / "private_context",
    Path("/root/.ssh"),
    Path.home() / ".ssh",
]

# --- command intent tiers ---------------------------------------------------

# PROTECTED: never runs, not even for an approved job. Infra/secret/self surgery
# a 24/7 daemon must not do unsupervised — that is the architect's job from the
# keyboard. (bwrap already neuters most of these; this is the readable refusal.)
_PROTECTED = re.compile(
    r"""(?xi)
    \bsudo\b | \bsu\s | \bsystemctl\b | \bservice\s+\S+\s+(start|stop|restart) |
    \bdocker\b | \bpodman\b | \bnerdctl\b |
    \breboot\b | \bshutdown\b | \bhalt\b | \bpoweroff\b |
    \bmkfs | \bdd\s+if= | \bfdisk\b | \bmount\b | \bumount\b |
    \bchown\b | \bchmod\s+-?R?\s*0?777 | \bpasswd\b | \buseradd\b | \buserdel\b |
    \bvisudo\b | \bcrontab\b | \bat\s+now | \bufw\b | \biptables\b | \bnft\b |
    \bapt(-get)?\b | \byum\b | \bdnf\b | \bpacman\b | \bapk\b | \bbrew\b |
    \bpip3?\s+install\b.*-g | \bnpm\s+(i|install)\b[^\n]*\s-g\b | \bnpm\s+publish\b |
    \bgit\s+remote\s+set-url\b | \bgit\s+config\b |
    \.env\b | (^|[\s/])secrets/ | keys\.vault | \.ssh/ | id_(ed25519|rsa) |
    KEY_VAULT | TELEGRAM_BOT_TOKEN | (^|\s)/etc/ |
    \bkillall\b | \bpkill\b | \b:\(\)\s*\{ |            # fork bomb
    curl[^\n|]*\|\s*(sudo\s+)?(ba)?sh | wget[^\n|]*\|\s*(sudo\s+)?(ba)?sh
    """
)

# RISKY: outward / irreversible. Blocked unless THIS job was owner-approved.
_RISKY = re.compile(
    r"""(?xi)
    \bgit\s+push\b | \brsync\b | \bscp\b | \bsftp\b | \bpm2\b |
    \bdeploy\b | \bpublish\b | \bnetlify\b | \bvercel\b | \bgh\s+release\b |
    \bsendmail\b | \bmutt\b | \b(mail|mailx)\s | \bftp\b |
    curl\b[^\n]*(-X\s*(POST|PUT|DELETE|PATCH)|--data|\s-d\s|--upload-file|-T\s) |
    wget\b[^\n]*(--post-data|--post-file|--method=(POST|PUT|DELETE))
    """
)


@dataclass
class _Ctx:
    job_id: int = 0
    workspace: Path = WORKSPACE_ROOT
    chat_id: str | None = None
    approved: bool = False
    count: int = 0
    deliverables: list[str] = field(default_factory=list)


_CTX = _Ctx()


def configure(job_id: int, workspace: str | Path, chat_id: str | None, approved: bool) -> Path:
    """Point the tools at this job's sandbox. Called by the executor per job."""
    ws = Path(workspace).resolve()
    ws.mkdir(parents=True, exist_ok=True)
    globals()["_CTX"] = _Ctx(job_id=job_id, workspace=ws, chat_id=chat_id, approved=bool(approved))
    return ws


def _killed() -> bool:
    return _KILL.exists() or os.getenv("WORKSPACE_AGENT_DISABLED", "").lower() in {"1", "true", "yes"}


def _inside_workspace(path: Path) -> bool:
    try:
        path.resolve().relative_to(_CTX.workspace)
        return True
    except ValueError:
        return False


def _classify(command: str) -> str:
    if _PROTECTED.search(command):
        return "protected"
    if _RISKY.search(command):
        return "risky"
    return "safe"


def _bwrap_argv(command: str) -> list[str]:
    argv = ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
            "--tmpfs", "/tmp"]
    for f in _MASK_FILES:
        if f.exists():
            argv += ["--ro-bind", "/dev/null", str(f)]
    for d in _MASK_DIRS:
        if d.exists():
            argv += ["--tmpfs", str(d)]
    argv += ["--bind", str(_CTX.workspace), str(_CTX.workspace),
             "--chdir", str(_CTX.workspace),
             "--unshare-pid", "--die-with-parent",
             "/bin/bash", "-c", command]
    return argv


def _clip(text: str) -> str:
    text = text or ""
    return text if len(text) <= _OUT_LIMIT else text[:_OUT_LIMIT] + f"\n…[{len(text) - _OUT_LIMIT} chars truncated]"


def run_command(command: str) -> str:
    """Run a shell command inside THIS job's sandboxed workspace.

    Use this to build things: create project files, scaffold a site, run a build
    (npm/vite/python), run tests, generate output. The command runs with the
    workspace as its working directory; the rest of the filesystem is read-only,
    so you cannot modify the engine, .env or secrets. Reversible/build work runs
    freely. Outward or irreversible actions (git push, deploy, publish, sending
    to the internet) are refused here — for those call request_owner_approval.

    Args:
        command: the bash command line to execute in the workspace.
    """
    if _killed():
        return "BLOCKED: workspace agent is disabled (kill switch active)."
    _CTX.count += 1
    if _CTX.count > _CMD_CAP:
        return f"BLOCKED: command cap ({_CMD_CAP}) reached for this job — stop and summarize."

    tier = _classify(command)
    sense.emit("shell", f"[{tier}] {command[:160]}", {"job": _CTX.job_id, "approved": _CTX.approved})

    if tier == "protected":
        return ("BLOCKED (protected): this touches infrastructure or secrets "
                "(systemd/docker/packages/firewall/.env/keys/ssh/git-remote). A "
                "background agent may never do this. If it is truly needed, tell "
                "the owner to do it from the keyboard with the architect.")
    if tier == "risky" and not _CTX.approved:
        return ("NOT RUN (needs approval): this is an outward/irreversible action "
                "(push/deploy/publish/send). Do NOT retry. Finish the reversible "
                "work first, then call request_owner_approval('<describe the exact "
                "action>') so the owner can /approve it.")

    if not _HAVE_BWRAP:
        return ("BLOCKED: the hard sandbox (bubblewrap) is unavailable, so shell "
                "execution is disabled for safety. Use write_file/read_file for "
                "file work, or ask the owner to run the command.")

    try:
        proc = subprocess.run(
            _bwrap_argv(command),
            capture_output=True, text=True, timeout=_CMD_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return f"TIMEOUT after {_CMD_TIMEOUT}s — command killed. Break the work into smaller steps."
    except Exception as exc:  # never crash the agent loop
        return f"run_command error: {exc.__class__.__name__}: {exc}"

    out = _clip((proc.stdout or "") + (("\n[stderr]\n" + proc.stderr) if proc.stderr else ""))
    status = "ok" if proc.returncode == 0 else f"exit {proc.returncode}"
    return f"[{status}] {out or '(no output)'}"


def write_file(path: str, content: str) -> str:
    """Create or overwrite a file INSIDE the job workspace.

    Prefer this over shell redirection for writing source files (HTML, CSS, JS,
    Python, Markdown, JSON) — it avoids quoting problems. The path is relative to
    the workspace; writing outside the workspace is refused.

    Args:
        path: workspace-relative file path, e.g. 'site/index.html'.
        content: the full file contents to write.
    """
    if _killed():
        return "BLOCKED: workspace agent is disabled (kill switch active)."
    target = (_CTX.workspace / path).resolve()
    if not _inside_workspace(target):
        return f"BLOCKED: '{path}' is outside the workspace. Write only inside the workspace."
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    except Exception as exc:
        return f"write_file error: {exc.__class__.__name__}: {exc}"
    rel = target.relative_to(_CTX.workspace)
    if str(rel) not in _CTX.deliverables:
        _CTX.deliverables.append(str(rel))
    sense.emit("file", f"wrote {rel} ({len(content)}b)", {"job": _CTX.job_id})
    return f"wrote {rel} ({len(content)} bytes)"


def read_file(path: str) -> str:
    """Read a text file from the workspace or the (read-only) engine repo.

    Secret/private files (.env, secrets/, keys, ssh, private_context) are refused.

    Args:
        path: workspace-relative path, or a repo path to consult existing code.
    """
    p = Path(path)
    candidate = p if p.is_absolute() else (_CTX.workspace / p)
    candidate = candidate.resolve()
    low = str(candidate).lower()
    if any(s in low for s in (".env", "/secrets/", "keys.vault", "/.ssh/", "id_ed25519",
                              "id_rsa", "private_context", "key_vault")):
        return "BLOCKED: that file is secret/private and cannot be read."
    if not (_inside_workspace(candidate) or _inside_workspace(candidate.parent)
            or str(candidate).startswith(str(REPO_ROOT))):
        return "BLOCKED: read only inside the workspace or the engine repo."
    try:
        return _clip(candidate.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        return f"read_file error: {exc.__class__.__name__}: {exc}"


def request_owner_approval(action: str) -> str:
    """Park an outward/irreversible action for the owner's explicit approval.

    Call this when the finished work must be shipped outward — deploy a site,
    publish an article, post to social, push to git. It creates a parked job the
    owner approves with /approve; only then does that action run (with full
    rights on this same workspace).

    Args:
        action: a precise description of the exact action to perform on approval,
                including the workspace path and the concrete command(s).
    """
    task = f"[approved-action] {action}\n\n(workspace: {_CTX.workspace})"
    try:
        jid = queue.submit(task, source="agent-approval", chat_id=_CTX.chat_id)
        queue.park_for_approval(jid, "agent-requested outward action")
    except Exception as exc:
        return f"request_owner_approval error: {exc.__class__.__name__}: {exc}"
    sense.emit("approval", f"agent requested approval job #{jid}", {"action": action[:160]})
    return (f"Parked as job #{jid} for the owner. In your final answer tell the owner: "
            f"“/approve {jid}” to run it, “/reject {jid}” to cancel.")


# Defensive PEP563: real annotations so google-genai automatic function-calling
# can introspect these even under `from __future__ import annotations`.
run_command.__annotations__ = {"command": str, "return": str}
write_file.__annotations__ = {"path": str, "content": str, "return": str}
read_file.__annotations__ = {"path": str, "return": str}
request_owner_approval.__annotations__ = {"action": str, "return": str}

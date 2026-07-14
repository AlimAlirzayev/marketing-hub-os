"""Subscriber-CLI based multi-model council for Agent Terminal tasks.

The council avoids API keys by default. It calls the local CLIs that are already
authenticated on this Windows profile:
- Codex via ``codex exec``.
- Claude Code via ``claude --print``.
- Gemini via the local Gemini CLI OAuth profile.

Each model gives an independent note. A CLI model then synthesizes those notes,
and the normal executor performs the final task. Every child process has a hard
timeout and is killed as a process tree on Windows, so the dashboard does not
hang when one provider hits a quota, session limit, or auth prompt.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ._bootstrap import load_env
from . import knowledge

load_env()

ROOT_DIR = Path(__file__).resolve().parent.parent
RUNTIME_DIR = Path(
    os.getenv("AI_COUNCIL_RUNTIME_DIR")
    or Path(tempfile.gettempdir()) / "xidigitalos-council-runtime"
)
DEFAULT_TIMEOUT = int(os.getenv("AI_COUNCIL_TIMEOUT_SECONDS", "60"))
GEMINI_TIMEOUT = int(os.getenv("AI_COUNCIL_GEMINI_TIMEOUT_SECONDS", "45"))
# OpenCode runs a free model with full repo access; its first run downloads
# ripgrep and indexes the tree, so it gets a longer leash than the CLI members.
OPENCODE_TIMEOUT = int(os.getenv("AI_COUNCIL_OPENCODE_TIMEOUT_SECONDS", "120"))
MAX_NOTE_CHARS = int(os.getenv("AI_COUNCIL_MAX_NOTE_CHARS", "6000"))


@dataclass
class CouncilNote:
    name: str
    status: str
    text: str
    seconds: float
    auth: str = "subscriber-cli"


def _clip(text: str, limit: int = MAX_NOTE_CHARS) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n\n[trimmed]"


def _clean_output(name: str, text: str) -> str:
    text = (text or "").strip()
    if not text or "gemini" not in name.lower():
        return text

    lines = text.splitlines()
    noise_prefixes = (
        "Warning:",
        "Ripgrep is not available",
        "Attempt ",
        "Error when talking",
        "An unexpected critical error",
    )
    for idx, line in enumerate(lines):
        if idx > 0 and line.startswith(noise_prefixes):
            return "\n".join(lines[:idx]).strip()
    return text


def _council_prompt(member: str, task: str) -> str:
    return f"""
You are {member}, a specialist member of the Xalq Insurance Digital OS AI Council.

Workspace path:
{ROOT_DIR}

User task:
{task}

Give an independent, high-signal answer for the other agents. Focus on:
- what the user is really asking for
- the best execution plan
- risks, missing context, and assumptions
- concrete implementation steps

Do not edit files or execute changes in this consultation round. Answer in the
same language as the user when practical.
""".strip()


def _gemini_prompt(task: str) -> str:
    return f"""
You are Gemini CLI in the Xalq Insurance Digital OS AI Council.
Use Google Code Assist / OAuth CLI reasoning. Do not edit files.

Workspace:
{ROOT_DIR}

Task:
{task}

Return a concise Azerbaijani council note with:
- intent
- best plan
- risks
- next action
""".strip()


def _synthesis_prompt(task: str, notes: list[CouncilNote]) -> str:
    blocks = []
    for note in notes:
        blocks.append(
            f"### {note.name} [{note.status}, {note.auth}, {note.seconds:.1f}s]\n{note.text}"
        )
    return f"""
You are the chair of the Xalq Insurance Digital OS AI Council.

User task:
{task}

Council notes:
{chr(10).join(blocks)}

Synthesize the strongest answer. Return:
1. A short decision.
2. The best execution plan.
3. Any risk or assumption.
4. The exact next action the executor should perform.

Hard rules:
- Ground every claim in the council notes or in files actually present in the
  workspace. Never invent metrics, statistics, customer feedback, or events.
- If the notes are empty, off-topic, or only status messages (timeouts, smoke
  tests), say so explicitly and answer from verifiable workspace facts only.
- For reports: real data comes from running collectors (for example
  scripts/daily_briefing.py), not from imagination. If a data source is
  unavailable, state the gap instead of filling it.

Answer in Azerbaijani unless the task is clearly in another language.
""".strip()


def _base_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("TERM", "xterm-256color")
    env.setdefault("NO_COLOR", "1")

    # Force subscriber/CLI auth for council members. The gateway can still use
    # API keys elsewhere, but the council itself should not silently switch to
    # API billing or API quotas.
    for key in (
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "CODEX_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GOOGLE_GENAI_USE_VERTEXAI",
    ):
        env.pop(key, None)

    return env


def _run_cli(
    name: str,
    args: list[str],
    timeout: int,
    *,
    input_text: str | None = None,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    output_file: Path | None = None,
) -> CouncilNote:
    started = time.perf_counter()
    proc: subprocess.Popen[str] | None = None
    try:
        proc = subprocess.Popen(
            args,
            cwd=str(cwd or ROOT_DIR),
            stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env or _base_env(),
        )
        stdout, stderr = proc.communicate(input=input_text, timeout=timeout)
        elapsed = time.perf_counter() - started

        output = ""
        if output_file and output_file.exists():
            output = output_file.read_text(encoding="utf-8", errors="replace").strip()
        if not output:
            output = (stdout or "").strip()
        output = _clean_output(name, output)

        if proc.returncode == 0 and output:
            return CouncilNote(name=name, status="ok", text=_clip(output), seconds=elapsed)

        detail = f"exit_code={proc.returncode}\n{(stderr or stdout or '').strip()}"
        return CouncilNote(
            name=name,
            status="unavailable",
            text=_clip(detail, 5000),
            seconds=elapsed,
        )
    except subprocess.TimeoutExpired:
        if proc is not None:
            _kill_tree(proc.pid)
        elapsed = time.perf_counter() - started
        return CouncilNote(
            name=name,
            status="timeout",
            text=f"{name} did not finish within {timeout} seconds.",
            seconds=elapsed,
        )
    except Exception as exc:
        if proc is not None and proc.poll() is None:
            _kill_tree(proc.pid)
        elapsed = time.perf_counter() - started
        return CouncilNote(name=name, status="error", text=str(exc), seconds=elapsed)


def _kill_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            timeout=10, encoding="utf-8", errors="replace")
        return
    try:
        os.kill(pid, 9)
    except OSError:
        pass


def _codex_exe() -> str | None:
    return shutil.which("codex")


def _claude_exe() -> str | None:
    return shutil.which("claude")


def _gemini_exe() -> str | None:
    configured = os.getenv("GEMINI_CLI_PATH")
    if configured and Path(configured).exists():
        return configured
    found = shutil.which("gemini")
    if found:
        return found
    local = ROOT_DIR / "video-studio" / "tools" / "node-v24.15.0-win-x64" / "gemini.cmd"
    return str(local) if local.exists() else None


def _opencode_exe() -> str | None:
    found = shutil.which("opencode")
    if found:
        return found
    local = ROOT_DIR / "video-studio" / "tools" / "node-v24.15.0-win-x64" / "opencode.cmd"
    return str(local) if local.exists() else None


def _new_runtime_file(name: str) -> Path:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    return RUNTIME_DIR / f"{name}-{uuid.uuid4().hex}.md"


def _ask_codex(task: str) -> CouncilNote:
    exe = _codex_exe()
    if not exe:
        return CouncilNote("Codex", "unavailable", "codex CLI is not installed or not in PATH.", 0.0)

    prompt = _council_prompt(
        "Codex (software engineering, repo analysis, implementation discipline)",
        task,
    )
    output_file = _new_runtime_file("codex")
    args = [
        exe,
        "exec",
        "-C",
        str(ROOT_DIR),
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
        "--ephemeral",
        "--output-last-message",
        str(output_file),
        "-",
    ]
    return _run_cli("Codex", args, DEFAULT_TIMEOUT, input_text=prompt, output_file=output_file)


def _ask_claude(task: str) -> CouncilNote:
    exe = _claude_exe()
    if not exe:
        return CouncilNote("Claude Code", "unavailable", "claude CLI is not installed or not in PATH.", 0.0)

    prompt = _council_prompt(
        "Claude Code (deep reasoning, architecture, edge cases, review)",
        task,
    )
    args = [
        exe,
        "--print",
        "--model",
        os.getenv("CLAUDE_COUNCIL_MODEL", "sonnet"),
        "--permission-mode",
        "default",
        "--output-format",
        "text",
        prompt,
    ]
    return _run_cli("Claude Code", args, DEFAULT_TIMEOUT)


def _ask_gemini(task: str) -> CouncilNote:
    exe = _gemini_exe()
    if not exe:
        return CouncilNote("Gemini CLI", "unavailable", "gemini CLI is not installed or not configured.", 0.0)

    prompt = _gemini_prompt(task)
    env = _base_env()
    env["GEMINI_DEFAULT_AUTH_TYPE"] = "oauth-personal"
    env["GEMINI_CLI_TRUST_WORKSPACE"] = "true"
    env["GOOGLE_GENAI_USE_GCA"] = "true"

    # Run outside the project tree so Gemini CLI cannot auto-load this repo's
    # .env file and accidentally switch back to API-key auth.
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    args = [
        exe,
        "-p",
        prompt,
        "--approval-mode",
        "plan",
        "--output-format",
        "text",
        "--skip-trust",
        "-m",
        os.getenv("GEMINI_COUNCIL_CLI_MODEL", "gemini-2.5-flash-lite"),
    ]
    note = _run_cli("Gemini CLI", args, GEMINI_TIMEOUT, cwd=RUNTIME_DIR, env=env)
    note.auth = "google-oauth-cli"
    return note


def _ask_opencode(task: str) -> CouncilNote:
    exe = _opencode_exe()
    if not exe:
        return CouncilNote(
            "OpenCode",
            "unavailable",
            "opencode CLI is not installed (portable Node or PATH).",
            0.0,
        )

    # OpenCode injects its own agent identity + AGENTS.md, so the persona wrapper
    # the CLI members use double-frames it and the model just acknowledges ("ready
    # for instructions") instead of answering. Lead with the task, then a short
    # format tail. Verified: this makes it read repo files and answer directly.
    prompt = (
        f"{task}\n\n---\n"
        "Reply as a brief engineering council note: intent, best plan, risks, and "
        "the concrete next action. Read workspace files as needed. Do not edit "
        "files or run changes; answer in the user's language when practical."
    )

    env = _base_env()
    # OpenCode is a Node shim: the portable Node must be on PATH to launch it.
    node_dir = ROOT_DIR / "video-studio" / "tools" / "node-v24.15.0-win-x64"
    if node_dir.exists():
        env["Path"] = f"{node_dir};{env.get('Path', '')}"
    # _base_env() strips GEMINI_API_KEY as a paid-API guard. OpenCode's Google
    # provider reads GOOGLE_GENERATIVE_AI_API_KEY and the *free* Gemini quota, so
    # re-supply that one key, mapped to the var OpenCode expects.
    free_key = os.environ.get("GEMINI_API_KEY")
    if free_key:
        env["GOOGLE_GENERATIVE_AI_API_KEY"] = free_key

    model = os.getenv("OPENCODE_COUNCIL_MODEL", "google/gemini-2.5-flash")
    args = [
        exe,
        "run",
        "--agent",
        "plan",  # read-only agent: no file edits during a consult round
        "-m",
        model,
        prompt,
    ]
    note = _run_cli("OpenCode", args, OPENCODE_TIMEOUT, cwd=ROOT_DIR, env=env)
    note.auth = "gemini-api-free"
    return note


def _opencode_in_council() -> bool:
    """OpenCode joins the advice panel only when it adds a model the panel lacks.

    A council's value is *diverse* models catching different things. The only free
    model OpenCode can reliably run is Gemini (Groq's 12k TPM is too small for its
    ~42k context), and the panel already has a Gemini voice — a second one is
    redundant (correlated opinions, extra latency), not diversity. So OpenCode
    joins ONLY when configured with a non-Gemini free model (e.g. deepseek/qwen via
    OpenRouter). Force on/off with AI_COUNCIL_OPENCODE=1/0. OpenCode's primary role
    stays the free *executor* (see docs/ORCHESTRATION.md), not a 4th opinion.
    """
    force = os.getenv("AI_COUNCIL_OPENCODE", "").strip().lower()
    if force in {"1", "true", "yes", "on"}:
        return True
    if force in {"0", "false", "no", "off"}:
        return False
    model = os.getenv("OPENCODE_COUNCIL_MODEL", "google/gemini-2.5-flash").lower()
    return "gemini" not in model and "google/" not in model


def consult(task: str) -> list[CouncilNote]:
    """Collect independent advice from available subscriber-CLI council members."""
    workers = [_ask_codex, _ask_claude, _ask_gemini]
    if _opencode_in_council():
        workers.append(_ask_opencode)
    notes: list[CouncilNote] = []
    with ThreadPoolExecutor(max_workers=len(workers)) as pool:
        futures = [pool.submit(worker, task) for worker in workers]
        for future in as_completed(futures):
            notes.append(future.result())
    return sorted(notes, key=lambda n: n.name)


def _synthesize_with_cli(task: str, notes: list[CouncilNote]) -> CouncilNote:
    prompt = _synthesis_prompt(task, notes)

    # Prefer Codex for the chair because it is the strongest executor in this
    # workspace. Then try Claude, then Gemini. No API fallback here.
    if _codex_exe():
        output_file = _new_runtime_file("codex-synthesis")
        note = _run_cli(
            "Codex Synthesis",
            [
                _codex_exe() or "codex",
                "exec",
                "-C",
                str(ROOT_DIR),
                "--sandbox",
                "read-only",
                "--skip-git-repo-check",
                "--ephemeral",
                "--output-last-message",
                str(output_file),
                "-",
            ],
            DEFAULT_TIMEOUT,
            input_text=prompt,
            output_file=output_file,
        )
        if note.status == "ok":
            return note

    if _claude_exe():
        note = _run_cli(
            "Claude Synthesis",
            [
                _claude_exe() or "claude",
                "--print",
                "--model",
                os.getenv("CLAUDE_COUNCIL_MODEL", "sonnet"),
                "--permission-mode",
                "default",
                "--output-format",
                "text",
                prompt,
            ],
            DEFAULT_TIMEOUT,
        )
        if note.status == "ok":
            return note

    if _gemini_exe():
        env = _base_env()
        env["GEMINI_DEFAULT_AUTH_TYPE"] = "oauth-personal"
        env["GEMINI_CLI_TRUST_WORKSPACE"] = "true"
        env["GOOGLE_GENAI_USE_GCA"] = "true"
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        note = _run_cli(
            "Gemini Synthesis",
            [
                _gemini_exe() or "gemini",
                "-p",
                prompt,
                "--approval-mode",
                "plan",
                "--output-format",
                "text",
                "--skip-trust",
                "-m",
                os.getenv("GEMINI_COUNCIL_CLI_MODEL", "gemini-2.5-flash-lite"),
            ],
            DEFAULT_TIMEOUT,
            cwd=RUNTIME_DIR,
            env=env,
        )
        note.auth = "google-oauth-cli"
        if note.status == "ok":
            return note

    ok_notes = [n for n in notes if n.status == "ok"]
    if ok_notes:
        return CouncilNote("Deterministic Synthesis", "ok", ok_notes[0].text, 0.0)
    return CouncilNote(
        "Deterministic Synthesis",
        "unavailable",
        "Council members were unavailable; continuing with the direct executor.",
        0.0,
        auth="local-fallback",
    )


def execute_with_codex(task: str) -> tuple[str, str]:
    """Execute the final task through the authenticated Codex CLI."""
    exe = _codex_exe()
    if not exe:
        return "codex-cli:unavailable", "Codex CLI is not installed or not in PATH."

    output_file = _new_runtime_file("codex-execution")
    ctx = knowledge.recall_context(task)
    knowledge_block = f"\n\n{ctx}" if ctx else ""
    prompt = f"""
You are the execution agent for Xalq Insurance Digital OS.

Workspace:
{ROOT_DIR}

User task:
{task}{knowledge_block}

Execute the task end-to-end when it is safe and possible inside this workspace.
If the task only needs an answer, answer directly. If you edit files, keep the
change focused and explain what changed. Do not wait for confirmation.
""".strip()

    note = _run_cli(
        "Codex Execution",
        [
            exe,
            "exec",
            "-C",
            str(ROOT_DIR),
            "--sandbox",
            os.getenv("AI_COUNCIL_CODEX_EXECUTION_SANDBOX", "workspace-write"),
            "--skip-git-repo-check",
            "--ephemeral",
            "--output-last-message",
            str(output_file),
            "-",
        ],
        int(os.getenv("AI_COUNCIL_EXECUTION_TIMEOUT_SECONDS", "180")),
        input_text=prompt,
        output_file=output_file,
    )
    return f"codex-cli:{note.status}", note.text


def run(
    task: str,
    direct_runner: Callable[[str], tuple[str, str]],
) -> tuple[str, str]:
    """Run the council and then execute the task with the normal gateway."""
    notes = consult(task)
    synthesis = _synthesize_with_cli(task, notes)

    execute_enabled = os.getenv("AI_COUNCIL_AUTO_EXECUTE", "1").lower() not in {"0", "false", "no"}
    exec_label = "not-executed"
    execution = "Auto-icra sondurulub: AI_COUNCIL_AUTO_EXECUTE=0."
    if execute_enabled:
        exec_label, execution = direct_runner(task)

    available = ", ".join(f"{n.name}:{n.status}" for n in notes)
    text = f"""## AI Council neticesi

**Istirakcilar:** {available}

**Sintez:** {synthesis.name}:{synthesis.status} ({synthesis.auth})

### Birge qerar ve plan
{synthesis.text}

### Icra neticesi
_[{exec_label}]_

{execution}
"""
    return "ai-council-subscriber-cli", text.strip()

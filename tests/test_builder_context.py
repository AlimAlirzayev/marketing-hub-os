"""Tests for the cross-builder cold-start context bridge."""

import json
from pathlib import Path

from scripts import builder_context


ROOT = Path(__file__).resolve().parents[1]


def test_render_context_prioritizes_live_truth_and_shared_decisions():
    text = builder_context.render_context(
        claude_memory="- old Claude hint",
        codex_memory="- old Codex hint",
        decisions=[{"ts": "2026-07-24", "kind": "decision", "summary": "one system"}],
        state="HUB: healthy",
        claude_path=Path("claude-memory.md"),
        codex_path=Path("codex-memory.md"),
    )
    assert "## Authority Order" in text
    assert "Live repository code" in text
    assert "one system" in text
    assert "HUB: healthy" in text
    assert "potentially stale hints" in text


def test_redaction_covers_assignments_and_common_secret_shapes():
    source = (
        "API_KEY=super-secret-value "
        "access_token: abcdefghijklmnopqrstuvwxyz "
        "sk-abcdefghijklmnopqrstu "
        "ghp_abcdefghijklmnopqrstuvwxyz123456"
    )
    clean = builder_context._redact(source)
    assert "super-secret-value" not in clean
    assert "abcdefghijklmnopqrstuvwxyz" not in clean
    assert "sk-abcdefghijklmnopqrstu" not in clean
    assert "ghp_abcdefghijklmnopqrstuvwxyz123456" not in clean


def test_memory_discovery_prefers_current_project(monkeypatch, tmp_path):
    project = tmp_path / ".claude" / "projects" / "c--Users-a-ramin-os" / "memory"
    project.mkdir(parents=True)
    expected = project / "MEMORY.md"
    expected.write_text("- shared", encoding="utf-8")
    monkeypatch.setattr(builder_context.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(builder_context, "ROOT", Path("C:/Users/a/ramin-os"))
    assert builder_context.find_claude_memory() == expected


def test_every_builder_entrypoint_loads_the_bridge():
    entrypoints = (
        "AGENTS.md",
        "CLAUDE.md",
        "GEMINI.md",
        ".github/copilot-instructions.md",
        "claude-agents/CLAUDE.md",
    )
    for relative in entrypoints:
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "builder_context.py" in text, relative

    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    commands = [
        hook["command"]
        for group in settings["hooks"]["SessionStart"]
        for hook in group["hooks"]
    ]
    assert "python scripts/builder_context.py --print" in commands


def test_bridge_is_governed_and_visible_from_the_hub_registry():
    services = json.loads((ROOT / "services.json").read_text(encoding="utf-8"))
    capability = next(c for c in services["capabilities"] if c["key"] == "builder-context")
    assert capability["invoke"] == "python scripts/builder_context.py --print"
    assert capability["docs"] == "docs/BUILDER_CONTEXT.md"

    permissions = json.loads(
        (ROOT / "config" / "agent_permissions.json").read_text(encoding="utf-8")
    )
    agent = next(a for a in permissions["agents"] if a["id"] == "builder_context_bridge")
    assert "raw agent transcripts" in agent["blocked_inputs"]
    assert "edit or merge agent-owned memory stores" in agent["blocked_actions"]

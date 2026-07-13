"""Guard tests for the Meta WRITE layer — it drives a live ad account with real spend.

The test that matters: an unapproved write must never reach the network. Everything
here runs offline (the Graph read/POST are stubbed) so the suite never touches the
real Xalq Sigorta account.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ADS_DIR = ROOT / "ads-studio"
if str(ADS_DIR) not in sys.path:
    sys.path.insert(0, str(ADS_DIR))

from connectors import meta_write  # noqa: E402

NODE = "120229356028220100"


@pytest.fixture
def offline(monkeypatch):
    """Stub the Graph reads/writes; record whether a POST ever fired."""
    posted: list[dict] = []
    monkeypatch.setattr(meta_write, "_read_node", lambda node_id, fields: {
        "id": node_id, "name": "Awareness", "status": "ACTIVE",
        "effective_status": "ACTIVE", "daily_budget": "1400",
    })
    monkeypatch.setattr(meta_write, "_post",
                        lambda node_id, payload: posted.append({"node": node_id, **payload}) or {"success": True})
    return posted


# ---------- the money guard ----------
def test_unapproved_write_is_blocked_and_never_reaches_the_network(offline):
    plan = meta_write.propose("pause", NODE)
    with pytest.raises(meta_write.WriteBlocked):
        meta_write.execute(plan)                    # no approved=True
    assert offline == [], "an unapproved write reached the Graph API"


def test_approved_write_applies_exactly_the_proposed_change(offline):
    plan = meta_write.propose("pause", NODE)
    result = meta_write.execute(plan, approved=True)
    assert result["applied"] is True
    assert offline == [{"node": NODE, "status": "PAUSED"}]


# ---------- only reversible operations exist ----------
@pytest.mark.parametrize("op", ["create", "delete", "duplicate", "spend"])
def test_irreversible_operations_do_not_exist(offline, op):
    with pytest.raises(ValueError):
        meta_write.propose(op, NODE)


def test_unknown_level_is_rejected(offline):
    with pytest.raises(ValueError):
        meta_write.propose("pause", NODE, level="account")


# ---------- budget bounds: a hallucinated number must not become a real spend ----------
@pytest.mark.parametrize("bad", [0, 99, 100_001, 999_999])
def test_budget_outside_safety_bounds_is_refused(offline, bad):
    with pytest.raises(ValueError):
        meta_write.propose("set_daily_budget", NODE, daily_budget=bad)
    assert offline == []


def test_budget_within_bounds_builds_a_plan_showing_the_before_and_after(offline):
    plan = meta_write.propose("set_daily_budget", NODE, daily_budget=2000)
    assert plan["change"] == {"daily_budget": 2000}
    assert plan["current_daily_budget"] == "1400"
    assert plan["requires_approval"] is True
    assert "1400" in plan["human"] and "2000" in plan["human"]


def test_set_daily_budget_requires_a_budget(offline):
    with pytest.raises(ValueError):
        meta_write.propose("set_daily_budget", NODE)


# ---------- the proposal is human-readable (it is what the owner approves) ----------
def test_proposal_reads_current_state_so_the_human_sees_what_changes(offline):
    plan = meta_write.propose("pause", NODE)
    assert plan["current_status"] == "ACTIVE"
    assert plan["name"] == "Awareness"
    assert "PAUSE" in plan["human"] and "Awareness" in plan["human"]

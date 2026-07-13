"""Guard tests for the plain-language Meta ads lane.

The point of the lane is that Alim can say "Awareness kampaniyasını dayandır" and it
works. The point of these tests is that saying it is still NOT enough to touch a live
ad account — the plan must be shown and approved first, and the approved plan must be
the one that runs.
"""
from __future__ import annotations

import types

import pytest

from gateway import ads_agent


class FakeJob:
    def __init__(self, task: str, job_id: int = 7, approved: int = 0) -> None:
        self.id = job_id
        self.task = task
        self.approved = approved


CAMPAIGNS = [
    {"id": "111", "name": "Awareness", "effective_status": "ACTIVE", "daily_budget": None},
    {"id": "222", "name": "KASKO Bayram", "effective_status": "PAUSED", "daily_budget": "1400"},
    {"id": "333", "name": "KASKO Yay", "effective_status": "PAUSED", "daily_budget": "1000"},
]


@pytest.fixture
def meta(monkeypatch):
    """Stub the ad account. Records any write that reaches meta_write.execute()."""
    executed: list[dict] = []

    def propose(op, node_id, daily_budget=None):
        c = next(c for c in CAMPAIGNS if c["id"] == node_id)
        plan = {"op": op, "level": "campaign", "node_id": node_id, "name": c["name"],
                "current_status": c["effective_status"],
                "current_daily_budget": c["daily_budget"], "requires_approval": True}
        if op == "set_daily_budget":
            if daily_budget is None or not (100 <= daily_budget <= 100_000):
                raise ValueError("daily_budget outside the safety bounds")
            plan["change"] = {"daily_budget": daily_budget}
        else:
            plan["change"] = {"status": "PAUSED" if op == "pause" else "ACTIVE"}
        return plan

    def execute(plan, *, approved=False):
        if not approved:
            raise AssertionError("execute() called without approval")
        executed.append(plan)
        return {"applied": True}

    fake = types.SimpleNamespace(
        list_campaigns=lambda limit=100: CAMPAIGNS,
        propose=propose, execute=execute,
    )
    monkeypatch.setattr(ads_agent, "_meta", lambda: fake)
    monkeypatch.setattr(ads_agent, "_account_summary",
                        lambda: {"name": "Test acct", "currency": "USD", "amount_spent": "2301243"})
    return executed


def _intent(monkeypatch, **data):
    monkeypatch.setattr(ads_agent, "_intent", lambda task: data)


# ---------- the gate: normal chat must never be hijacked ----------
@pytest.mark.parametrize("task", [
    "Awareness kampaniyasını dayandır",
    "kampaniyaları göstər",
    "KASKO kampaniyasının büdcəsini 20 et",
    "reklam hesabında nə var",
])
def test_ads_sentences_enter_the_lane(task):
    assert ads_agent.wants_ads(task) is True


@pytest.mark.parametrize("task", [
    "salam, necəsən",
    "instagram üçün reklam mətni yaz",          # content lane, not ads ops
    "bu ay strategiya hazırla",
    "kompüteri söndür",
])
def test_non_ads_sentences_fall_through(task):
    assert ads_agent.wants_ads(task) is False


# ---------- the money guard, through natural language ----------
def test_pause_request_parks_and_executes_nothing(meta, monkeypatch, tmp_path):
    monkeypatch.setattr(ads_agent, "PLANS_DIR", tmp_path)
    _intent(monkeypatch, action="pause", campaign="Awareness", amount=None)
    out = ads_agent.handle(FakeJob("Awareness kampaniyasını dayandır"))
    assert out["needs_approval"] is True
    assert meta == [], "a live write happened before approval"
    assert "Awareness" in out["result"] and "hə" in out["result"]


def test_approved_rerun_executes_exactly_the_saved_plan(meta, monkeypatch, tmp_path):
    monkeypatch.setattr(ads_agent, "PLANS_DIR", tmp_path)
    _intent(monkeypatch, action="pause", campaign="Awareness", amount=None)
    ads_agent.handle(FakeJob("Awareness kampaniyasını dayandır"))       # parks
    out = ads_agent.handle(FakeJob("Awareness kampaniyasını dayandır", approved=1))
    assert meta and meta[0]["node_id"] == "111" and meta[0]["change"] == {"status": "PAUSED"}
    assert "dayandırıldı" in out["result"]


def test_approval_is_refused_if_the_account_drifted_since_the_owner_saw_it(
        meta, monkeypatch, tmp_path):
    monkeypatch.setattr(ads_agent, "PLANS_DIR", tmp_path)
    _intent(monkeypatch, action="pause", campaign="Awareness", amount=None)
    ads_agent.handle(FakeJob("Awareness dayandır"))                      # plan says ACTIVE
    CAMPAIGNS[0]["effective_status"] = "PAUSED"                          # someone else changed it
    try:
        out = ads_agent.handle(FakeJob("Awareness dayandır", approved=1))
        assert meta == [], "executed against a drifted account"
        assert "dəyişib" in out["result"]
    finally:
        CAMPAIGNS[0]["effective_status"] = "ACTIVE"


# ---------- name resolution: the owner never types an id ----------
def test_ambiguous_name_asks_which_one_instead_of_guessing(meta, monkeypatch, tmp_path):
    monkeypatch.setattr(ads_agent, "PLANS_DIR", tmp_path)
    _intent(monkeypatch, action="pause", campaign="KASKO", amount=None)
    out = ads_agent.handle(FakeJob("KASKO kampaniyasını dayandır"))
    assert "needs_approval" not in out
    assert "Hansı" in out["result"]
    assert meta == []


def test_budget_outside_bounds_is_refused_in_plain_language(meta, monkeypatch, tmp_path):
    monkeypatch.setattr(ads_agent, "PLANS_DIR", tmp_path)
    _intent(monkeypatch, action="budget", campaign="Awareness", amount=99_999)
    out = ads_agent.handle(FakeJob("Awareness büdcəsini 99999 et"))
    assert "edə bilmərəm" in out["result"]
    assert meta == []


def test_reads_answer_immediately_without_any_approval(meta, monkeypatch):
    _intent(monkeypatch, action="list", campaign="", amount=None)
    out = ads_agent.handle(FakeJob("kampaniyaları göstər"))
    assert "needs_approval" not in out
    assert "Awareness" in out["result"]


def test_llm_saying_not_an_ads_ask_falls_through_to_normal_chat(meta, monkeypatch):
    _intent(monkeypatch, action="none")
    assert ads_agent.handle(FakeJob("kampaniya haqqında nə düşünürsən")) is None

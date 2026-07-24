"""Guard tests for the MCP client + ad-platform connectors.

The one that matters most: a WRITE tool (it can spend a live ad budget) must be
refused unless a human checkpoint approved it. Everything else is transport hygiene.
"""
from __future__ import annotations

import pytest

from gateway import ad_mcp
from gateway.mcp_client import _parse_sse, _parse_www_authenticate


# ---------- the money guard ----------
@pytest.mark.parametrize("tool", [
    "create_campaign", "update_adset", "pause_ad", "delete_creative",
    "set_daily_budget", "launch_campaign", "update_bid_strategy", "publish_ad",
])
def test_write_tools_are_classified_as_write(tool):
    assert ad_mcp.is_write_tool(tool) is True


@pytest.mark.parametrize("tool", [
    "list_campaigns", "get_insights", "read_account", "search_ads", "fetch_report",
])
def test_read_tools_are_not_write(tool):
    assert ad_mcp.is_write_tool(tool) is False


def test_write_call_is_blocked_without_human_approval():
    """No token is even needed: the gate must trip before we touch the network."""
    with pytest.raises(PermissionError) as exc:
        ad_mcp.call("meta", "pause_ad", {"ad_id": "123"})
    assert "human checkpoint" in str(exc.value)


def test_unknown_platform_is_rejected():
    with pytest.raises(Exception):
        ad_mcp.client_for("myspace")


# ---------- transport hygiene ----------
def test_sse_body_is_parsed_into_json_messages():
    body = 'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"ok":true}}\n\n'
    msgs = _parse_sse(body)
    assert msgs == [{"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}]


def test_sse_ignores_non_json_and_empty_blocks():
    body = 'event: ping\n\ndata: not-json\n\ndata: {"id":2}\n\n'
    assert _parse_sse(body) == [{"id": 2}]


def test_www_authenticate_hint_is_extracted_for_the_human():
    header = ('Bearer resource_metadata="https://mcp.facebook.com/.well-known/'
              'oauth-protected-resource/ads", scope="ads_management ads_read"')
    meta, scope = _parse_www_authenticate(header)
    assert meta.endswith("/oauth-protected-resource/ads")
    assert "ads_management" in scope


# ---------- readiness ----------
def test_status_reports_needs_token_with_an_actionable_next_step(monkeypatch):
    monkeypatch.setattr(ad_mcp, "token_for", lambda p: "")
    rows = {r["platform"]: r for r in ad_mcp.status()}
    assert set(rows) >= {"meta", "tiktok", "adroll", "canva"}
    meta = rows["meta"]
    assert meta["state"] == "needs-token"
    assert meta["has_token"] is False
    assert "SECURE_KEY.bat META_ADS_TOKEN" in meta["next_step"]

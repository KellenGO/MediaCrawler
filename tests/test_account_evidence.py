import asyncio
from unittest.mock import AsyncMock

import pytest
from api.services import accounts
from media_platform.xhs.client import XiaoHongShuClient
from media_platform.xhs.exception import DataFetchError, XhsRateLimitError


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch, tmp_path):
    for name in ("_platform_state", "_evidence_revision", "_usage_evidence", "_verification_checks", "_last_search_outcomes", "_session_snapshots", "_account_generation"):
        monkeypatch.setattr(accounts, name, {})
    monkeypatch.setattr(accounts, "profile_dir_for", lambda p: tmp_path / p)


def test_new_session_rejects_old_task_and_clears_usage():
    old = accounts.evidence_token("xhs")
    assert accounts.record_usage("xhs", "search", "succeeded", old)
    accounts._set_state("xhs", status="syncing")
    assert accounts.usage_evidence("xhs") == {}
    assert not accounts.record_usage("xhs", "search", "login_required", old)


def test_old_failure_cannot_replace_newer_success_across_operations():
    old = accounts.evidence_token("xhs")
    new = accounts.evidence_token("xhs")
    assert accounts.record_usage("xhs", "favorites", "succeeded", new)
    assert not accounts.record_usage("xhs", "search", "login_required", old)


def test_public_success_retires_failure_without_claiming_authenticated():
    accounts._set_state("xhs", status="expired", verified=False)
    assert accounts.record_usage("xhs", "search", "succeeded", accounts.evidence_token("xhs"))
    assert accounts._state_of("xhs")["status"] == "unverified"
    assert not accounts._state_of("xhs")["verified"]


def test_cancel_is_not_login_evidence():
    assert not accounts.record_usage("xhs", "favorites", "cancelled", accounts.evidence_token("xhs"))
    assert accounts.usage_evidence("xhs") == {}


def test_check_time_is_stable_and_cached_for_one_minute(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(accounts.time, "monotonic", lambda: now[0])
    accounts._finalize_verdict("xhs", "unavailable", None, True)
    assert accounts._state_of("xhs")["status"] == "unavailable"
    stamp = accounts._verification_checks["xhs"]["evidence"]["checked_at"]
    assert accounts.recent_verification("xhs")
    assert accounts._verification_checks["xhs"]["evidence"]["checked_at"] == stamp
    now[0] = 161
    assert accounts.recent_verification("xhs") is None


@pytest.mark.parametrize("payload", [{}, {"data": {}}, {"data": {"result": {}}}, {"success": False}])
def test_unknown_xhs_response_is_not_logout(payload):
    client = XiaoHongShuClient(proxy=None, headers={}, playwright_page=None, cookie_dict={})
    client.query_self = AsyncMock(return_value=payload)
    with pytest.raises(DataFetchError):
        asyncio.run(client.pong(raise_on_error=True))


def test_browser_confirmation_can_correct_http_false():
    page = type("Page", (), {"is_visible": AsyncMock(return_value=True)})()
    client = XiaoHongShuClient(proxy=None, headers={}, playwright_page=page, cookie_dict={})
    client.query_self = AsyncMock(return_value={"data": {"result": {"success": False}}})
    assert asyncio.run(client.pong(raise_on_error=True))


def test_rate_limit_does_not_trigger_browser_fallback():
    client = XiaoHongShuClient(proxy=None, headers={}, playwright_page=None, cookie_dict={})
    client.query_self = AsyncMock(side_effect=XhsRateLimitError(461))
    client.browser_login_confirmed = AsyncMock(return_value=True)
    with pytest.raises(XhsRateLimitError):
        asyncio.run(client.pong(raise_on_error=True))
    client.browser_login_confirmed.assert_not_awaited()


def test_scan_success_publishes_verification_without_reopening_profile():
    accounts._set_state("xhs", status="expired", verified=False)
    accounts._session_snapshots["xhs"] = {"test": "old"}
    asyncio.run(accounts.begin_scan_login("xhs"))
    assert accounts.get_session_snapshot("xhs") is None
    accounts.finish_scan_login("xhs", True)
    assert accounts._state_of("xhs")["verified"] is True
    assert accounts._state_of("xhs")["status"] == "connected"
    assert accounts._verification_checks["xhs"]["evidence"]["source"] == "scan_login"
    assert accounts.recent_verification("xhs")["verified"] is True


def test_live_login_rejection_invalidates_recent_success():
    accounts._finalize_verdict("xhs", "verified", None, False)
    assert accounts.recent_verification("xhs")["verified"]
    accounts.mark_login_required_from_search("xhs")
    assert accounts.recent_verification("xhs") is None
    assert accounts._state_of("xhs")["status"] == "expired"


def test_new_verification_does_not_reuse_older_check():
    accounts._finalize_verdict("xhs", "verified", None, False)
    accounts._set_state("xhs", status="verifying")
    assert accounts.recent_verification("xhs") is None

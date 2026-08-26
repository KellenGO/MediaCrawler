from types import SimpleNamespace

from api.services import accounts as acc


def _prepare(monkeypatch, tmp_path):
    monkeypatch.setattr(acc, "_platform_state", {})
    monkeypatch.setattr(acc, "_session_snapshots", {})
    monkeypatch.setattr(acc, "_last_search_outcomes", {})
    profile_root = tmp_path / "browser_data"
    monkeypatch.setattr(acc, "profile_dir_for", lambda platform: profile_root / platform)
    return profile_root


def _timing(fast_path_used=None, provider_used=None, provider_attempts=None,
            fallback_active=None):
    return SimpleNamespace(
        fast_path_used=fast_path_used,
        provider_used=provider_used,
        provider_attempts=provider_attempts,
        fallback_active=fallback_active,
        fallback_reason=None,
    )


def test_xhs_unverified_browser_fallback_remains_search_available(monkeypatch, tmp_path):
    root = _prepare(monkeypatch, tmp_path)
    (root / "xhs").mkdir(parents=True)
    acc._set_state("xhs", status="unverified", verified=False)
    acc.record_search_outcome("xhs", "succeeded", _timing(False))

    diagnostic = acc.get_platform_diagnostic("xhs")
    assert diagnostic["search_available"] is True
    assert diagnostic["search_mode"] == "browser_fallback"
    assert diagnostic["fallback_active"] is True
    assert diagnostic["hydration_available"] is True
    assert diagnostic["limitation_code"] == "account_unverified"
    assert "不影响当前公开搜索" in diagnostic["user_message"]


def test_bilibili_normal_fast_path_supports_hydration(monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path)
    acc._session_snapshots["bilibili"] = {"SESSDATA": "secret-value"}
    acc.record_search_outcome("bilibili", "succeeded", _timing(True))

    diagnostic = acc.get_platform_diagnostic("bilibili")
    assert diagnostic["search_available"] is True
    assert diagnostic["search_mode"] == "fast_path"
    assert diagnostic["fallback_active"] is False
    assert diagnostic["hydration_available"] is True


def test_doctor_prefers_real_browser_provider_metadata(monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path)
    acc.record_search_outcome(
        "xhs", "succeeded",
        _timing(provider_used="browser", provider_attempts=["session_api", "browser"],
                fallback_active=True),
    )

    diagnostic = acc.get_platform_diagnostic("xhs")
    assert diagnostic["search_mode"] == "browser_fallback"
    assert diagnostic["fallback_active"] is True


def test_doctor_prefers_real_session_provider_metadata(monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path)
    acc.record_search_outcome(
        "bilibili", "succeeded",
        _timing(provider_used="light_api", provider_attempts=["light_api"]),
    )

    diagnostic = acc.get_platform_diagnostic("bilibili")
    assert diagnostic["search_mode"] == "fast_path"
    assert diagnostic["fallback_active"] is False


def test_douyin_search_snippet_is_available_without_detail_hydration(monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path)

    diagnostic = acc.get_platform_diagnostic("douyin")
    assert diagnostic["search_available"] is True
    assert diagnostic["snippet_available"] is True
    assert diagnostic["hydration_available"] is False
    assert diagnostic["limitation_code"] is None
    assert "简介" in diagnostic["user_message"]


def test_failed_platform_gets_safe_unavailable_diagnostic(monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path)
    acc.record_search_outcome("zhihu", "failed", _timing(False))

    diagnostic = acc.get_platform_diagnostic("zhihu")
    assert diagnostic["search_available"] is False
    assert diagnostic["search_mode"] == "unavailable"
    assert diagnostic["limitation_code"] == "platform_unavailable"
    assert diagnostic["recommended_action"]


def test_accounts_response_contains_only_safe_diagnostic_fields(monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path)
    acc._session_snapshots["xhs"] = {
        "a1": "A1-SECRET", "web_session": "SESSION-SECRET"
    }
    payload = acc.get_accounts()
    serialized = str(payload)
    assert "A1-SECRET" not in serialized
    assert "SESSION-SECRET" not in serialized
    assert "browser_data" not in serialized
    assert "cookie" not in serialized.lower()
    assert "token" not in serialized.lower()
    for account in payload:
        assert set(account["diagnostic"]) == {
            "platform", "search_available", "search_mode", "account_state",
            "snippet_available", "hydration_available", "fallback_active", "limitation_code",
            "user_message", "recommended_action", "checked_at",
        }

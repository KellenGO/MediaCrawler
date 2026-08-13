# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1

"""Account service tests — all call production functions in
``api/services/accounts.py``.

Covers: one-time sync tickets, cookie domain whitelist, Chrome→Playwright
cookie mapping, profile path bounds, per-platform profile lock, verify
paths that never launch a visible browser, and secret-free responses.
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.services import accounts as acc
from api.services.accounts import (
    BROWSER_DATA_DIR,
    COOKIE_FORMAT_CHROME_V1,
    CookieDomainRejectedError,
    CookieFormatInvalidError,
    PlatformError,
    SessionImportError,
    TicketError,
    cookie_domain_allowed,
    consume_sync_ticket,
    create_sync_ticket,
    delete_platform_session,
    get_accounts,
    map_chrome_cookie,
    profile_dir_for,
    sync_platform_cookies,
    validate_chrome_v1_cookie_list,
    verify_platform,
)

_SECRET_KEYS = {"cookie", "cookies", "token", "password", "secret",
                "authorization", "xsec_token", "set-cookie"}


# ── One-time tickets ────────────────────────────────────────────────────

def test_ticket_is_at_least_128bit():
    """token_urlsafe(32) → 256 bits of entropy, single string value."""
    ticket = create_sync_ticket("xhs")
    assert len(ticket) >= 32  # 43 chars base64url > 128 bits


def test_ticket_creation_rejects_unknown_platform():
    with pytest.raises(PlatformError):
        create_sync_ticket("myspace")


def test_ticket_single_use():
    ticket = create_sync_ticket("bilibili")
    asyncio.run(consume_sync_ticket(ticket, "bilibili"))
    with pytest.raises(TicketError):
        asyncio.run(consume_sync_ticket(ticket, "bilibili"))


def test_ticket_wrong_platform_rejected():
    """Wrong platform is rejected — and the single-use ticket is burned:
    production pops it before validation, so one wrong attempt kills it."""
    ticket = create_sync_ticket("xhs")
    with pytest.raises(TicketError):
        asyncio.run(consume_sync_ticket(ticket, "douyin"))
    with pytest.raises(TicketError):
        asyncio.run(consume_sync_ticket(ticket, "xhs"))


def test_ticket_expiry(monkeypatch):
    """Expired tickets are rejected; the entry is purged."""
    now = [1000.0]
    monkeypatch.setattr(acc.time, "monotonic", lambda: now[0])
    ticket = create_sync_ticket("zhihu")
    now[0] += acc.TICKET_TTL_SECONDS + 1
    with pytest.raises(TicketError):
        asyncio.run(consume_sync_ticket(ticket, "zhihu"))


def test_ticket_unknown_rejected():
    with pytest.raises(TicketError):
        asyncio.run(consume_sync_ticket("totally-fake-ticket", "xhs"))


# ── Cookie domain whitelist (production function) ───────────────────────

@pytest.mark.parametrize("domain,platform,ok", [
    ("www.xiaohongshu.com", "xhs", True),
    (".xiaohongshu.com", "xhs", True),
    ("sub.xiaohongshu.com", "xhs", True),
    ("xiaohongshu.com", "xhs", True),
    ("www.douyin.com", "douyin", True),
    ("space.bilibili.com", "bilibili", True),
    ("www.zhihu.com", "zhihu", True),
    ("XIAOHONGSHU.COM", "xhs", True),          # case-insensitive
    ("evil-xiaohongshu.com", "xhs", False),    # suffix, not subdomain
    ("xiaohongshu.com.evil.com", "xhs", False),
    ("google.com", "xhs", False),
    ("", "xhs", False),
    (None, "xhs", False),
])
def test_cookie_domain_whitelist(domain, platform, ok):
    assert cookie_domain_allowed(platform, domain) is ok


# ── Chrome → Playwright cookie mapping (production function) ────────────

def test_map_chrome_cookie_full():
    mapped = map_chrome_cookie({
        "name": "sessionid", "value": "abc123",
        "domain": ".zhihu.com", "path": "/",
        "expirationDate": 1750000000.0,
        "httpOnly": True, "secure": True,
        "sameSite": "no_restriction",
    })
    assert mapped == {
        "name": "sessionid", "value": "abc123",
        "domain": ".zhihu.com", "path": "/",
        "expires": 1750000000.0,
        "httpOnly": True, "secure": True,
        "sameSite": "None",
    }


def test_map_chrome_cookie_session_and_samesite():
    """Session cookies get NO expires key (never -1); unspecified sameSite
    omits the key entirely (never sameSite: null — Playwright rejects it)."""
    mapped = map_chrome_cookie({
        "name": "d_c0", "value": "x", "domain": ".zhihu.com",
        "sameSite": "lax",
    })
    assert "expires" not in mapped          # session cookie
    assert mapped["sameSite"] == "Lax"
    mapped = map_chrome_cookie({
        "name": "n", "value": "v", "domain": ".zhihu.com",
        "sameSite": "strict",
    })
    assert mapped["sameSite"] == "Strict"
    # unspecified / null / unknown sameSite -> no sameSite key at all
    for cookie in (
        {"name": "n", "value": "v", "domain": ".zhihu.com"},
        {"name": "n", "value": "v", "domain": ".zhihu.com", "sameSite": "unspecified"},
        {"name": "n", "value": "v", "domain": ".zhihu.com", "sameSite": None},
        {"name": "n", "value": "v", "domain": ".zhihu.com", "sameSite": "weird"},
    ):
        mapped = map_chrome_cookie(cookie)
        assert "sameSite" not in mapped
        assert "sameSite" not in mapped or mapped["sameSite"] is not None, (
            "sameSite must never be null")


def test_map_chrome_cookie_expiration_edge_cases():
    """NaN / Infinity / non-positive / non-numeric expiration -> no expires
    key (Playwright would reject non-finite values)."""
    for expiration in (float("nan"), float("inf"), 0, -5, "1750000000", True, None):
        mapped = map_chrome_cookie({
            "name": "n", "value": "v", "domain": ".zhihu.com",
            "expirationDate": expiration,
        })
        assert "expires" not in mapped, f"expirationDate={expiration!r} must not map"


def test_map_chrome_cookie_skips_partitioned():
    assert map_chrome_cookie({
        "name": "n", "value": "v", "domain": ".zhihu.com",
        "partitionKey": {"topLevelSite": "https://www.zhihu.com"},
    }) is None


def test_map_chrome_cookie_requires_fields():
    assert map_chrome_cookie({"name": "", "value": "v", "domain": ".x.com"}) is None
    assert map_chrome_cookie({"name": "n", "value": None, "domain": ".x.com"}) is None
    assert map_chrome_cookie({"name": "n", "value": "v", "domain": ""}) is None


def test_validate_cookie_list_rejects_third_party():
    """Third-party cookie -> whole batch rejected, rejected count recorded."""
    with pytest.raises(CookieDomainRejectedError) as exc:
        validate_chrome_v1_cookie_list("xhs", [
            {"name": "web_session", "value": "v", "domain": "tracker.evil.com"},
        ])
    assert exc.value.diagnostics["rejected_cookie_count"] == 1


def test_validate_cookie_list_skips_partitioned_and_maps():
    """Partitioned cookies are counted as skipped, never sent to Playwright.
    Cookie names are the platform's REAL login cookies (fake values)."""
    mapped, diag = validate_chrome_v1_cookie_list("xhs", [
        {"name": "web_session", "value": "1", "domain": ".xiaohongshu.com"},
        {"name": "a1", "value": "2", "domain": ".xiaohongshu.com",
         "partitionKey": {"topLevelSite": "https://www.xiaohongshu.com"}},
    ])
    assert [m["name"] for m in mapped] == ["web_session"]
    assert diag["received_cookie_count"] == 2
    assert diag["accepted_cookie_count"] == 1
    assert diag["skipped_cookie_count"] == 1
    assert diag["rejected_cookie_count"] == 0
    assert diag["required_cookie_present"] is True


def test_validate_rejects_unknown_fields_and_mixed_formats():
    """Old/foreign formats must fail with cookie_format_invalid, not a
    confusing session_import_failed."""
    bad_cookies = [
        # old format: expires key (not chrome-v1)
        [{"name": "n", "value": "v", "domain": ".xiaohongshu.com",
          "expires": 1750000000.0}],
        # both expirationDate and expires
        [{"name": "n", "value": "v", "domain": ".xiaohongshu.com",
          "expirationDate": 1750000000.0, "expires": 1750000000.0}],
        # Playwright-style uppercase sameSite
        [{"name": "n", "value": "v", "domain": ".xiaohongshu.com",
          "sameSite": "Lax"}],
        # unknown field
        [{"name": "n", "value": "v", "domain": ".xiaohongshu.com",
          "url": "https://www.xiaohongshu.com"}],
    ]
    for cookies in bad_cookies:
        with pytest.raises(CookieFormatInvalidError) as exc:
            validate_chrome_v1_cookie_list("xhs", cookies)
        assert exc.value.safe_code == "cookie_format_invalid"


def test_validate_import_allowed_without_login_marker():
    """Round 9: 联调观察到抖音/知乎只有非登录 Cookie 时被
    required_login_cookie_missing 拦截。阶段模型修正：≥1 条合法平台 Cookie
    即允许导入 —— 登录 marker 只是诊断。没有任何白名单登录 marker →
    required_cookie_present False、login_marker_presence 全 False，
    但 mapped 非空且不再抛异常。"""
    cases = {
        "xhs": [{"name": "a1", "value": "x", "domain": ".xiaohongshu.com"}],
        "bilibili": [{"name": "buvid3", "value": "x", "domain": ".bilibili.com"}],
        "zhihu": [{"name": "x-zse-96", "value": "x", "domain": ".zhihu.com"}],
        "douyin": [{"name": "ttwid", "value": "x", "domain": ".douyin.com"}],
    }
    for platform, cookies in cases.items():
        mapped, diag = validate_chrome_v1_cookie_list(platform, cookies)
        assert len(mapped) == 1, platform  # 导入允许
        assert diag["required_cookie_present"] is False, platform
        assert diag["login_marker_presence"] == {
            name: False for name in acc.LOGIN_MARKER_NAMES[platform]
        }, platform


@pytest.mark.parametrize("platform,pairs", [
    ("xhs", (("web_session", "fake"),)),
    ("bilibili", (("SESSDATA", "fake"),)),
    ("zhihu", (("z_c0", "fake"), ("d_c0", "fake"))),
    ("douyin", (("LOGIN_STATUS", "1"),)),
])
def test_validate_login_marker_presence_per_platform(platform, pairs):
    """白名单登录 marker 存在（值非空）→ login_marker_presence 对应 true、
    required_cookie_present True —— 启发式诊断，不是登录结论。"""
    domain = acc.PLATFORM_COOKIE_DOMAINS[platform][0]
    cookies = [{"name": n, "value": v, "domain": f".{domain}"}
               for n, v in pairs]
    mapped, diag = validate_chrome_v1_cookie_list(platform, cookies)
    assert len(mapped) == len(pairs)
    for name, _ in pairs:
        assert diag["login_marker_presence"][name] is True, name
    assert diag["required_cookie_present"] is True


def test_validate_cookie_list_empty_fails_import(monkeypatch):
    """Empty cookie list → no mapped cookies → sync fails at import
    (before any profile/browser is touched)."""
    launched = []
    monkeypatch.setattr(
        "api.services.accounts._launch_profile_context",
        lambda platform: launched.append(platform))
    mapped, diag = validate_chrome_v1_cookie_list("xhs", [])
    assert mapped == []
    assert diag["received_cookie_count"] == 0
    with pytest.raises(SessionImportError):
        asyncio.run(sync_platform_cookies("xhs", [],
                                          cookie_format=COOKIE_FORMAT_CHROME_V1, extension_protocol_version=2))
    assert launched == [], "no browser may be launched for an empty cookie list"


def test_sync_rejects_non_chrome_v1_format(monkeypatch):
    """Only cookie_format=chrome-v1 is accepted — anything else fails before
    any browser launch with cookie_format_invalid."""
    launched = []
    monkeypatch.setattr(
        "api.services.accounts._launch_profile_context",
        lambda platform: launched.append(platform))
    with pytest.raises(CookieFormatInvalidError):
        asyncio.run(sync_platform_cookies(
            "xhs",
            [{"name": "web_session", "value": "v", "domain": ".xiaohongshu.com"}],
            cookie_format="playwright-v1"))
    assert launched == []


# ── Profile paths are backend-generated and bounded ─────────────────────

def test_profile_dir_is_whitelisted_generated():
    for platform in ("xhs", "douyin", "bilibili", "zhihu"):
        d = profile_dir_for(platform)
        assert str(d).startswith(str(BROWSER_DATA_DIR))
    with pytest.raises(PlatformError):
        profile_dir_for("myspace")


def test_resolve_profile_path_stays_inside_browser_data():
    for platform in ("xhs", "douyin", "bilibili", "zhihu"):
        resolved = acc._resolve_profile_path(platform)
        base = BROWSER_DATA_DIR.resolve()
        assert str(resolved).startswith(str(base) + os.sep) or str(resolved) == str(base)


def test_accounts_response_contains_no_secrets():
    """GET /accounts payload must never include cookies/paths."""
    for acc_info in get_accounts():
        for k, v in acc_info.items():
            assert k.lower() not in _SECRET_KEYS
            assert not isinstance(v, str) or "cookie" not in v.lower()
            assert not isinstance(v, str) or "user_data" not in v.lower()


# ── Per-platform profile lock blocks concurrent opens ───────────────────

class _FakeCtx:
    """Signature mirrors real playwright BrowserContext: clear_cookies is
    KEYWORD-ONLY (clear_cookies(*, name, domain, path)); cookies() accepts
    urls by keyword (tools.crawler_util calls context.cookies(urls=...))."""

    def __init__(self, existing=None):
        self.existing = existing or []
        self.added = []
        self.cleared_domains = []

    async def cookies(self, urls=None):
        return list(self.existing)

    async def add_cookies(self, mapped):
        self.added.extend(mapped)

    async def clear_cookies(self, *, name=None, domain=None, path=None):
        self.cleared_domains.append(domain)

    async def new_page(self, *a, **k):
        page = getattr(self, "page", None)
        if page is not None:
            return page
        class _P:
            async def goto(self, *a, **k):
                pass
        return _P()

    async def close(self):
        pass


class _FakePW:
    async def stop(self):
        pass


def _patch_launch(monkeypatch):
    """Patch _launch_profile_context to return a preset fake context
    (the SAME context instance for import and verify phases)."""
    ctx = _FakeCtx()

    async def fake_launch(platform):
        return _FakePW(), ctx, "edge"

    monkeypatch.setattr("api.services.accounts._launch_profile_context",
                        fake_launch)
    return ctx


def test_profile_lock_blocks_concurrent_use(monkeypatch):
    """The same platform profile must not be opened by two contexts at once."""
    import api.services.accounts as accounts_mod

    _patch_launch(monkeypatch)
    monkeypatch.setattr(accounts_mod, "_pong_with_profile",
                        lambda p, c: asyncio.sleep(0, result=True))
    # Real production lock: hold it, then sync must wait.
    lock = accounts_mod._profile_lock("xhs")

    async def scenario():
        async with lock:
            task = asyncio.create_task(sync_platform_cookies(
                "xhs",
                [{"name": "web_session", "value": "1",
                  "domain": ".xiaohongshu.com"}],
                cookie_format=COOKIE_FORMAT_CHROME_V1, extension_protocol_version=2))
            await asyncio.sleep(0.2)
            assert not task.done(), "sync started while profile lock held"
        await asyncio.wait_for(task, timeout=5)
        result = task.result()
        assert result["success"] is True
        assert result["verified"] is True

    asyncio.run(scenario())


def test_profile_lock_is_per_platform():
    """xhs lock must not block bilibili."""
    xhs_lock = acc._profile_lock("xhs")
    bili_lock = acc._profile_lock("bilibili")
    assert xhs_lock is not bili_lock


# ── sync: import + bounded verify (方案 A, ≤30s) ─────────────────────────

_XHS_COOKIES = [
    {"name": "web_session", "value": "fake-xhs-session",
     "domain": ".xiaohongshu.com", "path": "/",
     "expirationDate": 1750000000.0, "httpOnly": True, "secure": True,
     "sameSite": "no_restriction"},
    {"name": "a1", "value": "fake-a1", "domain": ".xiaohongshu.com",
     "sameSite": "lax"},
]


def test_sync_import_clears_only_platform_cookies(monkeypatch):
    """Before import, ONLY the platform's own stale cookies are cleared —
    never the whole profile, never other platforms' cookies."""
    ctx = _patch_launch(monkeypatch)
    ctx.existing = [
        {"name": "stale1", "domain": ".xiaohongshu.com"},
        {"name": "stale2", "domain": "www.xiaohongshu.com"},
    ]
    monkeypatch.setattr(
        "api.services.accounts._pong_with_profile",
        lambda p, c: asyncio.sleep(0, result=True))

    result = asyncio.run(sync_platform_cookies(
        "xhs", _XHS_COOKIES, cookie_format=COOKIE_FORMAT_CHROME_V1, extension_protocol_version=2,
        browser_cookie_store_count=2))
    assert result["success"] is True
    assert result["verified"] is True
    assert set(ctx.cleared_domains) == {".xiaohongshu.com", "www.xiaohongshu.com"}
    added_names = [c["name"] for c in ctx.added]
    assert added_names == ["web_session", "a1"]
    assert result["received_cookie_count"] == 2
    assert result["accepted_cookie_count"] == 2


def test_sync_verify_failure_reports_unverified_not_failure(monkeypatch):
    """Round 9: 导入成功但 pong 未确认登录 ≠ 同步失败 —— success=true、
    verified=false、status=unverified、login_not_verified；UI 提示仍可尝试
    搜索，绝不显示“同步失败”。"""
    # Round 10: previous_status 现在在 sync 入口捕获 —— 测试必须从干净
    # 状态出发，否则残留的 connected 会（正确地）走向 expired 语义。
    acc._set_state("xhs", status="disconnected", verified=False)
    _patch_launch(monkeypatch)
    monkeypatch.setattr(
        "api.services.accounts._pong_with_profile",
        lambda p, c: asyncio.sleep(0, result=False))

    result = asyncio.run(sync_platform_cookies(
        "xhs", _XHS_COOKIES, cookie_format=COOKIE_FORMAT_CHROME_V1, extension_protocol_version=2))
    assert result["success"] is True
    assert result["verified"] is False
    assert result["status"] == "unverified"
    assert result["safe_error_code"] == "login_not_verified"
    assert "尚未确认账号登录" in result["safe_message"]
    assert result["sync_stage"] == "verification"
    state = acc._state_of("xhs")
    assert state["status"] == "unverified"
    assert state["verified"] is False


def test_sync_verify_timeout_reports_verifying(monkeypatch):
    """pong slower than the bound -> success=true, verified=false,
    status=verifying; the verify continues in the background."""
    import api.services.accounts as accounts_mod

    gate = asyncio.Event()
    _patch_launch(monkeypatch)
    monkeypatch.setattr(
        "api.services.accounts._pong_with_profile",
        lambda p, c: gate.wait())
    monkeypatch.setattr(accounts_mod, "SYNC_VERIFY_TIMEOUT_SECONDS", 0.05)

    async def scenario():
        result = await sync_platform_cookies(
            "xhs", _XHS_COOKIES, cookie_format=COOKIE_FORMAT_CHROME_V1, extension_protocol_version=2)
        assert result["success"] is True
        assert result["verified"] is False
        assert result["status"] == "verifying"
        assert result["safe_message"] == "会话已导入，仍在后台验证"
        assert result["sync_stage"] == "verification"
        # let the background verify finish so asyncio.run can close cleanly
        gate.set()
        await asyncio.sleep(0.1)

    asyncio.run(scenario())


def test_sync_success_marks_connected_verified(monkeypatch):
    """Sync + verified pong -> connected with verified=True (never
    connected+verified=False)."""
    _patch_launch(monkeypatch)
    monkeypatch.setattr(
        "api.services.accounts._pong_with_profile",
        lambda p, c: asyncio.sleep(0, result=True))

    result = asyncio.run(sync_platform_cookies(
        "xhs", _XHS_COOKIES, cookie_format=COOKIE_FORMAT_CHROME_V1, extension_protocol_version=2))
    assert result["verified"] is True
    assert result["status"] == "connected"
    assert result["sync_stage"] == "completed"
    state = acc._state_of("xhs")
    assert state["status"] == "connected"
    assert state["verified"] is True


# ── state semantics: profile exists != logged in ─────────────────────────

def test_profile_dir_alone_is_not_connected(monkeypatch, tmp_path):
    """A leftover profile directory means unverified, never connected."""
    monkeypatch.setattr(acc, "BROWSER_DATA_DIR", tmp_path)
    monkeypatch.setattr(acc, "profile_dir_for",
                        lambda p: tmp_path / acc.PLATFORM_PROFILE_DIRS[p])
    # 清除其他测试可能残留的 bilibili 全局状态条目：本测试语义是
    # "目录存在但从未同步/验证"（无状态记录 → unverified）。
    acc._platform_state.pop("bilibili", None)
    target = acc.profile_dir_for("bilibili")
    target.mkdir(parents=True)

    state = acc._state_of("bilibili")
    assert state["status"] == "unverified"
    assert state["verified"] is False

    for info in get_accounts():
        assert not (info["status"] == "connected" and not info["verified"]), (
            "connected must imply verified")


def test_delete_returns_to_disconnected(monkeypatch, tmp_path):
    """After delete the profile is gone -> disconnected."""
    monkeypatch.setattr(acc, "BROWSER_DATA_DIR", tmp_path)
    monkeypatch.setattr(acc, "profile_dir_for",
                        lambda p: tmp_path / acc.PLATFORM_PROFILE_DIRS[p])
    acc.profile_dir_for("zhihu").mkdir(parents=True)
    asyncio.run(delete_platform_session("zhihu"))
    assert acc._state_of("zhihu")["status"] == "disconnected"


# ── verify: headless only, never auto-opens a visible browser ───────────

def test_launch_profile_context_is_headless_only():
    """The accounts service must never open a visible browser."""
    src = Path(acc.__file__).read_text(encoding="utf-8")
    assert '"headless": True' in src
    assert '"headless": False' not in src


def test_verify_unverified_session_reports_unverified(monkeypatch):
    """从未确认过登录的会话在真实验证中 pong=False → unverified /
    login_not_verified（不是 expired/login_required，也不抛内部异常）。"""
    class _FakeCtx:
        async def cookies(self, urls):
            return []  # no session cookies

        async def close(self):
            pass

    class _FakePW:
        async def stop(self):
            pass

    async def fake_launch(platform):
        return _FakePW(), _FakeCtx(), "edge"

    monkeypatch.setattr("api.services.accounts._launch_profile_context",
                        fake_launch)

    result = asyncio.run(verify_platform("bilibili"))
    assert result["success"] is True
    assert result["status"] == "unverified"
    assert result["safe_error_code"] == "login_not_verified"
    state = acc._state_of("bilibili")
    assert state["status"] == "unverified"
    assert state["verified"] is False


def test_verify_connected_then_pong_failure_returns_expired(monkeypatch):
    """之前已确认登录（connected），现在真实验证明确失效 → expired +
    login_required（区别于从未确认过的 unverified）。"""
    _patch_launch(monkeypatch)
    acc._set_state("douyin", status="disconnected", verified=False)
    monkeypatch.setattr(
        "api.services.accounts._pong_with_profile",
        lambda p, c: asyncio.sleep(0, result=True))
    assert asyncio.run(verify_platform("douyin"))["status"] == "connected"

    monkeypatch.setattr(
        "api.services.accounts._pong_with_profile",
        lambda p, c: asyncio.sleep(0, result=False))
    result = asyncio.run(verify_platform("douyin"))
    assert result["success"] is True
    assert result["status"] == "expired"
    assert result["safe_error_code"] == "login_required"
    state = acc._state_of("douyin")
    assert state["status"] == "expired"
    assert state["verified"] is False


def test_verify_exception_sets_failed_state(monkeypatch):
    """真实验证阶段的技术失败（浏览器启动等）→ status=failed +
    login_verification_failed + SessionImportError（不是 unverified）。"""

    def boom(platform):
        raise RuntimeError("launch failed")

    monkeypatch.setattr("api.services.accounts._launch_profile_context", boom)
    with pytest.raises(SessionImportError):
        asyncio.run(verify_platform("douyin"))
    state = acc._state_of("douyin")
    assert state["status"] == "failed"
    assert state["safe_error_code"] == "login_verification_failed"


def test_verify_success_marks_verified(monkeypatch):
    """Verified session → connected/verified. (pong result is mocked: a real
    pong needs a live network session; the state transition is production.)"""
    class _FakeCtx:
        async def cookies(self, urls):
            return [{"name": "n", "value": "v"}]

        async def close(self):
            pass

    class _FakePW:
        async def stop(self):
            pass

    async def fake_launch(platform):
        return _FakePW(), _FakeCtx(), "edge"

    monkeypatch.setattr("api.services.accounts._launch_profile_context",
                        fake_launch)
    monkeypatch.setattr("api.services.accounts._pong_with_profile",
                        lambda platform, ctx: asyncio.sleep(0, result=True))

    result = asyncio.run(verify_platform("xhs"))
    assert result["verified"] is True
    state = acc._state_of("xhs")
    assert state["status"] == "connected"
    assert state["verified"] is True
    assert state["last_verified_at"] is not None


# ── delete session ──────────────────────────────────────────────────────

def test_delete_session_removes_only_own_profile(monkeypatch, tmp_path):
    """delete removes the platform's own dir; the response has no paths."""
    # Point BROWSER_DATA_DIR at a temp dir so we never touch real data.
    monkeypatch.setattr(acc, "BROWSER_DATA_DIR", tmp_path)
    monkeypatch.setattr(acc, "profile_dir_for",
                        lambda p: tmp_path / acc.PLATFORM_PROFILE_DIRS[p])

    target = acc.profile_dir_for("bilibili")
    target.mkdir(parents=True)
    (target / "Default").mkdir()
    (target / "Default" / "Cookies").write_text("x")

    result = asyncio.run(delete_platform_session("bilibili"))
    assert result["success"] is True
    assert not target.exists()
    assert acc._state_of("bilibili")["status"] == "disconnected"
    # Nothing outside browser_data was touched.
    assert (tmp_path / "keep.txt").exists() is False


# ── Problem 4: douyin pong gets a REAL page from the profile context ─────

class _FakePage:
    def __init__(self, evaluate_result=None, evaluate_error=None):
        self.evaluate_result = evaluate_result
        self.evaluate_error = evaluate_error
        self.evaluate_calls = 0
        self.goto_urls = []

    async def evaluate(self, script):
        self.evaluate_calls += 1
        if self.evaluate_error is not None:
            raise self.evaluate_error
        return self.evaluate_result

    async def goto(self, url, **kw):
        self.goto_urls.append(url)

    async def close(self):
        pass


def _douyin_ctx(existing):
    ctx = _FakeCtx(existing=existing)
    ctx.page = _FakePage(evaluate_result={"HasUserLogin": "0"})
    return ctx


def test_pong_douyin_passes_real_page_and_uses_cookie_fallback():
    """Production _pong_with_profile('douyin', ctx): the client receives a
    REAL page created from the context (never None), the official site is
    visited, and when localStorage says not logged in the pong falls back to
    context-cookie LOGIN_STATUS == '1'. No network, all fictional cookies."""
    ctx = _douyin_ctx([
        {"name": "LOGIN_STATUS", "value": "1", "domain": ".douyin.com"},
        {"name": "sessionid", "value": "fake", "domain": ".douyin.com"},
    ])
    result = asyncio.run(acc._pong_with_profile("douyin", ctx))
    assert result == "verified"
    assert ctx.page.evaluate_calls == 1, "DouYinClient must receive the real page"
    assert ctx.page.goto_urls == ["https://www.douyin.com"]


def test_pong_douyin_login_status_zero_is_not_logged_in():
    ctx = _douyin_ctx([
        {"name": "LOGIN_STATUS", "value": "0", "domain": ".douyin.com"},
        {"name": "sessionid", "value": "fake", "domain": ".douyin.com"},
    ])
    result = asyncio.run(acc._pong_with_profile("douyin", ctx))
    assert result == "not_logged_in"


def test_pong_douyin_survives_page_evaluate_failure():
    """A broken/unloaded page must not crash pong — it falls back to the
    context-cookie LOGIN_STATUS check (the pre-fix behaviour crashed inside
    the try and returned False even with LOGIN_STATUS=1)."""
    ctx = _douyin_ctx([
        {"name": "LOGIN_STATUS", "value": "1", "domain": ".douyin.com"},
    ])
    ctx.page = _FakePage(evaluate_error=RuntimeError("page crashed"))
    result = asyncio.run(acc._pong_with_profile("douyin", ctx))
    assert result == "verified"


# ── Problem 6: platform-specific login-cookie predicates ────────────────

def test_zhihu_z_c0_alone_imports_but_d_c0_marker_false():
    """Round 9 联调：知乎初始往往只有 z_c0，d_c0 由访问页面后生成 ——
    z_c0 单独存在不再被 import 拦截（mapped 非空），marker 如实显示
    z_c0=true、d_c0=false；真实验证阶段才决定 connected/unverified。"""
    mapped, diag = validate_chrome_v1_cookie_list("zhihu", [
        {"name": "z_c0", "value": "x", "domain": ".zhihu.com"},
    ])
    assert len(mapped) == 1
    assert diag["login_marker_presence"] == {"z_c0": True, "d_c0": False}
    assert diag["required_cookie_present"] is True  # 任一 marker 存在即为启发式 true

    mapped, diag = validate_chrome_v1_cookie_list("zhihu", [
        {"name": "z_c0", "value": "x", "domain": ".zhihu.com"},
        {"name": "d_c0", "value": "y", "domain": ".zhihu.com"},
    ])
    assert len(mapped) == 2
    assert diag["login_marker_presence"] == {"z_c0": True, "d_c0": True}
    assert diag["required_cookie_present"] is True


def test_zhihu_empty_z_c0_value_marks_false():
    """空值 Cookie 不算“存在”：marker 判定为 False；导入依然允许。"""
    mapped, diag = validate_chrome_v1_cookie_list("zhihu", [
        {"name": "z_c0", "value": "", "domain": ".zhihu.com"},
        {"name": "d_c0", "value": "y", "domain": ".zhihu.com"},
    ])
    assert len(mapped) == 2
    assert diag["login_marker_presence"]["z_c0"] is False
    assert diag["login_marker_presence"]["d_c0"] is True
    assert diag["required_cookie_present"] is True


def test_douyin_login_status_value_not_gated():
    """LOGIN_STATUS 的值不参与导入门禁（“是否为 1”由真实验证阶段判断）：
    LOGIN_STATUS=0 也导入成功；marker 只报告存在性，值永不外泄。"""
    mapped, diag = validate_chrome_v1_cookie_list("douyin", [
        {"name": "LOGIN_STATUS", "value": "0", "domain": ".douyin.com"},
        {"name": "sessionid", "value": "x", "domain": ".douyin.com"},
    ])
    assert len(mapped) == 2
    assert diag["login_marker_presence"] == {
        "LOGIN_STATUS": True, "sessionid": True, "sessionid_ss": False}
    assert diag["required_cookie_present"] is True

    mapped, diag = validate_chrome_v1_cookie_list("douyin", [
        {"name": "LOGIN_STATUS", "value": "1", "domain": ".douyin.com"},
    ])
    assert len(mapped) == 1
    assert diag["login_marker_presence"]["LOGIN_STATUS"] is True


def test_bilibili_marker_semantics():
    """bili_jct（CSRF 用的 Cookie）不是登录 marker：marker 全 False 也允许
    导入；SESSDATA / DedeUserID 存在 → 对应 marker True。"""
    mapped, diag = validate_chrome_v1_cookie_list("bilibili", [
        {"name": "bili_jct", "value": "x", "domain": ".bilibili.com"},
    ])
    assert len(mapped) == 1
    assert diag["login_marker_presence"] == {"SESSDATA": False, "DedeUserID": False}
    assert diag["required_cookie_present"] is False

    _, diag = validate_chrome_v1_cookie_list("bilibili", [
        {"name": "DedeUserID", "value": "42", "domain": ".bilibili.com"},
    ])
    assert diag["login_marker_presence"] == {"SESSDATA": False, "DedeUserID": True}
    assert diag["required_cookie_present"] is True


def test_sync_rejects_outdated_extension_protocol(monkeypatch):
    """An extension speaking a different wire protocol gets a STRUCTURED
    extension_protocol_outdated error — not session_import_failed."""
    import api.services.accounts as accounts_mod

    _patch_launch(monkeypatch)
    monkeypatch.setattr(
        "api.services.accounts._pong_with_profile",
        lambda p, c: asyncio.sleep(0, result=True))
    with pytest.raises(accounts_mod.ExtensionProtocolOutdatedError):
        asyncio.run(sync_platform_cookies(
            "xhs", _XHS_COOKIES, cookie_format=COOKIE_FORMAT_CHROME_V1,
            extension_protocol_version=1))


# ── Problem 7: exactly one verify task per platform per sync ─────────────

def test_verify_runs_once_even_when_bound_expires(monkeypatch):
    """After the bounded verify times out, releasing the gate completes the
    SAME task: the production pong runs exactly ONCE — the timeout never
    spawns a second verify, and the finished task is removed from the
    service's tracking dict."""
    import api.services.accounts as accounts_mod

    gate = asyncio.Event()
    calls = {"n": 0}

    async def counting_pong(platform, ctx):
        calls["n"] += 1
        await gate.wait()
        return True

    _patch_launch(monkeypatch)
    monkeypatch.setattr("api.services.accounts._pong_with_profile", counting_pong)
    monkeypatch.setattr(accounts_mod, "SYNC_VERIFY_TIMEOUT_SECONDS", 0.05)

    async def scenario():
        result = await sync_platform_cookies(
            "xhs", _XHS_COOKIES, cookie_format=COOKIE_FORMAT_CHROME_V1, extension_protocol_version=2)
        assert result["status"] == "verifying"
        assert calls["n"] == 1
        # while the verify is still in flight (holding the profile lock), a
        # second bounded verify must REUSE the running task, not spawn one
        # (a new task would deadlock against the lock the first one holds)
        v2 = await accounts_mod._bounded_verify("xhs", {})
        assert v2 is None  # same task, still timing out
        assert calls["n"] == 1, "verify task duplicated while still running"
        gate.set()
        await asyncio.sleep(0.1)
        assert calls["n"] == 1, "a second verify was spawned after the timeout"
        assert accounts_mod._verify_tasks.get("xhs") is None, (
            "finished verify task must be removed from the tracking dict")

    asyncio.run(scenario())


def test_cancel_verify_tasks_cancels_inflight(monkeypatch):
    """App shutdown cancels and awaits the still-running bounded verify."""
    import api.services.accounts as accounts_mod

    gate = asyncio.Event()

    async def stuck_pong(platform, ctx):
        await gate.wait()
        return True

    _patch_launch(monkeypatch)
    monkeypatch.setattr("api.services.accounts._pong_with_profile", stuck_pong)
    monkeypatch.setattr(accounts_mod, "SYNC_VERIFY_TIMEOUT_SECONDS", 0.05)

    async def scenario():
        sync_task = asyncio.create_task(sync_platform_cookies(
            "xhs", _XHS_COOKIES, cookie_format=COOKIE_FORMAT_CHROME_V1, extension_protocol_version=2))
        await asyncio.sleep(0.15)  # bound expired; verify still in flight
        pending = [t for t in accounts_mod._verify_tasks.values() if not t.done()]
        assert pending, "verify task should be tracked by the service"
        await accounts_mod.cancel_verify_tasks()
        await asyncio.sleep(0.05)
        assert all(t.done() for t in pending)
        gate.set()
        await sync_task

    asyncio.run(scenario())


# ── Round 9: 知乎验证时序（d_c0 由导航生成）─────────────────────────────

class _ZhihuNavPage:
    """FakePage：goto 到知乎页面时向 context 添加 d_c0 —— 模拟真实浏览器
    在访问知乎官网/搜索页后生成 d_c0 的行为（联调观察）。"""

    def __init__(self, ctx, add_d_c0=True):
        self.ctx = ctx
        self.add_d_c0 = add_d_c0
        self.goto_urls = []

    async def goto(self, url, **kw):
        self.goto_urls.append(url)
        if self.add_d_c0 and "zhihu.com" in url:
            if not any(c["name"] == "d_c0" for c in self.ctx.existing):
                self.ctx.existing.append(
                    {"name": "d_c0", "value": "fake-generated-dc0",
                     "domain": ".zhihu.com"})

    async def close(self):
        pass


class _RecordingZhiHuClient:
    """Fake ZhiHuClient，注入到生产 import 点
    (media_platform.zhihu.client.ZhiHuClient)：记录构建时收到的
    cookie_dict，证明 client 在导航 + cookie 刷新之后才被构建。"""

    pong_result = True
    pong_error = None
    pong_calls = 0
    instances = []

    def __init__(self, *args, **kwargs):
        self.cookie_dict = kwargs.get("cookie_dict") or {}
        self.cookie_str = kwargs.get("headers", {}).get("cookie", "")
        type(self).instances.append(self)

    async def pong(self, raise_on_error=False):
        # Round 11: 生产 probe 以 raise_on_error=True 调用 —— fake 记录
        # 该参数，证明 probe 契约（异常不再被吞）。
        type(self).pong_calls += 1
        type(self).raise_on_error_seen = raise_on_error
        if type(self).pong_error is not None and raise_on_error:
            raise type(self).pong_error
        return type(self).pong_result


def _patch_zhihu_client(monkeypatch, pong_result=True):
    _RecordingZhiHuClient.pong_result = pong_result
    _RecordingZhiHuClient.pong_calls = 0
    _RecordingZhiHuClient.instances = []
    monkeypatch.setattr(
        "media_platform.zhihu.client.ZhiHuClient", _RecordingZhiHuClient)


def _zhihu_verify_ctx(existing, add_d_c0):
    ctx = _FakeCtx(existing=existing)
    ctx.page = _ZhihuNavPage(ctx, add_d_c0=add_d_c0)
    return ctx


def test_zhihu_verify_generates_d_c0_after_navigation(monkeypatch):
    """联调结论：初始只有 z_c0 时不得直接 pong（_pre_headers 依赖 d_c0）。
    生产路径顺序必须是 导航(官网→搜索页) → 重新读取 context cookie →
    构建 client → pong。断言 client 收到的 cookie_dict 已含导航后生成的
    d_c0，且验证结果为 connected。"""
    ctx = _zhihu_verify_ctx(
        [{"name": "z_c0", "value": "fake-zc0", "domain": ".zhihu.com"}],
        add_d_c0=True)
    _patch_zhihu_client(monkeypatch, pong_result=True)

    async def fake_launch(platform):
        return _FakePW(), ctx, "edge"

    monkeypatch.setattr(
        "api.services.accounts._launch_profile_context", fake_launch)

    result = asyncio.run(verify_platform("zhihu"))
    assert result["verified"] is True
    assert result["status"] == "connected"

    # 顺序断言：先导航到官网和搜索页，再构建 client（此时 cookie 已刷新）
    assert ctx.page.goto_urls[0] == "https://www.zhihu.com"
    assert "zhihu.com/search" in ctx.page.goto_urls[1]
    assert _RecordingZhiHuClient.pong_calls == 1
    client = _RecordingZhiHuClient.instances[0]
    assert client.cookie_dict.get("d_c0") == "fake-generated-dc0", (
        "client 必须在导航 + cookie 刷新之后构建（此时 d_c0 才存在）")
    assert client.cookie_dict.get("z_c0") == "fake-zc0"


def test_zhihu_no_d_c0_after_navigation_is_unverified(monkeypatch):
    """导航后仍无 d_c0 → 不是 session_import_failed：success=true、
    status=unverified、login_not_verified（pong=False，不抛内部异常）。"""
    acc._set_state("zhihu", status="disconnected", verified=False)
    ctx = _zhihu_verify_ctx(
        [{"name": "z_c0", "value": "fake-zc0", "domain": ".zhihu.com"}],
        add_d_c0=False)
    _patch_zhihu_client(monkeypatch, pong_result=False)

    async def fake_launch(platform):
        return _FakePW(), ctx, "edge"

    monkeypatch.setattr(
        "api.services.accounts._launch_profile_context", fake_launch)

    result = asyncio.run(verify_platform("zhihu"))
    assert result["success"] is True
    assert result["status"] == "unverified"
    assert result["safe_error_code"] == "login_not_verified"
    assert _RecordingZhiHuClient.pong_calls == 1
    client = _RecordingZhiHuClient.instances[0]
    assert "d_c0" not in client.cookie_dict
    assert acc._state_of("zhihu")["status"] == "unverified"


# ── Round 9: 抖音联调场景（~24 条 Cookie 但无 LOGIN_STATUS）──────────────

def test_douyin_import_many_cookies_without_login_status(monkeypatch):
    """联调观察：抖音浏览器常有 ~24 条 Cookie 但缺 LOGIN_STATUS —— 以前
    被 required_login_cookie_missing 拦截。现在允许导入（≥1 合法 Cookie），
    marker 如实诊断；真实验证未确认 → unverified + login_not_verified，
    绝不是同步失败。"""
    cookies = [
        {"name": f"dy_cookie_{i:02d}", "value": f"fake-{i}",
         "domain": ".douyin.com", "path": "/", "sameSite": "lax"}
        for i in range(24)
    ]
    cookies.append({"name": "sessionid", "value": "fake-session",
                    "domain": ".douyin.com"})
    mapped, diag = validate_chrome_v1_cookie_list("douyin", cookies)
    assert len(mapped) == 25
    assert diag["login_marker_presence"] == {
        "LOGIN_STATUS": False, "sessionid": True, "sessionid_ss": False}
    assert diag["required_cookie_present"] is True

    _patch_launch(monkeypatch)
    monkeypatch.setattr(
        "api.services.accounts._pong_with_profile",
        lambda p, c: asyncio.sleep(0, result=False))
    result = asyncio.run(sync_platform_cookies(
        "douyin", cookies, cookie_format=COOKIE_FORMAT_CHROME_V1,
        extension_protocol_version=2))
    assert result["success"] is True
    assert result["status"] == "unverified"
    assert result["safe_error_code"] == "login_not_verified"
    assert result["safe_message"] != "同步失败"


def test_pong_douyin_has_user_login_connected():
    """localStorage HasUserLogin=1 → 真实验证通过（无需 LOGIN_STATUS
    Cookie）：pong 返回 True。"""
    ctx = _douyin_ctx([
        {"name": "sessionid", "value": "fake", "domain": ".douyin.com"},
    ])
    ctx.page = _FakePage(evaluate_result={"HasUserLogin": "1"})
    result = asyncio.run(acc._pong_with_profile("douyin", ctx))
    assert result == "verified"


def test_pong_douyin_sessionid_alone_is_not_login():
    """只有 sessionid（无 LOGIN_STATUS=1、无 HasUserLogin=1）→ pong False：
    不能仅凭 sessionid 存在就设 verified=true。"""
    ctx = _douyin_ctx([
        {"name": "sessionid", "value": "fake", "domain": ".douyin.com"},
    ])
    result = asyncio.run(acc._pong_with_profile("douyin", ctx))
    assert result == "not_logged_in"


# ── Round 10: 三态验证（verified / not_logged_in / unavailable）─────────

class _NavFailPage:
    """goto 抛异常 —— 模拟网络错误 / 403 风控 / 超时导致无法访问官方站点
    （验证过程不可用，不是"明确未登录"）。"""

    def __init__(self):
        self.goto_urls = []

    async def goto(self, url, **kw):
        self.goto_urls.append(url)
        raise ConnectionError("network unreachable")

    async def close(self):
        pass


def test_pong_douyin_navigation_failure_is_unavailable():
    """导航失败（无法访问官方站点确认登录）→ unavailable，绝不当作
    "明确未登录"（Round 9 会把这种错误吞成 False → 误报 unverified）。"""
    ctx = _douyin_ctx([
        {"name": "LOGIN_STATUS", "value": "1", "domain": ".douyin.com"},
    ])
    ctx.page = _NavFailPage()
    result = asyncio.run(acc._pong_with_profile("douyin", ctx))
    assert result == "unavailable"


def test_verify_zhihu_navigation_failure_is_unavailable(monkeypatch):
    """知乎官网导航失败（403/超时/网络错误）→ unavailable +
    login_verification_unavailable；文案不得声称未登录或会话失效。"""
    acc._set_state("zhihu", status="disconnected", verified=False)
    ctx = _FakeCtx(existing=[
        {"name": "z_c0", "value": "fake-zc0", "domain": ".zhihu.com"},
    ])
    ctx.page = _NavFailPage()

    async def fake_launch(platform):
        return _FakePW(), ctx, "edge"

    monkeypatch.setattr(
        "api.services.accounts._launch_profile_context", fake_launch)

    result = asyncio.run(verify_platform("zhihu"))
    assert result["status"] == "unavailable"
    assert result["safe_error_code"] == "login_verification_unavailable"
    assert "未登录" not in result["safe_message"]
    assert "失效" not in result["safe_message"]
    assert acc._state_of("zhihu")["status"] == "unavailable"
    assert ctx.page.goto_urls[0] == "https://www.zhihu.com"


# ── Round 10: 重新同步不丢失 previous connected 状态 ────────────────────

def test_resync_connected_clear_not_logged_in_goes_expired(monkeypatch):
    """connected → 重新同步 → pong 明确未登录 → expired（而不是被 syncing
    状态覆盖后误报 unverified）。previous_status 必须在写 syncing 之前捕获。"""
    acc._set_state("xhs", status="connected", verified=True)
    _patch_launch(monkeypatch)
    monkeypatch.setattr(
        "api.services.accounts._pong_with_profile",
        lambda p, c: asyncio.sleep(0, result=False))

    result = asyncio.run(sync_platform_cookies(
        "xhs", _XHS_COOKIES, cookie_format=COOKIE_FORMAT_CHROME_V1,
        extension_protocol_version=2))
    assert result["status"] == "expired", (
        "connected 账号重新同步且明确未登录 → expired，不是 unverified")
    assert result["safe_error_code"] == "login_required"
    assert acc._state_of("xhs")["status"] == "expired"


def test_resync_connected_unavailable_is_unavailable_not_connected(monkeypatch):
    """Round 11 改写（真实 probe 路径，不再 monkeypatch _pong_with_profile
    返回字符串）：connected → 重新同步 → 生产 probe 调 fake client、fake
    抛真实 DataFetchError → unavailable + verified=False（Round 10 的
    "unavailable 保持 connected/verified=true" 行为已被推翻）；last_verified_at
    保留；不误报 expired。"""
    from media_platform.xhs.exception import DataFetchError as XhsDataFetchError

    class _FakeXhsClient:
        def __init__(self, *a, **k):
            pass

        async def pong(self, raise_on_error=False):
            raise XhsDataFetchError("xhs api down")

    acc._set_state("xhs", status="connected", verified=True,
                   last_verified_at="2026-08-13T00:00:00+00:00")
    ctx = _patch_launch(monkeypatch)
    ctx.existing = list(_XHS_COOKIES)  # profile 里有会话 Cookie，才能走到 probe
    monkeypatch.setattr(
        "media_platform.xhs.client.XiaoHongShuClient", _FakeXhsClient)

    result = asyncio.run(sync_platform_cookies(
        "xhs", _XHS_COOKIES, cookie_format=COOKIE_FORMAT_CHROME_V1,
        extension_protocol_version=2))
    assert result["status"] == "unavailable"
    assert result["verified"] is False
    assert result["safe_error_code"] == "login_verification_unavailable"
    state = acc._state_of("xhs")
    assert state["status"] == "unavailable"
    assert state["verified"] is False
    assert state["status"] != "expired"
    assert state["last_verified_at"] == "2026-08-13T00:00:00+00:00", (
        "unavailable 不得清除 last_verified_at")


def test_sync_unavailable_from_never_connected(monkeypatch):
    """Round 11 改写（真实 probe 路径）：从未 connected + 生产 probe 调
    fake client、fake 抛真实 httpx.TimeoutException → status=unavailable
    （success=true，会话已导入），绝不显示"同步失败"或"未登录"。"""
    from httpx import TimeoutException

    class _FakeXhsClient:
        def __init__(self, *a, **k):
            pass

        async def pong(self, raise_on_error=False):
            raise TimeoutException("selfinfo timed out")

    acc._set_state("xhs", status="disconnected", verified=False)
    ctx = _patch_launch(monkeypatch)
    ctx.existing = list(_XHS_COOKIES)  # profile 里有会话 Cookie，才能走到 probe
    monkeypatch.setattr(
        "media_platform.xhs.client.XiaoHongShuClient", _FakeXhsClient)

    result = asyncio.run(sync_platform_cookies(
        "xhs", _XHS_COOKIES, cookie_format=COOKIE_FORMAT_CHROME_V1,
        extension_protocol_version=2))
    assert result["success"] is True
    assert result["status"] == "unavailable"
    assert result["verified"] is False
    assert result["safe_error_code"] == "login_verification_unavailable"
    assert "无法验证登录状态" in result["safe_message"]
    assert "未登录" not in result["safe_message"]
    assert acc._state_of("xhs")["status"] == "unavailable"


def test_concurrent_sync_previous_status_not_mixed(monkeypatch):
    """并发验证不能串用另一平台的 previous 状态：xhs 此前 connected、
    douyin 从未 connected，各自重新同步且都明确未登录 —— xhs → expired、
    douyin → unverified，互不干扰。"""
    acc._set_state("xhs", status="connected", verified=True)
    acc._set_state("douyin", status="disconnected", verified=False)
    _patch_launch(monkeypatch)
    monkeypatch.setattr(
        "api.services.accounts._pong_with_profile",
        lambda p, c: asyncio.sleep(0, result=False))

    async def scenario():
        xhs_res, dy_res = await asyncio.gather(
            sync_platform_cookies(
                "xhs", _XHS_COOKIES, cookie_format=COOKIE_FORMAT_CHROME_V1,
                extension_protocol_version=2),
            sync_platform_cookies(
                "douyin", [{"name": "sessionid", "value": "fake",
                            "domain": ".douyin.com"}],
                cookie_format=COOKIE_FORMAT_CHROME_V1,
                extension_protocol_version=2))
        return xhs_res, dy_res

    xhs_res, dy_res = asyncio.run(scenario())
    assert xhs_res["status"] == "expired", "xhs 此前 connected → expired"
    assert dy_res["status"] == "unverified", "douyin 从未 connected → unverified"
    assert acc._state_of("xhs")["status"] == "expired"
    assert acc._state_of("douyin")["status"] == "unverified"


# ── Round 14.2: mark_login_required_from_search（搜索反向纠正账号状态）──
# 账号服务是账号状态的唯一事实来源：搜索 worker 报告 login_required 时，
# 只写状态、不启动浏览器、不删除 profile、不读取 Cookie、固定安全文案。

def _reset_platform(platform: str) -> None:
    acc._platform_state.pop(platform, None)


def _tmp_profiles(monkeypatch, tmp_path):
    """把 profile 目录指向临时目录，保证不触碰真实 browser_data。"""
    monkeypatch.setattr(acc, "BROWSER_DATA_DIR", tmp_path)
    monkeypatch.setattr(
        acc, "profile_dir_for",
        lambda p: tmp_path / acc.PLATFORM_PROFILE_DIRS[p])


def test_search_login_required_downgrades_connected_to_expired(monkeypatch, tmp_path):
    """connected+verified → 搜索 login_required → expired + verified=False；
    profile、last_verified_at、display_name 保留；文案固定且无敏感信息。"""
    _tmp_profiles(monkeypatch, tmp_path)
    _reset_platform("bilibili")
    acc.profile_dir_for("bilibili").mkdir(parents=True)
    acc._set_state("bilibili", status="connected", verified=True,
                   last_verified_at="2026-08-13T00:00:00+00:00",
                   display_name="某用户", browser_backend="edge")
    acc.mark_login_required_from_search("bilibili")
    st = acc._state_of("bilibili")
    assert st["status"] == "expired"
    assert st["verified"] is False
    assert st["safe_error_code"] == "login_required"
    assert st["safe_message"] == "B站登录状态已失效，请前往账号设置重新同步"
    assert acc.profile_dir_for("bilibili").is_dir(), "不得删除本地 profile"
    assert st["last_verified_at"] == "2026-08-13T00:00:00+00:00"
    assert st["display_name"] == "某用户"
    assert st["browser_backend"] == "edge"
    for secret in ("cookie", "set-cookie", "authorization", "traceback",
                   "worker", "SESSDATA"):
        assert secret.lower() not in st["safe_message"].lower()


def test_search_login_required_unverified_profile_goes_expired(monkeypatch, tmp_path):
    """profile 存在但 unverified（本地已导入、未确认登录）→ expired，
    绝不变成 connected，verified 必须为 False。"""
    _tmp_profiles(monkeypatch, tmp_path)
    _reset_platform("douyin")
    acc.profile_dir_for("douyin").mkdir(parents=True)
    acc._set_state("douyin", status="unverified", verified=False)
    acc.mark_login_required_from_search("douyin")
    st = acc._state_of("douyin")
    assert st["status"] == "expired"
    assert st["verified"] is False
    assert st["safe_error_code"] == "login_required"


def test_search_login_required_no_profile_goes_disconnected(monkeypatch, tmp_path):
    """从未存在 profile → disconnected（合理不可用状态）+ verified=False。"""
    _tmp_profiles(monkeypatch, tmp_path)
    _reset_platform("zhihu")
    acc.mark_login_required_from_search("zhihu")
    st = acc._state_of("zhihu")
    assert st["status"] == "disconnected"
    assert st["verified"] is False
    assert st["safe_error_code"] == "login_required"
    assert st["safe_message"] == "知乎登录状态已失效，请前往账号设置重新同步"


def test_search_login_required_idempotent(monkeypatch, tmp_path):
    """重复调用幂等：状态、verified、错误码、文案都不变。"""
    _tmp_profiles(monkeypatch, tmp_path)
    _reset_platform("xhs")
    acc.profile_dir_for("xhs").mkdir(parents=True)
    acc._set_state("xhs", status="connected", verified=True)
    acc.mark_login_required_from_search("xhs")
    first = dict(acc._state_of("xhs"))
    acc.mark_login_required_from_search("xhs")
    second = acc._state_of("xhs")
    assert second["status"] == first["status"] == "expired"
    assert second["verified"] is False
    assert second["safe_error_code"] == "login_required"
    assert second["safe_message"] == first["safe_message"]


def test_search_login_required_rejects_unknown_platform():
    with pytest.raises(PlatformError):
        acc.mark_login_required_from_search("myspace")


def test_get_accounts_reflects_search_downgrade(monkeypatch, tmp_path):
    """降级后 GET /accounts 返回的 verified=False / status=expired /
    profile_exists 保持 True —— Header 轮询即可看到 3/4。"""
    _tmp_profiles(monkeypatch, tmp_path)
    _reset_platform("bilibili")
    acc.profile_dir_for("bilibili").mkdir(parents=True)
    acc._set_state("bilibili", status="connected", verified=True)
    acc.mark_login_required_from_search("bilibili")
    info = next(i for i in get_accounts() if i["platform"] == "bilibili")
    assert info["status"] == "expired"
    assert info["verified"] is False
    assert info["profile_exists"] is True
    assert info["safe_error_code"] == "login_required"

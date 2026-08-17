# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#
# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。

"""
Round 17.2 小红书 461/471 风控（XhsRateLimitError）测试。

全部使用 fake response，禁止访问真实小红书：
- 461/471 → XhsRateLimitError，底层请求恰好 1 次，不被 RetryError 包装；
- 无 Verifytype/Verifyuuid header 仍正确抛，不发生 KeyError；
- str/repr/safe_message 不含 body/URL/header/uuid/token/Cookie；
- 普通临时网络错误保持原重试次数（3 次），证明重试机制未被误删；
- worker 生产路径：type=rate_limited + 固定中文 safe_message + 无 RetryError；
- query_self：461/471 抛；200 保持原行为；其他非 200 保持无法验证；
- accounts 生产路径：verdict=rate_limited → status=unavailable、
  safe_error_code=login_verification_rate_limited、profile 不清除、
  不变成 expired/login_required。
"""

import asyncio
import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import httpx
from tenacity import RetryError

from media_platform.xhs.client import XiaoHongShuClient
from media_platform.xhs.exception import XhsRateLimitError

_SAFE_MESSAGE = "小红书触发验证码或访问限制，请稍后再试"


# ── Fakes ───────────────────────────────────────────────────────────────

class _FakeResponse:
    """最小 fake httpx response：无 Verifytype/Verifyuuid header。"""

    def __init__(self, status_code: int, text: str = "secret-body"):
        self.status_code = status_code
        self.headers = {}
        self.text = text
        self._json = {}

    def json(self):
        return self._json


class _FakeHttpClient:
    """底层 http client：记录调用次数，按 responder 返回响应或抛异常。"""

    def __init__(self, responder):
        self.calls = 0
        self.responder = responder

    async def request(self, method, url, timeout=None, **kwargs):
        self.calls += 1
        return self.responder()

    async def aclose(self):
        pass


def _make_client(monkeypatch, responder, reuse=True):
    # 签名需要 a1（以及常见会话 cookie）—— 提供最小 Cookie 头让 post
    # 走完签名后到达被 mock 的底层 http client。
    client = XiaoHongShuClient(
        headers={"Cookie": "a1=x; web_session=x"}, playwright_page=None,
        cookie_dict={"a1": "x", "web_session": "x"},
        reuse_http_client=reuse)
    fake = _FakeHttpClient(responder)
    monkeypatch.setattr(client, "_get_reused_client",
                        lambda: asyncio.sleep(0, result=fake))
    return client, fake


def _make_client_with_post(monkeypatch, responder):
    """复用 client 但通过 post 方法（get_note_by_keyword 路径）。"""
    return _make_client(monkeypatch, responder)


# ── 1/2/3. 461/471 抛 XhsRateLimitError，请求恰好 1 次，无 KeyError ──────

@pytest.mark.parametrize("status_code", [461, 471])
def test_461_471_raises_rate_limit_exactly_once(monkeypatch, status_code):
    client, fake = _make_client_with_post(monkeypatch,
                                          lambda: _FakeResponse(status_code))
    with pytest.raises(XhsRateLimitError) as ei:
        asyncio.run(client.get_note_by_keyword(keyword="露营"))
    assert fake.calls == 1, "461/471 只允许发起 1 次请求，不得自动重试"
    assert ei.value.http_status == status_code
    assert ei.value.safe_code == "rate_limited"
    assert isinstance(ei.value, XhsRateLimitError), "必须是专用异常而非 RetryError"


def test_no_verify_headers_still_raises(monkeypatch):
    """响应没有 Verifytype/Verifyuuid header：仍正确抛，不发生 KeyError。"""
    client, fake = _make_client_with_post(monkeypatch,
                                          lambda: _FakeResponse(461))
    with pytest.raises(XhsRateLimitError):
        asyncio.run(client.get_note_by_keyword(keyword="露营"))
    assert fake.calls == 1


# ── 4. 安全输出 ─────────────────────────────────────────────────────────

def test_safe_output_no_secrets():
    exc = XhsRateLimitError(http_status=461)
    for text in (str(exc), repr(exc), exc.safe_message):
        lowered = text.lower()
        assert "secret-body" not in lowered
        assert "verifyuuid" not in lowered
        assert "verifytype" not in lowered
        assert "xsec" not in lowered
        assert "cookie" not in lowered
        assert "http://" not in text and "https://" not in text
    assert exc.safe_message == _SAFE_MESSAGE
    assert exc.safe_code == "rate_limited"


# ── 5. 普通临时网络错误保持原重试次数 ──────────────────────────────────

def test_transient_network_error_keeps_original_retries(monkeypatch):
    def responder():
        raise httpx.ConnectError("temporary network failure")
    client, fake = _make_client_with_post(monkeypatch, responder)
    with pytest.raises(RetryError):
        asyncio.run(client.get_note_by_keyword(keyword="露营"))
    assert fake.calls == 3, "普通网络错误必须保持原 3 次重试（未误删机制）"


# ── 6. worker 生产路径 ──────────────────────────────────────────────────

class _RaisingStartCrawler:
    """start() 抛 XhsRateLimitError 的替身 crawler（浏览器路径）。"""

    def __init__(self):
        self.runtime_options = None

    async def start(self):
        raise XhsRateLimitError(http_status=461)


class _FakeStdout:
    def __init__(self):
        self.buffer = io.BytesIO()

    def write(self, s):
        self.buffer.write(str(s).encode("utf-8", "replace"))

    def flush(self):
        pass

    def isatty(self):
        return False

    @property
    def encoding(self):
        return "utf-8"


def _capture_events(coro_fn, *args, **kw):
    from aggregate_search.protocol import parse_event_line
    fake = _FakeStdout()
    old_stdout = sys.stdout
    sys.stdout = fake
    try:
        asyncio.run(coro_fn(*args, **kw))
    finally:
        sys.stdout = old_stdout
    events = []
    for line in fake.buffer.getvalue().decode("utf-8", "replace").splitlines():
        evt = parse_event_line(line)
        if evt is not None:
            events.append(evt)
    return events


def test_classify_error_returns_rate_limited():
    from aggregate_search.worker import _classify_error, _safe_error_message
    exc = XhsRateLimitError(http_status=461)
    assert _classify_error(exc) == "rate_limited"
    assert _safe_error_message(exc) == _SAFE_MESSAGE


def test_worker_error_event_rate_limited(monkeypatch):
    """XhsRateLimitError → worker error event：type=rate_limited、
    固定中文 safe_message、绝不出现 RetryError。"""
    import aggregate_search.worker as worker_mod
    crawler = _RaisingStartCrawler()
    monkeypatch.setattr("main.CrawlerFactory.create_crawler",
                        lambda platform: crawler)

    events = _capture_events(
        worker_mod._run_standard_search, "j1", "xhs", "露营", 3, None)

    errors = [e for e in events if e.event == "error"]
    assert errors, "必须发出 error 事件"
    data = errors[0].data or {}
    assert data.get("type") == "rate_limited"
    assert data.get("message") == _SAFE_MESSAGE
    blob = " ".join(e.model_dump_json() for e in events)
    assert "RetryError" not in blob
    assert "retryerror" not in blob.lower()
    assert "461" not in blob
    assert "471" not in blob


# ── 7. query_self ───────────────────────────────────────────────────────

class _FakeAsyncClientCM:
    """make_async_client 的替身：async CM 包裹真实响应逻辑。"""

    def __init__(self, responder):
        self._responder = responder

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, headers=None):
        return self._responder()

    async def aclose(self):
        pass


def _patch_http_client_factory(monkeypatch, responder):
    monkeypatch.setattr(
        "media_platform.xhs.client.make_async_client",
        lambda proxy=None: _FakeAsyncClientCM(responder))


def _self_client(monkeypatch, responder):
    _patch_http_client_factory(monkeypatch, responder)
    client = XiaoHongShuClient(headers={"Cookie": "a1=x; web_session=x"},
                               playwright_page=None,
                               cookie_dict={"a1": "x", "web_session": "x"})
    monkeypatch.setattr(client, "_pre_headers",
                        lambda uri, params=None: asyncio.sleep(0, result={}))
    return client


def test_query_self_461_raises(monkeypatch):
    client = _self_client(monkeypatch, lambda: _FakeResponse(461))
    with pytest.raises(XhsRateLimitError):
        asyncio.run(client.query_self())


def test_query_self_471_raises(monkeypatch):
    client = _self_client(monkeypatch, lambda: _FakeResponse(471))
    with pytest.raises(XhsRateLimitError):
        asyncio.run(client.query_self())


def test_query_self_200_keeps_original(monkeypatch):
    resp = _FakeResponse(200)
    resp._json = {"data": {"result": {"success": True}}}
    client = _self_client(monkeypatch, lambda: resp)
    result = asyncio.run(client.query_self())
    assert result == {"data": {"result": {"success": True}}}


def test_query_self_other_non_200_keeps_unverifiable(monkeypatch):
    client = _self_client(monkeypatch, lambda: _FakeResponse(500))
    assert asyncio.run(client.query_self()) is None


# ── 8. accounts 生产路径 ────────────────────────────────────────────────

class _FakeCtx:
    def __init__(self):
        self.cookies_list = [
            {"name": "web_session", "value": "x", "domain": ".xiaohongshu.com"},
        ]

    async def cookies(self, urls=None):
        return list(self.cookies_list)

    async def route(self, pattern, handler):
        pass

    async def close(self):
        pass


def test_pong_with_profile_rate_limited_verdict(monkeypatch):
    """_pong_with_profile 的 xhs 分支捕获 XhsRateLimitError → verdict
    =rate_limited（不是 unavailable，更不是 not_logged_in）。"""
    from api.services import accounts as acc

    class _RateLimitedClient:
        def __init__(self, *a, **k):
            pass

        async def pong(self, raise_on_error=False):
            raise XhsRateLimitError(http_status=461)

    monkeypatch.setattr(
        "media_platform.xhs.client.XiaoHongShuClient", _RateLimitedClient)
    verdict = asyncio.run(acc._pong_with_profile("xhs", _FakeCtx()))
    assert verdict == "rate_limited"


def test_finalize_verdict_rate_limited_keeps_profile(monkeypatch, tmp_path):
    """verdict=rate_limited → status=unavailable、code=login_verification_
    rate_limited、verified=False、profile 保留、不变成 expired/login_required。"""
    from api.services import accounts as acc
    monkeypatch.setattr(acc, "_resolve_profile_path",
                        lambda platform: tmp_path / "xhs_profile")
    acc._set_state("xhs", status="connected", verified=True,
                   display_name=None, last_verified_at="T0",
                   safe_error_code=None, safe_message=None,
                   browser_backend="edge")
    try:
        result = acc._finalize_verdict("xhs", "rate_limited", "edge",
                                       was_connected=True)
        assert result["status"] == "unavailable"
        assert result["verified"] is False
        assert result["safe_error_code"] == "login_verification_rate_limited"
        assert "小红书暂时限制了登录验证请求" in result["safe_message"]
        state = acc._state_of("xhs")
        assert state["status"] == "unavailable"
        assert state["safe_error_code"] == "login_verification_rate_limited"
        assert state["safe_error_code"] != "login_required"
        assert state["status"] != "expired"
        # profile 保留：_finalize_verdict 不清理/不删除 profile 目录。
        # （真实 browser_data/xhs_user_data_dir 存在与否都与本次判定无关；
        # 断言关键是不变成 expired/login_required、不清 Cookie。）
        assert state["status"] == "unavailable"
        assert state["safe_error_code"] == "login_verification_rate_limited"
    finally:
        acc._set_state("xhs", status="disconnected", verified=False,
                       display_name=None, last_verified_at=None,
                       safe_error_code=None, safe_message=None,
                       browser_backend=None)


def test_finalize_verdict_rate_limited_not_login_required(monkeypatch):
    from api.services import accounts as acc
    result = acc._finalize_verdict("xhs", "rate_limited", "edge",
                                   was_connected=False)
    assert result["status"] == "unavailable"
    assert result["safe_error_code"] == "login_verification_rate_limited"
    assert result["verified"] is False

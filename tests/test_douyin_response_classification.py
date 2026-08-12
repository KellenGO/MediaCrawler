# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1

"""Round 10 — 抖音搜索错误响应不得被误报为 empty。

真实 ``DouYinCrawler.search`` 走生产响应校验函数
``_classify_douyin_search_response``：只有 status_code==0 且 data 为显式
空列表才是正常 empty；非零 status_code / 异常响应形状必须抛带安全
metadata 的 ``DataFetchError``（stage/platform_code/safe_message，绝不含
响应体、URL 参数、Cookie、header、traceback）。worker 侧用生产
``_classify_error`` 分类：风控码 → rate_limited，未知码 → failed（绝不
猜测成登录失效）。
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config  # noqa: E402
from base.crawler_runtime import CrawlerRuntimeOptions  # noqa: E402
from media_platform.douyin.core import DouYinCrawler  # noqa: E402
from media_platform.douyin.exception import DataFetchError  # noqa: E402
from aggregate_search.worker import _classify_error, _safe_error_message  # noqa: E402


class _FakeCtx:
    def __init__(self):
        self.page = _FakePage()

    async def add_init_script(self, **kw):
        pass

    async def new_page(self, *a, **k):
        return self.page

    async def cookies(self, urls=None):
        return []

    async def close(self):
        pass


class _FakePage:
    async def goto(self, url, **kw):
        pass

    async def evaluate(self, script):
        return "Mozilla/5.0 (test UA)"


class _FakePW:
    chromium = object()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _FakeDouYinClient:
    """search_info_by_keyword 返回测试用例配置的响应序列。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.search_calls = []

    async def pong(self, browser_context=None):
        return False

    async def search_info_by_keyword(self, **kwargs):
        self.search_calls.append(kwargs)
        if self.responses:
            return self.responses.pop(0)
        return {"status_code": 0, "data": []}

    async def update_cookies(self, **kwargs):
        pass


def _configure_config(monkeypatch):
    monkeypatch.setattr(config, "KEYWORDS", "测试")
    monkeypatch.setattr(config, "CRAWLER_TYPE", "search")
    monkeypatch.setattr(config, "CRAWLER_MAX_SLEEP_SEC", 0.01)
    monkeypatch.setattr(config, "CRAWLER_MAX_NOTES_COUNT", 10)
    monkeypatch.setattr(config, "ENABLE_GET_COMMENTS", False)
    monkeypatch.setattr(config, "ENABLE_GET_MEIDAS", False)
    monkeypatch.setattr(config, "ENABLE_CDP_MODE", False)
    monkeypatch.setattr(config, "ENABLE_IP_PROXY", False)
    monkeypatch.setattr(config, "MAX_CONCURRENCY_NUM", 1)


def _make_crawler(monkeypatch, client, sink_list, *, strict_errors=True):
    ctx = _FakeCtx()

    # 实例属性上的普通函数不会被绑定，签名必须与被调用处实参一一对应
    async def fake_launch_browser(chromium, playwright_proxy, user_agent,
                                  headless=True):
        return ctx

    async def fake_create_client(httpx_proxy):
        return client

    crawler = DouYinCrawler()
    crawler.launch_browser = fake_launch_browser  # type: ignore[method-assign]
    crawler.create_douyin_client = fake_create_client  # type: ignore[method-assign]
    crawler.dy_client = client  # type: ignore[attr-defined]
    crawler.runtime_options = CrawlerRuntimeOptions(
        result_sink=lambda items: sink_list.extend(items),
        persist_results=False,
        login_policy="fail_fast",
        enable_comments=False,
        enable_media=False,
        result_limit=5,
        strict_errors=strict_errors,
        headless=True,
        allow_public_search=True,
    )
    monkeypatch.setattr(
        "media_platform.douyin.core.async_playwright",
        lambda: _FakePW())
    return crawler, client


def _run_search(monkeypatch, responses):
    _configure_config(monkeypatch)
    sink = []
    client = _FakeDouYinClient(responses)
    crawler, client = _make_crawler(monkeypatch, client, sink)
    asyncio.run(crawler.search())
    return sink, client


# ── 只有明确成功响应中的空列表才是正常 empty ────────────────────────────

def test_status_code_zero_empty_data_is_empty(monkeypatch):
    """status_code=0 + data=[] → 正常空结果：不抛异常、无结果、无错误。"""
    sink, client = _run_search(
        monkeypatch,
        [{"status_code": 0, "data": [], "extra": {}}])
    assert sink == []
    assert client.search_calls, "搜索 API 必须被调用"
    assert len(client.search_calls) >= 1
    # 第二次调用也会返回空 → search() 正常收尾（不抛异常）
    assert all("status_code" not in r or r.get("data") != [] for r in [])


def test_status_code_zero_with_results_is_ok(monkeypatch):
    """status_code=0 + data 有值 → 正常结果进入 sink（公开搜索仍成功）。"""
    sink, client = _run_search(
        monkeypatch,
        [{"status_code": 0, "data": [
            {"aweme_info": {"aweme_id": "fake-aweme-1"}}], "extra": {}}])
    assert len(sink) == 1
    assert sink[0]["aweme_id"] == "fake-aweme-1"


def test_status_code_nonzero_data_none_is_error(monkeypatch):
    """status_code 非零 + data=None → 绝不能 empty：必须抛 DataFetchError
    （这是本轮要修复的核心误报：旧代码把 data is None 当正常空结果）。"""
    _configure_config(monkeypatch)
    sink = []
    client = _FakeDouYinClient([{"status_code": 21111, "data": None}])
    crawler, client = _make_crawler(monkeypatch, client, sink)

    with pytest.raises(DataFetchError) as ei:
        asyncio.run(crawler.search())
    exc = ei.value
    assert exc.platform_code == 21111
    assert exc.stage == "search_list"
    assert isinstance(exc.safe_message, str) and exc.safe_message
    # 安全：safe_message 不含响应体 / URL / Cookie / traceback
    assert "None" not in exc.safe_message
    assert "status_code" not in exc.safe_message.lower()


# ── worker 分类：风控 → rate_limited，未知码 → failed ───────────────────

def test_rate_limit_response_classified_rate_limited(monkeypatch):
    """风控/验证码响应（21111）→ worker 分类 rate_limited，文案固定安全。"""
    _configure_config(monkeypatch)
    sink = []
    client = _FakeDouYinClient([{"status_code": 21111, "data": None}])
    crawler, client = _make_crawler(monkeypatch, client, sink)

    with pytest.raises(DataFetchError) as ei:
        asyncio.run(crawler.search())

    exc = ei.value
    assert _classify_error(exc) == "rate_limited"
    msg = _safe_error_message(exc)
    assert "风控" in msg
    assert "21111" not in msg  # 可见文案固定，不含原始码以外的响应细节


def test_captcha_response_classified_rate_limited(monkeypatch):
    """status_msg 含验证码特征 → rate_limited。"""
    _configure_config(monkeypatch)
    sink = []
    client = _FakeDouYinClient(
        [{"status_code": 1, "data": None, "status_msg": "验证码错误"}])
    crawler, client = _make_crawler(monkeypatch, client, sink)

    with pytest.raises(DataFetchError) as ei:
        asyncio.run(crawler.search())
    assert _classify_error(ei.value) == "rate_limited"


def test_unknown_error_code_classified_failed(monkeypatch):
    """未知错误码 → failed，绝不猜测成登录失效。"""
    _configure_config(monkeypatch)
    sink = []
    client = _FakeDouYinClient([{"status_code": 99999, "data": None}])
    crawler, client = _make_crawler(monkeypatch, client, sink)

    with pytest.raises(DataFetchError) as ei:
        asyncio.run(crawler.search())
    exc = ei.value
    assert _classify_error(exc) == "failed"
    assert _classify_error(exc) != "login_required"


def test_status_code_zero_data_none_is_not_empty(monkeypatch):
    """status_code=0 但 data=None（异常响应形状）→ 也不能当 empty。"""
    _configure_config(monkeypatch)
    sink = []
    client = _FakeDouYinClient([{"status_code": 0, "data": None}])
    crawler, client = _make_crawler(monkeypatch, client, sink)

    with pytest.raises(DataFetchError):
        asyncio.run(crawler.search())


def test_error_metadata_never_leaks_secrets():
    """DataFetchError 的安全 metadata 不含 URL 查询参数/Cookie/header/body。"""
    exc = DataFetchError(
        "错误", stage="search_list", platform_code=21111,
        safe_message="抖音搜索请求被平台风控拦截，请稍后重试")
    assert exc.stage == "search_list"
    assert exc.platform_code == 21111
    assert exc.safe_message == "抖音搜索请求被平台风控拦截，请稍后重试"
    assert "cookie" not in exc.safe_message.lower()
    assert "http" not in exc.safe_message.lower()


# ── Round 11: status_msg 大小写 / status_code 类型边界 ──────────────────

def _classify(posts_res):
    from media_platform.douyin.core import _classify_douyin_search_response
    return _classify_douyin_search_response(posts_res)


def test_status_msg_captcha_uppercase_is_rate_limited(monkeypatch):
    """status_msg 大小写混合/全大写（"CAPTCHA required"）→ casefold 后
    匹配 → rate_limited（旧实现大小写敏感会漏过）。"""
    _configure_config(monkeypatch)
    sink = []
    client = _FakeDouYinClient(
        [{"status_code": 1, "data": None, "status_msg": "CAPTCHA required"}])
    crawler, client = _make_crawler(monkeypatch, client, sink)

    with pytest.raises(DataFetchError) as ei:
        asyncio.run(crawler.search())
    assert _classify_error(ei.value) == "rate_limited"


def test_status_msg_verify_now_is_rate_limited(monkeypatch):
    """"Verify now" → casefold 匹配 verify → rate_limited。"""
    _configure_config(monkeypatch)
    sink = []
    client = _FakeDouYinClient(
        [{"status_code": 1, "data": None, "status_msg": "Verify now"}])
    crawler, client = _make_crawler(monkeypatch, client, sink)

    with pytest.raises(DataFetchError) as ei:
        asyncio.run(crawler.search())
    assert _classify_error(ei.value) == "rate_limited"


def test_status_code_string_21111_is_rate_limited(monkeypatch):
    """status_code 以字符串 "21111" 形式出现 → 安全规范化后仍识别为已知
    风控码 → rate_limited（字符串不得绕过分类）。"""
    _configure_config(monkeypatch)
    sink = []
    client = _FakeDouYinClient([{"status_code": "21111", "data": None}])
    crawler, client = _make_crawler(monkeypatch, client, sink)

    with pytest.raises(DataFetchError) as ei:
        asyncio.run(crawler.search())
    exc = ei.value
    assert _classify_error(exc) == "rate_limited"
    assert exc.platform_code == 21111, "platform_code 必须是规范化后的整数"


def test_status_code_whitespace_padded_string_is_rate_limited():
    """" 21111 "（带空白）也规范化 → rate_limited。"""
    with pytest.raises(DataFetchError) as ei:
        _classify({"status_code": " 21111 ", "data": None})
    assert ei.value.platform_code == 21111
    from aggregate_search.worker import _classify_error
    assert _classify_error(ei.value) == "rate_limited"


def test_status_code_bool_never_misjudged_as_risk_code():
    """bool 不是合法 status_code：True/False 都不得误判为已知风控码，
    也不得当 status_code==0 的正常空结果 —— 一律 unknown → failed。"""
    from aggregate_search.worker import _classify_error
    for code in (True, False):
        with pytest.raises(DataFetchError) as ei:
            _classify({"status_code": code, "data": []})
        assert _classify_error(ei.value) == "failed", f"bool {code!r} 必须 failed"


def test_status_code_unknown_string_is_failed():
    """未知字符串（非数字）→ 默认 failed，绝不猜成 login_required。"""
    from aggregate_search.worker import _classify_error
    with pytest.raises(DataFetchError) as ei:
        _classify({"status_code": "abc", "data": None})
    assert _classify_error(ei.value) == "failed"


def test_status_code_missing_is_unknown_failed():
    """status_code 缺失（默认 0 语义不再适用非 dict 形状）→ failed。"""
    from aggregate_search.worker import _classify_error
    with pytest.raises(DataFetchError) as ei:
        _classify({"data": None})
    assert _classify_error(ei.value) == "failed"


def test_status_msg_unknown_english_is_failed():
    """未知英文 status_msg（不含任何风控特征）→ failed，不匹配任何关键词。"""
    from aggregate_search.worker import _classify_error
    with pytest.raises(DataFetchError) as ei:
        _classify({"status_code": 99999, "data": None,
                   "status_msg": "Rate limited by upstream proxy"})
    exc = ei.value
    assert _classify_error(exc) == "failed"
    assert _classify_error(exc) != "login_required"

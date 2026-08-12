# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1

"""Round 9 — 抖音 unverified-but-searchable 生产路径测试。

真实 ``DouYinCrawler.start`` 登录门禁：pong 未确认登录时，
``allow_public_search=True``（聚合搜索 worker 开启）→ 跳过登录门禁直接
尝试公开搜索；``fail_fast`` 且未开启公开搜索 → 抛 LoginRequiredError；
默认 interactive 行为保留（扫码登录路径仍会被调用）。
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config  # noqa: E402
from base.crawler_runtime import CrawlerRuntimeOptions  # noqa: E402
from base.exceptions import LoginRequiredError  # noqa: E402
from media_platform.douyin.core import DouYinCrawler  # noqa: E402


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
    # start() 非 CDP 分支会读 playwright.chromium（launch_browser 已替换，
    # 值本身无意义）
    chromium = object()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _FakeDouYinClient:
    """pong=False（未确认登录）+ 公开搜索有结果。"""

    def __init__(self):
        self.pong_calls = 0
        self.search_calls = []
        self.update_cookies_calls = 0

    async def pong(self, browser_context=None):
        self.pong_calls += 1
        return False

    async def search_info_by_keyword(self, **kwargs):
        self.search_calls.append(kwargs)
        if len(self.search_calls) > 1:
            return {"data": [], "status_code": 0}
        return {"data": [{"aweme_info": {"aweme_id": "fake-aweme-1"}}],
                "status_code": 0, "extra": {}}

    async def update_cookies(self, **kwargs):
        self.update_cookies_calls += 1


class _FakeDouYinLogin:
    begin_calls = 0

    def __init__(self, **kwargs):
        pass

    async def begin(self):
        type(self).begin_calls += 1

    async def update_cookies(self, **kwargs):
        pass


def _configure_config(monkeypatch):
    monkeypatch.setattr(config, "KEYWORDS", "测试")
    monkeypatch.setattr(config, "CRAWLER_TYPE", "search")
    monkeypatch.setattr(config, "CRAWLER_MAX_SLEEP_SEC", 0.01)
    monkeypatch.setattr(config, "ENABLE_GET_COMMENTS", False)
    monkeypatch.setattr(config, "ENABLE_GET_MEIDAS", False)
    monkeypatch.setattr(config, "ENABLE_CDP_MODE", False)
    monkeypatch.setattr(config, "ENABLE_IP_PROXY", False)
    monkeypatch.setattr(config, "MAX_CONCURRENCY_NUM", 1)


def _make_crawler(monkeypatch, client, sink_list, *, allow_public_search,
                  login_policy="fail_fast", headless=True):
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
    crawler.runtime_options = CrawlerRuntimeOptions(
        result_sink=lambda items: sink_list.extend(items),
        persist_results=False,
        login_policy=login_policy,
        enable_comments=False,
        enable_media=False,
        result_limit=5,
        strict_errors=False,
        headless=headless,
        allow_public_search=allow_public_search,
    )
    # 浏览器启动由 fake 承担；async_playwright 换成 fake 上下文管理器。
    monkeypatch.setattr(
        "media_platform.douyin.core.async_playwright",
        lambda: _FakePW())
    return crawler, client


def test_public_search_proceeds_when_pong_fails(monkeypatch):
    """pong=False + allow_public_search=True → 不抛 LoginRequiredError、
    不进入扫码登录，真实 search() 执行并产出结果（unverified 但可搜索）。"""
    _configure_config(monkeypatch)
    sink = []
    client = _FakeDouYinClient()
    crawler, client = _make_crawler(
        monkeypatch, client, sink, allow_public_search=True)

    asyncio.run(crawler.start())

    assert client.pong_calls == 1
    assert client.search_calls, "必须真正执行搜索（公开搜索路径）"
    assert len(sink) == 1, "公开搜索结果必须进入 result_sink"
    assert client.update_cookies_calls == 0, "未确认登录时不得走扫码登录"
    assert sink[0]["aweme_id"] == "fake-aweme-1", (
        "sink 收到的是 aweme_info 本体（search() 的 _result_sink_call 语义）")


def test_fail_fast_without_public_search_raises_login_required(monkeypatch):
    """pong=False + fail_fast + 未开启 allow_public_search → 保持原行为：
    抛 LoginRequiredError（聚合搜索之外的 console 默认语义不变）。"""
    _configure_config(monkeypatch)
    sink = []
    client = _FakeDouYinClient()
    crawler, client = _make_crawler(
        monkeypatch, client, sink, allow_public_search=False,
        login_policy="fail_fast")

    with pytest.raises(LoginRequiredError):
        asyncio.run(crawler.start())
    assert client.search_calls == []
    assert client.pong_calls == 1


def test_interactive_login_path_preserved(monkeypatch):
    """pong=False + interactive（默认 login_policy）+ 未开启公开搜索 →
    仍进入扫码登录路径（DouYinLogin.begin 被调用），原 console 行为不变。"""
    _configure_config(monkeypatch)
    monkeypatch.setattr(
        "media_platform.douyin.core.DouYinLogin", _FakeDouYinLogin)
    _FakeDouYinLogin.begin_calls = 0
    sink = []
    client = _FakeDouYinClient()
    crawler, client = _make_crawler(
        monkeypatch, client, sink, allow_public_search=False,
        login_policy="interactive")

    asyncio.run(crawler.start())

    assert _FakeDouYinLogin.begin_calls == 1, "interactive 必须进入扫码登录"
    assert client.update_cookies_calls == 1, "登录后必须刷新 client cookies"
    assert client.search_calls, "登录完成后继续搜索"

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
Round 16.1 账号同步去重复导航 + 同步耗时指标测试。

- 每个平台的 page 创建次数 / goto 次数 / context 启动次数（生产
  _pong_with_profile + fake client，无网络）；
- xhs / bilibili 纯 HTTP：零页面、零导航；
- douyin：最多一个页面、官网只导航一次（复用同一页面）；
- zhihu：已有 d_c0 → 零页面零导航；缺 d_c0 → 一个页面两次导航；
- 同步页面使用轻量路由（route 注册）；
- _sync_and_verify_platform 返回 sync_timings_ms（阶段耗时，只含整数）；
- 同步结果不泄露 Cookie 值。
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from api.services import accounts as acc


class _CountingPage:
    def __init__(self, ctx):
        self.ctx = ctx

    async def goto(self, url, **kw):
        self.ctx.goto_urls.append(url)

    async def close(self):
        pass


class _CountingCtx:
    """统计 page 创建 / goto / route 注册的 fake context。"""

    def __init__(self, cookies_list):
        self.cookies_list = list(cookies_list)
        self.page_creations = 0
        self.goto_urls = []
        self.route_calls = 0

    async def cookies(self, urls=None):
        return list(self.cookies_list)

    async def route(self, pattern, handler):
        self.route_calls += 1

    async def clear_cookies(self, *, name=None, domain=None, path=None):
        pass

    async def add_cookies(self, mapped):
        pass

    async def new_page(self, *a, **k):
        self.page_creations += 1
        return _CountingPage(self)

    async def close(self):
        pass


class _FakePW:
    async def stop(self):
        pass


def _fake_client_class(verified=True):
    class _FakeClient:
        def __init__(self, *a, **k):
            self.kwargs = k

        async def pong(self, *args, **kwargs):
            return verified

    return _FakeClient


_XHS_COOKIE = [
    {"name": "web_session", "value": "x", "domain": ".xiaohongshu.com"},
]
_BILI_COOKIE = [
    {"name": "SESSDATA", "value": "x", "domain": ".bilibili.com"},
]
_DY_COOKIE = [
    {"name": "LOGIN_STATUS", "value": "1", "domain": ".douyin.com"},
    {"name": "sessionid", "value": "x", "domain": ".douyin.com"},
]
_ZH_COOKIE_DC0 = [
    {"name": "z_c0", "value": "x", "domain": ".zhihu.com"},
    {"name": "d_c0", "value": "x", "domain": ".zhihu.com"},
]
_ZH_COOKIE_NO_DC0 = [
    {"name": "z_c0", "value": "x", "domain": ".zhihu.com"},
]


class TestPageCreationPerPlatform:
    @pytest.mark.parametrize("platform,import_path,cookies,expected_pages,expected_gotos", [
        ("xhs", "media_platform.xhs.client.XiaoHongShuClient",
         _XHS_COOKIE, 0, []),
        ("bilibili", "media_platform.bilibili.client.BilibiliClient",
         _BILI_COOKIE, 0, []),
        ("douyin", "media_platform.douyin.client.DouYinClient",
         _DY_COOKIE, 1, ["https://www.douyin.com"]),
        ("zhihu", "media_platform.zhihu.client.ZhiHuClient",
         _ZH_COOKIE_DC0, 0, []),
        ("zhihu", "media_platform.zhihu.client.ZhiHuClient",
         _ZH_COOKIE_NO_DC0, 1,
         ["https://www.zhihu.com",
          "https://www.zhihu.com/search?q=python&search_source=Guess"
          "&utm_content=search_hot&type=content"]),
    ])
    def test_pong_page_and_goto_counts(
            self, monkeypatch, platform, import_path, cookies,
            expected_pages, expected_gotos):
        """生产 _pong_with_profile：页面/导航数量按平台严格受控。"""
        monkeypatch.setattr(import_path, _fake_client_class(verified=True))
        ctx = _CountingCtx(cookies)
        metrics = {}
        result = asyncio.run(
            acc._pong_with_profile(platform, ctx, metrics=metrics))
        assert result == "verified"
        assert ctx.page_creations == expected_pages, (
            f"{platform}: page 创建次数应为 {expected_pages}")
        assert ctx.goto_urls == expected_gotos, (
            f"{platform}: goto 次数/顺序不符")
        # 需要页面的平台（douyin/zhihu 缺 d_c0）应注册轻量路由。
        if expected_pages > 0:
            assert ctx.route_calls >= 1, "页面导航前应注册轻量路由"

    def test_pong_navigation_ms_only_when_navigating(self, monkeypatch):
        """metrics.navigation_ms 只在真正导航的平台记录。"""
        monkeypatch.setattr(
            "media_platform.xhs.client.XiaoHongShuClient",
            _fake_client_class(verified=True))
        ctx = _CountingCtx(_XHS_COOKIE)
        metrics = {}
        asyncio.run(acc._pong_with_profile("xhs", ctx, metrics=metrics))
        assert "navigation_ms" not in metrics, "纯 HTTP 平台不得记录导航"

        monkeypatch.setattr(
            "media_platform.douyin.client.DouYinClient",
            _fake_client_class(verified=True))
        ctx = _CountingCtx(_DY_COOKIE)
        metrics = {}
        asyncio.run(acc._pong_with_profile("douyin", ctx, metrics=metrics))
        assert isinstance(metrics.get("navigation_ms"), int)


class TestSyncTimings:
    def _run_sync(self, monkeypatch, platform, cookies, import_path):
        ctx = _CountingCtx(cookies)
        launch_calls = {"n": 0}

        async def fake_launch(p):
            launch_calls["n"] += 1
            return _FakePW(), ctx, "edge"

        monkeypatch.setattr("api.services.accounts._launch_profile_context",
                            fake_launch)
        monkeypatch.setattr(import_path, _fake_client_class(verified=True))
        result = asyncio.run(acc.sync_platform_cookies(
            platform, cookies, cookie_format=acc.COOKIE_FORMAT_CHROME_V1,
            extension_protocol_version=2))
        return result, ctx, launch_calls

    def test_sync_xhs_timings_and_single_context(self, monkeypatch):
        """xhs 同步：1 次 context 启动、0 页面；sync_timings_ms 全整数。"""
        result, ctx, launch = self._run_sync(
            monkeypatch, "xhs", _XHS_COOKIE,
            "media_platform.xhs.client.XiaoHongShuClient")
        assert result["verified"] is True
        assert launch["n"] == 1
        assert ctx.page_creations == 0
        t = result["sync_timings_ms"]
        assert set(t.keys()) == {"browser_launch_ms", "cookie_import_ms",
                                 "verification_ms", "total_ms"}
        assert all(isinstance(v, int) for v in t.values())
        assert t["total_ms"] >= 0

    def test_sync_douyin_timings_include_navigation(self, monkeypatch):
        result, ctx, launch = self._run_sync(
            monkeypatch, "douyin", _DY_COOKIE,
            "media_platform.douyin.client.DouYinClient")
        assert result["verified"] is True
        assert launch["n"] == 1
        assert ctx.page_creations == 1
        t = result["sync_timings_ms"]
        assert "navigation_ms" in t
        assert isinstance(t["navigation_ms"], int)

    def test_sync_zhihu_dc0_zero_navigation(self, monkeypatch):
        result, ctx, launch = self._run_sync(
            monkeypatch, "zhihu", _ZH_COOKIE_DC0,
            "media_platform.zhihu.client.ZhiHuClient")
        assert result["verified"] is True
        assert ctx.page_creations == 0
        assert ctx.goto_urls == []
        assert "navigation_ms" not in result["sync_timings_ms"]

    def test_sync_result_never_leaks_cookie_values(self, monkeypatch):
        import json
        secret = "LEAKY-COOKIE-abc123"
        cookies = [
            {"name": "web_session", "value": secret,
             "domain": ".xiaohongshu.com"},
        ]
        result, _, _ = self._run_sync(
            monkeypatch, "xhs", cookies,
            "media_platform.xhs.client.XiaoHongShuClient")
        dump = json.dumps(result, ensure_ascii=False)
        assert secret not in dump
        assert "sync_timings_ms" in result

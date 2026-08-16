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
Round 16.1 tools/light_page 测试：analytics 拦截基于
``urlparse(url).hostname`` 的等值/子域匹配。

覆盖：URL path/query、大小写、恶意相似域名（google-analytics.com.evil
.example 不得命中）、resource type 不误伤 document/script/stylesheet/
XHR/fetch、analytics hostname 例外仍拦截。
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from tools.light_page import (
    _is_analytics,
    _light_route_handler,
    install_light_page_routes,
    light_goto_kwargs,
)


class _FakeRequest:
    def __init__(self, url: str, resource_type: str):
        self.url = url
        self.resource_type = resource_type


class _FakeRoute:
    def __init__(self, url: str, resource_type: str):
        self.request = _FakeRequest(url, resource_type)
        self.aborted = False
        self.continued = False

    async def abort(self):
        self.aborted = True

    async def continue_(self):
        self.continued = True


async def _route(url: str, resource_type: str) -> _FakeRoute:
    route = _FakeRoute(url, resource_type)
    await _light_route_handler(route)
    return route


class TestIsAnalytics:
    @pytest.mark.parametrize("url", [
        "https://www.google-analytics.com/analytics.js",
        "https://google-analytics.com",
        "https://www.google-analytics.com/analytics.js?x=1&y=2",
        "https://sub.hm.baidu.com/hm.js?ver=1.0",
        "https://cdn.googletagmanager.com/gtag/js?id=G-XXX",
        "HTTPS://WWW.GOOGLE-ANALYTICS.COM/ANALYTICS.JS",  # 大小写
        "https://www.google-analytics.com./analytics.js",  # 尾点
        "https://cnzz.com/track",
        "https://pos.baidu.com/foo",
    ])
    def test_hostname_equal_or_subdomain_blocked(self, url):
        assert _is_analytics(url) is True

    @pytest.mark.parametrize("url", [
        # 恶意相似域名：不得命中。
        "https://google-analytics.com.evil.example/x",
        "https://www.google-analytics.com.evil.example/x",
        "https://evilgoogle-analytics.com/x",
        "https://notgoogle-analytics.com/x",
        "https://google-analytics.com.org/x",
        "https://google-analytics.example/x",
        # 平台自身 API / 正常资源。
        "https://www.xiaohongshu.com/api/sns/web/v1/search/notes",
        "https://www.zhihu.com/api/v4/search_v3?q=python",
        "https://www.bilibili.com/video/BV1xx411c7mD",
        "https://www.douyin.com/aweme/v1/web/search/item/",
        "",
        "not-a-url",
    ])
    def test_malicious_similar_or_normal_not_blocked(self, url):
        assert _is_analytics(url) is False


class TestLightRouteHandler:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("resource_type", [
        "image", "media", "font",
    ])
    async def test_image_media_font_blocked_any_url(self, resource_type):
        route = await _route(
            "https://www.xiaohongshu.com/img/cover.jpg", resource_type)
        assert route.aborted and not route.continued

    @pytest.mark.asyncio
    async def test_analytics_hostname_blocked_even_for_script_document(self):
        """明确 analytics hostname：即使 script/document 也按安全规则拦截。"""
        for rtype in ("script", "document"):
            route = await _route(
                "https://www.googletagmanager.com/gtag/js?id=G-1", rtype)
            assert route.aborted, f"{rtype} 且 analytics hostname 应拦截"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("resource_type", [
        "document", "script", "stylesheet", "xhr", "fetch", "other",
    ])
    async def test_core_resource_types_never_blocked_by_type(self, resource_type):
        """document/script/stylesheet/XHR/fetch 绝不因 resource type 被拦截。"""
        route = await _route(
            "https://www.xiaohongshu.com/assets/app.js", resource_type)
        assert route.continued and not route.aborted

    @pytest.mark.asyncio
    async def test_analytics_url_with_path_query_blocked(self):
        """修复点：完整 URL endswith(domain) 会漏掉带 path/query 的 analytics；
        hostname 匹配必须命中。"""
        route = await _route(
            "https://www.google-analytics.com/collect?v=1&t=pageview", "xhr")
        assert route.aborted

    @pytest.mark.asyncio
    async def test_malicious_similar_domain_not_blocked(self):
        route = await _route(
            "https://google-analytics.com.evil.example/track.js", "script")
        assert route.continued and not route.aborted


class TestInstallAndGoto:
    @pytest.mark.asyncio
    async def test_install_registers_route(self):
        installed = []

        class _FakeCtx:
            async def route(self, pattern, handler):
                installed.append((pattern, handler))

        ctx = _FakeCtx()
        await install_light_page_routes(ctx)
        assert len(installed) == 1
        assert installed[0][0] == "**/*"

    def test_goto_kwargs_domcontentloaded(self):
        assert light_goto_kwargs() == {"wait_until": "domcontentloaded"}

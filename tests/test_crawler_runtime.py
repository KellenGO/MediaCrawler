# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler
# GitHub: https://github.com/NanmiCoder
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
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。

"""
Compatibility tests for CrawlerRuntimeOptions and AbstractCrawler hooks.

These tests verify that the runtime options layer does NOT break
existing behaviour when options are not set (default / CLI path).
"""

import pytest
import sys
import os

# Ensure project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from base.crawler_runtime import CrawlerRuntimeOptions
from base.base_crawler import AbstractCrawler


class _DummyCrawler(AbstractCrawler):
    """Minimal crawler stub for testing runtime hooks."""

    async def start(self):
        pass

    async def search(self):
        pass

    async def launch_browser(self, chromium, playwright_proxy, user_agent, headless=True):
        pass


class TestCrawlerRuntimeOptionsDefaults:
    """Verify default options preserve original CLI behaviour."""

    def test_default_attributes(self):
        opts = CrawlerRuntimeOptions()
        assert opts.login_policy == "interactive"
        assert opts.result_limit == 20
        assert opts.strict_errors is False
        assert opts.result_sink is None
        assert opts.headless is None
        assert opts.allow_public_search is False  # Round 9: 默认保留登录门禁
        assert opts.extra == {}

    def test_can_override(self):
        results = []
        opts = CrawlerRuntimeOptions(
            result_sink=lambda items: results.extend(items),
            login_policy="fail_fast",
            result_limit=10,
            strict_errors=True,
            headless=True,
            allow_public_search=True,     # Round 9: 抖音公开搜索
        )
        assert opts.login_policy == "fail_fast"
        assert opts.result_limit == 10
        assert opts.strict_errors is True
        assert opts.result_sink is not None
        assert opts.headless is True
        assert opts.allow_public_search is True


class TestAbstractCrawlerHooks:
    """Test the helper methods on AbstractCrawler."""

    @pytest.fixture
    def crawler(self):
        return _DummyCrawler()

    # ── Default behaviour (no runtime_options) ────────────────

    def test_login_fail_fast_default(self, crawler):
        assert crawler._login_fail_fast() is False

    def test_result_limit_default(self, crawler):
        assert crawler._result_limit() > 100

    def test_strict_errors_default(self, crawler):
        assert crawler._strict_errors() is False

    def test_result_sink_call_default_noop(self, crawler):
        """result_sink_call should be a no-op when no sink is set."""
        # Should not raise
        crawler._result_sink_call([{"test": 1}])

    # ── Aggregate-search mode ────────────────────────────────

    def test_login_fail_fast(self, crawler):
        crawler.runtime_options = CrawlerRuntimeOptions(login_policy="fail_fast")
        assert crawler._login_fail_fast() is True

    def test_result_limit(self, crawler):
        crawler.runtime_options = CrawlerRuntimeOptions(result_limit=10)
        assert crawler._result_limit() == 10

    def test_strict_errors(self, crawler):
        crawler.runtime_options = CrawlerRuntimeOptions(strict_errors=True)
        assert crawler._strict_errors() is True

    # ── Public-search mode ─────────────────

    def test_allow_public_search_default(self, crawler):
        assert crawler._allow_public_search() is False

    def test_allow_public_search_true(self, crawler):
        crawler.runtime_options = CrawlerRuntimeOptions(allow_public_search=True)
        assert crawler._allow_public_search() is True

    def test_result_sink_receives_items(self):
        crawler = _DummyCrawler()
        received = []
        crawler.runtime_options = CrawlerRuntimeOptions(
            result_sink=lambda items: received.extend(items),
        )
        test_data = [{"id": "1"}, {"id": "2"}]
        crawler._result_sink_call(test_data)
        assert len(received) == 2
        assert received[0] == {"id": "1"}
        assert received[1] == {"id": "2"}


class TestBackwardCompatibility:
    """Verify that existing crawler classes work without runtime_options."""

    def test_xhs_crawler_has_runtime_attr(self):
        from media_platform.xhs.core import XiaoHongShuCrawler
        c = XiaoHongShuCrawler()
        assert c.runtime_options is None

    def test_douyin_crawler_has_runtime_attr(self):
        from media_platform.douyin.core import DouYinCrawler
        c = DouYinCrawler()
        assert c.runtime_options is None

    def test_bilibili_crawler_has_runtime_attr(self):
        from media_platform.bilibili.core import BilibiliCrawler
        c = BilibiliCrawler()
        assert c.runtime_options is None

    def test_zhihu_crawler_has_runtime_attr(self):
        from media_platform.zhihu.core import ZhihuCrawler
        c = ZhihuCrawler()
        assert c.runtime_options is None

    def test_all_crawlers_accept_runtime_options(self):
        """Set runtime_options on each crawler and verify it sticks."""
        from media_platform.xhs.core import XiaoHongShuCrawler
        from media_platform.douyin.core import DouYinCrawler
        from media_platform.bilibili.core import BilibiliCrawler
        from media_platform.zhihu.core import ZhihuCrawler

        for crawler_cls in [XiaoHongShuCrawler, DouYinCrawler, BilibiliCrawler, ZhihuCrawler]:
            c = crawler_cls()
            opts = CrawlerRuntimeOptions(result_limit=5)
            c.runtime_options = opts
            assert c._result_limit() == 5

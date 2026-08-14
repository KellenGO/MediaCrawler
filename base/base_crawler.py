# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/base/base_crawler.py
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

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from playwright.async_api import BrowserContext, BrowserType, Playwright


class AbstractCrawler(ABC):
    """Base crawler with optional runtime behaviour overrides.

    Attach a ``CrawlerRuntimeOptions`` instance before ``start()`` to
    control result sinking, persistence, login policy, and error handling.
    Default (None) preserves 100% backward-compatible behaviour.
    """

    def __init__(self) -> None:
        self.runtime_options: Optional[Any] = None  # CrawlerRuntimeOptions | None

    @abstractmethod
    async def start(self):
        """
        start crawler
        """
        pass

    @abstractmethod
    async def search(self):
        """
        search
        """
        pass

    @abstractmethod
    async def launch_browser(self, chromium: BrowserType, playwright_proxy: Optional[Dict], user_agent: Optional[str], headless: bool = True) -> BrowserContext:
        """
        launch browser
        :param chromium: chromium browser
        :param playwright_proxy: playwright proxy
        :param user_agent: user agent
        :param headless: headless mode
        :return: browser context
        """
        pass

    async def launch_browser_with_cdp(self, playwright: Playwright, playwright_proxy: Optional[Dict], user_agent: Optional[str], headless: bool = True) -> BrowserContext:
        """
        Launch browser using CDP mode (optional implementation)
        :param playwright: playwright instance
        :param playwright_proxy: playwright proxy configuration
        :param user_agent: user agent
        :param headless: headless mode
        :return: browser context
        """
        # Default implementation: fallback to standard mode
        return await self.launch_browser(playwright.chromium, playwright_proxy, user_agent, headless)


    def _should_persist(self) -> bool:
        """Return True if results should be written to the store layer."""
        opts = self.runtime_options
        if opts is None:
            return True
        return getattr(opts, "persist_results", True)

    def _should_fetch_comments(self) -> bool:
        """Return True if comments should be fetched."""
        opts = self.runtime_options
        if opts is None:
            return True
        return getattr(opts, "enable_comments", True)

    def _should_fetch_media(self) -> bool:
        """Return True if media (images/video) should be downloaded."""
        opts = self.runtime_options
        if opts is None:
            return True
        return getattr(opts, "enable_media", True)

    def _result_sink_call(self, items: List[Dict]) -> None:
        """Invoke the result sink callback if configured."""
        opts = self.runtime_options
        if opts is None:
            return
        sink = getattr(opts, "result_sink", None)
        if sink is not None:
            sink(items)

    def _login_fail_fast(self) -> bool:
        """Return True if login failure should raise immediately."""
        opts = self.runtime_options
        if opts is None:
            return False
        return getattr(opts, "login_policy", "interactive") == "fail_fast"

    def _result_limit(self) -> int:
        """Return the result limit from runtime options, or a large default."""
        opts = self.runtime_options
        if opts is None:
            return 100000
        return getattr(opts, "result_limit", 20)

    def _strict_errors(self) -> bool:
        """Return True if errors should propagate instead of being swallowed."""
        opts = self.runtime_options
        if opts is None:
            return False
        return getattr(opts, "strict_errors", False)

    def _fetch_details(self) -> bool:
        """Return True if per-item detail fetching is enabled (Bilibili)."""
        opts = self.runtime_options
        if opts is None:
            return True
        return getattr(opts, "fetch_details", True)

    def _allow_public_search(self) -> bool:
        """Return True if search may proceed without a confirmed login."""
        opts = self.runtime_options
        if opts is None:
            return False
        return getattr(opts, "allow_public_search", False)

    def _stream_results(self) -> bool:
        """Return True if each detail should be pushed to the sink as soon as
        it is fetched (in original order) instead of after the whole batch."""
        opts = self.runtime_options
        if opts is None:
            return False
        return getattr(opts, "stream_results", False)

    def _reuse_http_client(self) -> bool:
        """Return True if the platform client should reuse one httpx client."""
        opts = self.runtime_options
        if opts is None:
            return False
        return getattr(opts, "reuse_http_client", False)


class AbstractLogin(ABC):

    @abstractmethod
    async def begin(self):
        pass

    @abstractmethod
    async def login_by_qrcode(self):
        pass

    @abstractmethod
    async def login_by_mobile(self):
        pass

    @abstractmethod
    async def login_by_cookies(self):
        pass


class AbstractStore(ABC):

    @abstractmethod
    async def store_content(self, content_item: Dict):
        pass

    @abstractmethod
    async def store_comment(self, comment_item: Dict):
        pass

    # TODO support all platform
    # only xhs is supported, so @abstractmethod is commented
    @abstractmethod
    async def store_creator(self, creator: Dict):
        pass


class AbstractStoreImage(ABC):
    # TODO: support all platform
    # only weibo is supported
    # @abstractmethod
    async def store_image(self, image_content_item: Dict):
        pass


class AbstractStoreVideo(ABC):
    # TODO: support all platform
    # only weibo is supported
    # @abstractmethod
    async def store_video(self, video_content_item: Dict):
        pass


class AbstractApiClient(ABC):

    @abstractmethod
    async def request(self, method, url, **kwargs):
        pass

    @abstractmethod
    async def update_cookies(self, browser_context: BrowserContext):
        pass

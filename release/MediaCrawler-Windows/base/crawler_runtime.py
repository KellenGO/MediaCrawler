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
Minimal runtime options for integrating aggregate search with MediaCrawler cores.

These options are attached to a crawler instance BEFORE calling ``start()``.
They describe the aggregate search runtime only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

# Result sink callback signature: receives platform-native result items.
ResultSink = Callable[[List[Any]], None]


@dataclass
class CrawlerRuntimeOptions:
    """Runtime behaviour overrides for an aggregate-search crawler.
    Set on a crawler instance before ``await crawler.start()``::

        crawler = CrawlerFactory.create_crawler(platform="xhs")
        crawler.runtime_options = CrawlerRuntimeOptions(login_policy="fail_fast")
        await crawler.start()
    """

    #: Callback invoked with each batch of platform-native search results.
    #: When set, native results are pushed to this sink.
    result_sink: Optional[ResultSink] = None

    #: ``"interactive"`` — wait for QR code / manual login prompt.
    #: ``"fail_fast"`` — raise ``LoginRequiredError`` immediately when
    #: the platform is not logged in.
    login_policy: str = "interactive"

    #: Maximum number of native results to extract.
    #: The adapter may further limit this.
    result_limit: int = 20

    #: When True, re-raise exceptions caught inside the crawler instead
    #: of logging and swallowing them. Useful for workers that need to
    #: report failures to the parent process.
    strict_errors: bool = False

    #: Whether to run the browser headless. None means use config default.
    headless: Optional[bool] = None

    #: Reuse a single httpx.AsyncClient across requests for this platform
    #: (created lazily, closed on proxy change / cleanup). Default False
    #: keeps the original per-request client lifecycle.
    reuse_http_client: bool = False

    #: Aggregate-only performance metric callback: ``cb(phase, elapsed_ms)``
    #: invoked by the crawler at phase boundaries (browser_launch /
    #: navigation / preflight / search_api). None (console mode) keeps the
    #: original behaviour with zero overhead. Only numbers are reported.
    metrics_cb: Optional[Callable[[str, int], None]] = None

    #: Light page load (aggregate-only): goto uses ``domcontentloaded`` and
    #: image/media/font/analytics requests are intercepted. Never touches
    #: document/script/stylesheet/XHR/fetch. Default False (console keeps
    #: the original full-page behaviour).
    light_page: bool = False

    #: Public-search mode: when True, the crawler proceeds to search even
    #: when pong did NOT confirm a logged-in session (douyin/zhihu aggregate
    #: search use this — public search APIs can work without login).
    #: Default False preserves the original login-gate behaviour.
    allow_public_search: bool = False

    #: Extra keyword arguments forwarded to platform-specific init.
    extra: dict = field(default_factory=dict)

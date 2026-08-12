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
The default values maintain backward compatibility with the existing CLI flow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

# Result sink callback signature: receives platform-native result items.
ResultSink = Callable[[List[Any]], None]


@dataclass
class CrawlerRuntimeOptions:
    """Optional runtime behaviour overrides for a crawler instance.

    Default values preserve the original CLI behaviour exactly.
    Set on a crawler instance before ``await crawler.start()``::

        crawler = CrawlerFactory.create_crawler(platform="xhs")
        crawler.runtime_options = CrawlerRuntimeOptions(
            persist_results=False,
            login_policy="fail_fast",
        )
        await crawler.start()
    """

    #: Callback invoked with each batch of platform-native search results.
    #: When set, results are pushed to this sink IN ADDITION to normal
    #: store processing (unless ``persist_results`` is False).
    result_sink: Optional[ResultSink] = None

    #: Whether to continue calling the existing store layer.
    #: Set to False in aggregate-search mode to avoid writing files.
    persist_results: bool = True

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

    #: Whether to enable comment fetching (default False for aggregate search).
    enable_comments: bool = False

    #: Whether to enable media download (default False for aggregate search).
    enable_media: bool = False

    #: Whether to run the browser headless. None means use config default.
    headless: Optional[bool] = None

    #: Bilibili light-list mode: when False, the search list
    #: (/x/web-interface/wbi/search/type flat items) is passed to the result
    #: sink directly — no per-item detail API call, no store, no comments,
    #: no media. Default True keeps the original detail-fetching behaviour.
    fetch_details: bool = True

    #: Public-search mode: when True, the crawler proceeds to search even
    #: when pong did NOT confirm a logged-in session (douyin/zhihu aggregate
    #: search use this — public search APIs can work without login).
    #: Default False preserves the original login-gate behaviour.
    allow_public_search: bool = False

    #: Extra keyword arguments forwarded to platform-specific init.
    extra: dict = field(default_factory=dict)

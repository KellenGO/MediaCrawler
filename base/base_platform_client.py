# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
# This file is part of MediaCrawler project.
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1

"""四个平台 HTTP client 共用的 httpx 生命周期。

xhs / douyin / bilibili / zhihu 的 client 各自抄了一份「懒创建 + 复用 + 关旧建新」
的 httpx 管理代码（约 25 行 ×4），连 docstring 都一样。这里收成一份 mixin。

**只有机制**：怎么复用/关闭 httpx client、Cookie 写进哪个请求头。签名（`_pre_headers`）、
状态码解释（`_raise_for_status`）、登录探测（`pong`）刻意留在各平台 —— 那三处没有
共同的抽象面，硬抽只会做出一个满是分支的上帝方法。

用法（见各平台 `client.py`）：

    class XxxClient(ReusableHttpClientMixin, AbstractApiClient):   # ← mixin 必须排在前面
        def __init__(...):
            self.proxy = proxy
            self._init_http_client_state()   # 替代 self._http_client = None 那两行

⚠️ **mixin 必须写在 `AbstractApiClient` 前面**：`AbstractApiClient.update_cookies` 是
`@abstractmethod`，MRO 里若抽象基类在前，`update_cookies` 会解析到那个抽象声明，
实例化直接 `TypeError: Can't instantiate abstract class ... without an implementation
for abstract method 'update_cookies'`（这个坑踩过一次，别把顺序"整理"回去）。
"""

from __future__ import annotations

from typing import Any, Optional

from tools import utils
from tools.httpx_util import make_async_client

DEFAULT_TIMEOUT = 60


class ReusableHttpClientMixin:
    """httpx.AsyncClient 的懒创建与幂等关闭。

    子类需要提供：``self.proxy``（当前代理 URL 或 None）、``self.timeout``、
    ``self.cookie_urls``、``self.cookie_dict``，以及一个请求头字典
    （默认 `self.headers`，zhihu 用 `self.default_headers`）。
    """

    #: Cookie 写进哪个请求头字典 / 用哪个键名（zhihu 覆盖这两项）。
    _cookie_header_bag = "headers"
    _cookie_header_name = "Cookie"

    def _init_http_client_state(self) -> None:
        """在 __init__ 里调用：初始化复用的 httpx client 与其缓存代理。"""
        self._http_client: Optional[Any] = None
        self._http_client_proxy: Optional[str] = None

    async def _get_reused_client(self):
        """懒创建并复用单个 httpx.AsyncClient；代理变化时关闭旧 client 重建。"""
        if self._http_client is None or self._http_client_proxy != self.proxy:
            await self._close_http_client()
            self._http_client = make_async_client(proxy=self.proxy)
            self._http_client_proxy = self.proxy
        return self._http_client

    async def _close_http_client(self) -> None:
        client = self._http_client
        self._http_client = None
        self._http_client_proxy = None
        if client is not None:
            try:
                await client.aclose()
            except Exception:
                pass

    async def aclose(self) -> None:
        """幂等关闭复用的 httpx client（未启用复用时为空操作）。"""
        await self._close_http_client()

    async def close(self) -> None:
        """幂等关闭（aclose 的别名，便于统一清理调用）。"""
        await self._close_http_client()

    async def _send(self, method, url, **kwargs):
        """按 ``reuse_http_client`` 决定复用连接还是每次新建。"""
        if self.reuse_http_client:
            client = await self._get_reused_client()
            return await client.request(method, url, timeout=self.timeout, **kwargs)
        async with make_async_client(proxy=self.proxy) as client:
            return await client.request(method, url, timeout=self.timeout, **kwargs)

    async def update_cookies(self, browser_context, urls: Optional[list] = None):
        """登录成功后刷新 Cookie（请求头 + ``self.cookie_dict``）。"""
        cookie_str, cookie_dict = await utils.convert_browser_context_cookies(
            browser_context,
            urls=urls or self.cookie_urls,
        )
        getattr(self, self._cookie_header_bag)[self._cookie_header_name] = cookie_str
        self.cookie_dict = cookie_dict

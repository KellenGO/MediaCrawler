# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/media_platform/xhs/client.py
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

import json
import re
from typing import TYPE_CHECKING, Any, Dict, Optional, Union
from urllib.parse import quote

from playwright.async_api import BrowserContext, Page
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_not_exception_type, retry_if_exception
from aggregate_search.pagination import allow_client_retry, check_search_http_status
from tools.httpx_util import make_async_client

import config
from base.base_crawler import AbstractApiClient
from proxy.proxy_mixin import ProxyRefreshMixin
from tools import utils

if TYPE_CHECKING:
    from proxy.proxy_ip_pool import ProxyIpPool

from .exception import (
    DataFetchError, IPBlockError, NoteNotFoundError, XhsRateLimitError,
)
from .field import SearchNoteType, SearchSortType
from .help import get_search_id
from .playwright_sign import sign_with_xhshow


def _safe_debug_message(value: Any) -> Optional[str]:
    if not isinstance(value, str) or not value:
        return None
    message = re.sub(r"https?://[^\s]+", "[URL]", value)
    message = re.sub(
        r"(?i)(xsec[_-]?token|cookie|authorization|access[_-]?token|refresh[_-]?token)"
        r"\s*[:=]\s*[^\s,;}]+'?",
        r"\1=[REDACTED]",
        message,
    )
    return message[:120]


class XiaoHongShuClient(AbstractApiClient, ProxyRefreshMixin):

    def __init__(
        self,
        timeout=60,  # If media crawling is enabled, Xiaohongshu long videos need longer timeout
        proxy=None,
        *,
        headers: Dict[str, str],
        playwright_page: Page,
        cookie_dict: Dict[str, str],
        proxy_ip_pool: Optional["ProxyIpPool"] = None,
        reuse_http_client: bool = False,
    ):
        self.proxy = proxy
        self.timeout = timeout
        self.headers = headers
        self.reuse_http_client = reuse_http_client
        # 复用的 httpx client（懒创建；代理变化时安全关闭并重建）。
        self._http_client = None
        self._http_client_proxy: Optional[str] = None
        if config.XHS_INTERNATIONAL:
            self._host = "https://webapi.rednote.com"
            self._domain = "https://www.rednote.com"
        else:
            self._host = "https://edith.xiaohongshu.com"
            self._domain = "https://www.xiaohongshu.com"
        self.cookie_urls = [self._domain]
        self.IP_ERROR_STR = "Network connection error, please check network settings or restart"
        self.IP_ERROR_CODE = 300012
        self.NOTE_NOT_FOUND_CODE = -510000
        self.NOTE_ABNORMAL_CODE = -510001
        self.playwright_page = playwright_page
        self.cookie_dict = cookie_dict
        # Diagnostic-only response metadata for aggregate hydration. Never
        # store response bodies, URLs, cookies, or tokens here.
        self.last_response_status: Optional[int] = None
        self.last_business_code: Any = None
        self.last_business_msg: Optional[str] = None
        # Initialize proxy pool (from ProxyRefreshMixin)
        self.init_proxy_pool(proxy_ip_pool)

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

    async def _pre_headers(self, url: str, params: Optional[Dict] = None, payload: Optional[Dict] = None) -> Dict:
        """请求头参数签名 (使用 xhshow 纯算法)

        Args:
            url: 请求 URI path
            params: GET 请求参数
            payload: POST 请求参数

        Returns:
            Dict: 签名后的请求头参数
        """
        if params is not None:
            data = params
            method = "GET"
        elif payload is not None:
            data = payload
            method = "POST"
        else:
            raise ValueError("params or payload is required")

        # 使用 xhshow 纯算法生成签名
        signs = sign_with_xhshow(
            uri=url,
            data=data,
            cookie_str=self.headers.get("Cookie", ""),
            method=method,
        )

        headers = {
            "X-S": signs["x-s"],
            "X-T": signs["x-t"],
            "x-S-Common": signs["x-s-common"],
            "X-B3-Traceid": signs["x-b3-traceid"],
        }
        self.headers.update(headers)
        return self.headers

    # Round 17.2: 461/471 是平台风控（验证码/访问限制）—— XhsRateLimitError
    # 必须被排除在重试之外（只发 1 次请求，不重复触发风控）；NoteNotFoundError
    # 原语义保持不重试。其余网络/临时错误仍按原样重试 3 次。
    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1),
           retry=retry_if_not_exception_type(
                (NoteNotFoundError, XhsRateLimitError)) & retry_if_exception(allow_client_retry))
    async def request(self, method, url, **kwargs) -> Union[str, Any]:
        """
        Wrapper for httpx common request method, processes request response
        Args:
            method: Request method
            url: Request URL
            **kwargs: Other request parameters, such as headers, body, etc.

        Returns:

        """
        # Check if proxy is expired before each request
        await self._refresh_proxy_if_expired()

        # return response.text
        return_response = kwargs.pop("return_response", False)
        if self.reuse_http_client:
            # Phase 3.2: 复用单个 client（代理变化时内部会关闭并重建）。
            client = await self._get_reused_client()
            response = await client.request(method, url, timeout=self.timeout, **kwargs)
        else:
            # 旧行为：每个请求独立 client 生命周期。
            async with make_async_client(proxy=self.proxy) as client:
                response = await client.request(method, url, timeout=self.timeout, **kwargs)

        check_search_http_status(response.status_code)

        # Keep only safe response metadata for the hydration diagnostic log.
        self.last_response_status = response.status_code
        self.last_business_code = None
        self.last_business_msg = None

        if response.status_code == 471 or response.status_code == 461:
            # Round 17.2: 平台风控/验证码挑战 —— 立即抛专用异常，不读取
            # Verifyuuid/Verifytype，不记录 response 对象或 body，日志只写
            # 固定文案与状态码。XhsRateLimitError 被重试条件排除 → 只发 1 次。
            utils.logger.error(
                f"[XiaoHongShuClient.request] xhs rate-limited, "
                f"http_status={response.status_code}")
            raise XhsRateLimitError(http_status=response.status_code)

        if return_response:
            return response.text
        data: Dict = response.json()
        self.last_business_code = data.get("code")
        msg = data.get("msg")
        self.last_business_msg = _safe_debug_message(msg)
        if data["success"]:
            return data.get("data", data.get("success", {}))
        elif data["code"] == self.IP_ERROR_CODE:
            raise IPBlockError(self.IP_ERROR_STR)
        elif data["code"] in (self.NOTE_NOT_FOUND_CODE, self.NOTE_ABNORMAL_CODE):
            raise NoteNotFoundError(f"Note not found or abnormal, code: {data['code']}")
        else:
            err_msg = data.get("msg", None) or f"{response.text}"
            raise DataFetchError(err_msg)

    @staticmethod
    def _build_query_string(params: Dict) -> str:
        """Build URL query string with encoding matching browser behavior (commas not encoded)"""
        parts = []
        for key, value in params.items():
            value_str = str(value) if value is not None else ""
            parts.append(f"{key}={quote(value_str, safe=',')}")
        return "&".join(parts)

    async def get(self, uri: str, params: Optional[Dict] = None) -> Dict:
        """
        GET request, signs request headers
        Args:
            uri: Request route
            params: Request parameters

        Returns:

        """
        headers = await self._pre_headers(uri, params)
        # Build URL manually to ensure query string encoding matches the sign string
        # (httpx's default params encoding differs from browser/XHS frontend behavior)
        if params:
            full_url = f"{self._host}{uri}?{self._build_query_string(params)}"
        else:
            full_url = f"{self._host}{uri}"

        return await self.request(
            method="GET", url=full_url, headers=headers
        )

    async def post(self, uri: str, data: dict, **kwargs) -> Dict:
        """
        POST request, signs request headers
        Args:
            uri: Request route
            data: Request body parameters

        Returns:

        """
        headers = await self._pre_headers(uri, payload=data)
        json_str = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
        return await self.request(
            method="POST",
            url=f"{self._host}{uri}",
            data=json_str,
            headers=headers,
            **kwargs,
        )

    async def query_self(self) -> Optional[Dict]:
        """
        Query self user info to check login state
        Returns:
            Dict: User info if logged in, None otherwise
        """
        uri = "/api/sns/web/v1/user/selfinfo"
        headers = await self._pre_headers(uri, params={})
        async with make_async_client(proxy=self.proxy) as client:
            response = await client.get(f"{self._host}{uri}", headers=headers)
            # Round 17.2: 461/471 是平台风控（验证码/访问限制）—— 抛专用
            # 异常（不读取 Verifyuuid/Verifytype、不记录 body/URL）。
            if response.status_code in (461, 471):
                raise XhsRateLimitError(http_status=response.status_code)
            if response.status_code == 200:
                return response.json()
        return None

    async def pong(self, raise_on_error: bool = False) -> bool:
        """
        Check if login state is still valid by querying self user info
        Args:
            raise_on_error: True 时异常不再吞掉 —— 网络错误/超时/风控/接口
                异常向上传播（供账号验证 probe 区分"明确未登录"与"无法验证"）；
                False（默认）保持 console/login 模块的原始行为：任何异常
                都返回 False。
        Returns:
            bool: True if logged in, False otherwise
        """
        utils.logger.info("[XiaoHongShuClient.pong] Begin to check login state...")
        ping_flag = False
        try:
            self_info: Dict = await self.query_self()
            if raise_on_error and self_info is None:
                # query_self 仅在 HTTP 200 时返回响应 —— None 表示接口异常
                # 响应（403/5xx 等），绝不能被误判为"明确未登录"。
                raise DataFetchError("selfinfo 接口未返回有效响应")
            if self_info and self_info.get("data", {}).get("result", {}).get("success"):
                ping_flag = True
        except Exception as e:
            utils.logger.error(
                f"[XiaoHongShuClient.pong] Check login state failed: {e}, and try to login again..."
            )
            if raise_on_error:
                raise
            ping_flag = False
        utils.logger.info(f"[XiaoHongShuClient.pong] Login state result: {ping_flag}")
        return ping_flag

    async def update_cookies(self, browser_context: BrowserContext, urls: Optional[list[str]] = None):
        """
        Update cookies method provided by API client, usually called after successful login
        Args:
            browser_context: Browser context object

        Returns:

        """
        cookie_str, cookie_dict = await utils.convert_browser_context_cookies(
            browser_context,
            urls=urls or self.cookie_urls,
        )
        self.headers["Cookie"] = cookie_str
        self.cookie_dict = cookie_dict

    async def get_note_by_keyword(
        self,
        keyword: str,
        search_id: str = get_search_id(),
        page: int = 1,
        page_size: int = 20,
        sort: SearchSortType = SearchSortType.GENERAL,
        note_type: SearchNoteType = SearchNoteType.ALL,
    ) -> Dict:
        """
        Search notes by keyword
        Args:
            keyword: Keyword parameter
            page: Page number
            page_size: Page data length
            sort: Search result sorting specification
            note_type: Type of note to search

        Returns:

        """
        uri = "/api/sns/web/v1/search/notes"
        data = {
            "keyword": keyword,
            "page": page,
            "page_size": page_size,
            "search_id": search_id,
            "sort": sort.value,
            "note_type": note_type.value,
            # Round 17.1: 缺少 image_formats 时真实搜索响应里的 note_card.cover
            # 与 image_list[] 只有 height/width 没有任何图片 URL；与详情接口
            # 相同的 image_formats 参数让封面字段携带真实图片 URL（url_pre /
            # url_default / image_list[].info_list[].url）。
            "image_formats": ["jpg", "webp", "avif"],
        }
        return await self.post(uri, data)

    async def get_note_by_id(
        self,
        note_id: str,
        xsec_source: str,
        xsec_token: str,
    ) -> Dict:
        """
        Get note detail API
        Args:
            note_id: Note ID
            xsec_source: Channel source
            xsec_token: Token returned from search keyword result list

        Returns:

        """
        if xsec_source == "":
            xsec_source = "pc_search"

        data = {
            "source_note_id": note_id,
            "image_formats": ["jpg", "webp", "avif"],
            "extra": {"need_body_topic": 1},
            "xsec_source": xsec_source,
            "xsec_token": xsec_token,
        }
        uri = "/api/sns/web/v1/feed"
        res = await self.post(uri, data)
        if res and res.get("items"):
            res_dict: Dict = res["items"][0]["note_card"]
            return res_dict
        # When crawling frequently, some notes may have results while others don't
        utils.logger.error(
            f"[XiaoHongShuClient.get_note_by_id] get note id:{note_id} empty and res:{res}"
        )
        return dict()

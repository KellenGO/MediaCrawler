# -*- coding: utf-8 -*-
"""Best-effort, post-search description hydration.

This module deliberately uses existing lightweight detail clients. It never
starts a browser and it is independent from the resident search workers.
"""

from __future__ import annotations

import asyncio
from typing import Dict, Optional
from urllib.parse import parse_qs, urlsplit

from aggregate_search.hydration import hydrate_results
from aggregate_search.models import UnifiedSearchResult, clean_snippet
from .accounts import get_session_snapshot


class ResultHydrator:
    """Reuse at most one HTTP client per supported platform for one job."""

    def __init__(self) -> None:
        self._clients: Dict[str, object] = {}
        self._locks: Dict[str, asyncio.Lock] = {}

    async def hydrate(self, results, cancel_event: asyncio.Event):
        try:
            return await hydrate_results(
                results,
                self.fetch_snippet,
                cancel_event=cancel_event,
            )
        finally:
            await self.close()

    async def close(self) -> None:
        clients = list(self._clients.values())
        self._clients.clear()
        for client in clients:
            close = getattr(client, "aclose", None) or getattr(client, "close", None)
            if close is not None:
                try:
                    await close()
                except Exception:
                    pass

    async def fetch_snippet(self, result: UnifiedSearchResult) -> Optional[str]:
        if result.platform == "bilibili":
            return await self._fetch_bilibili(result)
        if result.platform == "xhs":
            return await self._fetch_xhs(result)
        if result.platform == "zhihu":
            return await self._fetch_zhihu(result)
        # Douyin's detail endpoint requires the browser signing/page path;
        # do not launch a browser from the post-search task in V1.
        return None

    async def _fetch_bilibili(self, result: UnifiedSearchResult) -> Optional[str]:
        client = await self._get_bilibili()
        value = result.content_id
        detail = await client.get_video_info(
            bvid=value if value.upper().startswith("BV") else None,
            aid=int(value) if value.isdigit() else None,
        )
        if not isinstance(detail, dict):
            return None
        return clean_snippet(detail.get("desc") or detail.get("description"))

    async def _fetch_xhs(self, result: UnifiedSearchResult) -> Optional[str]:
        query = parse_qs(urlsplit(result.url).query)
        token = (query.get("xsec_token") or [""])[0]
        source = (query.get("xsec_source") or ["pc_search"])[0]
        snapshot = get_session_snapshot("xhs")
        if not token or not snapshot:
            return None
        client = await self._get_xhs(snapshot)
        detail = await client.get_note_by_id(result.content_id, source, token)
        if not isinstance(detail, dict):
            return None
        return clean_snippet(detail.get("desc") or detail.get("description"))

    async def _fetch_zhihu(self, result: UnifiedSearchResult) -> Optional[str]:
        snapshot = get_session_snapshot("zhihu")
        if not snapshot or not snapshot.get("d_c0"):
            return None
        client = await self._get_zhihu(snapshot)
        if result.content_type == "answer":
            parts = [part for part in urlsplit(result.url).path.split("/") if part]
            if len(parts) < 4 or parts[-2] != "answer":
                return None
            detail = await client.get_answer_info(parts[-3], parts[-1])
        elif result.content_type == "article":
            detail = await client.get_article_info(result.content_id)
        elif result.content_type == "zvideo":
            detail = await client.get_video_info(result.content_id)
        else:
            return None
        if detail is None:
            return None
        return clean_snippet(detail.desc or detail.content_text)

    async def _get_bilibili(self):
        if "bilibili" not in self._clients:
            from media_platform.bilibili.client import BilibiliClient

            snapshot = get_session_snapshot("bilibili") or {}
            cookie = "; ".join(f"{key}={value}" for key, value in snapshot.items())
            self._clients["bilibili"] = BilibiliClient(
                timeout=8,
                proxy=None,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Cookie": cookie,
                    "Origin": "https://www.bilibili.com",
                    "Referer": "https://www.bilibili.com",
                    "Content-Type": "application/json;charset=UTF-8",
                },
                playwright_page=None,
                cookie_dict=snapshot,
                proxy_ip_pool=None,
                reuse_http_client=True,
            )
        return self._clients["bilibili"]

    async def _get_xhs(self, snapshot):
        if "xhs" not in self._clients:
            from media_platform.xhs.client import XiaoHongShuClient

            cookie = "; ".join(f"{key}={value}" for key, value in snapshot.items())
            self._clients["xhs"] = XiaoHongShuClient(
                timeout=8,
                proxy=None,
                headers={
                    "accept": "application/json, text/plain, */*",
                    "accept-language": "zh-CN,zh;q=0.9",
                    "content-type": "application/json;charset=UTF-8",
                    "origin": "https://www.xiaohongshu.com",
                    "referer": "https://www.xiaohongshu.com/",
                    "user-agent": "Mozilla/5.0",
                    "Cookie": cookie,
                },
                playwright_page=None,
                cookie_dict=dict(snapshot),
                proxy_ip_pool=None,
                reuse_http_client=True,
            )
        return self._clients["xhs"]

    async def _get_zhihu(self, snapshot):
        if "zhihu" not in self._clients:
            from media_platform.zhihu.client import ZhiHuClient

            cookie = "; ".join(f"{key}={value}" for key, value in snapshot.items())
            self._clients["zhihu"] = ZhiHuClient(
                timeout=8,
                proxy=None,
                headers={
                    "accept": "*/*",
                    "accept-language": "zh-CN,zh;q=0.9",
                    "cookie": cookie,
                    "referer": "https://www.zhihu.com/",
                    "user-agent": "Mozilla/5.0",
                    "x-api-version": "3.0.91",
                    "x-app-za": "OS=Web",
                    "x-requested-with": "fetch",
                    "x-zse-93": "101_3_3.0",
                },
                playwright_page=None,
                cookie_dict=dict(snapshot),
                proxy_ip_pool=None,
                reuse_http_client=True,
            )
        return self._clients["zhihu"]

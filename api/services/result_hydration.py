# -*- coding: utf-8 -*-
"""Best-effort, post-search description hydration.

This module deliberately uses existing lightweight detail clients. It never
starts a browser and it is independent from the resident search workers.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Dict, Optional
from urllib.parse import parse_qs, urlsplit

from aggregate_search.hydration import hydrate_results
from aggregate_search.models import UnifiedSearchResult, clean_snippet
from .accounts import get_session_snapshot

logger = logging.getLogger(__name__)


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _safe_source(value: str) -> str:
    source = value if isinstance(value, str) else ""
    if re.fullmatch(r"[A-Za-z0-9_-]{1,40}", source):
        return source
    return "[redacted]"


def _safe_exception_message(exc: BaseException) -> str:
    """Keep useful exception context while removing URL/body credentials."""
    message = str(exc)
    message = re.sub(r"https?://[^\s]+", "[URL]", message)
    message = re.sub(
        r"(?i)(xsec[_-]?token|cookie|authorization|access[_-]?token|refresh[_-]?token)"
        r"\s*[:=]\s*[^\s,;}]+'?",
        r"\1=[REDACTED]",
        message,
    )
    return message[:160] or "[empty]"


def _safe_business_msg(value: object) -> str:
    if not isinstance(value, str) or not value:
        return "[none]"
    return _safe_exception_message(Exception(value))


def extract_xhs_snippet(detail: object) -> Optional[str]:
    """Extract description from the known XHS detail response shapes.

    ``get_note_by_id`` normally unwraps ``data.items[0].note_card`` to the
    note-card dict, while fixtures and compatible clients may return one of
    those outer shapes directly. Values are cleaned only after a candidate
    field is found.
    """
    if not isinstance(detail, dict):
        return None
    candidates = [detail.get("desc"), detail.get("description")]
    note_card = detail.get("note_card")
    if isinstance(note_card, dict):
        candidates.extend([note_card.get("desc"), note_card.get("description")])
    note = detail.get("note")
    if isinstance(note, dict):
        candidates.extend([note.get("desc"), note.get("description")])
    data = detail.get("data")
    if isinstance(data, dict):
        candidates.extend([data.get("desc"), data.get("description")])
        items = data.get("items")
        if isinstance(items, list) and items:
            first = items[0]
            if isinstance(first, dict):
                nested_card = first.get("note_card")
                if isinstance(nested_card, dict):
                    candidates.extend([
                        nested_card.get("desc"),
                        nested_card.get("description"),
                    ])
    for candidate in candidates:
        snippet = clean_snippet(candidate)
        if snippet:
            return snippet
    return None


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
        raw_snapshot = get_session_snapshot("xhs")
        has_snapshot = raw_snapshot is not None
        cookie_present = bool(raw_snapshot)
        source_value = _safe_source(source)
        diagnostic_prefix = (
            "[XHS hydration] note_id=%s has_xsec_token=%s xsec_source=%s "
            "has_session_snapshot=%s snapshot_cookie_present=%s"
        )
        if not token:
            logger.debug(
                diagnostic_prefix + " client_created=false request_started=false "
                "request_status=skipped exception_type=missing_xsec_token",
                result.content_id, _bool_text(False), source_value,
                _bool_text(has_snapshot), _bool_text(cookie_present),
            )
            return None
        # A browser search can succeed without an account snapshot in the API
        # process. The existing HTTP client can still make the token-scoped
        # request with an empty cookie set; let the request decide and log a
        # safe failure instead of silently skipping it here.
        snapshot = raw_snapshot or {}
        try:
            client = await self._get_xhs(snapshot)
        except Exception as exc:
            logger.debug(
                diagnostic_prefix + " client_created=false request_started=false "
                "request_status=client_create_exception exception_type=%s "
                "exception_message=%s",
                result.content_id, _bool_text(True), source_value,
                _bool_text(has_snapshot), _bool_text(cookie_present),
                type(exc).__name__, _safe_exception_message(exc),
            )
            raise
        logger.debug(
            diagnostic_prefix + " client_created=%s request_started=false",
            result.content_id, _bool_text(True), source_value,
            _bool_text(has_snapshot), _bool_text(cookie_present),
            _bool_text(client is not None),
        )
        try:
            logger.debug(
                diagnostic_prefix + " client_created=true request_started=true",
                result.content_id, _bool_text(True), source_value,
                _bool_text(has_snapshot), _bool_text(cookie_present),
            )
            detail = await client.get_note_by_id(result.content_id, source, token)
        except Exception as exc:
            logger.debug(
                diagnostic_prefix + " client_created=true request_started=true "
                "request_status=exception exception_type=%s exception_message=%s "
                "http_status=%s business_code=%s business_msg=%s",
                result.content_id, _bool_text(True), source_value,
                _bool_text(has_snapshot), _bool_text(cookie_present),
                type(exc).__name__, _safe_exception_message(exc),
                getattr(client, "last_response_status", None),
                getattr(client, "last_business_code", None),
                _safe_business_msg(getattr(client, "last_business_msg", None)),
            )
            raise
        if isinstance(detail, dict):
            response_keys = sorted(str(key) for key in detail.keys())[:20]
        else:
            response_keys = [f"<payload:{type(detail).__name__}>"]
        snippet = extract_xhs_snippet(detail)
        logger.debug(
            diagnostic_prefix + " client_created=true request_started=true "
            "request_status=success http_status=%s business_code=%s "
            "business_msg=%s response_top_level_keys=%s "
            "extracted_snippet_length=%s",
            result.content_id, _bool_text(True), source_value,
            _bool_text(has_snapshot), _bool_text(cookie_present),
            getattr(client, "last_response_status", None),
            getattr(client, "last_business_code", None),
            _safe_business_msg(getattr(client, "last_business_msg", None)),
            response_keys, len(snippet or ""),
        )
        return snippet

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

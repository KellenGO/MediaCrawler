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
Xiaohongshu (小红书) adapter.

Native data: note detail dict returned by ``XiaoHongShuClient.get_note_by_id``
and similar methods. Typical fields:

- note_id: str
- title: str
- desc: str
- type: str ("normal" = note, "video" = video)
- time: int (unix seconds)
- user: {nickname: str, user_id: str, avatar: str}
- interact_info: {liked_count, collected_count, comment_count, share_count}
- image_list: [{url_default: str, ...}]
- note_url: str (optional)
- tag_list: [{name: str, ...}]
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import urlencode, urlsplit

from aggregate_search.models import UnifiedSearchResult, _parse_timestamp

from .base import BasePlatformAdapter

# Official xhs domains allowed in navigation URLs. rednote.com is the
# international site — a note_url from it is accepted only because data that
# carries a rednote.com URL can only have come from international mode.
XHS_ALLOWED_HOSTS = {
    "www.xiaohongshu.com",
    "xiaohongshu.com",
    "www.rednote.com",
}
XHS_EXPLORE_URL = "https://www.xiaohongshu.com/explore/{note_id}"


def _is_allowed_xhs_host(url: str) -> bool:
    try:
        host = urlsplit(url).netloc.lower()
    except Exception:
        return False
    return host in XHS_ALLOWED_HOSTS


def build_note_url(
    note_id: str,
    note_url: Optional[str] = None,
    xsec_token: Optional[str] = None,
    xsec_source: Optional[str] = None,
) -> Optional[str]:
    """Build the navigation URL for an xhs note.

    Priority:
      1. an existing note_url, but only if its host is in the official
         domain whitelist — external domains are rejected;
      2. a generated ``https://www.xiaohongshu.com/explore/{note_id}`` URL.
    When xsec_token is present it is appended via ``urllib.parse.urlencode``
    (xsec_source defaults to ``pc_search``). Without a token the plain
    explore URL is used.

    The xsec_token may ONLY appear inside the returned navigation URL —
    never in logs, error_summary, or separate API fields.
    """
    if note_url and isinstance(note_url, str) and _is_allowed_xhs_host(note_url):
        return note_url

    base = XHS_EXPLORE_URL.format(note_id=note_id)
    if not xsec_token or not isinstance(xsec_token, str):
        return base
    query = urlencode({
        "xsec_token": xsec_token,
        "xsec_source": xsec_source or "pc_search",
    })
    return f"{base}?{query}"


class XhsAdapter(BasePlatformAdapter):
    PLATFORM = "xhs"

    def adapt(self, raw_results: List[Any], keyword: str = "") -> List[UnifiedSearchResult]:
        results: List[UnifiedSearchResult] = []
        for rank, item in enumerate(raw_results):
            if not isinstance(item, dict):
                continue

            note_id = self._safe_str(item.get("note_id"))
            if not note_id:
                continue

            # Round 16.1: 若 crawler 盖了 source_index（流式 sink 场景，
            # 详情完成顺序 ≠ 搜索相关性顺序），用它作为最终排序 rank。
            src_rank = item.get("source_index")
            if isinstance(src_rank, int) and not isinstance(src_rank, bool):
                rank = src_rank

            title = self._safe_str(item.get("title") or item.get("display_title"))
            if not title:
                title = self._safe_str(item.get("desc", ""))[:100]

            author = self._get_public_nickname(item)

            url = build_note_url(
                note_id,
                note_url=self._safe_str(item.get("note_url")) or None,
                xsec_token=self._safe_str(item.get("xsec_token")) or None,
                xsec_source=self._safe_str(item.get("xsec_source")) or None,
            ) or XHS_EXPLORE_URL.format(note_id=note_id)

            published_at = _parse_timestamp(item.get("time"))

            cover_url = self._extract_cover_url(item)

            metrics = self._extract_metrics(item)

            content_type = "video" if item.get("type") == "video" else "note"

            results.append(
                UnifiedSearchResult(
                    platform="xhs",
                    content_id=note_id,
                    content_type=content_type,
                    title=title,
                    author=author,
                    url=url,
                    published_at=published_at,
                    cover_url=cover_url,
                    metrics=metrics,
                    rank=rank,
                )
            )
        return results

    def _get_public_nickname(self, item: Dict) -> Optional[str]:
        user = item.get("user") or item.get("author")
        if isinstance(user, dict):
            return user.get("nickname") or user.get("name")
        return None

    def _extract_cover_url(self, raw_item: Dict) -> Optional[str]:
        # Image list first
        image_list = raw_item.get("image_list") or []
        if isinstance(image_list, list) and image_list:
            first_img = image_list[0]
            if isinstance(first_img, dict):
                url = first_img.get("url_default") or first_img.get("url")
                if url and isinstance(url, str):
                    return url
                # Check info_list for alternate URL format
                info_list = first_img.get("info_list") or []
                if info_list and isinstance(info_list, list):
                    info = info_list[0]
                    if isinstance(info, dict):
                        info_url = info.get("url")
                        if info_url and isinstance(info_url, str):
                            return info_url

        # Video cover fallback
        video = raw_item.get("video")
        if isinstance(video, dict):
            cover = video.get("image") or video.get("cover")
            if isinstance(cover, dict):
                return cover.get("url_default") or cover.get("url")
            if isinstance(cover, str) and cover:
                return cover

        # Any cover field
        cover = raw_item.get("cover") or raw_item.get("cover_url")
        if isinstance(cover, str) and cover:
            return cover

        return None

    def _extract_metrics(self, raw_item: Dict) -> Dict[str, int]:
        interact = raw_item.get("interact_info") or {}
        metrics: Dict[str, int] = {}
        if isinstance(interact, dict):
            for src, dst in [
                ("liked_count", "like_count"),
                ("collected_count", "collect_count"),
                ("comment_count", "comment_count"),
                ("share_count", "share_count"),
            ]:
                val = self._safe_int(interact.get(src), 0)
                if val > 0:
                    metrics[dst] = val
        return metrics

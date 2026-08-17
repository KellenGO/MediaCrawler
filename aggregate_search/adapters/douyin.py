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
Douyin (抖音) adapter.

Native data: aweme_info dict from Douyin search API response.

Typical fields:
- aweme_id: str
- desc: str
- create_time: int (unix seconds)
- author: {nickname: str, uid: str, sec_uid: str}
- statistics: {digg_count, collect_count, comment_count, share_count, play_count}
- video: {cover: {url_list: [str]}, play_addr: {...}}
- share_url: str
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from aggregate_search.models import UnifiedSearchResult, _parse_timestamp, clean_snippet, clean_title

from .base import BasePlatformAdapter


class DouyinAdapter(BasePlatformAdapter):
    PLATFORM = "douyin"

    def adapt(self, raw_results: List[Any], keyword: str = "") -> List[UnifiedSearchResult]:
        results: List[UnifiedSearchResult] = []
        seen_ids: set = set()

        for rank, item in enumerate(raw_results):
            if not isinstance(item, dict):
                continue

            aweme_id = self._safe_str(item.get("aweme_id"))
            if not aweme_id:
                continue

            # De-duplicate within platform (douyin offset can cause overlap)
            if aweme_id in seen_ids:
                continue
            seen_ids.add(aweme_id)

            title = clean_title(self._safe_str(item.get("desc") or item.get("title")))
            if not title:
                title = clean_title(self._safe_str(item.get("preview_title", ""))[:100])

            author = self._get_author(item)

            url = (
                item.get("share_url")
                or item.get("aweme_url")
                or f"https://www.douyin.com/video/{aweme_id}"
            )

            published_at = _parse_timestamp(item.get("create_time"))

            # 抖音通常只有 desc（同时也是搜索标题）；若响应带有更独立的
            # 描述字段则优先使用。绝不为 snippet 追加详情请求。
            snippet = clean_snippet(
                item.get("caption")
                or item.get("description")
                or item.get("video_description")
                or item.get("text")
                or item.get("desc")
            )

            cover_url = self._extract_cover_url(item)

            metrics = self._extract_metrics(item)

            content_type = "video"

            results.append(
                UnifiedSearchResult(
                    platform="douyin",
                    content_id=aweme_id,
                    content_type=content_type,
                    title=title,
                    snippet=snippet,
                    author=author,
                    url=url,
                    published_at=published_at,
                    cover_url=cover_url,
                    metrics=metrics,
                    rank=rank,
                )
            )
        return results

    def _get_author(self, item: Dict) -> Optional[str]:
        author = item.get("author") or item.get("user")
        if isinstance(author, dict):
            return author.get("nickname") or author.get("name")
        return None

    def _extract_cover_url(self, raw_item: Dict) -> Optional[str]:
        video = raw_item.get("video")
        if isinstance(video, dict):
            # cover is typically {url_list: [str]}
            cover = video.get("cover") or video.get("origin_cover")
            if isinstance(cover, dict):
                url_list = cover.get("url_list") or []
                if url_list:
                    # Pick the highest quality (last in list for douyin)
                    return url_list[-1] if isinstance(url_list[-1], str) else url_list[0]

            # animated cover
            animated = video.get("animated_cover") or video.get("dynamic_cover")
            if isinstance(animated, dict):
                url_list = animated.get("url_list") or []
                if url_list:
                    return url_list[0] if isinstance(url_list[0], str) else None

        # Try direct cover field
        cover = raw_item.get("cover")
        if isinstance(cover, dict):
            url_list = cover.get("url_list") or []
            if url_list:
                return url_list[0]
        if isinstance(cover, str) and cover:
            return cover

        return None

    def _extract_metrics(self, raw_item: Dict) -> Dict[str, int]:
        stats = raw_item.get("statistics") or raw_item.get("stats") or {}
        metrics: Dict[str, int] = {}
        if isinstance(stats, dict):
            mapping = [
                ("digg_count", "like_count"),
                ("collect_count", "collect_count"),
                ("comment_count", "comment_count"),
                ("share_count", "share_count"),
                ("play_count", "view_count"),
            ]
            for src, dst in mapping:
                val = self._safe_int(stats.get(src), 0)
                if val > 0:
                    metrics[dst] = val
        return metrics

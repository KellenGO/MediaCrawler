# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
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

"""
Round 17.1 XiaoHongShuClient.get_note_by_keyword 请求契约测试。

直接调用生产 ``XiaoHongShuClient.get_note_by_keyword``，mock 底层 post 并
捕获 data，断言：

- image_formats 恰好为 ["jpg", "webp", "avif"]（缺失时真实搜索响应的
  note_card.cover / image_list[] 只有 height/width 没有任何图片 URL）；
- keyword/page/page_size/search_id/sort/note_type 原字段保持不变；
- 不增加 Cookie、token 或其他无关参数；
- 不复制生产请求构造逻辑到测试中。
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from media_platform.xhs.client import XiaoHongShuClient
from media_platform.xhs.field import SearchNoteType, SearchSortType


def _make_client(monkeypatch):
    """真实 client 实例；只替换 post 为记录器（捕获请求 data）。"""
    client = XiaoHongShuClient(
        headers={}, playwright_page=None, cookie_dict={})
    captured = {"uri": None, "data": None}

    async def fake_post(uri, data, **kwargs):
        captured["uri"] = uri
        captured["data"] = data
        return {"items": [], "has_more": False}

    monkeypatch.setattr(client, "post", fake_post)
    return client, captured


def test_image_formats_present_and_exact(monkeypatch):
    client, captured = _make_client(monkeypatch)

    asyncio.run(client.get_note_by_keyword(
        keyword="露营", search_id="sid-123", page=1, page_size=20,
        sort=SearchSortType.GENERAL, note_type=SearchNoteType.ALL))

    data = captured["data"]
    assert data["image_formats"] == ["jpg", "webp", "avif"], (
        "get_note_by_keyword 必须携带 image_formats")
    # 原字段保持不变。
    assert data["keyword"] == "露营"
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert data["search_id"] == "sid-123"
    assert data["sort"] == SearchSortType.GENERAL.value
    assert data["note_type"] == SearchNoteType.ALL.value
    # 不增加 Cookie/token 或其他无关参数。
    assert set(data.keys()) == {
        "keyword", "page", "page_size", "search_id", "sort", "note_type",
        "image_formats",
    }
    lowered = str(data).lower()
    assert "cookie" not in lowered
    assert "token" not in lowered
    assert "xsec" not in lowered
    assert captured["uri"] == "/api/sns/web/v1/search/notes"


def test_image_formats_with_custom_page_and_note_type(monkeypatch):
    client, captured = _make_client(monkeypatch)

    asyncio.run(client.get_note_by_keyword(
        keyword="测试", search_id="sid-456", page=2, page_size=10,
        sort=SearchSortType.MOST_POPULAR, note_type=SearchNoteType.VIDEO))

    data = captured["data"]
    assert data["image_formats"] == ["jpg", "webp", "avif"]
    assert data["page"] == 2
    assert data["page_size"] == 10
    assert data["sort"] == SearchSortType.MOST_POPULAR.value
    assert data["note_type"] == SearchNoteType.VIDEO.value
    assert set(data.keys()) == {
        "keyword", "page", "page_size", "search_id", "sort", "note_type",
        "image_formats",
    }

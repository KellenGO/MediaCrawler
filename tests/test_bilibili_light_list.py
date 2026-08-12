# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1

"""Round 9 — B站轻量列表模式（fetch_details=False）生产路径测试。

调用真实的 ``BilibiliCrawler.search_by_keywords``（fetch_details=False 时
直接把 /search/type 扁平列表项交给 result_sink，绝不调用
``get_video_info`` 详情 API）；真实 ``BilibiliAdapter`` 提取扁平字段；
真实 ``worker._classify_error`` 分类 B站错误 metadata。
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config  # noqa: E402
from base.crawler_runtime import CrawlerRuntimeOptions  # noqa: E402
from media_platform.bilibili.core import BilibiliCrawler  # noqa: E402
from media_platform.bilibili.exception import DataFetchError  # noqa: E402
from aggregate_search.adapters.bilibili import BilibiliAdapter  # noqa: E402
from aggregate_search.worker import (  # noqa: E402
    _classify_error,
    _safe_error_message,
)


# ── 真实形状的扁平搜索列表项（/x/web-interface/wbi/search/type）──────────

def _flat_item(i: int) -> dict:
    return {
        "type": "video",
        "aid": 1000000 + i,
        "bvid": f"BV1fake{i:02d}",
        "title": f"<em class=\"keyword\">露营</em> 装备推荐第{i}期",
        "pic": f"https://i0.hdslb.com/bfs/archive/fake{i}.jpg",
        "author": f"测试UP主{i}",
        "arcurl": f"https://www.bilibili.com/video/BV1fake{i:02d}",
        "pubdate": 1736937000 + i * 86400,
        "senddate": 1736937000 + i * 86400,
        "play": 10000 + i * 100,
        "video_review": 100 + i,
        "review": 50 + i,
        "favorites": 200 + i,
        "duration": "10:00",
        "mid": 990000 + i,   # 隐私字段必须被 adapter 丢弃
        "upic": f"https://i0.hdslb.com/bfs/face/fake{i}.jpg",
    }


class _FakeBiliClient:
    """Fake BilibiliClient：search 返回真实形状扁平项；get_video_info 是
    触发线 —— 轻量模式下被调用即失败。"""

    def __init__(self, pages, raise_on_detail=True):
        self.pages = list(pages)
        self.search_calls = []
        self.detail_calls = 0
        self.raise_on_detail = raise_on_detail

    async def search_video_by_keyword(self, **kwargs):
        self.search_calls.append(kwargs)
        if self.pages:
            return self.pages.pop(0)
        return {"result": []}

    async def get_video_info(self, **kwargs):
        self.detail_calls += 1
        if self.raise_on_detail:
            raise AssertionError(
                "get_video_info must not be called in light-list mode")
        aid = kwargs.get("aid")
        return {"View": {
            "aid": aid, "bvid": f"BVdetail{aid}",
            "title": f"详情标题{aid}", "pic": f"https://i0.hdslb.com/bfs/archive/d{aid}.jpg",
            "pubdate": 1736937000,
            "owner": {"mid": 1, "name": "详情UP主"},
            "stat": {"view": 1, "danmaku": 1, "reply": 1, "favorite": 1},
        }}


def _make_crawler(fake_client, sink_list, limit=10, fetch_details=False):
    crawler = BilibiliCrawler()
    crawler.bili_client = fake_client
    crawler.runtime_options = CrawlerRuntimeOptions(
        result_sink=lambda items: sink_list.extend(items),
        persist_results=False,
        login_policy="fail_fast",
        enable_comments=False,
        enable_media=False,
        result_limit=limit,
        strict_errors=False,
        headless=True,
        fetch_details=fetch_details,
    )
    return crawler


def _configure_config(monkeypatch):
    monkeypatch.setattr(config, "KEYWORDS", "露营")
    monkeypatch.setattr(config, "CRAWLER_MAX_SLEEP_SEC", 0.01)
    monkeypatch.setattr(config, "ENABLE_GET_COMMENTS", False)
    monkeypatch.setattr(config, "ENABLE_GET_MEIDAS", False)
    monkeypatch.setattr(config, "BILI_SEARCH_MODE", "normal")


# ── 轻量列表模式：真实 crawler 路径，0 次详情 API ────────────────────────

def test_light_list_mode_never_calls_detail_api(monkeypatch):
    """fetch_details=False：真实 BilibiliCrawler.search_by_keywords 把 10 个
    扁平列表项直接交给 sink，get_video_info 调用次数必须为 0（详情 API
    tripwire 不触发）。"""
    _configure_config(monkeypatch)
    pages = [{"result": [_flat_item(i) for i in range(10)]}]
    fake = _FakeBiliClient(pages)
    sink = []
    crawler = _make_crawler(fake, sink, limit=10, fetch_details=False)

    asyncio.run(crawler.search_by_keywords())

    assert len(sink) == 10, "light-list 模式必须输出全部 10 项"
    assert fake.detail_calls == 0, "轻量模式不得调用详情 API"
    assert fake.search_calls, "搜索 API 必须被调用"
    assert [r["bvid"] for r in sink] == [f"BV1fake{i:02d}" for i in range(10)]


def test_legacy_detail_mode_still_calls_detail_api(monkeypatch):
    """fetch_details=True（默认）保留原行为：逐条调用 get_video_info，
    sink 收到带 View 的详情 dict。"""
    _configure_config(monkeypatch)
    pages = [{"result": [_flat_item(i) for i in range(10)]}]
    fake = _FakeBiliClient(pages, raise_on_detail=False)
    sink = []
    crawler = _make_crawler(fake, sink, limit=10, fetch_details=True)

    asyncio.run(crawler.search_by_keywords())

    assert fake.detail_calls == 10, "legacy 模式必须调用 10 次详情 API"
    assert len(sink) == 10
    assert all("View" in item for item in sink)


def test_light_list_limits_output(monkeypatch):
    """轻量模式按 result_limit 精确裁剪 remaining，不多输出。"""
    _configure_config(monkeypatch)
    pages = [{"result": [_flat_item(i) for i in range(10)]}]
    fake = _FakeBiliClient(pages)
    sink = []
    crawler = _make_crawler(fake, sink, limit=3, fetch_details=False)

    asyncio.run(crawler.search_by_keywords())

    assert len(sink) == 3, "轻量模式必须精确裁剪到 limit"
    assert fake.detail_calls == 0


# ── Adapter：扁平字段提取 ───────────────────────────────────────────────

def test_adapter_extracts_flat_fields():
    adapter = BilibiliAdapter()
    results = adapter.adapt([_flat_item(3)], keyword="露营")
    assert len(results) == 1
    r = results[0]
    assert r.content_id == "BV1fake03"          # bvid 优先
    assert r.title == "露营 装备推荐第3期", "必须移除 <em class=keyword> 高亮标签"
    assert r.author == "测试UP主3"               # string author
    assert r.url == "https://www.bilibili.com/video/BV1fake03"  # arcurl
    assert r.cover_url == "https://i0.hdslb.com/bfs/archive/fake3.jpg"  # pic
    assert r.published_at is not None           # pubdate
    assert r.metrics["view_count"] == 10300     # play
    assert r.metrics["danmaku_count"] == 103    # video_review
    assert r.metrics["comment_count"] == 53     # review
    assert r.metrics["collect_count"] == 203    # favorites
    # 隐私：mid/upic 绝不能进入 DTO
    dump = r.model_dump_json()
    assert "mid" not in dump
    assert "upic" not in dump
    assert "990003" not in dump


def test_end_to_end_crawler_sink_adapter_full_dto(monkeypatch):
    """Round 10 端到端：真实 BilibiliCrawler.search_by_keywords
    （fetch_details=False）→ result_sink → 真实 BilibiliAdapter.adapt
    （worker handle_results 的 dict 化路径）→ DTO 字段完整，且详情 API
    调用为 0 —— 整条链路只走轻量列表。"""
    _configure_config(monkeypatch)
    pages = [{"result": [_flat_item(i) for i in range(3)]}]
    fake = _FakeBiliClient(pages)
    sink = []
    crawler = _make_crawler(fake, sink, limit=3, fetch_details=False)

    asyncio.run(crawler.search_by_keywords())

    assert fake.detail_calls == 0, "端到端链路不得调用详情 API"
    adapter = BilibiliAdapter()
    results = adapter.adapt(list(sink), keyword="露营")
    assert len(results) == 3
    for r, i in zip(results, range(3)):
        assert r.content_id == f"BV1fake{i:02d}"
        assert r.title.startswith("露营")
        assert r.author == f"测试UP主{i}"
        assert r.url == f"https://www.bilibili.com/video/BV1fake{i:02d}"
        assert r.cover_url
        assert r.published_at is not None
        assert r.metrics["view_count"] == 10000 + i * 100
        assert r.metrics["danmaku_count"] == 100 + i
        assert r.metrics["comment_count"] == 50 + i
        assert r.metrics["collect_count"] == 200 + i
    dump = results[0].model_dump_json()
    assert "mid" not in dump and "upic" not in dump, "隐私字段绝不能进 DTO"


def test_adapter_flat_url_fallback_without_arcurl():
    """arcurl 缺失或非 bilibili 域名时，由 bvid/aid 构造链接。"""
    adapter = BilibiliAdapter()
    item = _flat_item(1)
    item.pop("arcurl")
    item["title"] = "没有链接的标题"
    results = adapter.adapt([item])
    assert results[0].url == "https://www.bilibili.com/video/BV1fake01"
    item2 = _flat_item(1)
    item2["arcurl"] = "https://evil.example.com/video/x"
    results = adapter.adapt([item2])
    assert results[0].url == "https://www.bilibili.com/video/BV1fake01"


# ── worker._classify_error：B站错误 metadata 分类 ────────────────────────

def test_classify_bili_rate_limited_code_412():
    exc = DataFetchError("B站搜索请求受限", stage="search_list",
                         http_status=200, platform_code=-412,
                         safe_message="B站搜索请求受限（code -412），请稍后重试")
    assert _classify_error(exc) == "rate_limited"
    assert _safe_error_message(exc) == "B站搜索请求受限（code -412），请稍后重试"


def test_classify_bili_captcha_code_352():
    exc = DataFetchError("验证码", stage="search_list",
                         platform_code=-352,
                         safe_message="B站触发验证码或风控，请稍后重试")
    assert _classify_error(exc) == "rate_limited"


def test_classify_bili_login_required_code_101():
    exc = DataFetchError("未登录", stage="login_check", platform_code=-101,
                         safe_message="B站登录状态失效，请前往账号设置重新同步")
    assert _classify_error(exc) == "login_required"


def test_classify_bili_http_5xx_is_failed():
    exc = DataFetchError("服务器错误", stage="video_detail", http_status=502,
                         safe_message="B站视频详情接口暂时不可用（HTTP 502），请稍后重试")
    assert _classify_error(exc) == "failed"
    assert _safe_error_message(exc) == "B站视频详情接口暂时不可用（HTTP 502），请稍后重试"


def test_classify_bili_http_403_is_rate_limited():
    exc = DataFetchError("Forbidden", stage="request", http_status=403,
                         safe_message="B站接口请求被拒绝，请稍后重试")
    assert _classify_error(exc) == "rate_limited"


def test_classify_bili_no_metadata_falls_back_to_failed():
    exc = DataFetchError("something broke")
    assert _classify_error(exc) == "failed"
    # 无 safe_message 时退回类名（安全文本），绝不含 traceback
    assert _safe_error_message(exc) == "DataFetchError"

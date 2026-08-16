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
Round 16 无浏览器快速路径（fast path）测试。

覆盖 worker 生产决策（aggregate_search/worker）：
- xhs 有快照 → 不启动浏览器、直接搜索；
- fast path 首条结果前失败 → 安全回退浏览器路径（fallback_reason）；
- 已 emit 结果后失败 → 不完整重跑；
- 无快照 → 跳过 fast path；
- bilibili 无快照也可尝试 fast path（轻量列表直搜）；
- douyin 默认浏览器路径（无 fast path）；
- zhihu 有 d_c0 → 零导航直搜；无 d_c0 / fast path 失败 → 回退浏览器路径；
- fast path 与回退路径输出同一 DTO（同一 adapter）；
- 真实 create_xhs_client_from_snapshot / get_wbi_keys(page=None) 语义。

全部为本地 fake（无网络、无浏览器）。
"""

import asyncio
import io
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import aggregate_search.worker as worker_mod
from aggregate_search.protocol import parse_event_line
from aggregate_search.models import UnifiedSearchResult
from api.services.search_job_manager import _ActiveJob
from base.crawler_runtime import CrawlerRuntimeOptions

# ── Fixtures（与 adapter 测试同源）───────────────────────────────────────

XHS_NOTE_FIXTURE = {
    "note_id": "abc123def",
    "title": "露营装备推荐",
    "desc": "测试笔记",
    "type": "normal",
    "time": 1736937000,
    "user": {"nickname": "户外小白", "user_id": "user_001"},
    "interact_info": {"liked_count": "2300", "collected_count": "1800",
                      "comment_count": "156", "share_count": "89"},
    "image_list": [{"url_default": "https://ci.xiaohongshu.com/abc123.jpg"}],
    "tag_list": [{"name": "露营"}],
}

BILIBILI_FLAT_FIXTURE = {
    "bvid": "BV1yy411c8nE", "aid": 87654321,
    "title": "露营美食｜户外烧烤全攻略",
    "pic": "https://i0.hdslb.com/bfs/archive/def456.jpg",
    "pubdate": 1737023400,
    "owner": {"name": "美食探险家"},
    "stat": {"view": 150000, "like": 8000, "danmaku": 1200, "coin": 2000},
}

ZHIHU_ANSWER_FIXTURE = {
    "id": 9876543210, "type": "answer",
    "title": "新手露营需要准备哪些装备？",
    "question": {"id": 12345678, "title": "新手露营需要准备哪些装备？"},
    "author": {"id": "auth_001", "name": "户外装备控"},
    "created_time": 1736937000, "voteup_count": 3200, "comment_count": 180,
    "excerpt": "经验分享", "thumbnail": "https://pic1.zhimg.com/80/thumb_abc.jpg",
}

_ZH_FAKE_SEARCH_RESPONSE = {
    "data": [{"type": "search_result", "object": ZHIHU_ANSWER_FIXTURE}],
}


# ── Capturing stdout events ─────────────────────────────────────────────

class _FakeStdout:
    def __init__(self):
        self.buffer = io.BytesIO()

    def write(self, s):
        self.buffer.write(str(s).encode("utf-8", "replace"))

    def flush(self):
        pass

    def isatty(self):
        return False

    @property
    def encoding(self):
        return "utf-8"


def _run_capture(coro_fn, *args, **kw):
    """运行协程并捕获 worker 发出的全部协议事件（过滤非协议行）。"""
    fake = _FakeStdout()
    old_stdout = sys.stdout
    sys.stdout = fake
    try:
        asyncio.run(coro_fn(*args, **kw))
    finally:
        sys.stdout = old_stdout
    events = []
    for line in fake.buffer.getvalue().decode("utf-8", "replace").splitlines():
        evt = parse_event_line(line)
        if evt is not None:
            events.append(evt)
    return events


def _event_type(events):
    return [e.event for e in events]


def _metrics(events):
    return [e.data or {} for e in events if e.event == "metrics"]


def _results(events):
    return [e.data for e in events if e.event == "result"]


# ── Fake crawler（生产 CrawlerFactory 的替身）────────────────────────────

class _FakeCrawler:
    def __init__(self, fp_search=None, browser_start=None):
        self.fp_search = fp_search
        self.browser_start = browser_start
        self.runtime_options = None
        self.snapshot_seen = None
        self.created_from_snapshot = False
        self.browser_path_used = False

    async def create_xhs_client_from_snapshot(self, snapshot):
        self.created_from_snapshot = True
        self.snapshot_seen = dict(snapshot or {})
        return object()

    async def create_bilibili_client_from_snapshot(self, snapshot):
        self.created_from_snapshot = True
        self.snapshot_seen = dict(snapshot or {})
        return object()

    async def search(self):
        if self.fp_search:
            await self.fp_search(self)

    async def search_by_keywords(self):
        if self.fp_search:
            await self.fp_search(self)

    async def start(self):
        self.browser_path_used = True
        if self.browser_start:
            await self.browser_start(self)


def _patch_factory(monkeypatch, crawler):
    monkeypatch.setattr(
        "main.CrawlerFactory.create_crawler",
        lambda platform: crawler)


def _sink(note):
    async def _run(crawler):
        crawler.runtime_options.result_sink([note])
    return _run


def _raise(exc):
    async def _run(crawler):
        raise exc
    return _run


def _sink_then_raise(note, exc):
    async def _run(crawler):
        crawler.runtime_options.result_sink([note])
        raise exc
    return _run


# ── XHS fast path ───────────────────────────────────────────────────────

class TestXhsFastPath:
    def test_fast_path_no_browser_with_snapshot(self, monkeypatch):
        crawler = _FakeCrawler(
            fp_search=_sink(XHS_NOTE_FIXTURE),
            browser_start=_raise(AssertionError("浏览器路径不得执行")))
        _patch_factory(monkeypatch, crawler)

        events = _run_capture(
            worker_mod._run_standard_search,
            "j1", "xhs", "露营", 3, {"web_session": "v1"})

        assert crawler.created_from_snapshot is True
        assert crawler.snapshot_seen == {"web_session": "v1"}
        assert crawler.browser_path_used is False
        metrics = _metrics(events)
        assert any(m.get("fast_path_used") is True for m in metrics)
        assert not any(m.get("fallback_reason") for m in metrics)
        results = _results(events)
        assert len(results) == 1
        assert results[0]["platform"] == "xhs"
        assert results[0]["content_id"] == "abc123def"
        assert "succeeded" in [e.data.get("status") for e in events
                               if e.event == "status"]
        assert "done" in _event_type(events)
        assert "error" not in _event_type(events)

    def test_fallback_before_first_result(self, monkeypatch):
        crawler = _FakeCrawler(
            fp_search=_raise(RuntimeError("api down")),
            browser_start=_sink(XHS_NOTE_FIXTURE))
        _patch_factory(monkeypatch, crawler)

        events = _run_capture(
            worker_mod._run_standard_search,
            "j1", "xhs", "露营", 3, {"web_session": "v1"})

        assert crawler.browser_path_used is True, "首条前失败必须回退浏览器路径"
        metrics = _metrics(events)
        assert any(m.get("fast_path_used") is False for m in metrics)
        assert any(m.get("fallback_reason") == "fast_path_failed"
                   for m in metrics)
        assert len(_results(events)) == 1
        assert "done" in _event_type(events)
        assert "error" not in _event_type(events)

    def test_error_after_first_result_never_reruns(self, monkeypatch):
        """已 emit 结果后失败：按错误上报，不完整重跑浏览器路径。"""
        crawler = _FakeCrawler(
            fp_search=_sink_then_raise(XHS_NOTE_FIXTURE, RuntimeError("boom")),
            browser_start=_raise(AssertionError("不得重跑浏览器路径")))
        _patch_factory(monkeypatch, crawler)

        events = _run_capture(
            worker_mod._run_standard_search,
            "j1", "xhs", "露营", 3, {"web_session": "v1"})

        assert crawler.browser_path_used is False
        assert len(_results(events)) == 1, "不得重复请求已成功的数据"
        assert "error" in _event_type(events)
        assert "done" in _event_type(events)

    def test_no_snapshot_skips_fast_path(self, monkeypatch):
        crawler = _FakeCrawler(
            fp_search=_raise(AssertionError("无快照不得走 fast path")),
            browser_start=_sink(XHS_NOTE_FIXTURE))
        _patch_factory(monkeypatch, crawler)

        events = _run_capture(
            worker_mod._run_standard_search, "j1", "xhs", "露营", 3, None)

        assert crawler.created_from_snapshot is False
        assert crawler.browser_path_used is True
        assert not any(m.get("fast_path_used") for m in _metrics(events))
        assert len(_results(events)) == 1

    def test_fast_path_and_fallback_same_dto(self, monkeypatch):
        """fast path 与回退路径输出同一 DTO（同一 adapter/handle_results）。"""
        fast_crawler = _FakeCrawler(fp_search=_sink(XHS_NOTE_FIXTURE))
        _patch_factory(monkeypatch, fast_crawler)
        fast_events = _run_capture(
            worker_mod._run_standard_search,
            "j1", "xhs", "露营", 3, {"web_session": "v1"})

        fallback_crawler = _FakeCrawler(
            fp_search=_raise(RuntimeError("down")),
            browser_start=_sink(XHS_NOTE_FIXTURE))
        _patch_factory(monkeypatch, fallback_crawler)
        fallback_events = _run_capture(
            worker_mod._run_standard_search,
            "j2", "xhs", "露营", 3, {"web_session": "v1"})

        fast_result = _results(fast_events)[0]
        fallback_result = _results(fallback_events)[0]
        assert fast_result == fallback_result

    def test_second_completed_first_final_order_by_source_rank(self, monkeypatch):
        """Round 16.1: 第二条先完成、第一条后完成 → 渐进 emit 保持完成顺序，
        但 rank=原始 source index；manager 终态按 rank 重排恢复第一条、第二条。"""
        note_a = dict(XHS_NOTE_FIXTURE, source_index=0, note_id="aaa")
        note_b = dict(XHS_NOTE_FIXTURE, source_index=1, note_id="bbb")

        async def _sink_second_first(crawler):
            crawler.runtime_options.result_sink([note_b])  # 第二条先完成
            crawler.runtime_options.result_sink([note_a])  # 第一条后完成

        crawler = _FakeCrawler(
            fp_search=_sink_second_first,
            browser_start=_raise(AssertionError("浏览器路径不得执行")))
        _patch_factory(monkeypatch, crawler)

        events = _run_capture(
            worker_mod._run_standard_search,
            "j1", "xhs", "露营", 5, {"web_session": "v1"})

        results = _results(events)
        # 渐进 emit 顺序 = 详情完成顺序（bbb 先、aaa 后）。
        assert [r["content_id"] for r in results] == ["bbb", "aaa"]
        # rank 必须是原始 source index，而不是到达顺序。
        assert [r["rank"] for r in results] == [1, 0], \
            "rank 必须是 crawler 盖章的原始 source index"

        # manager 终态按 rank 稳定重排 → 恢复 第一条、第二条。
        job = _ActiveJob(job_id="j2", keyword="露营", platforms=["xhs"],
                         limit_per_platform=5)
        for r in results:
            job.add_result("xhs", UnifiedSearchResult(**r))
        job.finalize()
        final = [r.content_id for r in job.platform_results["xhs"]]
        assert final == ["aaa", "bbb"], \
            "最终平台结果必须按原始相关性顺序稳定排列"
        assert len(final) == 2, "不重复 emit、不改变 limit"


# ── Bilibili / Douyin ──────────────────────────────────────────────────

class TestBiliDouyinFastPath:
    def test_bilibili_fast_path_without_snapshot(self, monkeypatch):
        """bilibili 轻量列表：无快照也尝试 fast path（HTTP 直搜）。"""
        crawler = _FakeCrawler(
            fp_search=_sink(BILIBILI_FLAT_FIXTURE),
            browser_start=_raise(AssertionError("浏览器路径不得执行")))
        _patch_factory(monkeypatch, crawler)

        events = _run_capture(
            worker_mod._run_standard_search, "j1", "bilibili", "露营", 3, None)

        assert crawler.created_from_snapshot is True
        assert crawler.snapshot_seen == {}
        assert crawler.browser_path_used is False
        results = _results(events)
        assert len(results) == 1
        assert results[0]["platform"] == "bilibili"
        assert results[0]["content_id"] == "BV1yy411c8nE"
        assert "succeeded" in [e.data.get("status") for e in events
                               if e.event == "status"]

    def test_douyin_uses_browser_path_by_default(self, monkeypatch):
        """douyin 无 fast path：默认浏览器路径（无浏览器时正常失败分类）。"""
        crawler = _FakeCrawler(
            fp_search=_raise(AssertionError("douyin 没有 fast path")),
            browser_start=None)  # start 不产结果 → empty
        _patch_factory(monkeypatch, crawler)

        events = _run_capture(
            worker_mod._run_standard_search, "j1", "douyin", "露营", 3, None)

        assert crawler.browser_path_used is True
        assert crawler.created_from_snapshot is False
        assert not any(m.get("fast_path_used") for m in _metrics(events))
        assert "empty" in [e.data.get("status") for e in events
                           if e.event == "status"]
        assert "done" in _event_type(events)


# ── Zhihu fast path ─────────────────────────────────────────────────────

class TestZhihuFastPath:
    def _patch_zhihu(self, monkeypatch, fake_client_cls, playwright_calls):
        monkeypatch.setattr(
            "media_platform.zhihu.client.ZhiHuClient", fake_client_cls)

        class _NoBrowser:
            async def __aenter__(self):
                playwright_calls.append("async_playwright")
                raise RuntimeError("browser unavailable")

            async def __aexit__(self, *a):
                return False

        monkeypatch.setattr(
            "playwright.async_api.async_playwright", lambda: _NoBrowser())

    def test_dc0_fast_path_zero_navigation(self, monkeypatch):
        captured = {}

        class FakeZhiHuClient:
            def __init__(self, **kw):
                captured.update(kw)

            async def get(self, uri, params=None):
                assert "search_v3" in uri
                return _ZH_FAKE_SEARCH_RESPONSE

        playwright_calls = []
        self._patch_zhihu(monkeypatch, FakeZhiHuClient, playwright_calls)

        events = _run_capture(
            worker_mod._run_zhihu_search,
            "j1", "zhihu", "露营", 3,
            {"d_c0": "dc0-secret", "z_c0": "zc0-secret"})

        assert playwright_calls == [], "有 d_c0 时零浏览器启动/零导航"
        assert captured["playwright_page"] is None
        assert captured["cookie_dict"] == {"d_c0": "dc0-secret",
                                           "z_c0": "zc0-secret"}
        assert captured["reuse_http_client"] is True
        metrics = _metrics(events)
        assert any(m.get("fast_path_used") is True for m in metrics)
        results = _results(events)
        assert len(results) == 1
        assert results[0]["platform"] == "zhihu"
        assert results[0]["content_id"] == "9876543210"
        assert "succeeded" in [e.data.get("status") for e in events
                               if e.event == "status"]
        assert "done" in _event_type(events)

    def test_dc0_fast_path_failure_falls_back_to_browser(self, monkeypatch):
        class FakeZhiHuClient:
            def __init__(self, **kw):
                pass

            async def get(self, uri, params=None):
                raise RuntimeError("search api down")

        playwright_calls = []
        self._patch_zhihu(monkeypatch, FakeZhiHuClient, playwright_calls)

        events = _run_capture(
            worker_mod._run_zhihu_search,
            "j1", "zhihu", "露营", 3, {"d_c0": "dc0-secret"})

        assert playwright_calls, "fast path 失败必须进入浏览器路径"
        metrics = _metrics(events)
        assert any(m.get("fast_path_used") is False for m in metrics)
        assert any(m.get("fallback_reason") == "fast_path_failed"
                   for m in metrics)
        assert "error" in _event_type(events)
        assert "done" in _event_type(events)
        assert _results(events) == []

    def test_no_dc0_skips_fast_path(self, monkeypatch):
        class FakeZhiHuClient:
            def __init__(self, **kw):
                pass

            async def get(self, uri, params=None):
                raise AssertionError("不应在 fast path 中构造 client")

        playwright_calls = []
        self._patch_zhihu(monkeypatch, FakeZhiHuClient, playwright_calls)

        events = _run_capture(
            worker_mod._run_zhihu_search,
            "j1", "zhihu", "露营", 3, {"z_c0": "only-zc0"})

        assert playwright_calls, "缺 d_c0 必须回退浏览器路径"
        assert not any(m.get("fast_path_used") for m in _metrics(events))
        assert "done" in _event_type(events)


# ── 真实构造语义（page=None / WBI HTTP）─────────────────────────────────

class TestRealConstructors:
    def test_xhs_client_from_snapshot_no_page(self, monkeypatch):
        from media_platform.xhs.core import XiaoHongShuCrawler
        captured = {}

        class FakeClient:
            def __init__(self, **kw):
                captured.update(kw)

        monkeypatch.setattr("media_platform.xhs.core.XiaoHongShuClient",
                            FakeClient)
        crawler = XiaoHongShuCrawler.__new__(XiaoHongShuCrawler)
        crawler.index_url = "https://www.xiaohongshu.com"
        crawler.runtime_options = CrawlerRuntimeOptions(reuse_http_client=True)

        asyncio.run(crawler.create_xhs_client_from_snapshot(
            {"web_session": "v1", "a1": "v2"}))

        assert captured["playwright_page"] is None
        assert captured["cookie_dict"] == {"web_session": "v1", "a1": "v2"}
        assert captured["reuse_http_client"] is True

    def test_bilibili_get_wbi_keys_page_none_uses_http(self, monkeypatch):
        """page=None：跳过 localStorage，直接经 /x/web-interface/nav 拿 WBI Key。"""
        from media_platform.bilibili.client import BilibiliClient
        requested = []

        async def fake_request(method, url, **kwargs):
            requested.append(url)
            return {
                "wbi_img": {
                    "img_url": "https://i0.hdslb.com/bfs/wbi/imgkey.png",
                    "sub_url": "https://i0.hdslb.com/bfs/wbi/subkey.png",
                },
            }

        client = BilibiliClient(
            headers={}, playwright_page=None, cookie_dict={},
            reuse_http_client=True)
        monkeypatch.setattr(client, "request", fake_request)

        img_key, sub_key = asyncio.run(client.get_wbi_keys())
        assert img_key == "imgkey"
        assert sub_key == "subkey"
        assert requested == ["https://api.bilibili.com/x/web-interface/nav"]

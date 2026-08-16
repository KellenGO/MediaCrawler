# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/tests/test_search_perf.py
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

"""Phase 3 性能链路测试（直接调用生产函数，不使用墙钟固定 sleep）：

- 3.2 小红书 httpx client 复用（多次请求只建一次 client、cleanup 只关一次、
      代理变化关闭并重建、默认关闭复用时维持每请求独立生命周期）；
- 3.3 三个平台"已达 limit 时跳过页尾 sleep"（fake sleep 计数）；
- 3.4 知乎 d_c0 有界条件等待（fake clock + fake context，确定性）；
- 3.1 小红书渐进 sink（首条结果在全部详情结束前发出、异常后取消回收）。
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import config
from base.crawler_runtime import CrawlerRuntimeOptions
from media_platform.xhs.client import XiaoHongShuClient
import media_platform.xhs.client as xhs_client_module
from media_platform.xhs.core import XiaoHongShuCrawler
from media_platform.xhs.exception import DataFetchError
from media_platform.douyin.core import DouYinCrawler
from media_platform.bilibili.core import BilibiliCrawler
from aggregate_search.worker import _wait_for_zhihu_dc0


# ═══════════════════════════════════════════════════════════════════════
# 3.2 小红书 httpx client 复用
# ═══════════════════════════════════════════════════════════════════════

class _FakeResponse:
    status_code = 200
    headers = {}
    text = '{"success": true}'

    def json(self):
        return {"success": True, "data": {}}


class _FakeAsyncClient:
    created = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.close_count = 0
        _FakeAsyncClient.created.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.aclose()

    async def aclose(self):
        self.close_count += 1

    async def request(self, method, url, timeout=None, **kwargs):
        return _FakeResponse()


@pytest.fixture
def fake_client_factory(monkeypatch):
    _FakeAsyncClient.created = []
    monkeypatch.setattr(xhs_client_module, "make_async_client", _FakeAsyncClient)
    return _FakeAsyncClient


def _make_xhs_client(reuse: bool) -> XiaoHongShuClient:
    return XiaoHongShuClient(
        proxy=None,
        headers={},
        playwright_page=None,
        cookie_dict={},
        reuse_http_client=reuse,
    )


@pytest.mark.asyncio
async def test_reuse_creates_single_client(fake_client_factory):
    client = _make_xhs_client(reuse=True)
    await client.request("GET", "http://example.com/a")
    await client.request("GET", "http://example.com/b")
    assert len(_FakeAsyncClient.created) == 1  # 多次请求只创建一次 client


@pytest.mark.asyncio
async def test_cleanup_closes_once_and_idempotent(fake_client_factory):
    client = _make_xhs_client(reuse=True)
    await client.request("GET", "http://example.com/a")
    await client.aclose()
    await client.aclose()
    await client.close()
    assert _FakeAsyncClient.created[0].close_count == 1  # 只关闭一次


@pytest.mark.asyncio
async def test_proxy_change_closes_and_recreates(fake_client_factory):
    client = _make_xhs_client(reuse=True)
    await client.request("GET", "http://example.com/a")
    first = _FakeAsyncClient.created[0]
    client.proxy = "http://new-proxy:8080"
    await client.request("GET", "http://example.com/b")
    assert len(_FakeAsyncClient.created) == 2  # 代理变化 → 重建
    assert first.close_count == 1  # 旧 client 已关闭


@pytest.mark.asyncio
async def test_disabled_reuse_keeps_per_request_lifecycle(fake_client_factory):
    client = _make_xhs_client(reuse=False)
    await client.request("GET", "http://example.com/a")
    await client.request("GET", "http://example.com/b")
    assert len(_FakeAsyncClient.created) == 2  # 每个请求独立 client
    assert all(c.close_count == 1 for c in _FakeAsyncClient.created)  # 各自关闭


# ═══════════════════════════════════════════════════════════════════════
# 3.4 知乎 d_c0 有界条件等待（fake clock + fake context）
# ═══════════════════════════════════════════════════════════════════════

class _FakeZhihuContext:
    def __init__(self, cookie_values):
        self._values = list(cookie_values)
        self.poll_count = 0

    async def cookies(self, urls):
        self.poll_count += 1
        value = self._values.pop(0) if self._values else None
        if value:
            return [{"name": "d_c0", "value": value}]
        return []


class _FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


def _make_sleep(clock):
    async def _sleep(seconds):
        clock.advance(seconds)
    return _sleep


@pytest.mark.asyncio
async def test_dc0_present_on_first_poll_no_fixed_wait():
    ctx = _FakeZhihuContext(["dc0-value-1"])
    clock = _FakeClock()
    result = await _wait_for_zhihu_dc0(ctx, monotonic=clock, sleep=_make_sleep(clock))
    assert result is True
    assert ctx.poll_count == 1
    assert clock.t == 0.0  # 不发生固定等待


@pytest.mark.asyncio
async def test_dc0_appears_on_third_poll_ends_immediately():
    ctx = _FakeZhihuContext([None, None, "dc0-value-3"])
    clock = _FakeClock()
    result = await _wait_for_zhihu_dc0(ctx, monotonic=clock, sleep=_make_sleep(clock))
    assert result is True
    assert ctx.poll_count == 3
    assert clock.t == pytest.approx(0.4)  # 两次 0.2s 间隔后立即结束


@pytest.mark.asyncio
async def test_dc0_never_appears_reaches_timeout():
    ctx = _FakeZhihuContext([])  # 始终为空
    clock = _FakeClock()
    result = await _wait_for_zhihu_dc0(
        ctx, timeout_seconds=3.0, interval_seconds=0.2,
        monotonic=clock, sleep=_make_sleep(clock),
    )
    assert result is False
    assert clock.t >= 3.0  # 到达上限后结束
    assert ctx.poll_count >= 15  # 至少轮询了 3.0/0.2 次


@pytest.mark.asyncio
async def test_dc0_value_never_reaches_logs(caplog):
    import logging
    caplog.set_level(logging.INFO)
    sentinel = "super-secret-dc0-7f3a"
    ctx = _FakeZhihuContext([sentinel])
    clock = _FakeClock()
    result = await _wait_for_zhihu_dc0(ctx, monotonic=clock, sleep=_make_sleep(clock))
    assert result is True
    assert sentinel not in caplog.text  # Cookie 值绝不出现在日志


# ═══════════════════════════════════════════════════════════════════════
# 3.3 已达 limit 时跳过页尾 sleep（fake sleep 计数，直接调用生产 search）
# ═══════════════════════════════════════════════════════════════════════

def _record_sleep_caller(sleeps):
    import inspect

    async def fake_sleep(seconds):
        caller = inspect.currentframe().f_back.f_code.co_name
        sleeps.append((caller, seconds))
    return fake_sleep


class TestXhsTailSleep:
    @pytest.fixture
    def base_config(self, monkeypatch):
        monkeypatch.setattr(config, "KEYWORDS", "test")
        monkeypatch.setattr(config, "START_PAGE", 1)
        monkeypatch.setattr(config, "CRAWLER_MAX_SLEEP_SEC", 2)
        monkeypatch.setattr(config, "CRAWLER_TYPE", "search")

    def _crawler(self, result_limit, sleeps, monkeypatch):
        crawler = XiaoHongShuCrawler()
        crawler.runtime_options = CrawlerRuntimeOptions(
            result_limit=result_limit, persist_results=False,
            enable_comments=False, enable_media=False)
        crawler.xhs_client = _FakeXhsClient()
        monkeypatch.setattr(
            "media_platform.xhs.core.asyncio.sleep", _record_sleep_caller(sleeps))
        return crawler

    @pytest.mark.asyncio
    async def test_limit_reached_skips_tail_sleep(self, base_config, monkeypatch):
        sleeps = []
        crawler = self._crawler(result_limit=2, sleeps=sleeps, monkeypatch=monkeypatch)
        await crawler.search()
        tail = [s for caller, s in sleeps if caller == "search"]
        assert tail == []  # limit 已满足：页尾 sleep 调用次数为 0

    @pytest.mark.asyncio
    async def test_more_pages_needed_still_sleeps(self, base_config, monkeypatch):
        sleeps = []
        crawler = self._crawler(result_limit=10, sleeps=sleeps, monkeypatch=monkeypatch)
        await crawler.search()
        tail = [s for caller, s in sleeps if caller == "search"]
        assert len(tail) >= 1  # 仍需下一页：sleep 仍调用


class _FakeXhsClient:
    def __init__(self):
        self.sink = []

    async def get_note_by_keyword(self, **kwargs):
        return {
            "items": [
                {"id": f"n{i}", "xsec_source": "pc_search",
                 "xsec_token": "tok", "model_type": "note"}
                for i in range(5)
            ],
            "has_more": True,
        }

    async def get_note_by_id(self, note_id, xsec_source, xsec_token):
        return {"note_id": note_id, "title": f"title-{note_id}"}

    async def get_note_by_id_from_html(self, note_id, xsec_source, xsec_token,
                                       enable_cookie=False):
        return None


class TestDouyinTailSleep:
    @pytest.fixture
    def base_config(self, monkeypatch):
        monkeypatch.setattr(config, "KEYWORDS", "test")
        monkeypatch.setattr(config, "START_PAGE", 1)
        monkeypatch.setattr(config, "CRAWLER_MAX_SLEEP_SEC", 2)
        monkeypatch.setattr(config, "CRAWLER_TYPE", "search")
        monkeypatch.setattr(config, "ENABLE_GET_COMMENTS", False)
        monkeypatch.setattr(config, "ENABLE_GET_MEIDAS", False)

    def _crawler(self, result_limit, sleeps, monkeypatch):
        crawler = DouYinCrawler()
        crawler.runtime_options = CrawlerRuntimeOptions(
            result_limit=result_limit, persist_results=False,
            enable_comments=False, enable_media=False)
        crawler.dy_client = _FakeDouyinClient()
        monkeypatch.setattr(
            "media_platform.douyin.core.asyncio.sleep", _record_sleep_caller(sleeps))
        return crawler

    @pytest.mark.asyncio
    async def test_limit_reached_skips_tail_sleep(self, base_config, monkeypatch):
        sleeps = []
        crawler = self._crawler(result_limit=2, sleeps=sleeps, monkeypatch=monkeypatch)
        await crawler.search()
        assert sleeps == []  # limit 已满足：无任何页尾 sleep

    @pytest.mark.asyncio
    async def test_more_pages_needed_still_sleeps(self, base_config, monkeypatch):
        sleeps = []
        crawler = self._crawler(result_limit=10, sleeps=sleeps, monkeypatch=monkeypatch)
        await crawler.search()
        assert len(sleeps) == 1  # 仍需下一页：保留一次页尾 sleep


class _FakeDouyinClient:
    async def search_info_by_keyword(self, **kwargs):
        return {
            "status_code": 0,
            "data": [
                {"aweme_info": {"aweme_id": f"a{i}", "desc": f"d{i}",
                                "statistics": {}}, "aweme_mix_info": {}}
                for i in range(5)
            ],
            "extra": {"logid": "x"},
        }


class TestBilibiliLightListTailSleep:
    @pytest.fixture
    def base_config(self, monkeypatch):
        monkeypatch.setattr(config, "KEYWORDS", "test")
        monkeypatch.setattr(config, "START_PAGE", 1)
        monkeypatch.setattr(config, "CRAWLER_MAX_SLEEP_SEC", 2)
        monkeypatch.setattr(config, "CRAWLER_TYPE", "search")

    def _crawler(self, result_limit, sleeps, monkeypatch):
        crawler = BilibiliCrawler()
        crawler.runtime_options = CrawlerRuntimeOptions(
            result_limit=result_limit, fetch_details=False,
            persist_results=False, enable_comments=False, enable_media=False)
        crawler.bili_client = _FakeBiliClient()
        monkeypatch.setattr(
            "media_platform.bilibili.core.asyncio.sleep", _record_sleep_caller(sleeps))
        return crawler

    @pytest.mark.asyncio
    async def test_limit_reached_skips_tail_sleep(self, base_config, monkeypatch):
        sleeps = []
        crawler = self._crawler(result_limit=2, sleeps=sleeps, monkeypatch=monkeypatch)
        await crawler.search_by_keywords()
        assert sleeps == []

    @pytest.mark.asyncio
    async def test_more_pages_needed_still_sleeps(self, base_config, monkeypatch):
        sleeps = []
        crawler = self._crawler(result_limit=10, sleeps=sleeps, monkeypatch=monkeypatch)
        await crawler.search_by_keywords()
        assert len(sleeps) == 1

    @pytest.mark.asyncio
    async def test_fetch_details_false_never_calls_detail_api(self, base_config, monkeypatch):
        """fetch_details=False：sink 收到的是列表项，不是详情 DTO（不调详情 API）。"""
        sleeps = []
        crawler = self._crawler(result_limit=2, sleeps=sleeps, monkeypatch=monkeypatch)
        sunk = []
        crawler.runtime_options = CrawlerRuntimeOptions(
            result_limit=2, fetch_details=False, persist_results=False,
            result_sink=lambda items: sunk.extend(items))
        await crawler.search_by_keywords()
        assert len(sunk) == 2  # 结果数量不超过 limit
        for item in sunk:
            assert "aid" in item  # 原始列表项
            assert "View" not in item  # 绝不是详情 DTO


class _FakeBiliClient:
    async def search_video_by_keyword(self, **kwargs):
        return {"result": [{"aid": i, "title": f"t{i}", "bvid": f"BV{i}"}
                           for i in range(5)]}


# ═══════════════════════════════════════════════════════════════════════
# 3.1 小红书渐进 sink：首条 result 在全部详情结束前发出
# ═══════════════════════════════════════════════════════════════════════

class _GatedXhsClient(_FakeXhsClient):
    """第一个详情立即返回，第二个详情（n1）等待 gate（模拟慢详情）。"""

    def __init__(self, gate):
        super().__init__()
        self.gate = gate
        self.second_started = asyncio.Event()

    async def get_note_by_id(self, note_id, xsec_source, xsec_token):
        if note_id == "n1":
            self.second_started.set()
            await self.gate.wait()
        return {"note_id": note_id, "title": f"title-{note_id}"}


class TestXhsStreamingSink:
    @pytest.fixture
    def base_config(self, monkeypatch):
        monkeypatch.setattr(config, "KEYWORDS", "test")
        monkeypatch.setattr(config, "START_PAGE", 1)
        monkeypatch.setattr(config, "CRAWLER_MAX_SLEEP_SEC", 0)  # pacing 归零加速测试
        monkeypatch.setattr(config, "CRAWLER_TYPE", "search")

    @pytest.mark.asyncio
    async def test_first_result_emitted_before_all_details_finish(
            self, base_config, monkeypatch):
        """首条 result 在全部详情 gather 完成前发出，且 sink 先于 cooldown。"""
        gate = asyncio.Event()
        client = _GatedXhsClient(gate)
        crawler = XiaoHongShuCrawler()
        first_sunk = asyncio.Event()
        sink_items = []
        events = []  # ("sink", note_id) / ("sleep", secs) —— 记录生产顺序

        def sink(items):
            sink_items.extend(items)
            events.append(("sink", items[0]["note_id"]))
            if len(sink_items) == 1:
                first_sunk.set()

        crawler.runtime_options = CrawlerRuntimeOptions(
            result_limit=2, persist_results=False, stream_results=True,
            enable_comments=False, enable_media=False,
            result_sink=sink)
        crawler.xhs_client = client
        real_sleep = asyncio.sleep

        def fake_sleep(secs):
            events.append(("sleep", secs))
            return real_sleep(0)

        monkeypatch.setattr(
            "media_platform.xhs.core.asyncio.sleep", fake_sleep)

        search_task = asyncio.create_task(crawler.search())
        # 第一个详情已 sink（n0 立即返回）；第二个详情（n1）仍在等待 gate。
        await asyncio.wait_for(first_sunk.wait(), timeout=5)
        assert sink_items[0]["note_id"] == "n0"
        assert len(sink_items) == 1  # 首条已发出，n1 尚未完成（整体未结束）
        # Round 16: sink 必须先于该详情的 cooldown sleep。
        assert events.index(("sink", "n0")) < events.index(("sleep", 0))
        gate.set()
        await asyncio.wait_for(search_task, timeout=5)
        assert [i["note_id"] for i in sink_items] == ["n0", "n1"]  # 顺序保持
        # 每个详情恰好一次 sink（不重复 emit）。
        assert [e for e in events if e[0] == "sink"] == \
            [("sink", "n0"), ("sink", "n1")]

    @pytest.mark.asyncio
    async def test_streaming_strict_errors_cancels_remaining(
            self, base_config, monkeypatch):
        """strict_errors=True：DataFetchError 上抛，且剩余任务被取消回收。"""
        crawler = XiaoHongShuCrawler()
        crawler.runtime_options = CrawlerRuntimeOptions(
            result_limit=5, persist_results=False, stream_results=True,
            strict_errors=True, enable_comments=False, enable_media=False)

        class _RaisingClient(_FakeXhsClient):
            def __init__(self):
                super().__init__()
                self.cancelled = asyncio.Event()

            async def get_note_by_id(self, note_id, xsec_source, xsec_token):
                if note_id == "n2":
                    # 模拟慢任务：等待被取消
                    try:
                        await asyncio.sleep(30)
                    except asyncio.CancelledError:
                        self.cancelled.set()
                        raise
                raise DataFetchError(f"boom {note_id}")

        client = _RaisingClient()
        crawler.xhs_client = client
        real_sleep = asyncio.sleep
        monkeypatch.setattr(
            "media_platform.xhs.core.asyncio.sleep",
            lambda s: real_sleep(0))

        with pytest.raises(DataFetchError):
            await crawler.search()
        # 剩余任务已被取消（无后台泄漏）
        await asyncio.wait_for(client.cancelled.wait(), timeout=5)


# ═══════════════════════════════════════════════════════════════════════
# 4.1 小红书 source_index 盖章：详情完成顺序 ≠ 相关性顺序
# ═══════════════════════════════════════════════════════════════════════

class TestXhsSourceIndexStamping:
    @pytest.fixture
    def base_config(self, monkeypatch):
        monkeypatch.setattr(config, "KEYWORDS", "test")
        monkeypatch.setattr(config, "START_PAGE", 1)
        monkeypatch.setattr(config, "CRAWLER_MAX_SLEEP_SEC", 0)
        monkeypatch.setattr(config, "CRAWLER_TYPE", "search")

    @pytest.mark.asyncio
    async def test_detail_task_stamps_source_index(self, base_config, monkeypatch):
        """每个详情带原始搜索列表序号（0..n-1），供 worker 恢复相关性顺序。"""
        sunk = []
        crawler = XiaoHongShuCrawler()
        crawler.runtime_options = CrawlerRuntimeOptions(
            result_limit=5, persist_results=False, stream_results=True,
            result_sink=lambda items: sunk.extend(items))
        crawler.xhs_client = _FakeXhsClient()
        real_sleep = asyncio.sleep
        monkeypatch.setattr(
            "media_platform.xhs.core.asyncio.sleep", lambda s: real_sleep(0))

        await crawler.search()
        by_id = {d["note_id"]: d["source_index"] for d in sunk}
        assert by_id == {"n0": 0, "n1": 1, "n2": 2, "n3": 3, "n4": 4}

    @pytest.mark.asyncio
    async def test_source_index_survives_rec_hot_filtering(self, base_config, monkeypatch):
        """rec/hot 推荐项占位但不抓取：被过滤后序号仍按过滤前列表计算。"""
        sunk = []

        class _MixedClient(_FakeXhsClient):
            async def get_note_by_keyword(self, **kwargs):
                return {
                    "items": [
                        {"id": "rec1", "model_type": "rec_query"},
                        {"id": "n0", "xsec_source": "pc_search",
                         "xsec_token": "tok", "model_type": "note"},
                        {"id": "rec2", "model_type": "hot_query"},
                        {"id": "n1", "xsec_source": "pc_search",
                         "xsec_token": "tok", "model_type": "note"},
                    ],
                    "has_more": False,
                }

        crawler = XiaoHongShuCrawler()
        crawler.runtime_options = CrawlerRuntimeOptions(
            result_limit=2, persist_results=False, stream_results=True,
            result_sink=lambda items: sunk.extend(items))
        crawler.xhs_client = _MixedClient()
        real_sleep = asyncio.sleep
        monkeypatch.setattr(
            "media_platform.xhs.core.asyncio.sleep", lambda s: real_sleep(0))

        await crawler.search()
        by_id = {d["note_id"]: d["source_index"] for d in sunk}
        # n0 在原始列表 index=1，n1 在 index=3。
        assert by_id == {"n0": 1, "n1": 3}

    @pytest.mark.asyncio
    async def test_legacy_default_no_source_index(self, base_config, monkeypatch):
        """Round 16.2: 不传 source_index（原爬虫控制台路径）→ 数据不新增该字段。"""
        crawler = XiaoHongShuCrawler()
        crawler.runtime_options = CrawlerRuntimeOptions(
            result_limit=5, persist_results=False, stream_results=False,
            result_sink=lambda items: None)
        crawler.xhs_client = _FakeXhsClient()
        real_sleep = asyncio.sleep
        monkeypatch.setattr(
            "media_platform.xhs.core.asyncio.sleep", lambda s: real_sleep(0))

        semaphore = asyncio.Semaphore(2)
        detail = await crawler.get_note_detail_async_task(
            note_id="n0", xsec_source="pc_search", xsec_token="tok",
            semaphore=semaphore)  # 不传 source_index
        assert detail is not None
        assert "source_index" not in detail, (
            "legacy/default 路径不得向数据添加 source_index")

    @pytest.mark.asyncio
    async def test_non_stream_search_no_source_index(self, base_config, monkeypatch):
        """Round 16.2: 非聚合（非 stream）search 路径不盖章 source_index。"""
        sunk = []
        crawler = XiaoHongShuCrawler()
        crawler.runtime_options = CrawlerRuntimeOptions(
            result_limit=2, persist_results=False, stream_results=False,
            result_sink=lambda items: sunk.extend(items))
        crawler.xhs_client = _FakeXhsClient()
        real_sleep = asyncio.sleep
        monkeypatch.setattr(
            "media_platform.xhs.core.asyncio.sleep", lambda s: real_sleep(0))

        await crawler.search()
        assert sunk, "非 stream 路径也应 sink 结果"
        for detail in sunk:
            assert "source_index" not in detail, (
                "非聚合路径不得添加 source_index 字段")


class TestFinalizeSortsByRank:
    def test_finalize_restores_source_order(self):
        """manager 终态按 rank 稳定重排：第二条先到达也恢复第一条、第二条。"""
        from api.services.search_job_manager import _ActiveJob
        from aggregate_search.models import UnifiedSearchResult

        def _mk(cid, rank):
            return UnifiedSearchResult(
                platform="xhs", content_id=cid, title=cid,
                url=f"https://x/{cid}", rank=rank)

        job = _ActiveJob(job_id="j1", keyword="test", platforms=["xhs"],
                         limit_per_platform=5)
        job.add_result("xhs", _mk("b", 1))  # 第二条先到达
        job.add_result("xhs", _mk("a", 0))  # 第一条后到达
        assert [r.content_id for r in job.platform_results["xhs"]] == ["b", "a"]
        job.finalize()
        assert [r.content_id for r in job.platform_results["xhs"]] == ["a", "b"]

    def test_duplicate_content_id_not_duplicated_after_sort(self):
        """去重不受排序影响：同一 content_id 只出现一次。"""
        from api.services.search_job_manager import _ActiveJob
        from aggregate_search.models import UnifiedSearchResult

        def _mk(cid, rank):
            return UnifiedSearchResult(
                platform="xhs", content_id=cid, title=cid,
                url=f"https://x/{cid}", rank=rank)

        job = _ActiveJob(job_id="j1", keyword="test", platforms=["xhs"],
                         limit_per_platform=5)
        job.add_result("xhs", _mk("b", 1))
        job.add_result("xhs", _mk("a", 0))
        job.add_result("xhs", _mk("b", 1))  # 重复到达（应被去重）
        job.finalize()
        ids = [r.content_id for r in job.platform_results["xhs"]]
        assert ids == ["a", "b"]
        assert len(ids) == len(set(ids))

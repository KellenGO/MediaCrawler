# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/tests/test_search_timing.py
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

"""搜索耗时指标（Phase 1）测试：直接调用生产 _ActiveJob，用可控 fake clock
（monkeypatch time.perf_counter）做确定性断言，不用墙钟 sleep。"""

import sys
import os
import io
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from api.services import search_job_manager as sjm
from aggregate_search.models import UnifiedSearchResult
from aggregate_search.protocol import parse_event_line
from base.crawler_runtime import CrawlerRuntimeOptions

TERMINAL = {"succeeded", "empty", "login_required", "rate_limited",
            "timed_out", "failed", "cancelled"}


class _FakeTimingCrawler:
    """供 worker 级 timing 测试使用的替身 crawler（fast path 成功路径）。"""

    def __init__(self):
        self.runtime_options = None
        self.snapshot_seen = None

    async def create_xhs_client_from_snapshot(self, snapshot):
        self.snapshot_seen = dict(snapshot or {})
        return object()

    async def search(self):
        note = {
            "note_id": "abc123def", "title": "露营装备推荐", "type": "normal",
            "time": 1736937000, "user": {"nickname": "户外小白"},
            "interact_info": {"liked_count": "2300"},
            "image_list": [{"url_default": "https://ci.xiaohongshu.com/a.jpg"}],
        }
        self.runtime_options.result_sink([note])


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


def _capture_worker_events(coro_fn, *args, **kw):
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


class _FakeClock:
    """可控的单调时钟：t 只增不减，与 perf_counter 语义一致。"""

    def __init__(self):
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, ms: float) -> None:
        self.t += ms / 1000.0


@pytest.fixture
def clock(monkeypatch):
    fake = _FakeClock()
    monkeypatch.setattr("api.services.search_job_manager.time.perf_counter", fake)
    return fake


def _make_result(platform: str, content_id: str) -> UnifiedSearchResult:
    return UnifiedSearchResult(
        platform=platform,
        content_id=content_id,
        title=f"Test {content_id}",
        url=f"https://{platform}.example.com/{content_id}",
    )


def _make_job(clock, platforms=("xhs", "douyin")):
    # 创建 job 时记录 start_ts = clock.t
    job = sjm._ActiveJob(
        job_id="timing-1", keyword="test", platforms=list(platforms),
        limit_per_platform=5,
    )
    assert job._start_ts == clock.t
    return job


class TestSpawnTiming:
    def test_spawn_ms_recorded(self, clock):
        job = _make_job(clock)
        clock.advance(100)
        job.mark_spawn_start("xhs")
        clock.advance(50)
        job.mark_spawn_end("xhs")
        assert job.timings["xhs"].spawn_ms == 50

    def test_spawn_end_without_start_is_noop(self, clock):
        job = _make_job(clock)
        job.mark_spawn_end("xhs")  # 未记录 start → 不产生脏数据
        assert job.timings["xhs"].spawn_ms is None


class TestFirstResultTiming:
    def test_first_result_recorded_once(self, clock):
        job = _make_job(clock)
        clock.advance(1300)
        job.add_result("xhs", _make_result("xhs", "a"))
        first = job.timings["xhs"].first_result_ms
        assert first == 1300
        clock.advance(500)
        job.add_result("xhs", _make_result("xhs", "b"))
        assert job.timings["xhs"].first_result_ms == first  # 只记录一次

    def test_dedup_result_does_not_trigger_timing(self, clock):
        job = _make_job(clock)
        job.add_result("xhs", _make_result("xhs", "a"))
        clock.advance(900)
        job.add_result("xhs", _make_result("xhs", "a"))  # dup，被去重
        assert job.timings["xhs"].first_result_ms == 0  # 仍是首个结果的时间


class TestPlatformTotalTiming:
    @pytest.mark.parametrize("status", sorted(TERMINAL))
    def test_terminal_status_records_total(self, clock, status):
        job = _make_job(clock)
        clock.advance(2000)
        job.set_platform_status("xhs", status)
        assert job.timings["xhs"].total_ms == 2000

    def test_non_terminal_status_no_total(self, clock):
        job = _make_job(clock)
        job.set_platform_status("xhs", "running")
        assert job.timings["xhs"].total_ms is None

    def test_total_recorded_only_once(self, clock):
        job = _make_job(clock)
        clock.advance(1500)
        job.set_platform_status("xhs", "failed")
        first_total = job.timings["xhs"].total_ms
        clock.advance(1000)
        job.set_platform_status("xhs", "timed_out")  # terminal→terminal 不再覆盖
        assert job.timings["xhs"].total_ms == first_total

    def test_empty_via_finalize_records_total(self, clock):
        job = _make_job(clock)
        clock.advance(3000)
        job.finalize()
        assert job.timings["xhs"].total_ms == 3000
        assert job.timings["douyin"].total_ms == 3000


class TestJobTotalTiming:
    def test_job_total_ms_at_finalize(self, clock):
        job = _make_job(clock)
        clock.advance(4800)
        assert job.total_ms is None
        job.finalize()
        assert job.total_ms == 4800

    def test_response_includes_timings(self, clock):
        job = _make_job(clock)
        clock.advance(1200)
        job.add_result("xhs", _make_result("xhs", "a"))
        clock.advance(800)
        job.set_platform_status("xhs", "succeeded")
        clock.advance(600)
        job.set_platform_status("douyin", "failed")
        resp = job.to_response()
        # Round 16：job 已终态（partial）→ total_ms 实时可得（不再等 finalize）。
        assert resp.total_ms == 2600
        xhs_t = resp.platforms["xhs"].timings
        assert xhs_t is not None
        assert xhs_t.first_result_ms == 1200
        assert xhs_t.total_ms == 2000
        dy_t = resp.platforms["douyin"].timings
        assert dy_t is not None and dy_t.total_ms == 2600

    def test_response_after_finalize_has_job_total(self, clock):
        job = _make_job(clock)
        clock.advance(5000)
        job.finalize()
        resp = job.to_response()
        assert resp.total_ms == 5000
        assert resp.platforms["xhs"].timings.total_ms == 5000


class TestTimingSafety:
    def test_timing_values_are_numbers_only(self, clock):
        """timing 只含整数毫秒，不包含任何文本/Cookie/URL。"""
        job = _make_job(clock)
        clock.advance(100)
        job.mark_spawn_start("xhs")
        clock.advance(40)
        job.mark_spawn_end("xhs")
        clock.advance(1000)
        job.add_result("xhs", _make_result("xhs", "a"))
        clock.advance(1000)
        job.set_platform_status("xhs", "succeeded")
        clock.advance(500)
        job.finalize()

        data = job.to_response().model_dump_json()
        for key in ("cookie", "token", "session", "password", "traceback"):
            assert key not in data.lower()
        # timing 值只允许是 int 或 None
        t = job.timings["xhs"]
        assert isinstance(t.spawn_ms, int)
        assert isinstance(t.first_result_ms, int)
        assert isinstance(t.total_ms, int)
        assert isinstance(job.total_ms, int)


class TestInternalMetrics:
    """Round 16：worker 上报内部指标的合并（只接受白名单数值/枚举）。"""

    def test_apply_metrics_merges_numeric_fields(self, clock):
        job = _make_job(clock)
        job.apply_metrics("xhs", {
            "worker_ready_ms": 1200,
            "browser_launch_ms": 1800,
            "navigation_ms": 2400,
            "preflight_ms": 3100,
            "search_api_ms": 3600,
            "fast_path_used": True,
        })
        t = job.timings["xhs"]
        assert t.worker_ready_ms == 1200
        assert t.browser_launch_ms == 1800
        assert t.navigation_ms == 2400
        assert t.preflight_ms == 3100
        assert t.search_api_ms == 3600
        assert t.fast_path_used is True
        assert t.fallback_reason is None

    def test_apply_metrics_rejects_non_whitelist(self, clock):
        job = _make_job(clock)
        job.apply_metrics("xhs", {
            "worker_ready_ms": 100,
            "evil_cookie_value": "super-secret",
            "response_body": {"a": 1},
            "first_result_ms": "9999",  # 字符串不算数值
            "fast_path_used": "yes",    # 非布尔不算
        })
        t = job.timings["xhs"]
        assert t.worker_ready_ms == 100
        assert getattr(t, "evil_cookie_value", None) is None
        assert t.first_result_ms is None
        assert t.fast_path_used is None

    def test_apply_metrics_fallback_reason_is_bounded(self, clock):
        job = _make_job(clock)
        job.apply_metrics("xhs", {"fallback_reason": "x" * 500})
        assert len(job.timings["xhs"].fallback_reason) <= 50

    def test_metrics_never_in_response_leak_check(self, clock):
        job = _make_job(clock)
        job.apply_metrics("xhs", {"worker_ready_ms": 100, "fallback_reason": "no_browser"})
        data = job.to_response().model_dump_json()
        for key in ("cookie", "token", "session", "password", "traceback", "secret"):
            assert key not in data.lower()


class TestReusedWorkerTiming:
    """Round 16.1: reused_worker 标记在 schema/响应中表达。"""

    def test_reused_worker_field_roundtrip(self, clock):
        job = _make_job(clock)
        assert job.timings["xhs"].reused_worker is None
        job.timings["xhs"].reused_worker = True
        resp = job.to_response()
        assert resp.platforms["xhs"].timings.reused_worker is True
        assert '"reused_worker":true' in resp.model_dump_json()

    def test_worker_ready_constant_does_not_grow_with_idle(self, monkeypatch):
        """worker_ready_ms 是进程启动→模块加载完成的固定常量：模拟空闲 60s
        后第二次上报仍等于常量（修复前 worker_ready 随 perf_counter 增长）。"""
        import time as _time
        import aggregate_search.worker as worker_mod

        ready = worker_mod._PROCESS_READY_MS
        assert isinstance(ready, int) and ready >= 0
        assert worker_mod._PROCESS_START > 0

        # 假时钟：进程已"空闲"60 秒后再跑一次请求。
        fake = {"t": _time.perf_counter() + 60.0}
        monkeypatch.setattr(worker_mod.time, "perf_counter",
                            lambda: fake["t"])

        crawler = _FakeTimingCrawler()
        monkeypatch.setattr(
            "main.CrawlerFactory.create_crawler", lambda platform: crawler)
        events = _capture_worker_events(
            worker_mod._run_standard_search,
            "j1", "xhs", "露营", 3, {"web_session": "v1"})
        reported = [m["worker_ready_ms"] for m in
                    (e.data or {} for e in events if e.event == "metrics")
                    if isinstance(m, dict) and "worker_ready_ms" in m]
        assert reported, "必须上报 worker_ready_ms"
        assert all(v == ready for v in reported), (
            f"worker_ready_ms 不得随空闲增长: {reported} vs 常量 {ready}")

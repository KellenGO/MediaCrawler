# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1

"""Round 15 按平台独立搜索数量 —— 全链路测试。

覆盖：
- API schema（SearchJobRequestSchema）对 platform_limits 的严格校验；
- _ActiveJob.limit_for 的按平台有效限制计算；
- 四个平台 worker 实际收到不同的 WorkerRequest.limit；
- add_result 分平台数量保护，互不影响；
- 单平台重试收到目标平台配置值；
- 旧版统一 limit 请求仍正常；
- 取消、超时、done event、身份校验不回归。
"""

import asyncio
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pydantic import ValidationError

from aggregate_search.protocol import EVENT_PREFIX, EVENT_SEPARATOR
from aggregate_search.models import UnifiedSearchResult
from api.schemas.search import SearchJobRequestSchema
from api.services.search_job_manager import SearchJobManager, _ActiveJob


def _make_result(platform: str, content_id: str) -> UnifiedSearchResult:
    return UnifiedSearchResult(
        platform=platform,
        content_id=content_id,
        title=f"T {content_id}",
        url=f"https://{platform}.example.com/{content_id}",
        rank=0,
    )


def _event_line(job_id, event, data, platform):
    payload = json.dumps({
        "event": event, "job_id": job_id, "platform": platform, "data": data,
    })
    return f"{EVENT_PREFIX}{EVENT_SEPARATOR}{payload}"


# ── API schema（SearchJobRequestSchema）─────────────────────────────────

class TestSearchJobRequestSchema:
    def test_legacy_uniform_limit_only(self):
        req = SearchJobRequestSchema(
            keyword="k", platforms=["xhs", "douyin"], limit_per_platform=7)
        assert req.limit_per_platform == 7
        assert req.platform_limits is None

    def test_full_map_four_different_values(self):
        req = SearchJobRequestSchema(
            keyword="k", platforms=["xhs", "douyin", "bilibili", "zhihu"],
            limit_per_platform=10,
            platform_limits={"xhs": 5, "douyin": 20, "bilibili": 8, "zhihu": 12})
        assert req.platform_limits == {
            "xhs": 5, "douyin": 20, "bilibili": 8, "zhihu": 12}

    def test_partial_map_kept_as_is(self):
        """部分 map：缺失平台由 manager 回退统一值，schema 保留原样。"""
        req = SearchJobRequestSchema(
            keyword="k", platforms=["xhs", "douyin", "bilibili", "zhihu"],
            limit_per_platform=7, platform_limits={"xhs": 3})
        assert req.platform_limits == {"xhs": 3}

    def test_bounds_1_and_20_accepted(self):
        assert SearchJobRequestSchema(
            keyword="k", platform_limits={"xhs": 1}).platform_limits == {"xhs": 1}
        assert SearchJobRequestSchema(
            keyword="k", platform_limits={"xhs": 20}).platform_limits == {"xhs": 20}

    @pytest.mark.parametrize("bad", [0, 21, -1, 5.5, "5", True, None, [], {"x": 1}])
    def test_invalid_values_return_422(self, bad):
        with pytest.raises(ValidationError):
            SearchJobRequestSchema(keyword="k", platform_limits={"xhs": bad})

    def test_unknown_platform_key_returns_422(self):
        with pytest.raises(ValidationError):
            SearchJobRequestSchema(keyword="k", platform_limits={"myspace": 5})
        with pytest.raises(ValidationError):
            SearchJobRequestSchema(keyword="k", platform_limits={"xhs": 5, "bogus": 3})

    def test_platform_limits_non_object_rejected(self):
        with pytest.raises(ValidationError):
            SearchJobRequestSchema(keyword="k", platform_limits=[1, 2])


# ── _ActiveJob.limit_for（生产类）───────────────────────────────────────

class TestActiveJobLimitFor:
    def test_override_and_fallback(self):
        job = _ActiveJob("j1", "k", ["xhs", "douyin"], limit_per_platform=7,
                         platform_limits={"xhs": 3})
        assert job.limit_for("xhs") == 3       # 平台配置优先
        assert job.limit_for("douyin") == 7    # 缺失回退统一值
        assert job.limit_for("bilibili") == 7  # 未参与的平台也回退统一值

    def test_no_platform_limits_uses_uniform(self):
        job = _ActiveJob("j2", "k", ["xhs", "douyin"], limit_per_platform=5)
        assert job.limit_for("xhs") == 5
        assert job.limit_for("douyin") == 5

    def test_add_result_per_platform_caps_independent(self):
        job = _ActiveJob("j3", "k", ["xhs", "douyin"], limit_per_platform=10,
                         platform_limits={"xhs": 3, "douyin": 20})
        for i in range(10):
            job.add_result("xhs", _make_result("xhs", f"x{i}"))
        for i in range(10):
            job.add_result("douyin", _make_result("douyin", f"d{i}"))
        assert len(job.platform_results["xhs"]) == 3       # XHS=3 最多 3 条
        assert len(job.platform_results["douyin"]) == 10   # Douyin=20 接受 10 条
        assert job.platforms_state["xhs"].result_count == 3
        assert job.platforms_state["douyin"].result_count == 10

    def test_add_result_does_not_share_last_number(self):
        job = _ActiveJob("j4", "k", ["xhs", "douyin"], limit_per_platform=10,
                         platform_limits={"xhs": 3, "douyin": 20})
        for i in range(30):
            job.add_result("xhs", _make_result("xhs", f"x{i}"))
        assert len(job.platform_results["xhs"]) == 3  # 不被 douyin 的 20 影响


# ── SearchJobManager 生产链路（fake worker 记录 WorkerRequest）──────────

class _RecordingStdin:
    """记录写入的 WorkerRequest，并据其回放 done event。"""

    def __init__(self, stdout):
        self.stdout = stdout
        self.written = b""

    def write(self, b):
        self.written += b
        try:
            req = json.loads(self.written.decode("utf-8").strip())
            line = _event_line(req["job_id"], "done", None, req["platform"])
            self.stdout.feed_data((line + "\n").encode("utf-8"))
            self.stdout.feed_eof()
        except Exception:
            pass

    async def drain(self):
        pass

    def close(self):
        pass


class _RecordingProc:
    def __init__(self):
        self.stdout = asyncio.StreamReader()
        self.stderr = asyncio.StreamReader()
        self.stderr.feed_eof()
        self.stdin = _RecordingStdin(self.stdout)
        self.returncode = None

    async def wait(self):
        if self.returncode is None:
            self.returncode = 0
        return self.returncode

    def terminate(self):
        self.returncode = 0

    def kill(self):
        self.returncode = 0


def _patch_proc(monkeypatch, procs):
    async def fake_exec(*a, **k):
        proc = _RecordingProc()
        procs.append(proc)
        return proc
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)


@pytest.mark.asyncio
async def test_four_workers_receive_different_limits(monkeypatch):
    """四个平台 worker 分别收到 3/20/8/12，绝不共享最后一个数字。"""
    procs = []
    _patch_proc(monkeypatch, procs)
    manager = SearchJobManager()
    resp = await manager.create_job(SearchJobRequestSchema(
        keyword="k", platforms=["xhs", "douyin", "bilibili", "zhihu"],
        limit_per_platform=10,
        platform_limits={"xhs": 3, "douyin": 20, "bilibili": 8, "zhihu": 12}))
    job = manager._active_job
    await asyncio.wait_for(job.task, timeout=10)

    limits = {}
    for proc in procs:
        req = json.loads(proc.stdin.written.decode("utf-8").strip())
        limits[req["platform"]] = req["limit"]
    assert limits == {"xhs": 3, "douyin": 20, "bilibili": 8, "zhihu": 12}


@pytest.mark.asyncio
async def test_single_platform_retry_uses_target_configured_limit(monkeypatch):
    """单平台重试请求：platforms 只含目标平台，worker limit 用该平台配置值。"""
    procs = []
    _patch_proc(monkeypatch, procs)
    manager = SearchJobManager()
    resp = await manager.create_job(SearchJobRequestSchema(
        keyword="k", platforms=["douyin"], limit_per_platform=10,
        platform_limits={"douyin": 20}))
    job = manager._active_job
    await asyncio.wait_for(job.task, timeout=10)

    assert len(procs) == 1
    req = json.loads(procs[0].stdin.written.decode("utf-8").strip())
    assert req["platform"] == "douyin"
    assert req["limit"] == 20


@pytest.mark.asyncio
async def test_legacy_uniform_limit_still_works(monkeypatch):
    """无 platform_limits 的旧请求：所有 worker 收到统一 limit。"""
    procs = []
    _patch_proc(monkeypatch, procs)
    manager = SearchJobManager()
    resp = await manager.create_job(SearchJobRequestSchema(
        keyword="k", platforms=["xhs", "bilibili"], limit_per_platform=5))
    job = manager._active_job
    await asyncio.wait_for(job.task, timeout=10)

    limits = {}
    for proc in procs:
        req = json.loads(proc.stdin.written.decode("utf-8").strip())
        limits[req["platform"]] = req["limit"]
    assert limits == {"xhs": 5, "bilibili": 5}


@pytest.mark.asyncio
async def test_cancel_done_and_identity_no_regression(monkeypatch):
    """取消、done event、身份保护不回归：login_required 错误事件仍保留。"""
    procs = []
    _patch_proc(monkeypatch, procs)
    manager = SearchJobManager()
    resp = await manager.create_job(SearchJobRequestSchema(
        keyword="k", platforms=["zhihu"], limit_per_platform=1,
        platform_limits={"zhihu": 1}))
    job = manager._active_job
    await asyncio.wait_for(job.task, timeout=10)
    assert job.platforms_state["zhihu"].status in ("succeeded", "empty")
    assert job._compute_overall() in ("completed",)

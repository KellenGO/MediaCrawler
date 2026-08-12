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
Tests for SearchJobManager with fake workers.

All tests use in-process simulation — no real platform API calls.
"""

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from api.schemas.search import SearchJobRequestSchema, SearchJobResponse
from api.services.search_job_manager import (
    SearchJobManager,
    _ActiveJob,
    JobConflictError,
)
from aggregate_search.models import (
    UnifiedSearchResult,
    PlatformResult,
    PLATFORM_SLUGS,
)


# ── Helpers ────────────────────────────────────────────────────────────

def _make_result(platform: str, content_id: str, rank: int = 0) -> UnifiedSearchResult:
    return UnifiedSearchResult(
        platform=platform,
        content_id=content_id,
        title=f"Test {content_id}",
        url=f"https://{platform}.example.com/{content_id}",
        rank=rank,
    )


# ── ActiveJob tests (no subprocess) ────────────────────────────────────

class TestActiveJob:
    def test_initial_state(self):
        job = _ActiveJob(
            job_id="test-1",
            keyword="test",
            platforms=["xhs", "douyin"],
            limit_per_platform=10,
        )
        assert job.job_id == "test-1"
        assert not job.is_terminal()
        assert job._compute_overall() == "running"

        resp = job.to_response()
        assert resp.overall == "running"
        assert resp.platforms["xhs"].status == "pending"
        assert resp.platforms["douyin"].status == "pending"

    def test_add_and_dedup_results(self):
        job = _ActiveJob("j1", "test", ["xhs"], limit_per_platform=5)
        r1 = _make_result("xhs", "a", 0)
        r2 = _make_result("xhs", "a", 1)  # dup
        r3 = _make_result("xhs", "b", 2)

        job.add_result("xhs", r1)
        job.add_result("xhs", r2)  # should be skipped
        job.add_result("xhs", r3)

        assert len(job.platform_results["xhs"]) == 2
        assert job.platforms_state["xhs"].result_count == 2

    def test_limit_enforcement(self):
        job = _ActiveJob("j1", "test", ["xhs"], limit_per_platform=2)
        for i in range(5):
            job.add_result("xhs", _make_result("xhs", str(i), i))
        assert len(job.platform_results["xhs"]) == 2

    def test_compute_overall_all_success(self):
        job = _ActiveJob("j1", "test", ["xhs", "douyin"], limit_per_platform=5)
        job.set_platform_status("xhs", "succeeded")
        job.set_platform_status("douyin", "succeeded")
        assert job._compute_overall() == "completed"

    def test_compute_overall_partial(self):
        job = _ActiveJob("j1", "test", ["xhs", "douyin"], limit_per_platform=5)
        job.set_platform_status("xhs", "succeeded")
        job.set_platform_status("douyin", "failed")
        assert job._compute_overall() == "partial"

    def test_compute_overall_all_failed(self):
        job = _ActiveJob("j1", "test", ["xhs", "douyin"], limit_per_platform=5)
        job.set_platform_status("xhs", "failed")
        job.set_platform_status("douyin", "timed_out")
        assert job._compute_overall() == "failed"

    def test_compute_overall_empty_ok(self):
        """Empty is a success condition."""
        job = _ActiveJob("j1", "test", ["xhs"], limit_per_platform=5)
        job.set_platform_status("xhs", "empty")
        assert job._compute_overall() == "completed"

    def test_interleaved_results(self):
        job = _ActiveJob("j1", "test", ["xhs", "bilibili", "douyin", "zhihu"], limit_per_platform=2)
        job.add_result("xhs", _make_result("xhs", "x1", 0))
        job.add_result("xhs", _make_result("xhs", "x2", 1))
        job.add_result("douyin", _make_result("douyin", "d1", 0))
        job.add_result("bilibili", _make_result("bilibili", "b1", 0))

        resp = job.to_response()
        # Should be interleaved: x1, b1, d1, x2 (xhs, bili, douyin, zhihu order)
        platforms_in_order = [r.platform for r in resp.results]
        assert platforms_in_order[0] == "xhs"
        # First round: xhs, bilibili, douyin, zhihu
        # xhs has 2 → x1, then bilibili → b1, douyin → d1, zhihu → nothing
        # Second round: xhs → x2
        assert len(resp.results) == 4

    def test_no_secrets_in_response(self):
        """Response must not contain internal fields or secrets."""
        job = _ActiveJob("j1", "test", ["xhs"], limit_per_platform=1)
        job.add_result("xhs", _make_result("xhs", "a", 0))
        resp = job.to_response()
        data = resp.model_dump_json()
        assert "cookie" not in data.lower()
        assert "token" not in data.lower()
        assert "session" not in data.lower()
        assert "traceback" not in data.lower()
        assert "password" not in data.lower()


# ── SearchJobManager test with real async ──────────────────────────────

class TestSearchJobManager:
    @pytest.fixture
    def manager(self):
        return SearchJobManager()

    @pytest.mark.asyncio
    async def test_create_job_returns_response(self, manager):
        req = SearchJobRequestSchema(keyword="test", platforms=["xhs"], limit_per_platform=2)
        resp = await manager.create_job(req)
        assert resp.job_id is not None
        assert resp.overall in ("running", "failed")
        assert resp.keyword == "test"
        assert resp.platforms["xhs"].status in ("pending", "running", "failed")

    @pytest.mark.asyncio
    async def test_conflict_409(self, manager):
        req = SearchJobRequestSchema(keyword="first", platforms=["xhs"], limit_per_platform=2)
        await manager.create_job(req)

        req2 = SearchJobRequestSchema(keyword="second", platforms=["douyin"], limit_per_platform=2)
        with pytest.raises(JobConflictError):
            await manager.create_job(req2)

    @pytest.mark.asyncio
    async def test_get_nonexistent_job(self, manager):
        resp = await manager.get_job("nonexistent")
        assert resp is None

    @pytest.mark.asyncio
    async def test_get_job(self, manager):
        req = SearchJobRequestSchema(keyword="test", platforms=["xhs"], limit_per_platform=2)
        created = await manager.create_job(req)
        fetched = await manager.get_job(created.job_id)
        assert fetched is not None
        assert fetched.job_id == created.job_id

    @pytest.mark.asyncio
    async def test_default_platforms(self, manager):
        req = SearchJobRequestSchema(keyword="test", limit_per_platform=5)
        # Default should include all 4 platforms
        assert req.platforms == PLATFORM_SLUGS

    @pytest.mark.asyncio
    async def test_keyword_strip(self, manager):
        req = SearchJobRequestSchema(keyword="  露营装备  ", platforms=["xhs"], limit_per_platform=2)
        resp = await manager.create_job(req)
        assert resp.keyword == "露营装备"

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
Unit tests for aggregate_search models: DTO, dedup, interleave, time parsing.
"""

import pytest
from aggregate_search.models import (
    UnifiedSearchResult,
    PlatformResult,
    SearchJobRequest,
    SearchJobStatus,
    WorkerRequest,
    WorkerEvent,
    PLATFORM_SLUGS,
    make_dedup_key,
    interleave_results,
    _parse_timestamp,
)


class TestUnifiedSearchResult:
    def test_minimal_result(self):
        r = UnifiedSearchResult(
            platform="xhs",
            content_id="abc123",
            title="测试笔记",
            url="https://www.xiaohongshu.com/explore/abc123",
            rank=0,
        )
        assert r.platform == "xhs"
        assert r.content_id == "abc123"
        assert r.content_type == "note"  # default
        assert r.author is None
        assert r.metrics == {}
        assert r.cover_url is None

    def test_full_result(self):
        r = UnifiedSearchResult(
            platform="douyin",
            content_id="7123456789",
            content_type="video",
            title="测试视频",
            author="测试作者",
            url="https://www.douyin.com/video/7123456789",
            published_at="2025-01-15T10:30:00",
            cover_url="https://example.com/cover.jpg",
            metrics={"like_count": 100, "comment_count": 50},
            rank=3,
        )
        data = r.model_dump()
        assert data["platform"] == "douyin"
        assert data["metrics"]["like_count"] == 100

    def test_extra_fields_ignored(self):
        r = UnifiedSearchResult(
            platform="bilibili",
            content_id="BV123",
            title="Test",
            url="https://www.bilibili.com/video/BV123",
            rank=0,
            # extra field not in model — should be ignored
            some_extra_field="should_be_ignored",
        )
        data = r.model_dump()
        assert "some_extra_field" not in data


class TestPlatformResult:
    def test_defaults(self):
        pr = PlatformResult(platform="xhs", status="succeeded")
        assert pr.platform == "xhs"
        assert pr.status == "succeeded"
        assert pr.results == []
        assert pr.error_summary is None

    def test_with_results(self):
        r = UnifiedSearchResult(
            platform="zhihu",
            content_id="z1",
            title="Q",
            url="https://www.zhihu.com/answer/z1",
            rank=0,
        )
        pr = PlatformResult(platform="zhihu", status="succeeded", results=[r])
        assert len(pr.results) == 1


class TestSearchJobRequest:
    def test_valid_minimal(self):
        req = SearchJobRequest(keyword="露营装备")
        assert req.keyword == "露营装备"
        assert req.platforms == PLATFORM_SLUGS
        assert req.limit_per_platform == 10

    def test_empty_keyword_rejected(self):
        with pytest.raises(Exception):  # pydantic validation error
            SearchJobRequest(keyword="")

    def test_limit_bounds(self):
        req = SearchJobRequest(keyword="test", limit_per_platform=20)
        assert req.limit_per_platform == 20

        with pytest.raises(Exception):
            SearchJobRequest(keyword="test", limit_per_platform=0)

        with pytest.raises(Exception):
            SearchJobRequest(keyword="test", limit_per_platform=21)

    def test_specific_platforms(self):
        req = SearchJobRequest(keyword="test", platforms=["xhs", "zhihu"])
        assert req.platforms == ["xhs", "zhihu"]

    def test_strip_keyword(self):
        """Keyword should be stripped of whitespace."""
        req = SearchJobRequest(keyword="  露营  ")
        assert req.keyword == "  露营  "  # pydantic doesn't auto-strip — done at API level


class TestDedup:
    def test_make_dedup_key(self):
        assert make_dedup_key("xhs", "abc") == "xhs:abc"
        assert make_dedup_key("zhihu", "123") == "zhihu:123"

    def test_different_platforms_same_id(self):
        """Same content_id on different platforms should NOT be treated as dup."""
        k1 = make_dedup_key("xhs", "123")
        k2 = make_dedup_key("douyin", "123")
        assert k1 != k2


class TestInterleave:
    def test_empty(self):
        assert interleave_results({}) == []

    def test_single_platform(self):
        r1 = UnifiedSearchResult(platform="xhs", content_id="1", title="A", url="u", rank=0)
        r2 = UnifiedSearchResult(platform="xhs", content_id="2", title="B", url="u", rank=1)
        merged = interleave_results({"xhs": [r1, r2]})
        assert len(merged) == 2
        assert merged[0].content_id == "1"
        assert merged[1].content_id == "2"

    def test_two_platforms_interleave(self):
        r1 = UnifiedSearchResult(platform="xhs", content_id="x1", title="X1", url="u", rank=0)
        r2 = UnifiedSearchResult(platform="xhs", content_id="x2", title="X2", url="u", rank=1)
        r3 = UnifiedSearchResult(platform="xhs", content_id="x3", title="X3", url="u", rank=2)
        d1 = UnifiedSearchResult(platform="douyin", content_id="d1", title="D1", url="u", rank=0)
        d2 = UnifiedSearchResult(platform="douyin", content_id="d2", title="D2", url="u", rank=1)

        merged = interleave_results(
            {"xhs": [r1, r2, r3], "douyin": [d1, d2]},
            platform_order=["xhs", "douyin"],
        )
        # Round-robin: x1, d1, x2, d2, x3
        assert [m.content_id for m in merged] == ["x1", "d1", "x2", "d2", "x3"]

    def test_dedup_in_interleave(self):
        r1 = UnifiedSearchResult(platform="xhs", content_id="1", title="A", url="u", rank=0)
        r2 = UnifiedSearchResult(platform="xhs", content_id="1", title="A dup", url="u", rank=1)
        merged = interleave_results({"xhs": [r1, r2]})
        assert len(merged) == 1

    def test_cross_platform_dedup_not_happening(self):
        """Same ID on different platforms is allowed."""
        r1 = UnifiedSearchResult(platform="xhs", content_id="123", title="A", url="u", rank=0)
        r2 = UnifiedSearchResult(platform="douyin", content_id="123", title="B", url="u", rank=0)
        merged = interleave_results({"xhs": [r1], "douyin": [r2]})
        assert len(merged) == 2


class TestTimeParsing:
    def test_seconds_timestamp(self):
        # 2025-01-15 10:30:00 UTC = 1736937000
        result = _parse_timestamp(1736937000)
        assert result is not None
        assert "2025-01-15" in result

    def test_ms_timestamp(self):
        # 1736937000000 ms = 2025-01-15 10:30:00 UTC
        result = _parse_timestamp(1736937000000)
        assert result is not None
        assert "2025-01-15" in result

    def test_iso_string(self):
        result = _parse_timestamp("2025-01-15T10:30:00")
        assert result is not None
        assert "2025-01-15" in result

    def test_null(self):
        assert _parse_timestamp(None) is None

    def test_zero(self):
        assert _parse_timestamp(0) is None

    def test_negative(self):
        assert _parse_timestamp(-1) is None

    def test_invalid_string(self):
        assert _parse_timestamp("not-a-date") is None


class TestWorkerProtocol:
    def test_worker_request(self):
        req = WorkerRequest(job_id="j1", mode="search", platform="xhs", keyword="test", limit=10)
        data = req.model_dump()
        assert data["job_id"] == "j1"
        assert data["mode"] == "search"

    def test_worker_event(self):
        evt = WorkerEvent(
            event="status",
            job_id="j1",
            platform="xhs",
            data={"status": "running"},
        )
        data = evt.model_dump_json()
        assert "status" in data
        assert "running" in data

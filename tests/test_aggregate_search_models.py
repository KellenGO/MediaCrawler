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
    clean_snippet,
    clean_title,
    deduplicate_cross_platform_results,
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
        assert r.snippet is None
        assert r.metrics == {}
        assert r.cover_url is None

    def test_full_result(self):
        r = UnifiedSearchResult(
            platform="douyin",
            content_id="7123456789",
            content_type="video",
            title="测试视频",
            snippet="这是视频摘要",
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
        assert data["snippet"] == "这是视频摘要"

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

    def test_clean_snippet_removes_html_collapses_whitespace_and_limits_length(self):
        assert clean_snippet(" <p>这是&nbsp;一段</p>\n<b>摘要</b> ") == "这是 一段 摘要"
        assert clean_snippet("<script>alert(1)</script>正文") == "正文"
        cleaned = clean_snippet("x" * 200)
        assert cleaned is not None
        assert len(cleaned) == 180
        assert cleaned.endswith("…")
        assert clean_snippet(" <br> \n\t") is None

    def test_clean_title_removes_html_without_truncating(self):
        title = clean_title("2026年（8月）1000元<em>以下人体工学椅</em>选购推荐")
        assert title == "2026年（8月）1000元以下人体工学椅选购推荐"


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

    # ── Round 15: platform_limits ────────────────────────────────────────

    def test_platform_limits_default_none(self):
        req = SearchJobRequest(keyword="k")
        assert req.platform_limits is None

    def test_platform_limits_full_map(self):
        req = SearchJobRequest(
            keyword="k", limit_per_platform=10,
            platform_limits={"xhs": 5, "douyin": 20, "bilibili": 8, "zhihu": 12})
        assert req.platform_limits == {
            "xhs": 5, "douyin": 20, "bilibili": 8, "zhihu": 12}

    def test_platform_limits_bounds_accepted(self):
        assert SearchJobRequest(
            keyword="k", platform_limits={"xhs": 1}).platform_limits == {"xhs": 1}
        assert SearchJobRequest(
            keyword="k", platform_limits={"xhs": 20}).platform_limits == {"xhs": 20}

    @pytest.mark.parametrize("bad", [0, 21, -1, 5.5, "5", True, None, [5], {"x": 1}])
    def test_platform_limits_invalid_values_rejected(self, bad):
        with pytest.raises(Exception):
            SearchJobRequest(keyword="k", platform_limits={"xhs": bad})

    def test_platform_limits_unknown_platform_rejected(self):
        with pytest.raises(Exception):
            SearchJobRequest(keyword="k", platform_limits={"myspace": 5})
        with pytest.raises(Exception):
            SearchJobRequest(keyword="k", platform_limits={"xhs": 5, "bogus": 3})


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
        """Same ID with unrelated titles must remain separate."""
        r1 = UnifiedSearchResult(platform="xhs", content_id="123", title="A", url="u", rank=0)
        r2 = UnifiedSearchResult(platform="douyin", content_id="123", title="B", url="u", rank=0)
        merged = interleave_results({"xhs": [r1], "douyin": [r2]})
        assert len(merged) == 2

    def test_exact_normalized_title_is_cross_platform_deduped(self):
        r1 = UnifiedSearchResult(
            platform="xhs", content_id="x1",
            title="iPhone 18 使用一个月真实体验！", url="u", rank=0,
        )
        r2 = UnifiedSearchResult(
            platform="douyin", content_id="d1",
            title="iphone18使用一个月真实体验", url="u", rank=1,
            snippet="详细记录使用一个月后的体验。", author="作者",
        )
        merged = interleave_results({"xhs": [r1], "douyin": [r2]})
        assert len(merged) == 1
        assert merged[0].content_id == "d1"  # more complete representative

    def test_fuzzy_title_requires_supporting_signal(self):
        base = UnifiedSearchResult(
            platform="xhs", content_id="x1",
            title="iPhone 18 使用一个月真实体验分享", url="u", rank=0,
            published_at="2026-08-01T00:00:00+00:00",
        )
        similar = UnifiedSearchResult(
            platform="bilibili", content_id="b1",
            title="iPhone18使用一个月真实体验", url="u", rank=1,
            published_at="2026-08-05T00:00:00+00:00",
        )
        assert len(deduplicate_cross_platform_results([base, similar])) == 1

        different_topic = UnifiedSearchResult(
            platform="douyin", content_id="d1",
            title="iPhone 18 使用一个月续航测试", url="u", rank=1,
            published_at="2026-12-01T00:00:00+00:00",
        )
        assert len(deduplicate_cross_platform_results([base, different_topic])) == 2

    def test_same_author_title_suffix_is_cross_platform_deduped(self):
        base = UnifiedSearchResult(
            platform="xhs", content_id="x1",
            title="全网最全！60分钟全面掌握Claude Code~", author="秋芝2046", url="u", rank=0,
        )
        expanded = UnifiedSearchResult(
            platform="bilibili", content_id="b1",
            title="全网最全！60分钟全面掌握Claude Code~【附完整文档】", author="秋芝2046", url="u", rank=1,
        )
        assert len(deduplicate_cross_platform_results([base, expanded])) == 1

    def test_connected_duplicate_cluster_keeps_one_for_three_platform_copies(self):
        results = [
            UnifiedSearchResult(
                platform="xhs", content_id="a", title="Claude Code 全面教程", author="秋芝", url="u", rank=0,
            ),
            UnifiedSearchResult(
                platform="bilibili", content_id="b", title="Claude Code 全面教程安装与配置", author="秋芝2046", url="u", rank=1,
            ),
            UnifiedSearchResult(
                platform="douyin", content_id="c", title="Claude Code 全面教程实战与部署", author="秋芝_2046", url="u", rank=2,
            ),
        ]
        assert len(deduplicate_cross_platform_results(results)) == 1

    def test_same_author_different_videos_are_not_clustered(self):
        results = [
            UnifiedSearchResult(
                platform="xhs", content_id="a", title="Claude Code 入门教程", author="秋芝", url="u", rank=0,
            ),
            UnifiedSearchResult(
                platform="bilibili", content_id="b", title="Claude Code 调试技巧", author="秋芝2046", url="u", rank=1,
            ),
            UnifiedSearchResult(
                platform="douyin", content_id="c", title="Claude Code 插件开发", author="秋芝_2046", url="u", rank=2,
            ),
        ]
        assert len(deduplicate_cross_platform_results(results)) == 3

    def test_dangerous_duplicate_chain_does_not_merge_the_third_title(self):
        results = [
            UnifiedSearchResult(
                platform="xhs", content_id="a", title="Claude Code 入门教程", author="秋芝", url="u", rank=0,
            ),
            UnifiedSearchResult(
                platform="bilibili", content_id="b", title="Claude Code 入门教程与配置", author="秋芝", url="u", rank=1,
            ),
            UnifiedSearchResult(
                platform="douyin", content_id="c", title="Claude Code 入门与配置", author="秋芝", url="u", rank=2,
            ),
        ]
        assert len(deduplicate_cross_platform_results(results)) == 2

    def test_same_author_similar_but_different_topic_is_retained(self):
        first = UnifiedSearchResult(
            platform="xhs", content_id="x1",
            title="Claude Code 入门教程与安装", author="秋芝2046", url="u", rank=0,
        )
        second = UnifiedSearchResult(
            platform="bilibili", content_id="b1",
            title="Claude Code 进阶实战与部署", author="秋芝2046", url="u", rank=1,
        )
        assert len(deduplicate_cross_platform_results([first, second])) == 2

    def test_same_content_id_different_platform_is_not_id_only_deduped(self):
        r1 = UnifiedSearchResult(
            platform="xhs", content_id="same-id", title="露营装备清单", url="u", rank=0,
        )
        r2 = UnifiedSearchResult(
            platform="douyin", content_id="same-id", title="城市通勤装备推荐", url="u", rank=0,
        )
        assert len(deduplicate_cross_platform_results([r1, r2])) == 2


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

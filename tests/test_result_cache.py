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
Round 16 短内存结果缓存测试。

- 默认 TTL=90 秒：普通重复搜索命中缓存；
- 启用后：命中缓存不启动 worker，结果回放一致；
- TTL 过期 → 未命中；账号代数变化（同步/失效/清除）→ 未命中；
- bypass_cache 跳过查/写；limit/关键词不同 → 不同 key；
- 只缓存 succeeded/empty（failed 不缓存）；empty 也缓存；
- shutdown 清理。
"""

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio

import api.services.search_job_manager as sjm
import api.services.result_cache as result_cache
from api.services import accounts as acc
from aggregate_search.models import UnifiedSearchResult
from api.schemas.search import SearchJobRequestSchema


def _make_result(content_id: str, rank: int = 0) -> UnifiedSearchResult:
    return UnifiedSearchResult(
        platform="xhs", content_id=content_id, title=f"T {content_id}",
        url=f"https://xhs.example.com/{content_id}", rank=rank)


@pytest_asyncio.fixture
async def manager(monkeypatch):
    """缓存测试 manager：_run_worker 用记录桩替代（无子进程）。"""
    mgr = sjm.SearchJobManager()
    calls = []

    async def fake_run_worker(job, platform):
        calls.append((job.job_id, platform))
        job.add_result(platform, _make_result("cached-note", 0))
        job.set_platform_status(platform, "succeeded")

    monkeypatch.setattr(mgr, "_run_worker", fake_run_worker)
    yield mgr, calls
    await mgr.cleanup()
    result_cache.clear()


def _enable_cache(monkeypatch):
    monkeypatch.setattr(result_cache, "_CACHE_TTL_SECONDS", 60)


async def _run(manager, keyword="露营", platforms=None, limit=5,
               bypass_cache=False):
    req = SearchJobRequestSchema(
        keyword=keyword, platforms=platforms or ["xhs"],
        limit_per_platform=limit, bypass_cache=bypass_cache)
    resp = await manager.create_job(req)
    job = manager._active_job
    if job is not None and job.task is not None:
        await asyncio.wait_for(job.task, timeout=10)
    return await manager.get_job(resp.job_id)


class TestResultCache:
    def test_enabled_by_default(self, manager, monkeypatch):
        """默认 TTL=90 秒：普通重复搜索命中短缓存。"""
        mgr, calls = manager
        assert result_cache.ttl_seconds() == result_cache.DEFAULT_CACHE_TTL_SECONDS
        first = asyncio.run(_run(mgr))
        assert first.platforms["xhs"].status == "succeeded"
        second = asyncio.run(_run(mgr))
        assert second.platforms["xhs"].status == "succeeded"
        assert len(calls) == 1, "默认缓存应复用短时间内的结果"

    def test_cache_hit_skips_worker(self, manager, monkeypatch):
        """启用后：第二次搜索命中缓存，不启动 worker，结果一致。"""
        _enable_cache(monkeypatch)
        mgr, calls = manager
        first = asyncio.run(_run(mgr))
        assert first.platforms["xhs"].status == "succeeded"
        assert len(calls) == 1

        second = asyncio.run(_run(mgr))
        assert len(calls) == 1, "命中缓存不得再启动 worker"
        assert second.platforms["xhs"].status == "succeeded"
        assert second.platforms["xhs"].result_count == 1
        assert second.results[0].content_id == "cached-note"

    def test_ttl_expiry_misses(self, manager, monkeypatch):
        _enable_cache(monkeypatch)
        mgr, calls = manager
        asyncio.run(_run(mgr))
        assert len(calls) == 1
        # 让缓存过期（TTL 60s，直接改写入时间戳）。
        key = None
        for k in result_cache._cache:
            if k[1] == "xhs":
                key = k
        result_cache._cache[key]["ts"] -= 61
        second = asyncio.run(_run(mgr))
        assert len(calls) == 2, "过期后必须重新搜索"

    def test_account_generation_invalidates(self, manager, monkeypatch):
        """账号同步/失效/清除（代数自增）→ 缓存自动失效。"""
        _enable_cache(monkeypatch)
        mgr, calls = manager
        asyncio.run(_run(mgr))
        assert len(calls) == 1
        asyncio.run(acc.clear_session_snapshot("xhs"))  # 账号操作 → 代数 +1
        second = asyncio.run(_run(mgr))
        assert len(calls) == 2, "账号操作后缓存必须失效"

    def test_bypass_cache_skips_lookup_and_store(self, manager, monkeypatch):
        _enable_cache(monkeypatch)
        mgr, calls = manager
        first = asyncio.run(_run(mgr, bypass_cache=True))
        assert first.platforms["xhs"].status == "succeeded"
        assert len(calls) == 1
        # bypass 不写缓存 → 普通搜索仍未命中。
        second = asyncio.run(_run(mgr))
        assert len(calls) == 2

    def test_different_limit_is_different_key(self, manager, monkeypatch):
        _enable_cache(monkeypatch)
        mgr, calls = manager
        asyncio.run(_run(mgr, limit=5))
        assert len(calls) == 1
        asyncio.run(_run(mgr, limit=10))
        assert len(calls) == 2, "limit 不同 → 不同缓存 key"

    def test_different_keyword_normalization(self, manager, monkeypatch):
        """关键词标准化：大小写/首尾空白相同 → 命中；不同词 → 未命中。"""
        _enable_cache(monkeypatch)
        mgr, calls = manager
        asyncio.run(_run(mgr, keyword="露营"))
        assert len(calls) == 1
        asyncio.run(_run(mgr, keyword="  露营  "))
        assert len(calls) == 1, "标准化关键词应命中缓存"
        asyncio.run(_run(mgr, keyword="帐篷"))
        assert len(calls) == 2, "不同关键词不命中"

    def test_failed_platform_not_cached(self, manager, monkeypatch):
        """failed 终态绝不缓存。"""
        _enable_cache(monkeypatch)
        mgr, calls = manager

        async def failing_run_worker(job, platform):
            calls.append((job.job_id, platform))
            job.set_platform_status(platform, "failed",
                                    error_summary="boom")

        monkeypatch.setattr(mgr, "_run_worker", failing_run_worker)
        first = asyncio.run(_run(mgr))
        assert first.platforms["xhs"].status == "failed"
        assert result_cache._cache == {}, "failed 不得写入缓存"

    def test_partial_job_is_not_cached(self, manager, monkeypatch):
        """一个平台失败时，另一个平台的成功结果也不能单独落缓存。"""
        _enable_cache(monkeypatch)
        mgr, calls = manager

        async def partial_run_worker(job, platform):
            calls.append((job.job_id, platform))
            if platform == "xhs":
                job.add_result(platform, _make_result("partial-success"))
                job.set_platform_status(platform, "succeeded")
            else:
                job.set_platform_status(platform, "failed", error_summary="boom")

        monkeypatch.setattr(mgr, "_run_worker", partial_run_worker)
        result = asyncio.run(_run(mgr, platforms=["xhs", "douyin"]))
        assert result.overall == "partial"
        assert result_cache._cache == {}, "partial 结果不得写入任何平台缓存"

    def test_empty_is_cached(self, manager, monkeypatch):
        """empty（无结果）也缓存，避免重复搜索空关键词。"""
        _enable_cache(monkeypatch)
        mgr, calls = manager

        async def empty_run_worker(job, platform):
            calls.append((job.job_id, platform))
            job.set_platform_status(platform, "empty")

        monkeypatch.setattr(mgr, "_run_worker", empty_run_worker)
        first = asyncio.run(_run(mgr))
        assert first.platforms["xhs"].status == "empty"
        assert len(calls) == 1
        second = asyncio.run(_run(mgr))
        assert len(calls) == 1, "empty 命中缓存"
        assert second.platforms["xhs"].status == "empty"

    def test_shutdown_clears_cache(self, manager, monkeypatch):
        _enable_cache(monkeypatch)
        mgr, calls = manager
        asyncio.run(_run(mgr))
        assert result_cache._cache
        asyncio.run(mgr.cleanup())
        assert result_cache._cache == {}


class TestCacheCapacityAndEviction:
    """Round 16.1: 容量上限、LRU 淘汰、过期清理、旧代数清理。"""

    def test_evicts_oldest_when_over_capacity(self, monkeypatch):
        _enable_cache(monkeypatch)
        monkeypatch.setattr(result_cache, "MAX_ENTRIES", 3)
        result_cache.clear()
        try:
            for i in range(4):
                result_cache.set(f"kw{i}", "xhs", 5, [_make_result(str(i))])
            assert len(result_cache._cache) == 3
            # 最早写入的 kw0 被淘汰。
            assert result_cache.get("kw0", "xhs", 5) is None
            assert result_cache.get("kw3", "xhs", 5) is not None
        finally:
            result_cache.clear()

    def test_lru_hit_moves_to_back(self, monkeypatch):
        _enable_cache(monkeypatch)
        monkeypatch.setattr(result_cache, "MAX_ENTRIES", 2)
        result_cache.clear()
        try:
            result_cache.set("a", "xhs", 5, [_make_result("a")])
            result_cache.set("b", "xhs", 5, [_make_result("b")])
            result_cache.get("a", "xhs", 5)  # 命中 a → a 变为最近使用
            result_cache.set("c", "xhs", 5, [_make_result("c")])
            # b 最久未使用被淘汰，a 保留。
            assert result_cache.get("b", "xhs", 5) is None
            assert result_cache.get("a", "xhs", 5) is not None
        finally:
            result_cache.clear()

    def test_expired_entries_cleaned_on_get(self, monkeypatch):
        _enable_cache(monkeypatch)
        result_cache.clear()
        try:
            result_cache.set("kw", "xhs", 5, [_make_result("a")])
            key = next(iter(result_cache._cache))
            result_cache._cache[key]["ts"] -= 61  # 过期
            assert result_cache.get("kw", "xhs", 5) is None
            assert result_cache._cache == {}, "get 应清理过期项"
        finally:
            result_cache.clear()

    def test_stale_generation_cleaned_on_set(self, monkeypatch):
        """账号代数推进后：旧代数条目在 set 时被清理（不永久留存）。"""
        _enable_cache(monkeypatch)
        result_cache.clear()
        try:
            result_cache.set("kw", "xhs", 5, [_make_result("old")])
            assert len(result_cache._cache) == 1
            # 账号操作推进代数（模拟）。
            asyncio.run(acc.clear_session_snapshot("xhs"))
            assert result_cache._cache, "代数推进后旧条目暂时仍存在（不可达）"
            # 任意平台 set 触发清理（生产每次成功搜索都会 set）。
            result_cache.set("kw2", "xhs", 5, [_make_result("new")])
            stale = [k for k in result_cache._cache if k[1] == "xhs"
                     and k[3] != acc.get_account_generation("xhs")]
            assert stale == [], "旧代数条目必须被清理"
            assert result_cache.get("kw", "xhs", 5) is None
        finally:
            result_cache.clear()

    def test_empty_results_cached_as_empty(self, monkeypatch):
        """empty（无结果）也缓存：命中返回 []（非 None），不重复搜索。"""
        _enable_cache(monkeypatch)
        result_cache.clear()
        try:
            result_cache.set("kw", "xhs", 5, [])
            hit = result_cache.get("kw", "xhs", 5)
            assert hit == []
        finally:
            result_cache.clear()

    def test_ttl_zero_stores_nothing(self, monkeypatch):
        """显式 TTL=0 时完全禁用缓存。"""
        monkeypatch.setattr(result_cache, "_CACHE_TTL_SECONDS", 0)
        result_cache.clear()
        try:
            assert result_cache.ttl_seconds() == 0
            result_cache.set("kw", "xhs", 5, [_make_result("a")])
            result_cache.set("kw2", "xhs", 5, [])
            assert result_cache._cache == {}
        finally:
            result_cache.clear()

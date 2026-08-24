import asyncio

import pytest

from aggregate_search.hydration import (
    HYDRATION_CONCURRENCY,
    hydrate_results,
    hydration_candidates,
    needs_hydration,
)
from aggregate_search.models import UnifiedSearchResult


def result(title="Claude Code 教程", snippet=None, index=0):
    return UnifiedSearchResult(
        platform="bilibili", content_id=str(index), title=title,
        snippet=snippet, author="作者", url="https://example.test", rank=index,
    )


def test_needs_hydration_for_empty_title_duplicate_and_weak_text():
    assert needs_hydration(result(snippet=None))
    assert needs_hydration(result(snippet="Claude Code 教程"))
    assert needs_hydration(result(snippet="暂无简介"))


def test_normal_snippet_is_not_hydrated():
    assert not needs_hydration(result(
        snippet="从安装、配置到实际项目使用，整理了完整操作流程和常见问题。"
    ))


@pytest.mark.asyncio
async def test_hydration_updates_success_and_preserves_failure():
    items = [result(snippet=None, index=1), result(snippet=None, index=2)]

    async def fetch(item):
        if item.content_id == "2":
            raise RuntimeError("detail failed")
        return "这是补全后的正文简介。"

    updates = await hydrate_results(items, fetch)
    assert [(u.result.content_id, u.snippet) for u in updates] == [
        ("1", "这是补全后的正文简介。")
    ]
    assert items[0].snippet == "这是补全后的正文简介。"
    assert items[1].snippet is None


@pytest.mark.asyncio
async def test_timeout_does_not_block_other_results_and_concurrency_is_bounded():
    items = [result(snippet=None, index=i) for i in range(20)]
    active = 0
    maximum = 0

    async def fetch(item):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        try:
            if item.content_id == "0":
                await asyncio.sleep(0.05)
            else:
                await asyncio.sleep(0.001)
                return f"正文简介 {item.content_id}"
        finally:
            active -= 1

    updates = await hydrate_results(
        items, fetch, limit=12, concurrency=HYDRATION_CONCURRENCY,
        timeout=0.01,
    )
    assert len(updates) == 11
    assert maximum <= HYDRATION_CONCURRENCY
    assert len(hydration_candidates(items, limit=12)) == 12

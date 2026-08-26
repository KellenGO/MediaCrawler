import asyncio

import pytest

from aggregate_search.provider_chain import SearchProvider, run_provider_chain


def test_successful_fast_provider_does_not_run_browser():
    calls = []

    async def fast():
        calls.append("fast")
        return 1

    async def browser():
        calls.append("browser")
        return 1

    result = asyncio.run(run_provider_chain([
        SearchProvider("session_api", fast),
        SearchProvider("browser", browser),
    ]))

    assert calls == ["fast"]
    assert result.provider_used == "session_api"
    assert result.fallback_active is False
    assert result.provider_attempts == ["session_api"]


def test_exception_before_result_falls_back_after_cleanup():
    calls = []

    async def fast():
        calls.append("fast")
        raise RuntimeError("api down")

    async def cleanup_fast():
        calls.append("cleanup-fast")

    async def browser():
        calls.append("browser")
        assert calls[-2:] == ["cleanup-fast", "browser"]
        return 1

    result = asyncio.run(run_provider_chain([
        SearchProvider("light_api", fast, cleanup=cleanup_fast,
                       fallback_reason="fast_path_failed"),
        SearchProvider("browser", browser),
    ]))

    assert calls == ["fast", "cleanup-fast", "browser"]
    assert result.provider_used == "browser"
    assert result.fallback_active is True
    assert result.fallback_reason == "fast_path_failed"
    assert result.provider_attempts == ["light_api", "browser"]


def test_legal_empty_is_terminal_and_does_not_fallback():
    calls = []

    async def empty():
        calls.append("empty")
        return 0

    async def browser():
        calls.append("browser")
        return 1

    result = asyncio.run(run_provider_chain([
        SearchProvider("session_api", empty),
        SearchProvider("browser", browser),
    ]))

    assert calls == ["empty"]
    assert result.provider_used == "session_api"
    assert result.emitted_count == 0


def test_failure_after_result_does_not_fallback():
    calls = []
    emitted = 1

    async def partial():
        calls.append("partial")
        raise RuntimeError("late failure")

    async def browser():
        calls.append("browser")
        return 1

    with pytest.raises(RuntimeError):
        asyncio.run(run_provider_chain([
            SearchProvider("session_api", partial,
                           emitted_count=lambda: emitted),
            SearchProvider("browser", browser),
        ]))
    assert calls == ["partial"]


def test_cancelled_error_does_not_fallback():
    calls = []

    async def cancelled():
        calls.append("cancelled")
        raise asyncio.CancelledError()

    async def browser():
        calls.append("browser")
        return 1

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(run_provider_chain([
            SearchProvider("session_api", cancelled),
            SearchProvider("browser", browser),
        ]))
    assert calls == ["cancelled"]


def test_ineligible_provider_is_skipped():
    calls = []

    async def skipped():
        calls.append("skipped")
        return 1

    async def browser():
        calls.append("browser")
        return 0

    result = asyncio.run(run_provider_chain([
        SearchProvider("session_api", skipped, eligible=False),
        SearchProvider("browser", browser),
    ]))

    assert calls == ["browser"]
    assert result.provider_attempts == ["browser"]

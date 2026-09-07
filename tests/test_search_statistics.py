"""Third-batch regressions: real manager paths, fake requests, no platform calls."""

import asyncio
import json

import pytest
import pytest_asyncio

from aggregate_search.models import UnifiedSearchResult
from api.schemas.search import SearchJobRequestSchema
from api.services import result_cache
from api.services import search_job_manager as sjm
from api.services.search_metrics import PlatformCooldowns, SearchMetrics, _duration


class Clock:
    now = 1000.0

    def __call__(self):
        return self.now


def test_cooldown_uses_monotonic_clock_and_capped_backoff():
    clock, wall = Clock(), Clock()
    cooldowns = PlatformCooldowns(clock, wall)
    for seconds in (60, 120, 240, 300, 300):
        cooldowns.record("xhs", "rate_limited")
        assert cooldowns.remaining("xhs") == seconds
        assert cooldowns.remaining("bilibili") == 0
        wall.now += 100000  # System-clock adjustment cannot release the gate.
        assert cooldowns.remaining("xhs") == seconds
        clock.now += seconds
        assert cooldowns.remaining("xhs") == 0 and cooldowns.until("xhs") is None
    cooldowns.record("xhs", "empty")
    cooldowns.record("xhs", "rate_limited")
    assert cooldowns.remaining("xhs") == 60


@pytest.mark.parametrize("status", ["failed", "login_required", "timed_out", "cancelled"])
def test_only_explicit_rate_limit_starts_cooldown(status):
    cooldowns = PlatformCooldowns()
    cooldowns.record("xhs", status)
    assert cooldowns.remaining("xhs") == 0


def test_duration_ignores_missing_invalid_values_and_uses_nearest_rank_p95():
    stats = _duration([None, -1, float("inf"), True, *range(1, 21)])
    assert stats == {"samples": 20, "mean_ms": 10, "median_ms": 10, "p95_ms": 19}
    assert _duration([])["median_ms"] is None


def sample(status="succeeded", *, cache=False, skipped=False, duration=100):
    job = sjm._ActiveJob("sample", "PRIVATE KEYWORD", ["xhs"], 10)
    job.set_platform_status("xhs", status)
    info = job.platforms_state["xhs"]
    info.cache_hit, info.cooldown_skipped = cache, skipped
    info.error_summary = "PRIVATE ERROR"
    if not cache and not skipped:
        job.worker_platforms.add("xhs")
    job.timings["xhs"].total_ms = duration
    job.timings["xhs"].first_result_ms = duration
    job.timings["xhs"].fallback_active = None
    job.finalize()
    return job


def test_statistics_separate_cache_cooldown_cancel_and_unknown_fallback():
    metrics = SearchMetrics()
    first = sample()
    first.timings["xhs"].fallback_active = True
    metrics.record(first)
    metrics.record(first)  # Repeated finalization must not duplicate a sample.
    metrics.record(sample("failed", duration=300))
    metrics.record(sample(cache=True, duration=1))
    metrics.record(sample("rate_limited", skipped=True, duration=1))
    metrics.record(sample("cancelled", duration=10000))
    snapshot = metrics.snapshot(PlatformCooldowns())
    row = snapshot["platforms"]["xhs"]
    assert snapshot["job_count"] == 5
    assert row["worker_runs"] == 3 and row["success_samples"] == 2
    assert row["success_rate"] == .5 and row["cache_hit_rate"] == .2
    assert row["cooldown_skips"] == 1 and row["cancelled_runs"] == 1
    assert row["fallback_samples"] == 1 and row["fallback_rate"] == 1
    assert row["failures"] == {"failed": 1}
    assert row["first_result_ms"]["median_ms"] == 200
    assert snapshot["platforms"]["zhihu"]["success_rate"] is None
    assert "PRIVATE" not in json.dumps(snapshot)
    assert "PRIVATE" not in repr(metrics._jobs)


def test_statistics_window_is_bounded_to_last_100_jobs():
    metrics = SearchMetrics()
    for n in range(105):
        metrics.record(sample(duration=n))
    snapshot = metrics.snapshot(PlatformCooldowns())
    assert snapshot["job_count"] == 100
    assert snapshot["platforms"]["xhs"]["total_ms"]["median_ms"] == 54


@pytest_asyncio.fixture
async def manager(monkeypatch):
    result_cache.clear()
    monkeypatch.setattr(result_cache, "_CACHE_TTL_SECONDS", 90)
    mgr = sjm.SearchJobManager()
    yield mgr
    await mgr.cleanup()


async def run(manager, keyword="test", platforms=None, bypass=False):
    response = await manager.create_job(SearchJobRequestSchema(
        keyword=keyword, platforms=platforms or ["xhs"], bypass_cache=bypass))
    await asyncio.wait_for(manager._active_job.task, 2)
    return await manager.get_job(response.job_id)


@pytest.mark.asyncio
async def test_cooling_refreshes_do_not_request_or_extend_deadline(manager, monkeypatch):
    clock = Clock()
    manager.cooldowns = PlatformCooldowns(clock, clock)
    calls = []

    async def worker(job, platform):
        calls.append(platform)
        job.set_platform_status(platform, "rate_limited" if platform == "xhs" else "empty")

    monkeypatch.setattr(manager, "_run_worker", worker)
    first = await run(manager)
    deadline = first.platforms["xhs"].cooldown_until
    for _ in range(3):
        response = await run(manager, platforms=["xhs", "bilibili"], bypass=True)
        assert response.overall == "partial"
        assert response.platforms["xhs"].cooldown_skipped
        assert response.platforms["xhs"].cooldown_until == deadline
    assert calls.count("xhs") == 1 and calls.count("bilibili") == 3
    snapshot = manager.metrics.snapshot(manager.cooldowns)["platforms"]["xhs"]
    assert snapshot["worker_runs"] == 1 and snapshot["cooldown_skips"] == 3
    assert snapshot["failures"] == {"rate_limited": 1}
    clock.now += 60
    await run(manager, bypass=True)
    assert calls.count("xhs") == 2 and manager.cooldowns.remaining("xhs") == 120


@pytest.mark.asyncio
async def test_cache_remains_usable_but_does_not_reset_cooldown(manager, monkeypatch):
    calls = []

    async def worker(job, platform):
        calls.append(platform)
        job.set_platform_status(platform, "empty" if len(calls) == 1 else "rate_limited")

    monkeypatch.setattr(manager, "_run_worker", worker)
    await run(manager)
    await run(manager, bypass=True)
    response = await run(manager)
    assert len(calls) == 2 and response.platforms["xhs"].cache_hit
    assert manager.cooldowns.remaining("xhs") > 0


@pytest.mark.asyncio
async def test_new_search_awaits_old_hydration_client_close(manager, monkeypatch):
    entered, closed = asyncio.Event(), asyncio.Event()
    calls = []

    class Hydrator:
        async def hydrate(self, results, cancel_event):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0)
                closed.set()

    async def worker(job, platform):
        if calls:
            assert closed.is_set()
            job.set_platform_status(platform, "empty")
        else:
            job.add_result(platform, UnifiedSearchResult(platform=platform, content_id="1", title="title",
                           url="https://www.xiaohongshu.com/explore/1"))
            job.set_platform_status(platform, "succeeded")
        calls.append(platform)

    monkeypatch.setattr(manager, "_run_worker", worker)
    monkeypatch.setattr(sjm, "ResultHydrator", Hydrator)
    await run(manager)
    old = manager._active_job
    await asyncio.wait_for(entered.wait(), 1)
    await run(manager, keyword="next")
    assert old.hydration_task.done() and old.hydration_cancel_event.is_set()
    assert old.hydration_status == "completed" and closed.is_set()
    assert manager.metrics.snapshot(manager.cooldowns)["job_count"] == 2


@pytest.mark.asyncio
async def test_terminal_status_does_not_release_worker_before_cleanup(manager, monkeypatch):
    entered, release = asyncio.Event(), asyncio.Event()

    async def worker(job, platform):
        job.set_platform_status(platform, "empty")
        entered.set()
        await release.wait()

    monkeypatch.setattr(manager, "_run_worker", worker)
    await manager.create_job(SearchJobRequestSchema(keyword="test", platforms=["xhs"]))
    await entered.wait()
    assert manager._active_job.is_terminal() and manager.is_search_active()
    with pytest.raises(sjm.JobConflictError):
        await manager.create_job(SearchJobRequestSchema(keyword="next", platforms=["xhs"]))
    release.set()
    await manager._active_job.task
    assert not manager.is_search_active()


@pytest.mark.asyncio
async def test_cancel_is_counted_once_and_does_not_create_cooldown(manager, monkeypatch):
    entered = asyncio.Event()

    async def worker(job, platform):
        job.set_platform_status(platform, "running")
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(manager, "_run_worker", worker)
    response = await manager.create_job(SearchJobRequestSchema(keyword="test", platforms=["xhs"]))
    await entered.wait()
    assert await manager.cancel_job(response.job_id)
    assert await manager.cancel_job(response.job_id)
    snapshot = manager.metrics.snapshot(manager.cooldowns)
    assert snapshot["job_count"] == 1 and snapshot["platforms"]["xhs"]["cancelled_runs"] == 1
    assert manager.cooldowns.remaining("xhs") == 0


@pytest.mark.asyncio
async def test_supervisor_shutdown_reaps_cancelled_background_tasks():
    supervisor = sjm.PlatformWorkerSupervisor()
    await supervisor.start()
    task = supervisor._reaper_task
    await asyncio.sleep(0)
    await supervisor.stop_all()
    assert task.done()


@pytest.mark.asyncio
async def test_statistics_endpoint_returns_safe_aggregate(manager, monkeypatch):
    from api.routers import search
    monkeypatch.setattr(search, "search_job_manager", manager)
    manager.metrics.record(sample())
    data = await search.get_search_statistics()
    assert data["job_count"] == 1 and "PRIVATE" not in json.dumps(data)


@pytest.mark.asyncio
async def test_cancel_event_discards_late_hydration_result():
    from aggregate_search.hydration import hydrate_results
    cancelled = asyncio.Event()
    result = UnifiedSearchResult(platform="xhs", content_id="1", title="test",
                                 url="https://www.xiaohongshu.com/explore/1")

    async def fetch(item):
        cancelled.set()
        return "不应写入旧任务的迟到摘要内容"

    assert await hydrate_results([result], fetch, cancel_event=cancelled) == []
    assert result.snippet is None


@pytest.mark.asyncio
async def test_workers_finishing_during_cancel_do_not_start_hydration(manager, monkeypatch):
    entered, release = asyncio.Event(), asyncio.Event()

    async def worker(job, platform):
        job.set_platform_status(platform, "running")
        entered.set()
        await release.wait()

    async def cleanup(job):
        release.set()
        await job.task
        if job._cancelling:
            assert manager.metrics.snapshot(manager.cooldowns)["job_count"] == 0
        assert job.hydration_task is None

    monkeypatch.setattr(manager, "_run_worker", worker)
    monkeypatch.setattr(manager, "_cleanup_job_processes", cleanup)
    monkeypatch.setattr(sjm, "hydration_candidates", lambda results: [True])
    response = await manager.create_job(SearchJobRequestSchema(keyword="test", platforms=["xhs"]))
    await entered.wait()
    assert await manager.cancel_job(response.job_id)
    assert manager.metrics.snapshot(manager.cooldowns)["job_count"] == 1
    assert manager._active_job.hydration_task is None


@pytest.mark.parametrize("flag", ["_cancelling", "_cancelled"])
def test_cancel_preserves_completed_platform_when_worker_exits_late(flag):
    job = sjm._ActiveJob("cancel-race", "test", ["xhs", "bilibili"], 10)
    job.set_platform_status("xhs", "succeeded")
    setattr(job, flag, True)
    job.set_platform_status("bilibili", "cancelled")
    job.set_platform_status("xhs", "failed", error_summary="killed after status")
    job.set_platform_status("bilibili", "empty")
    assert job.platforms_state["xhs"].status == "succeeded"
    assert job.platforms_state["bilibili"].status == "cancelled"

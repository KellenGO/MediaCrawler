"""Sync integration boundaries, using isolated SQLite and synthetic workers only."""

import asyncio
import sys
from datetime import datetime, timezone

import pytest

from api.schemas.favorites import FavoritesJobRequest
from api.services.favorites_job_manager import FavoritesJobManager, _Job
from api.services.remote_favorites_store import RemoteFavoritesStore


@pytest.fixture
def store(tmp_path, monkeypatch):
    db = RemoteFavoritesStore(tmp_path / "library.db")
    monkeypatch.setattr("api.services.favorites_job_manager.get_remote_favorites_store", lambda: db)
    return db


def row(platform, content_id):
    return {"platform": platform, "content_id": content_id, "title": "示例", "url": "https://example.com"}


@pytest.mark.asyncio
async def test_subset_and_failed_sync_keep_saved_results_before_restart(store):
    store.save_platform("bilibili", [row("bilibili", "old-b")], status="succeeded")
    store.save_platform("xhs", [row("xhs", "old-x")], status="succeeded")
    manager = FavoritesJobManager()
    job = _Job(FavoritesJobRequest(platforms=["xhs"]))
    job.platforms["xhs"].status = "failed"
    job.completed_at = datetime.now(timezone.utc)
    manager._recent = job
    response = await manager.get(job.job_id)
    assert {r.content_id for r in response.results} == {"old-b", "old-x"}
    assert response.platforms["xhs"].status == "failed"
    assert response.platforms["bilibili"].synced_at is not None


@pytest.mark.asyncio
async def test_noisy_worker_does_not_deadlock_and_disk_failure_is_visible(store, monkeypatch):
    code = '''
import json, sys
r=json.loads(sys.stdin.readline())
sys.stderr.write('x'*1048576)
sys.stderr.flush()
for event, data in [('status', {'status':'empty'}), ('done', None)]:
 print('MC_AGG_EVENT\\t'+json.dumps({'event':event,'job_id':r['job_id'],'platform':r['platform'],'data':data}), flush=True)
'''
    monkeypatch.setattr("api.services.favorites_job_manager._command", lambda: [sys.executable, "-c", code])
    def fail(*args, **kwargs):
        raise OSError("synthetic disk error")
    monkeypatch.setattr(store, "save_platform", fail)
    manager = FavoritesJobManager()
    job = _Job(FavoritesJobRequest(platforms=["xhs"]))
    await asyncio.wait_for(manager._run(job), timeout=15)
    assert job.platforms["xhs"].status == "empty"
    assert job.response().persistence_error


@pytest.mark.asyncio
async def test_cancel_persists_terminal_status(store, monkeypatch):
    code = "import sys,time;sys.stdin.readline();time.sleep(30)"
    monkeypatch.setattr("api.services.favorites_job_manager._command", lambda: [sys.executable, "-c", code])
    manager = FavoritesJobManager()
    await manager.create(FavoritesJobRequest(platforms=["xhs"]))
    for _ in range(100):
        if manager._active.procs:
            break
        await asyncio.sleep(.01)
    await manager.cleanup()
    assert store.load()["platforms"]["xhs"]["status"] == "cancelled"
    assert (await manager.latest()).overall != "running"


@pytest.mark.asyncio
async def test_user_cancel_stops_workers_preserves_partial_and_is_idempotent(store, monkeypatch):
    store.save_platform("bilibili", [row("bilibili", "old")], status="succeeded")
    code = '''
import json,sys,time
r=json.loads(sys.stdin.readline())
print('MC_AGG_EVENT\\t'+json.dumps({'event':'result','job_id':r['job_id'],'platform':r['platform'],
'data':{'platform':r['platform'],'content_id':'partial','title':'partial','url':'https://example.com'}}),flush=True)
time.sleep(30)
'''
    monkeypatch.setattr("api.services.favorites_job_manager._command", lambda: [sys.executable, "-c", code])
    manager = FavoritesJobManager()
    created = await manager.create(FavoritesJobRequest(platforms=["xhs", "douyin"]))
    try:
        for _ in range(200):
            if all(manager._active.items.values()):
                break
            await asyncio.sleep(.01)
        assert all(manager._active.items.values())
        procs = list(manager._active.procs)
        result, repeated = await asyncio.wait_for(asyncio.gather(
            manager.cancel(created.job_id), manager.cancel(created.job_id)), timeout=10)
        assert result.overall != "running" and repeated.overall != "running"
        assert all(p.returncode is not None for p in procs)
        assert result.platforms["xhs"].status == "cancelled"
        assert result.platforms["douyin"].status == "cancelled"
        restored = await FavoritesJobManager().latest()
        assert {(r.platform, r.content_id) for r in restored.results} == {
            ("bilibili", "old"), ("xhs", "partial"), ("douyin", "partial")}
        assert await manager.cancel("unknown") is None
    finally:
        await manager.cleanup()


@pytest.mark.asyncio
async def test_cancel_endpoint_handles_pending_and_unknown_jobs(store, monkeypatch):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from api.routers.search import search_router

    manager = FavoritesJobManager()
    job = _Job(FavoritesJobRequest(platforms=["xhs"]))
    manager._active = manager._recent = job
    monkeypatch.setattr("api.routers.search.favorites_job_manager", manager)
    app = FastAPI()
    app.include_router(search_router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"/api/search/favorites/jobs/{job.job_id}/cancel")
        assert response.status_code == 200
        assert response.json()["platforms"]["xhs"]["status"] == "cancelled"
        assert response.json()["overall"] != "running"
        assert (await client.post("/api/search/favorites/jobs/unknown/cancel")).status_code == 404

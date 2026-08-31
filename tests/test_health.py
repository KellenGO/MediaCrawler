import json

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.services import environment_health


@pytest.fixture
def client(monkeypatch):
    async def browser_ok():
        return True, "test-browser"

    async def redis_status(_required):
        return None

    monkeypatch.setattr(environment_health, "_browser_status", browser_ok)
    monkeypatch.setattr(environment_health, "_redis_status", redis_status)
    return TestClient(app)


def test_health_returns_safe_environment_summary(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["backend_available"] is True
    assert payload["browser_available"] is True
    assert payload["version_match"] is True
    assert set(payload["platforms"]) == {"xhs", "douyin", "bilibili", "zhihu"}

    serialized = json.dumps(payload).lower()
    for secret_name in ("cookie", "token", "authorization", "profile_path"):
        assert secret_name not in serialized


def test_health_keeps_backend_ok_but_marks_browser_degraded(monkeypatch):
    async def browser_unavailable():
        return False, None

    monkeypatch.setattr(environment_health, "_browser_status", browser_unavailable)
    client = TestClient(app)
    payload = client.get("/api/health").json()
    assert payload["status"] == "ok"
    assert payload["environment_status"] == "degraded"
    assert payload["browser_available"] is False


def test_health_checks_redis_only_when_proxy_is_enabled(monkeypatch):
    import config

    calls = []

    async def browser_ok():
        return True, "test-browser"

    async def redis_unavailable(required):
        calls.append(required)
        return False

    monkeypatch.setattr(config, "ENABLE_IP_PROXY", True)
    monkeypatch.setattr(environment_health, "_browser_status", browser_ok)
    monkeypatch.setattr(environment_health, "_redis_status", redis_unavailable)
    payload = TestClient(app).get("/api/health").json()
    assert calls == [True]
    assert payload["redis_required"] is True
    assert payload["redis_available"] is False
    assert payload["environment_status"] == "degraded"

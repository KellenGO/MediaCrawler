"""收藏库 API 测试（/api/library）。

只验证 HTTP 层：路由、状态码、错误处理，以及「删除收藏夹保留内容」这类产品规则。
存储层自身的规则在 tests/test_library_store.py 覆盖。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.services.library_store import LibraryStore, get_library_store


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    store = LibraryStore(tmp_path / "api.db")
    app.dependency_overrides[get_library_store] = lambda: store
    yield TestClient(app)
    app.dependency_overrides.clear()


def _result(content_id: str = "n1", platform: str = "xhs", **overrides: object) -> dict:
    base = {
        "platform": platform,
        "content_id": content_id,
        "content_type": "note",
        "title": "露营装备怎么选",
        "snippet": "摘要",
        "author": "作者",
        "url": "https://example.com/x",
        "published_at": "2026-09-01T00:00:00",
        "cover_url": "https://example.com/c.jpg",
        "metrics": {"likes": 12},
    }
    base.update(overrides)
    return base


def test_library_starts_empty(client: TestClient) -> None:
    response = client.get("/api/library/stats")
    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_add_list_and_remove_item(client: TestClient) -> None:
    created = client.post("/api/library/items", json={"result": _result(), "note": "笔记"})
    assert created.status_code == 201
    assert created.json()["key"] == "xhs|n1"

    listed = client.get("/api/library/items")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["note"] == "笔记"

    removed = client.request("DELETE", "/api/library/items", json={"keys": [{"platform": "xhs", "content_id": "n1"}]})
    assert removed.status_code == 200
    assert removed.json()["removed"] == 1
    assert client.get("/api/library/stats").json()["total"] == 0


def test_add_item_requires_identifier(client: TestClient) -> None:
    response = client.post("/api/library/items", json={"result": {"platform": "xhs"}})
    assert response.status_code == 400
    assert "content_id" in response.json()["detail"]


def test_note_update_and_404(client: TestClient) -> None:
    client.post("/api/library/items", json={"result": _result()})

    ok = client.patch("/api/library/items/xhs/n1", json={"note": "更新后的备注"})
    assert ok.status_code == 200
    assert ok.json()["note"] == "更新后的备注"

    missing = client.patch("/api/library/items/xhs/不存在", json={"note": "x"})
    assert missing.status_code == 404


def test_collection_lifecycle_and_keep_items(client: TestClient) -> None:
    created = client.post("/api/library/collections", json={"name": "AI 学习"})
    assert created.status_code == 201
    collection_id = created.json()["id"]

    duplicate = client.post("/api/library/collections", json={"name": "ai 学习"})
    assert duplicate.status_code == 400  # 名称大小写不敏感去重

    client.post("/api/library/items", json={"result": _result(), "collection_ids": [collection_id]})
    collections = client.get("/api/library/collections").json()["collections"]
    assert collections[0]["item_count"] == 1

    renamed = client.patch(f"/api/library/collections/{collection_id}", json={"name": "AI 资料"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "AI 资料"

    deleted = client.delete(f"/api/library/collections/{collection_id}")
    assert deleted.status_code == 200
    assert deleted.json()["kept_items"] == 1
    # 内容保留，变成未分类
    stats = client.get("/api/library/stats").json()
    assert stats["total"] == 1
    assert stats["unclassified"] == 1


def test_batch_add_and_remove_from_collection(client: TestClient) -> None:
    collection_id = client.post("/api/library/collections", json={"name": "批量"}).json()["id"]
    for cid in ("a", "b"):
        client.post("/api/library/items", json={"result": _result(content_id=cid)})

    added = client.post(
        f"/api/library/collections/{collection_id}/items",
        json={"keys": [{"platform": "xhs", "content_id": "a"}, {"platform": "xhs", "content_id": "b"}]},
    )
    assert added.json()["added"] == 2

    removed = client.request(
        "DELETE",
        f"/api/library/collections/{collection_id}/items",
        json={"keys": [{"platform": "xhs", "content_id": "a"}]},
    )
    assert removed.json()["removed"] == 1
    # 移出收藏夹不等于取消收藏
    assert client.get("/api/library/stats").json()["total"] == 2


def test_items_filters(client: TestClient) -> None:
    client.post("/api/library/items", json={"result": _result(content_id="a", title="露营装备")})
    client.post("/api/library/items", json={"result": _result(content_id="b", platform="douyin", title="拍摄技巧")})

    assert client.get("/api/library/items", params={"platform": "xhs"}).json()["total"] == 1
    assert client.get("/api/library/items", params={"q": "露营"}).json()["total"] == 1
    assert client.get("/api/library/items", params={"unclassified": True}).json()["total"] == 2
    assert client.get("/api/library/items", params={"limit": 1}).json()["total"] == 2


def test_import_legacy_backup_and_export(client: TestClient) -> None:
    legacy = {
        "version": 1,
        "items": [
            {"result": _result(content_id="old"), "savedAt": "2026-08-01T00:00:00", "fetchedAt": None, "note": "旧备注"},
        ],
    }
    imported = client.post("/api/library/import", json={"payload": legacy})
    assert imported.status_code == 200
    assert imported.json()["added"] == 1

    exported = client.get("/api/library/export").json()
    assert exported["version"] == 2
    assert len(exported["items"]) == 1
    assert exported["items"][0]["note"] == "旧备注"


def test_import_rejects_garbage(client: TestClient) -> None:
    response = client.post("/api/library/import", json={"payload": {"version": 1}})
    assert response.status_code == 400

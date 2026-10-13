"""API 层应用域端到端测试（TestClient + SQLite）。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _create_app(
    client: TestClient, headers: dict[str, str], name: str = "助手", type: str = "lightweight"
) -> dict:
    resp = client.post("/apps", json={"name": name, "type": type}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_and_list(client: TestClient, auth_headers: dict[str, str]) -> None:
    _create_app(client, auth_headers, name="轻量应用")
    _create_app(client, auth_headers, name="知识库应用", type="knowledge")

    resp = client.get("/apps", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["nextCursor"] is None
    assert len(body["items"]) == 2

    resp = client.get("/apps?type=knowledge", headers=auth_headers)
    assert [a["name"] for a in resp.json()["items"]] == ["知识库应用"]


def test_create_rejects_readonly_and_bad_type(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post(
        "/apps", json={"name": "x", "type": "lightweight", "published": True}, headers=auth_headers
    )
    assert resp.status_code == 422  # extra=forbid：readOnly 字段拒绝携带
    resp = client.post("/apps", json={"name": "x", "type": "workflow"}, headers=auth_headers)
    assert resp.status_code == 422


def test_get_update_delete(client: TestClient, auth_headers: dict[str, str]) -> None:
    app = _create_app(client, auth_headers)
    resp = client.get(f"/apps/{app['id']}", headers=auth_headers)
    assert resp.json()["name"] == "助手"

    resp = client.patch(
        f"/apps/{app['id']}", json={"name": "新名字", "description": "简介"}, headers=auth_headers
    )
    assert resp.json()["name"] == "新名字"
    assert resp.json()["description"] == "简介"

    resp = client.delete(f"/apps/{app['id']}", headers=auth_headers)
    assert resp.status_code == 204
    resp = client.get(f"/apps/{app['id']}", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == "APP_NOT_FOUND"


def test_unknown_app_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.get("/apps/no-such-id", headers=auth_headers)
    assert resp.status_code == 404


def test_config_put_get_full_replace(client: TestClient, auth_headers: dict[str, str]) -> None:
    app = _create_app(client, auth_headers)

    resp = client.put(
        f"/apps/{app['id']}/config",
        json={"modelPrompt": {"modelCode": "gpt-4o", "temperature": 0.5}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["version"] == 1

    config = client.get(f"/apps/{app['id']}/config", headers=auth_headers).json()
    assert config["modelPrompt"]["modelCode"] == "gpt-4o"
    assert config["basic"] == {}  # 未提供段落为空对象

    # 全量替换：只给 basic → modelPrompt 清空
    resp = client.put(
        f"/apps/{app['id']}/config",
        json={"basic": {"welcomeMessage": "你好"}},
        headers=auth_headers,
    )
    assert resp.json()["version"] == 2
    config = client.get(f"/apps/{app['id']}/config", headers=auth_headers).json()
    assert config["modelPrompt"] == {}
    assert config["basic"]["welcomeMessage"] == "你好"

    # 空 body = 全部清空
    client.put(f"/apps/{app['id']}/config", json={}, headers=auth_headers)
    config = client.get(f"/apps/{app['id']}/config", headers=auth_headers).json()
    assert config["basic"] == {}


def test_config_validation(client: TestClient, auth_headers: dict[str, str]) -> None:
    app = _create_app(client, auth_headers)
    resp = client.put(
        f"/apps/{app['id']}/config",
        json={"modelPrompt": {"temperature": 5.0}},
        headers=auth_headers,
    )
    assert resp.status_code == 422  # 契约 temperature 0-2
    resp = client.put(
        f"/apps/{app['id']}/config",
        json={"basic": {"unknownField": 1}},
        headers=auth_headers,
    )
    assert resp.status_code == 422  # extra=forbid


def test_versions_snapshot_rollback(client: TestClient, auth_headers: dict[str, str]) -> None:
    app = _create_app(client, auth_headers)
    client.put(
        f"/apps/{app['id']}/config",
        json={"basic": {"welcomeMessage": "v1"}},
        headers=auth_headers,
    )
    snap = client.post(f"/apps/{app['id']}/versions", headers=auth_headers)
    assert snap.status_code == 201 and snap.json()["version"] == 2
    client.put(
        f"/apps/{app['id']}/config",
        json={"basic": {"welcomeMessage": "v2"}},
        headers=auth_headers,
    )

    versions = client.get(f"/apps/{app['id']}/versions", headers=auth_headers).json()
    assert [v["version"] for v in versions["items"]] == [3, 2, 1]

    rollback = client.post(f"/apps/{app['id']}/versions/1/rollback", headers=auth_headers)
    assert rollback.json()["version"] == 4  # append-only
    config = client.get(f"/apps/{app['id']}/config", headers=auth_headers).json()
    assert config["basic"]["welcomeMessage"] == "v1"

    resp = client.post(f"/apps/{app['id']}/versions/99/rollback", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == "APP_VERSION_NOT_FOUND"


def test_publish_unpublish_events(client: TestClient, auth_headers: dict[str, str]) -> None:
    app = _create_app(client, auth_headers)
    resp = client.post(f"/apps/{app['id']}/publish", headers=auth_headers)
    assert resp.status_code == 200 and resp.json()["published"] is True

    resp = client.delete(f"/apps/{app['id']}/publish", headers=auth_headers)
    assert resp.status_code == 204
    fetched = client.get(f"/apps/{app['id']}", headers=auth_headers).json()
    assert fetched["published"] is False

    event_types = [e.event_type for e in client.app.state.bus.published]  # type: ignore[attr-defined]
    assert "AppPublished" in event_types and "AppUnpublished" in event_types


def test_quota_summary(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.get("/quota/summary", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["plan"] == "basic"
    assert body["planBadge"] == "基础版"
    assert body["walletBalance"] == 0  # 占位（T-007 计费域对接）
    assert body["usage"]["messagesUsed"] == 0


def test_apps_require_auth(client: TestClient) -> None:
    assert client.get("/apps").status_code == 401
    assert client.post("/apps", json={"name": "x", "type": "lightweight"}).status_code == 401


def test_basic_plan_app_limit_via_api(client: TestClient, auth_headers: dict[str, str]) -> None:
    """docs/01 四档矩阵：基础版 3 个应用，第 4 个 403。"""
    for i in range(3):
        _create_app(client, auth_headers, name=f"app{i}")
    resp = client.post("/apps", json={"name": "app4", "type": "lightweight"}, headers=auth_headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "APP_LIMIT_EXCEEDED"


def test_cursor_pagination_via_api(client: TestClient, auth_headers: dict[str, str]) -> None:
    for i in range(3):
        _create_app(client, auth_headers, name=f"app{i}")
    page1 = client.get("/apps?limit=2", headers=auth_headers).json()
    assert len(page1["items"]) == 2
    assert page1["nextCursor"]
    page2 = client.get(f"/apps?limit=2&cursor={page1['nextCursor']}", headers=auth_headers).json()
    assert len(page2["items"]) == 1
    assert page2["nextCursor"] is None

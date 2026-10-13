"""使用记录 API 单测：全维度流水 + 游标分页。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import TEST_INTERNAL_TOKEN


def _seed_usage(client: TestClient, auth_headers: dict[str, str], count: int = 3) -> None:
    order = client.post(
        "/v1/recharge/orders",
        json={"packageCode": "tier_1k", "requestId": "req-u"},
        headers=auth_headers,
    ).json()
    client.post(f"/v1/recharge/orders/{order['orderNo']}/pay", headers=auth_headers)
    events = [
        {
            "eventId": f"evt-u{i}",
            "tenantId": "t-1",
            "credits": 10 * (i + 1),
            "outcome": "success",
            "provider": "openai" if i % 2 == 0 else "deepseek",
            "modelCode": "gpt-4o-mini" if i % 2 == 0 else "deepseek-chat",
            "promptTokens": 100 + i,
            "completionTokens": 50,
            "totalTokens": 150 + i,
            "latencyMs": 800 + i,
            "appCode": f"app-{i}",
        }
        for i in range(count)
    ]
    resp = client.post(
        "/internal/v1/metering/events",
        json=events,
        headers={"X-Internal-Token": TEST_INTERNAL_TOKEN},
    )
    assert resp.status_code == 200


def test_usage_records_full_dimensions(client: TestClient, auth_headers: dict[str, str]) -> None:
    """流水含全维度字段（来源/应用/模型/Token/积分/耗时/状态）。"""
    _seed_usage(client, auth_headers)
    resp = client.get("/v1/usage/records", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    # 3 笔计量扣减 + 1 笔充值入账
    debits = [r for r in body["items"] if r["kind"] == "debit"]
    assert len(debits) == 3
    sample = debits[0]
    assert sample["source"] == "metering"
    assert sample["status"] == "applied"
    assert sample["delta"] < 0  # 扣减为负
    assert sample["creditsCharged"] > 0
    assert sample["appCode"].startswith("app-")
    assert sample["modelCode"]
    assert sample["promptTokens"] > 0
    assert sample["latencyMs"] > 0


def test_usage_records_filter_by_model(client: TestClient, auth_headers: dict[str, str]) -> None:
    _seed_usage(client, auth_headers)
    resp = client.get(
        "/v1/usage/records", params={"modelCode": "deepseek-chat"}, headers=auth_headers
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["modelCode"] == "deepseek-chat"


def test_usage_records_cursor_pagination(client: TestClient, auth_headers: dict[str, str]) -> None:
    """cursor 分页：两页取全，无重复（keyset 口径）。"""
    _seed_usage(client, auth_headers, count=3)
    seen: list[str] = []
    cursor = None
    pages = 0
    while True:
        params = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        resp = client.get("/v1/usage/records", params=params, headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        seen.extend(r["requestId"] for r in body["items"])
        pages += 1
        cursor = body["nextCursor"]
        if not cursor or pages > 10:
            break
    assert len(seen) == 4  # 3 扣减 + 1 充值
    assert len(set(seen)) == 4  # 无重复


def test_usage_records_requires_auth(client: TestClient) -> None:
    assert client.get("/v1/usage/records").status_code == 401


def test_reconciliation_run_endpoint(client: TestClient, auth_headers: dict[str, str]) -> None:
    """对账端点：无差异时 alert=false（骨架可跑，验收⑤）。"""
    resp = client.post(
        "/internal/v1/reconciliation/run",
        headers={"X-Internal-Token": TEST_INTERNAL_TOKEN},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["alert"] is False
    assert body["frozenSettlement"] is False
    assert body["runId"] > 0

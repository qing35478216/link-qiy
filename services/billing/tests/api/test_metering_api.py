"""计量事件内部 API 单测：鉴权 / 幂等（同 eventId 重复只扣一次）/ 批量。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import TEST_INTERNAL_TOKEN


def _event_payload(event_id: str, credits: int = 100) -> dict:
    return {
        "eventId": event_id,
        "tenantId": "t-1",
        "credits": credits,
        "outcome": "success",
        "provider": "openai",
        "modelCode": "gpt-4o-mini",
        "promptTokens": 120,
        "completionTokens": 80,
        "totalTokens": 200,
        "latencyMs": 850,
        "attempt": 1,
        "traceId": "trace-1",
        "appCode": "app-1",
        "conversationId": "conv-1",
    }


def test_ingest_requires_internal_token(client: TestClient) -> None:
    resp = client.post("/internal/v1/metering/events", json=[_event_payload("evt-1")])
    assert resp.status_code == 401


def test_ingest_applies_and_balance_deducted(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """充值 1000 → 消费 100 → 余额 900（一次且仅一次）。"""
    order = client.post(
        "/v1/recharge/orders",
        json={"packageCode": "tier_1k", "requestId": "req-m"},
        headers=auth_headers,
    ).json()
    client.post(f"/v1/recharge/orders/{order['orderNo']}/pay", headers=auth_headers)

    resp = client.post(
        "/internal/v1/metering/events",
        json=[_event_payload("evt-m1", credits=100)],
        headers={"X-Internal-Token": TEST_INTERNAL_TOKEN},
    )
    assert resp.status_code == 200
    result = resp.json()["results"][0]
    assert result["result"] == "applied"
    assert result["balanceAfter"] == 900

    wallet = client.get("/v1/wallet", headers=auth_headers).json()
    assert wallet["balance"] == 900


def test_ingest_repeat_same_event_debits_once(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """同 eventId 重复投递（MQ 重投模拟）：只扣一次（幂等）。"""
    order = client.post(
        "/v1/recharge/orders",
        json={"packageCode": "tier_1k", "requestId": "req-m"},
        headers=auth_headers,
    ).json()
    client.post(f"/v1/recharge/orders/{order['orderNo']}/pay", headers=auth_headers)

    headers = {"X-Internal-Token": TEST_INTERNAL_TOKEN}
    for _ in range(5):
        resp = client.post(
            "/internal/v1/metering/events", json=[_event_payload("evt-dup")], headers=headers
        )
        assert resp.status_code == 200

    results = [r["result"] for r in resp.json()["results"]]
    assert results[-1] == "duplicate"
    wallet = client.get("/v1/wallet", headers=auth_headers).json()
    assert wallet["balance"] == 900  # 1000 - 100，只扣一次


def test_ingest_batch_multiple_events(client: TestClient, auth_headers: dict[str, str]) -> None:
    order = client.post(
        "/v1/recharge/orders",
        json={"packageCode": "tier_1k", "requestId": "req-b"},
        headers=auth_headers,
    ).json()
    client.post(f"/v1/recharge/orders/{order['orderNo']}/pay", headers=auth_headers)

    resp = client.post(
        "/internal/v1/metering/events",
        json=[_event_payload(f"evt-b{i}", credits=100) for i in range(3)],
        headers={"X-Internal-Token": TEST_INTERNAL_TOKEN},
    )
    assert resp.status_code == 200
    assert [r["result"] for r in resp.json()["results"]] == ["applied"] * 3
    wallet = client.get("/v1/wallet", headers=auth_headers).json()
    assert wallet["balance"] == 700  # 1000 - 300


def test_ingest_insufficient_credits_blocked(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """零余额消费：blocked 留痕不扣减，绝不为负。"""
    resp = client.post(
        "/internal/v1/metering/events",
        json=[_event_payload("evt-poor", credits=100)],
        headers={"X-Internal-Token": TEST_INTERNAL_TOKEN},
    )
    assert resp.status_code == 200
    result = resp.json()["results"][0]
    assert result["result"] == "blocked"
    wallet = client.get("/v1/wallet", headers=auth_headers).json()
    assert wallet["balance"] == 0


def test_ingest_rejects_bad_payload(client: TestClient) -> None:
    """坏载荷显式 422（不静默吞计费字段）。"""
    bad = _event_payload("evt-bad")
    del bad["tenantId"]
    resp = client.post(
        "/internal/v1/metering/events",
        json=[bad],
        headers={"X-Internal-Token": TEST_INTERNAL_TOKEN},
    )
    assert resp.status_code == 422


def test_ingest_failed_outcome_records_zero_delta(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """FAILED 事件：留痕 delta=0，不计费（对账可见失败面）。"""
    order = client.post(
        "/v1/recharge/orders",
        json={"packageCode": "tier_1k", "requestId": "req-f"},
        headers=auth_headers,
    ).json()
    client.post(f"/v1/recharge/orders/{order['orderNo']}/pay", headers=auth_headers)

    resp = client.post(
        "/internal/v1/metering/events",
        json=[_event_payload("evt-failed", credits=0) | {"outcome": "failed"}],
        headers={"X-Internal-Token": TEST_INTERNAL_TOKEN},
    )
    assert resp.status_code == 200
    assert resp.json()["results"][0]["result"] == "applied"
    wallet = client.get("/v1/wallet", headers=auth_headers).json()
    assert wallet["balance"] == 1_000  # 未扣

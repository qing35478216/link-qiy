"""配额 API 单测：/quota/summary 真实数据 / 权益校验错误码（验收④）。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import TEST_INTERNAL_TOKEN


def test_quota_summary_reflects_real_wallet(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """/quota/summary 返回真实余额与用量（替换 platform 占位 0 的数据源）。"""
    # 充值 10000 并制造两条计费消息
    order = client.post(
        "/v1/recharge/orders",
        json={"packageCode": "tier_10k", "requestId": "req-q"},
        headers=auth_headers,
    ).json()
    client.post(f"/v1/recharge/orders/{order['orderNo']}/pay", headers=auth_headers)
    for i in range(2):
        client.post(
            "/internal/v1/metering/events",
            json=[
                {
                    "eventId": f"evt-q{i}",
                    "tenantId": "t-1",
                    "credits": 100,
                    "outcome": "success",
                    "provider": "openai",
                    "modelCode": "gpt-4o-mini",
                    "promptTokens": 120,
                    "completionTokens": 80,
                    "totalTokens": 200,
                }
            ],
            headers={"X-Internal-Token": TEST_INTERNAL_TOKEN},
        )

    resp = client.get("/quota/summary", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["plan"] == "basic"
    assert body["planBadge"] == "基础版"
    assert body["walletBalance"] == 9_800  # 10000 - 2*100
    assert body["upgradeUrl"] == "/console/price"
    assert body["usage"]["messagesUsed"] == 2
    assert body["usage"]["tokensUsed"] == 400
    # 消息/Token 不设硬上限（积分即约束）——limit 省略，控制台优雅降级
    assert "messagesLimit" not in body["usage"]
    assert "tokensLimit" not in body["usage"]


def test_quota_check_within_limit(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.post(
        "/v1/quota/check",
        json={"dimension": "apps", "used": 2, "increment": 1},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["allowed"] is True
    assert body["limit"] == 3  # 基础版应用上限


def test_quota_check_exceeded_returns_error_contract(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """超限 → 403 QUOTA_EXCEEDED + details（验收④）。"""
    resp = client.post(
        "/v1/quota/check",
        json={"dimension": "apps", "used": 3, "increment": 1},
        headers=auth_headers,
    )
    assert resp.status_code == 403
    body = resp.json()
    assert body["code"] == "QUOTA_EXCEEDED"
    assert body["details"]["dimension"] == "apps"
    assert body["details"]["limit"] == 3
    assert body["details"]["used"] == 3
    assert body["details"]["plan"] == "basic"


def test_quota_check_workflow_dimension(client: TestClient, auth_headers: dict[str, str]) -> None:
    """基础版工作流上限 2：第 3 个被拒。"""
    ok = client.post(
        "/v1/quota/check",
        json={"dimension": "workflows", "used": 1, "increment": 1},
        headers=auth_headers,
    )
    assert ok.status_code == 200
    exceeded = client.post(
        "/v1/quota/check",
        json={"dimension": "workflows", "used": 2, "increment": 1},
        headers=auth_headers,
    )
    assert exceeded.status_code == 403
    assert exceeded.json()["details"]["limit"] == 2


def test_quota_check_unknown_dimension_rejected(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post(
        "/v1/quota/check",
        json={"dimension": "spaceships", "used": 0},
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_internal_quota_summary_for_platform(client: TestClient) -> None:
    """platform 拉取真实数据的内部端点（替换其 walletBalance=0 占位）。"""
    resp = client.get(
        "/internal/v1/quota/summary",
        headers={"X-Internal-Token": TEST_INTERNAL_TOKEN, "X-Tenant-Id": "t-1"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["plan"] == "basic"
    assert body["walletBalance"] == 0
    assert body["usage"]["messagesUsed"] == 0


def test_plan_sync_via_internal_endpoint(client: TestClient) -> None:
    """plan 同步（platform 套餐变更事件 → billing 只读副本）。"""
    resp = client.put(
        "/internal/v1/tenants/t-1/plan",
        json={"plan": "pro"},
        headers={"X-Internal-Token": TEST_INTERNAL_TOKEN},
    )
    assert resp.status_code == 200
    assert resp.json()["plan"] == "pro"

    summary = client.get(
        "/internal/v1/quota/summary",
        headers={"X-Internal-Token": TEST_INTERNAL_TOKEN, "X-Tenant-Id": "t-1"},
    ).json()
    assert summary["plan"] == "pro"
    assert summary["planBadge"] == "专业版"
    assert summary["monthlyCreditGrant"] == 1_000_000

    # 同步后权益校验按新版本（pro 应用上限 30）
    from tests.conftest import mint_token

    headers = {"Authorization": f"Bearer {mint_token(tenant_id='t-1')}"}
    resp = client.post(
        "/v1/quota/check", json={"dimension": "apps", "used": 25}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["limit"] == 30

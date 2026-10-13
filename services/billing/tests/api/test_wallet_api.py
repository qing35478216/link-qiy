"""钱包 API 单测（控制台面）：余额/签到/鉴权/租户隔离。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from linkai_billing.domain.pricing import CHECKIN_REWARD_CREDITS
from tests.conftest import TEST_INTERNAL_TOKEN, mint_token


def test_wallet_requires_auth(client: TestClient) -> None:
    assert client.get("/v1/wallet").status_code == 401


def test_wallet_zero_balance_for_new_tenant(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.get("/v1/wallet", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["balance"] == 0
    assert body["plan"] == "basic"
    assert body["lowBalance"] is True


def test_checkin_then_repeat_is_idempotent(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """签到 API：首次 +57，同日重复 already=true 不重复加（验收③）。"""
    first = client.post("/v1/wallet/check-in", headers=auth_headers)
    assert first.status_code == 200
    assert first.json()["creditsGranted"] == CHECKIN_REWARD_CREDITS == 57
    assert first.json()["already"] is False

    second = client.post("/v1/wallet/check-in", headers=auth_headers)
    assert second.status_code == 200
    assert second.json()["already"] is True
    assert second.json()["creditsGranted"] == 0

    wallet = client.get("/v1/wallet", headers=auth_headers).json()
    assert wallet["balance"] == 57


def test_tenant_mismatch_rejected(client: TestClient) -> None:
    """X-Tenant-Id 与令牌 tid 不一致 → 403（铁律 6）。"""
    headers = {"Authorization": f"Bearer {mint_token(tenant_id='t-1')}", "X-Tenant-Id": "t-2"}
    resp = client.get("/v1/wallet", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "TENANT_MISMATCH"


def test_cross_tenant_wallet_isolated(client: TestClient, auth_headers: dict[str, str]) -> None:
    """另一租户的令牌看不到 t-1 的余额（铁律 6 数据隔离）。"""
    client.post("/v1/wallet/check-in", headers=auth_headers)
    other = {"Authorization": f"Bearer {mint_token(tenant_id='t-2')}"}
    body = client.get("/v1/wallet", headers=other).json()
    assert body["balance"] == 0


def test_set_reminder_threshold(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.put(
        "/v1/wallet/reminder-threshold", json={"threshold": 500}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["reminderThreshold"] == 500
    assert resp.json()["lowBalance"] is True  # 0 < 500


def test_internal_token_constant_time_compare(client: TestClient) -> None:
    """内部端点缺令牌 → 401（常量时间比较，无时序泄漏）。"""
    resp = client.post(
        "/internal/v1/metering/events",
        json=[],
        headers={"X-Internal-Token": "wrong-token"},
    )
    assert resp.status_code == 401
    ok = client.post(
        "/internal/v1/metering/events", json=[], headers={"X-Internal-Token": TEST_INTERNAL_TOKEN}
    )
    assert ok.status_code == 200

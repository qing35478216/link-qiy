"""充值订单 API 单测：套餐四档实测值 / 下单-支付闭环 / 回调幂等 / 订单列表。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import TEST_INTERNAL_TOKEN


def _order(client: TestClient, headers: dict[str, str], package: str = "tier_10k") -> dict:
    resp = client.post(
        "/v1/recharge/orders",
        json={"packageCode": package, "requestId": f"req-{package}"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_packages_match_docs_measured_values(client: TestClient) -> None:
    """四档套餐与 docs/01 第十部分实测一致（积分 + 整数分 + 元展示）。"""
    resp = client.get("/v1/recharge/packages")
    assert resp.status_code == 200
    packages = resp.json()
    assert [(p["code"], p["credits"], p["amountFen"], p["amountYuan"]) for p in packages] == [
        ("tier_1k", 1_000, 290, "2.90"),
        ("tier_10k", 10_000, 1_900, "19.00"),
        ("tier_100k", 100_000, 17_000, "170.00"),
        ("tier_500k", 500_000, 80_000, "800.00"),
    ]
    assert packages[2]["tag"] == "API 调用最佳"


def test_create_order_rejects_unknown_package(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post(
        "/v1/recharge/orders",
        json={"packageCode": "tier_free", "requestId": "req-x"},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_PACKAGE"


def test_create_order_idempotent(client: TestClient, auth_headers: dict[str, str]) -> None:
    first = _order(client, auth_headers)
    again = _order(client, auth_headers)  # 同 requestId 重试
    assert again["orderNo"] == first["orderNo"]


def test_pay_flow_credits_wallet(client: TestClient, auth_headers: dict[str, str]) -> None:
    """下单 → Mock 支付 → 钱包到账（一次）。"""
    order = _order(client, auth_headers, "tier_1k")
    resp = client.post(f"/v1/recharge/orders/{order['orderNo']}/pay", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["credited"] is True
    assert body["credits"] == 1_000
    assert body["balanceAfter"] == 1_000

    wallet = client.get("/v1/wallet", headers=auth_headers).json()
    assert wallet["balance"] == 1_000

    # 重复支付 → 409 订单状态错误
    replay = client.post(f"/v1/recharge/orders/{order['orderNo']}/pay", headers=auth_headers)
    assert replay.status_code == 409
    assert replay.json()["code"] == "ORDER_STATE_ERROR"


def test_payment_callback_replay_idempotent(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """内部回调端点：同一回调重放只入账一次（验签 + 幂等双闸门）。"""
    order = _order(client, auth_headers, "tier_10k")

    # 构造签名回调（与 Mock 渠道同密钥——测试内直调 provider）
    from linkai_billing.infra.payment_mock import MockPaymentProvider

    secret = client.app.state.payment._secret  # type: ignore[attr-defined]
    provider = MockPaymentProvider(secret=secret)
    callback = provider.build_callback(
        order_no=order["orderNo"],
        amount_fen=1_900,
        callback_id="cb-api-1",
        trade_no="trade-api-1",
    )
    headers = {"X-Internal-Token": TEST_INTERNAL_TOKEN}
    first = client.post("/internal/v1/recharge/callback", json=callback, headers=headers)
    assert first.status_code == 200
    assert first.json()["credited"] is True

    second = client.post("/internal/v1/recharge/callback", json=callback, headers=headers)
    assert second.status_code == 200
    assert second.json()["credited"] is False  # 幂等命中

    wallet = client.get("/v1/wallet", headers=auth_headers).json()
    assert wallet["balance"] == 10_000  # 只加一次


def test_payment_callback_bad_signature_rejected(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    order = _order(client, auth_headers, "tier_1k")
    callback = {
        "payload": {
            "channel": "mock",
            "orderNo": order["orderNo"],
            "amountFen": "290",
            "callbackId": "cb-bad",
            "tradeNo": "trade-bad",
            "timestamp": "9999999999",
        },
        "signature": "forged-signature",
    }
    resp = client.post(
        "/internal/v1/recharge/callback",
        json=callback,
        headers={"X-Internal-Token": TEST_INTERNAL_TOKEN},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "PAYMENT_VERIFY_FAILED"

    wallet = client.get("/v1/wallet", headers=auth_headers).json()
    assert wallet["balance"] == 0  # 未入账


def test_list_orders(client: TestClient, auth_headers: dict[str, str]) -> None:
    _order(client, auth_headers, "tier_1k")
    _order(client, auth_headers, "tier_10k")
    resp = client.get("/v1/recharge/orders", headers=auth_headers)
    assert resp.status_code == 200
    orders = resp.json()
    assert len(orders) == 2
    assert {o["packageCode"] for o in orders} == {"tier_1k", "tier_10k"}
    assert all(o["status"] == "pending" for o in orders)

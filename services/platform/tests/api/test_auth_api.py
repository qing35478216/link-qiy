"""API 层端到端测试（TestClient + SQLite，Mock Provider 驱动）。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _send_code(client: TestClient, phone: str) -> str:
    resp = client.post("/auth/phone/sms-code", json={"phone": phone})
    assert resp.status_code == 204
    code = client.app.state.sms_codes.peek_code(phone)  # type: ignore[attr-defined]
    assert code is not None
    return code


def _phone_login(client: TestClient, phone: str) -> dict:
    code = _send_code(client, phone)
    resp = client.post(
        "/auth/phone/login",
        json={"phone": phone, "smsCode": code, "agreementAccepted": True},
    )
    assert resp.status_code == 200
    return resp.json()


def test_healthz(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_phone_login_agreement_not_accepted(client: TestClient) -> None:
    _send_code(client, "13800138000")
    resp = client.post(
        "/auth/phone/login",
        json={"phone": "13800138000", "smsCode": "000000", "agreementAccepted": False},
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "AGREEMENT_NOT_ACCEPTED"


def test_phone_login_and_get_me(client: TestClient) -> None:
    tokens = _phone_login(client, "13800138000")
    assert set(tokens) == {"accessToken", "refreshToken", "expiresIn", "tokenType"}

    resp = client.get("/me", headers={"Authorization": f"Bearer {tokens['accessToken']}"})
    assert resp.status_code == 200
    profile = resp.json()
    assert profile["phone"] == "13800138000"
    assert profile["plan"] == "basic"
    assert profile["agreementAcceptedAt"] is not None


def test_get_me_requires_bearer(client: TestClient) -> None:
    resp = client.get("/me")
    assert resp.status_code == 401
    assert resp.json()["code"] == "INVALID_TOKEN"


def test_get_me_tampered_token_rejected(client: TestClient) -> None:
    tokens = _phone_login(client, "13800138000")
    header, _, signature = tokens["accessToken"].rpartition(".")
    forged = f"{header}.eyJzdWIiOiJmb3JnZWQifQ.{signature}"
    resp = client.get("/me", headers={"Authorization": f"Bearer {forged}"})
    assert resp.status_code == 401


def test_get_me_tenant_mismatch_rejected(client: TestClient) -> None:
    tokens = _phone_login(client, "13800138000")
    resp = client.get(
        "/me",
        headers={
            "Authorization": f"Bearer {tokens['accessToken']}",
            "X-Tenant-Id": "someone-elses-tenant",
        },
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "TENANT_MISMATCH"


def test_patch_me(client: TestClient) -> None:
    tokens = _phone_login(client, "13800138000")
    headers = {"Authorization": f"Bearer {tokens['accessToken']}"}
    resp = client.patch(
        "/me", json={"nickname": "阿石", "avatarUrl": "https://x/y.png"}, headers=headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["nickname"] == "阿石"
    assert body["avatarUrl"] == "https://x/y.png"
    # 再读一次确认持久化
    assert client.get("/me", headers=headers).json()["nickname"] == "阿石"


def test_refresh_flow(client: TestClient) -> None:
    tokens = _phone_login(client, "13800138000")
    resp = client.post("/auth/refresh", json={"refreshToken": tokens["refreshToken"]})
    assert resp.status_code == 200
    new_tokens = resp.json()
    assert new_tokens["accessToken"] != tokens["accessToken"]

    # 旧 refresh 已轮换吊销
    resp = client.post("/auth/refresh", json={"refreshToken": tokens["refreshToken"]})
    assert resp.status_code == 401
    assert resp.json()["code"] == "REFRESH_TOKEN_REVOKED"


def test_logout_then_refresh_fails(client: TestClient) -> None:
    tokens = _phone_login(client, "13800138000")
    headers = {"Authorization": f"Bearer {tokens['accessToken']}"}
    resp = client.post("/auth/logout", headers=headers)
    assert resp.status_code == 204

    resp = client.post("/auth/refresh", json={"refreshToken": tokens["refreshToken"]})
    assert resp.status_code == 401
    assert resp.json()["code"] == "REFRESH_TOKEN_REVOKED"


def test_wechat_qrcode_flow(client: TestClient) -> None:
    resp = client.post("/auth/wechat/qrcode", json={"scene": "login"})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"ticket", "qrUrl", "expiresAt"}

    ticket = body["ticket"]
    resp = client.get(f"/auth/wechat/qrcode/{ticket}")
    assert resp.json()["status"] == "pending"

    provider = client.app.state.wechat_provider  # type: ignore[attr-defined]
    provider.mark_scanned(ticket)
    assert client.get(f"/auth/wechat/qrcode/{ticket}").json()["status"] == "scanned"

    provider.confirm(ticket, "openid-e2e-1")
    resp = client.get(f"/auth/wechat/qrcode/{ticket}")
    payload = resp.json()
    assert payload["status"] == "confirmed"
    assert payload["tokens"]["accessToken"]

    # 令牌可直接访问 /me
    me = client.get("/me", headers={"Authorization": f"Bearer {payload['tokens']['accessToken']}"})
    assert me.status_code == 200


def test_wechat_unknown_ticket(client: TestClient) -> None:
    resp = client.get("/auth/wechat/qrcode/not-exist")
    assert resp.json()["status"] == "expired"


def test_validation_error_shape(client: TestClient) -> None:
    resp = client.post("/auth/phone/login", json={"phone": "13800138000"})
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["requestId"]

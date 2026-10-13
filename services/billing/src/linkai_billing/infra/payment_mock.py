"""Mock 支付渠道（Phase 0；生产替换为微信/支付宝适配器，铁律 4 注册机制）。

安全契约（资金域零容错）：
- 回调签名 = HMAC-SHA256(共享密钥, 规范化载荷)；规范化 = 按键排序的
  k=v&... 拼串（跨语言稳定），**禁止**直接签 JSON 原文（键序/空白敏感）；
- 验签用 `hmac.compare_digest` 常量时间比较，防时序侧信道；
- 重放防护：载荷带 `timestamp`（秒），超过窗口（pricing.PAYMENT_CALLBACK_
  TTL_SECONDS）拒绝；同 `callback_id` 重复投递由订单侧幂等再兜底；
- 密钥经 LINKAI_PAYMENT_MOCK_SECRET 注入，默认值仅本地开发（启动告警）。

Mock 行为：`create_payment` 直接返回"预支付成功"，`build_callback`
模拟渠道异步通知（生产由渠道 HTTP 推送 /internal/v1/recharge/callback）。
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any

from linkai_billing.domain.pricing import PAYMENT_CALLBACK_TTL_SECONDS
from linkai_billing.infra.config import get_settings


def canonical_payload(payload: dict[str, str]) -> str:
    """规范化载荷：按键排序的 k=v&... 拼串（跨语言稳定，跨服务可复现）。"""
    return "&".join(f"{key}={payload[key]}" for key in sorted(payload))


class MockPaymentProvider:
    """Mock 支付渠道（domain.ports.PaymentProvider 实现）。"""

    def __init__(self, *, secret: str | None = None) -> None:
        self._secret = secret or get_settings().payment_mock_secret

    def channel(self) -> str:
        return "mock"

    # —— 签名原语（可独立单测）——

    def sign(self, payload: dict[str, str]) -> str:
        mac = hmac.new(self._secret.encode(), canonical_payload(payload).encode(), hashlib.sha256)
        return mac.hexdigest()

    def verify(self, payload: dict[str, str], signature: str) -> bool:
        expected = self.sign(payload)
        return hmac.compare_digest(expected, signature)

    # —— 渠道行为 ——

    def create_payment(self, *, order_no: str, amount_fen: int, description: str) -> dict[str, str]:
        """发起支付（Mock：直接成功，返回预支付参数）。"""
        return {
            "channel": self.channel(),
            "orderNo": order_no,
            "amountFen": str(amount_fen),
            "description": description,
            "prepayId": f"mock_prepay_{order_no}",
        }

    def build_callback(
        self,
        *,
        order_no: str,
        amount_fen: int,
        callback_id: str,
        trade_no: str,
        now: float | None = None,
    ) -> dict[str, Any]:
        """构造一条已签名的渠道回调（Mock 驱动/测试回放用）。

        生产形态由渠道推送；载荷字段与验签逻辑保持一致。
        """
        payload: dict[str, str] = {
            "channel": self.channel(),
            "orderNo": order_no,
            "amountFen": str(amount_fen),
            "callbackId": callback_id,
            "tradeNo": trade_no,
            "timestamp": str(int(now if now is not None else time.time())),
        }
        return {"payload": payload, "signature": self.sign(payload)}

    def verify_callback(self, body: dict[str, Any], *, now: float | None = None) -> dict[str, str]:
        """验签 + 重放窗口校验；失败抛 PaymentVerifyError（安全事件，须告警）。"""
        from linkai_billing.domain.errors import PaymentVerifyError

        payload_raw = body.get("payload")
        signature = body.get("signature")
        if not isinstance(payload_raw, dict) or not isinstance(signature, str):
            raise PaymentVerifyError("回调体缺失 payload/signature")
        payload = {str(k): str(v) for k, v in payload_raw.items()}
        if not self.verify(payload, signature):
            raise PaymentVerifyError("支付回调验签失败（疑似伪造/篡改）")
        ts_raw = payload.get("timestamp")
        if ts_raw is None or not ts_raw.isdigit():
            raise PaymentVerifyError("回调缺少合法 timestamp")
        age = (now if now is not None else time.time()) - int(ts_raw)
        if age > PAYMENT_CALLBACK_TTL_SECONDS:
            raise PaymentVerifyError(
                f"回调超出重放窗口（{age:.0f}s > {PAYMENT_CALLBACK_TTL_SECONDS}s）"
            )
        return payload

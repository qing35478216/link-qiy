"""计费域错误体系（契约 common.yaml#/Error：code/message 由 api 层映射 HTTP）。

资金域零容错：所有错误显式携带稳定 `code`（前端/看板按 code 分流），
消息面向人（可进日志/告警），**禁止**把异常消息当程序判据。
"""

from __future__ import annotations


class BillingError(Exception):
    """计费域错误基类。`http_status` 由 api 层统一映射。

    `details` 为结构化附加信息（进契约 Error.details 字段）——
    控制台/看板按 code + details 分流，**禁止**解析异常消息文本。
    """

    code = "BILLING_ERROR"
    http_status = 400

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.details: dict[str, object] = details or {}


class InsufficientCredits(BillingError):
    """积分余额不足（扣减被阻断；事件已留痕，见 MeteringService 规则）。"""

    code = "INSUFFICIENT_CREDITS"
    http_status = 402


class QuotaExceeded(BillingError):
    """版本权益超限（功能开关未开/用量达上限）。

    details 契约：{"dimension": 权益维度, "limit": 上限, "used": 当前用量,
    "plan": 当前版本}——控制台据此渲染"升级后可继续使用"。
    """

    code = "QUOTA_EXCEEDED"
    http_status = 403


class FeatureNotAvailable(BillingError):
    """功能开关未对当前版本开放（权益矩阵 feature flag = False）。"""

    code = "FEATURE_NOT_AVAILABLE"
    http_status = 403


class OrderStateError(BillingError):
    """订单状态机非法流转（如重复支付、已关单订单支付）。"""

    code = "ORDER_STATE_ERROR"
    http_status = 409


class OrderNotFound(BillingError):
    code = "ORDER_NOT_FOUND"
    http_status = 404


class PaymentVerifyError(BillingError):
    """支付回调验签失败/重放窗口过期——安全事件，必须告警。"""

    code = "PAYMENT_VERIFY_FAILED"
    http_status = 401


class InvalidPackage(BillingError):
    """充值套餐编码不存在（四档之外）。"""

    code = "INVALID_PACKAGE"
    http_status = 400


class DuplicateRequestId(BillingError):
    """幂等键冲突且载荷不一致（同 request_id 不同内容——疑似重放攻击）。

    仅在仓储层检测到"键相同、业务字段不同"时抛出；键相同且内容一致是
    正常幂等命中（返回既有结果，不抛错）。
    """

    code = "DUPLICATE_REQUEST_ID"
    http_status = 409


class TenantMismatch(BillingError):
    """X-Tenant-Id 头与令牌 tid 不一致（铁律 6 的服务侧 enforcement）。"""

    code = "TENANT_MISMATCH"
    http_status = 403


class InvalidToken(BillingError):
    code = "INVALID_TOKEN"
    http_status = 401


class WalletNotFound(BillingError):
    code = "WALLET_NOT_FOUND"
    http_status = 404

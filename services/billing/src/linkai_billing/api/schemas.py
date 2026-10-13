"""API 序列化模型（契约 console-api.yaml 的 camelCase 形状）。

与 platform 同款约定：**字段名即契约名（camelCase）**，不用 alias——
mypy --strict + pydantic 插件下构造参数与字段名一致，零适配噪音。

usage 的 limit 字段：不限制时**省略**（契约字段非 required；控制台
QuotaBadge 对缺失 limit 优雅降级，不渲染 "/ limit"、不误报超限）。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


# —— 钱包 ——


class WalletResponse(ApiModel):
    tenantId: str
    balance: int
    plan: str
    reminderThreshold: int
    lowBalance: bool
    shouldRemind: bool


class CheckInResponse(ApiModel):
    tenantId: str
    date: str
    creditsGranted: int
    already: bool
    balanceAfter: int


class ReminderThresholdRequest(ApiModel):
    threshold: int


# —— 充值套餐/订单 ——


class RechargePackageResponse(ApiModel):
    code: str
    credits: int
    amountFen: int
    amountYuan: str
    label: str
    tag: str | None = None


class CreateOrderRequest(ApiModel):
    packageCode: str
    requestId: str


class OrderResponse(ApiModel):
    orderNo: str
    tenantId: str
    packageCode: str
    credits: int
    amountFen: int
    status: str
    provider: str
    providerTradeNo: str | None = None
    paidAt: datetime | None = None
    createdAt: datetime


class PayOrderResponse(ApiModel):
    orderNo: str
    credited: bool
    credits: int
    balanceAfter: int | None = None


# —— 使用记录 ——


class UsageRecordResponse(ApiModel):
    entryId: str
    requestId: str
    kind: str
    source: str
    status: str
    delta: int
    balanceAfter: int | None = None
    appCode: str | None = None
    modelCode: str | None = None
    provider: str | None = None
    promptTokens: int
    completionTokens: int
    totalTokens: int
    creditsCharged: int
    latencyMs: int
    outcome: str | None = None
    traceId: str | None = None
    occurredAt: datetime


class UsagePageResponse(ApiModel):
    items: list[UsageRecordResponse]
    nextCursor: str | None = None


# —— 配额 ——


class QuotaUsageResponse(ApiModel):
    messagesUsed: int
    tokensUsed: int
    # messagesLimit/tokensLimit：不限制时省略（积分即约束，见 quota_service 说明）


class QuotaSummaryResponse(ApiModel):
    plan: str
    planBadge: str
    walletBalance: int
    upgradeUrl: str
    usage: QuotaUsageResponse
    monthlyCreditGrant: int | None = None


class QuotaCheckRequest(ApiModel):
    dimension: str
    used: int = 0
    increment: int = 1


class QuotaCheckResponse(ApiModel):
    allowed: bool
    plan: str
    dimension: str
    used: int
    increment: int
    limit: int | None = None


# —— 内部：计量事件 ——


class MeteringEventPayload(ApiModel):
    eventId: str
    tenantId: str
    credits: int
    outcome: str
    provider: str
    modelCode: str
    promptTokens: int = 0
    completionTokens: int = 0
    totalTokens: int = 0
    latencyMs: int = 0
    attempt: int = 1
    traceId: str | None = None
    appCode: str | None = None
    conversationId: str | None = None
    errorCode: str | None = None
    fallbackFrom: str | None = None
    occurredAt: datetime | None = None


class MeteringEventResult(ApiModel):
    requestId: str
    result: str  # applied / duplicate / blocked
    creditsCharged: int
    balanceAfter: int | None = None


class MeteringIngestResponse(ApiModel):
    results: list[MeteringEventResult]


# —— 内部：plan 同步 / 支付回调 / 对账 ——


class PlanSyncRequest(ApiModel):
    plan: str


class PaymentCallbackBody(ApiModel):
    payload: dict[str, str]
    signature: str


class ReconciliationResponse(ApiModel):
    runId: int
    scope: str
    streamCount: int
    dbCount: int
    matched: int
    diffCount: int
    diffRatio: float
    alert: bool
    frozenSettlement: bool
    missingInDb: list[str] = Field(default_factory=list)
    missingInStream: list[str] = Field(default_factory=list)
    amountMismatch: list[dict[str, int | str]] = Field(default_factory=list)

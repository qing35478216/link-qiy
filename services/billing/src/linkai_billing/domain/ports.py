"""领域层端口（协议）——infra 实现、services 消费、domain 不依赖任何框架。

约定（铁律 2/铁律 6）：
- 所有仓储方法签名强制带 tenant_id；
- 资金写路径只有 `WalletLedger.apply()` 一个入口（事务内：流水 INSERT
  幂等 + 余额条件 UPDATE 原子扣减）；
- 协议用 `typing.Protocol` 结构化子类型——测试可注入内存假件，
  生产换 PG/Redis 实现不改业务代码（铁律 4 注册机制）。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Protocol

from linkai_billing.domain.ledger import (
    LedgerApplyOutcome,
    LedgerEntry,
    LedgerEntryKind,
)
from linkai_billing.domain.orders import OrderStatus, RechargeOrder
from linkai_billing.domain.wallet import CreditWallet


class WalletLedger(Protocol):
    """资金写端口：原子地"记流水 + 动余额"。

    实现契约（infra 层必须满足，资金域零容错）：
    1. 同一事务内完成 `ledger_entries` INSERT 与 `wallets` 条件 UPDATE；
    2. INSERT 命中 (tenant_id, request_id) 唯一约束 → 回滚并返回
       `DUPLICATE`（幂等，绝不做第二次余额变动）；
    3. 扣减类条目（delta < 0）以 `balance + delta >= 0` 为条件 UPDATE，
       rowcount=0 → 以 `BLOCKED` 留痕（delta=0），**绝不允许负余额**；
    4. 钱包不存在时自动开户（balance=0），保证计量事件不因缺行被丢弃。
    """

    def apply(self, entry: LedgerEntry) -> LedgerApplyOutcome: ...


class WalletRepository(Protocol):
    """钱包读/写（非资金路径：开户、改提醒阈值、plan 同步）。

    **契约（B1 修复）**：`save()` 只允许变更 plan / reminder_threshold /
    low_balance_notified_on 三列，**绝不回写 balance**——余额是资金状态，
    唯一写路径是 `WalletLedger.apply()` 的条件 UPDATE（原子 + 幂等）。
    整行回放会把并发扣减抹掉（读-改-写丢失更新，资损窗口）。
    """

    def get(self, tenant_id: str) -> CreditWallet | None: ...

    def ensure(self, tenant_id: str) -> CreditWallet:
        """取钱包，不存在则开户（balance=0）。"""
        ...

    def save(self, wallet: CreditWallet) -> None: ...


class LedgerQuery(Protocol):
    """流水查询（使用记录/对账/用量聚合）。"""

    def get_by_request_id(self, tenant_id: str, request_id: str) -> LedgerEntry | None: ...

    def list_entries(
        self,
        tenant_id: str,
        *,
        kind: LedgerEntryKind | None = None,
        source: str | None = None,
        app_code: str | None = None,
        model_code: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 50,
        before: tuple[datetime, int] | None = None,
    ) -> Sequence[LedgerEntry]: ...

    def sum_delta(
        self,
        tenant_id: str,
        *,
        kind: LedgerEntryKind | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> int: ...

    def count_applied(
        self,
        tenant_id: str,
        *,
        kind: LedgerEntryKind | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> int: ...

    def usage_totals(
        self,
        tenant_id: str,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> tuple[int, int]:
        """(消息数, token 总数)——本月计费消息与 token 合计（配额面板）。"""
        ...

    def all_request_ids(self, tenant_id: str) -> Iterable[str]:
        """对账用：某租户全部已入账 request_id。"""
        ...

    def tenant_ids_with_debits(self) -> Iterable[str]:
        """对账用：存在计量扣减流水的租户清单（全量扫描入口）。"""
        ...


class OrderRepository(Protocol):
    """充值订单仓储（金额一律整数）。

    例外说明（铁律 6）：`get_by_order_no` 按订单号全局定位——支付渠道
    回调没有租户上下文（渠道只认订单号）；定位后所有后续操作均以订单行
    的 tenant_id 为准。其余方法一律租户域内。
    """

    def add(self, order: RechargeOrder) -> None: ...

    def get(self, tenant_id: str, order_no: str) -> RechargeOrder | None: ...

    def get_by_order_no(self, order_no: str) -> RechargeOrder | None: ...

    def get_by_idempotency_key(self, tenant_id: str, request_id: str) -> RechargeOrder | None: ...

    def list_orders(
        self,
        tenant_id: str,
        *,
        status: OrderStatus | None = None,
        limit: int = 50,
        before: tuple[datetime, str] | None = None,
    ) -> Sequence[RechargeOrder]: ...

    def find_expired_pending(
        self, *, now: datetime, timeout_minutes: int
    ) -> Sequence[RechargeOrder]: ...

    def save(self, order: RechargeOrder, *, expect_status: tuple[OrderStatus, ...]) -> None:
        """条件保存（N2 修复）：仅当订单行当前状态在 expect_status 内才写回。

        并发保护：rowcount=0 说明状态已被并发方迁移（如两路回调同时支付），
        抛 OrderStateError——**禁止**无条件整行覆盖（读-改-写丢失更新，
        会把对方的 provider_trade_no/callback_id/paid_at 抹掉）。
        与 B1 同类：资金邻域状态一律条件 UPDATE + rowcount 校验。
        """
        ...

    def get_by_order_no_fresh(self, order_no: str) -> RechargeOrder | None:
        """绕过身份映射的强制刷新读（populate_existing）——并发落败方
        重读最新态用（同会话内普通 get 会返回过期的身份映射对象）。"""
        ...


class CheckInRepository(Protocol):
    """签到仓储——(tenant_id, date) 唯一约束保证同日只加一次。

    `record` 返回 False 表示当日已签到（唯一约束命中，幂等）——
     infra 内部以 SAVEPOINT 吸收 IntegrityError，不把驱动异常泄漏到
    应用层（services 层零框架 import）。
    """

    def has_checked_in(self, tenant_id: str, date: str) -> bool: ...

    def record(self, tenant_id: str, date: str, credits: int) -> bool: ...


class MeteringEventStream(Protocol):
    """计量事件流水端口（Redis Streams 形态；内存实现用于 dev/测试）。

    角色：model-proxy 产出 → XADD 入流 → billing XREADGROUP 消费 →
    XACK。对账任务 XRANGE 全量比对"流水 vs DB 明细"（T-007 验收⑤）。
    """

    def append(self, event_id: str, payload: dict[str, str]) -> str:
        """XADD：返回流内条目 ID。"""
        ...

    def read_group(
        self, *, consumer: str, count: int = 100, block_ms: int = 0
    ) -> list[tuple[str, dict[str, str]]]:
        """XREADGROUP GROUP billing <consumer>：取本组未决/新消息。"""
        ...

    def ack(self, entry_id: str) -> None:
        """XACK：确认处理完成。"""
        ...

    def range_all(self) -> list[tuple[str, dict[str, str]]]:
        """XRANGE - +：对账全量扫描（含已 ACK 条目）。"""
        ...

    def pending_ids(self) -> list[str]:
        """XPENDING：本组未决条目 ID（消费了一半崩机的痕迹）。"""
        ...


class PaymentProvider(Protocol):
    """支付渠道（Phase 0 = Mock；生产替换为微信/支付宝适配器，铁律 4）。

    回调安全契约：`sign(payload)` 与 `verify(payload, signature)` 必须
    基于共享密钥的 HMAC；实现方负责时间戳重放窗口（见 pricing 常量）。
    `build_callback` 供 Mock/沙箱渠道构造已签名通知（生产适配器可直连
    渠道沙箱）；签名规范化见 infra/payment_mock.canonical_payload。
    """

    def channel(self) -> str: ...

    def create_payment(self, *, order_no: str, amount_fen: int, description: str) -> dict[str, str]:
        """发起支付（Mock 直接返回预支付参数）。"""
        ...

    def build_callback(
        self,
        *,
        order_no: str,
        amount_fen: int,
        callback_id: str,
        trade_no: str,
        now: float | None = None,
    ) -> dict[str, object]:
        """构造一条已签名回调（Mock 驱动/测试回放用）。"""
        ...

    def sign(self, payload: dict[str, str]) -> str: ...

    def verify(self, payload: dict[str, str], signature: str) -> bool: ...

    def verify_callback(
        self, body: dict[str, object], *, now: float | None = None
    ) -> dict[str, str]:
        """验签 + 重放窗口校验；失败抛 PaymentVerifyError（安全事件）。"""
        ...


class Clock(Protocol):
    """时钟（测试打桩用：签到跨日/订单超时/回调重放窗口）。"""

    def now(self) -> datetime: ...


class ReconciliationRunStore(Protocol):
    """对账运行留痕（infra 实现；services 不碰 ORM）。"""

    def save(
        self,
        *,
        scope: str,
        stream_count: int,
        db_count: int,
        matched: int,
        diff_count: int,
        diff_ratio: float,
        alert: bool,
        detail: dict[str, object],
    ) -> int: ...

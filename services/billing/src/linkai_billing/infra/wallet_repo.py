"""钱包/流水的 SQLAlchemy 实现——**资金写路径的核心**。

原子扣减选型（工单要求二选一并记录理由）：**DB 行锁路线
（条件 UPDATE + 唯一约束幂等）**，不采用 Redis Lua。理由：

1. **单一事实源**：余额与流水都在 PG，不存在 Redis/DB 双写的一致窗
   （Redis Lua 路线是"Redis 原子扣 + 异步落库"，窗口期内两处余额不
   同，对账与客诉都难解释）；
2. **幂等由唯一约束硬保证**：(tenant_id, request_id) 唯一索引让"同一
   request_id 只生效一次"成为数据库级不变量，不依赖 Lua 脚本正确性
   与 Redis 持久化配置（AOF everysec 最多丢 1 秒，资金域不可接受）；
3. **单语句原子**：`UPDATE wallets SET balance = balance + :delta
   WHERE tenant_id = :t AND balance + :delta >= 0` 在 PG 行锁下串行
   执行，rowcount=0 即余额不足——无竞态、无重试；
4. **可测性**：SQLite（测试）与 PG（生产）渲染相同 SQL 形态，并发用
   例可在 CI 无 Redis 环境下真实跑；fakeredis 对 Lua（EVAL）支持不
   完整，Redis 路线无法在单测中证明脚本语义。

Redis 定位（Phase 1+）：计量事件**流水**（Streams：XADD/XREADGROUP/
XACK）与对账数据源，以及热点余额的**读缓存预热**——不承担扣减权威。

事务边界：`apply()` 不自行 commit（参与调用方事务，由 api 层
session_scope/deps 统一提交）——保证"入账 + 订单状态迁移"同生同灭。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from linkai_billing.domain.errors import DuplicateRequestId, WalletNotFound
from linkai_billing.domain.ids import utcnow
from linkai_billing.domain.ledger import (
    LedgerApplyOutcome,
    LedgerApplyResult,
    LedgerEntry,
    LedgerEntryKind,
    LedgerEntryStatus,
)
from linkai_billing.domain.wallet import CreditWallet
from linkai_billing.infra.db import ensure_aware
from linkai_billing.infra.models import LedgerEntryModel, WalletModel


def _to_entity(row: WalletModel) -> CreditWallet:
    return CreditWallet(
        tenant_id=row.tenant_id,
        balance=int(row.balance),
        plan=row.plan,
        reminder_threshold=int(row.reminder_threshold),
        low_balance_notified_on=row.low_balance_notified_on,
        created_at=ensure_aware(row.created_at),
        updated_at=ensure_aware(row.updated_at),
    )


class SqlAlchemyWalletLedger:
    """资金写端口实现：流水 INSERT 幂等 + 余额条件 UPDATE，单事务。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    # —— WalletLedger 协议 ——

    def apply(self, entry: LedgerEntry) -> LedgerApplyOutcome:
        now = utcnow()
        self._ensure_wallet(entry.tenant_id, now=now)

        # ① 流水 INSERT（SAVEPOINT 内）——唯一约束即幂等硬保证
        row = LedgerEntryModel(
            entry_id=entry.entry_id,
            tenant_id=entry.tenant_id,
            request_id=entry.request_id,
            kind=str(entry.kind),
            source=str(entry.source),
            status=str(entry.status),
            delta=entry.delta,
            balance_after=None,
            app_code=entry.app_code,
            model_code=entry.model_code,
            provider=entry.provider,
            prompt_tokens=entry.prompt_tokens,
            completion_tokens=entry.completion_tokens,
            total_tokens=entry.total_tokens,
            credits_charged=entry.credits_charged,
            latency_ms=entry.latency_ms,
            outcome=entry.outcome,
            trace_id=entry.trace_id,
            event_id=entry.event_id,
            conversation_id=entry.conversation_id,
            occurred_at=entry.occurred_at,
            created_at=now,
        )
        try:
            with self._session.begin_nested():
                self._session.add(row)
                self._session.flush()
        except IntegrityError:
            # (tenant_id, request_id) 已存在——幂等命中：绝不做第二次余额变动。
            # 防篡改校验：键相同但业务内容不同 → 疑似重放/篡改，显式告警。
            # 比对 kind + credits_charged（不比对 delta：blocked 条目 delta
            # 归零是设计行为，重试同事件属正常幂等，不是篡改）。
            existing = self._session.execute(
                select(LedgerEntryModel).where(
                    LedgerEntryModel.tenant_id == entry.tenant_id,
                    LedgerEntryModel.request_id == entry.request_id,
                )
            ).scalar_one()
            if (
                existing.kind != str(entry.kind)
                or existing.credits_charged != entry.credits_charged
            ):
                raise DuplicateRequestId(
                    f"幂等键 {entry.request_id!r} 已存在且内容不一致"
                    f"（已有 kind={existing.kind}/credits={existing.credits_charged}，"
                    f"本次 kind={entry.kind}/credits={entry.credits_charged}）"
                ) from None
            return LedgerApplyOutcome(result=LedgerApplyResult.DUPLICATE)

        # ② 余额条件 UPDATE（单语句原子；delta<0 时防负余额）
        # cast：SQLAlchemy execute 的重载解析对 Update 链返回 Result[tuple]，
        # 运行时实为 CursorResult（带 rowcount）——显式收窄，语义不变。
        updated = cast(
            "CursorResult[Any]",
            self._session.execute(
                update(WalletModel)
                .where(
                    WalletModel.tenant_id == entry.tenant_id,
                    WalletModel.balance + entry.delta >= 0,
                )
                .values(balance=WalletModel.balance + entry.delta, updated_at=now)
            ),
        )
        if updated.rowcount == 0:
            # 余额不足：留痕不扣减（delta 归零，credits_charged 保留应扣值）
            row.status = str(LedgerEntryStatus.BLOCKED)
            row.delta = 0
            row.credits_charged = -entry.delta
            blocked_balance = self._current_balance(entry.tenant_id)
            row.balance_after = blocked_balance
            self._session.flush()
            return LedgerApplyOutcome(
                result=LedgerApplyResult.BLOCKED, balance_after=blocked_balance
            )

        balance_after = self._current_balance(entry.tenant_id)
        row.balance_after = balance_after
        self._session.flush()
        return LedgerApplyOutcome(result=LedgerApplyResult.APPLIED, balance_after=balance_after)

    def _current_balance(self, tenant_id: str) -> int:
        value = self._session.execute(
            select(WalletModel.balance).where(WalletModel.tenant_id == tenant_id)
        ).scalar_one()
        return int(value)

    def _ensure_wallet(self, tenant_id: str, *, now: datetime) -> WalletModel:
        """取钱包行，不存在则开户（balance=0）——计量事件不因缺行被丢弃。

        并发开户：PK 冲突时回滚 SAVEPOINT 后重取（先到先开，后者复用）。
        """
        row = self._session.execute(
            select(WalletModel).where(WalletModel.tenant_id == tenant_id)
        ).scalar_one_or_none()
        if row is not None:
            return row
        try:
            with self._session.begin_nested():
                self._session.add(
                    WalletModel(
                        tenant_id=tenant_id,
                        balance=0,
                        plan="basic",
                        created_at=now,
                        updated_at=now,
                    )
                )
                self._session.flush()
        except IntegrityError:
            pass  # 并发方已开户
        row = self._session.execute(
            select(WalletModel).where(WalletModel.tenant_id == tenant_id)
        ).scalar_one()
        return row

    # —— WalletRepository 协议（非资金路径）——

    def get(self, tenant_id: str) -> CreditWallet | None:
        row = self._session.execute(
            select(WalletModel).where(WalletModel.tenant_id == tenant_id)
        ).scalar_one_or_none()
        return None if row is None else _to_entity(row)

    def ensure(self, tenant_id: str) -> CreditWallet:
        row = self._ensure_wallet(tenant_id, now=utcnow())
        return _to_entity(row)

    def save(self, wallet: CreditWallet) -> None:
        """非资金路径保存（B1 修复，严明二审 BLOCKING 项）。

        **只显式更新 plan / reminder_threshold / low_balance_notified_on
        三列，绝不回写 balance**——balance 只准经 `apply()` 的条件 UPDATE
        原子路径变更。整行回放（read-modify-write）会把并发扣减抹掉：
        plan 同步读 balance=100 → 计量扣减提交（→90）→ plan UPDATE 写回
        100，扣减丢失（资损窗口）。列级收敛后该窗口在物理上不存在。
        """
        row = self._session.execute(
            select(WalletModel).where(WalletModel.tenant_id == wallet.tenant_id)
        ).scalar_one_or_none()
        if row is None:
            raise WalletNotFound(f"钱包不存在: {wallet.tenant_id}")
        row.plan = wallet.plan
        row.reminder_threshold = wallet.reminder_threshold
        row.low_balance_notified_on = wallet.low_balance_notified_on
        row.updated_at = utcnow()
        # balance 故意不赋值——见 docstring（B1）
        self._session.flush()


class SqlAlchemyLedgerQuery:
    """流水查询实现（使用记录/对账/用量聚合）。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_request_id(self, tenant_id: str, request_id: str) -> LedgerEntry | None:
        row = self._session.execute(
            select(LedgerEntryModel).where(
                LedgerEntryModel.tenant_id == tenant_id,
                LedgerEntryModel.request_id == request_id,
            )
        ).scalar_one_or_none()
        return None if row is None else _entry_to_entity(row)

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
    ) -> list[LedgerEntry]:
        stmt = select(LedgerEntryModel).where(
            LedgerEntryModel.tenant_id == tenant_id
        )
        if kind is not None:
            stmt = stmt.where(LedgerEntryModel.kind == str(kind))
        if source is not None:
            stmt = stmt.where(LedgerEntryModel.source == source)
        if app_code is not None:
            stmt = stmt.where(LedgerEntryModel.app_code == app_code)
        if model_code is not None:
            stmt = stmt.where(LedgerEntryModel.model_code == model_code)
        if since is not None:
            stmt = stmt.where(LedgerEntryModel.occurred_at >= since)
        if until is not None:
            stmt = stmt.where(LedgerEntryModel.occurred_at <= until)
        if before is not None:
            # keyset 分页游标：(occurred_at, id) 严格小于
            stmt = stmt.where(
                (LedgerEntryModel.occurred_at < before[0])
                | ((LedgerEntryModel.occurred_at == before[0]) & (LedgerEntryModel.id < before[1]))
            )
        stmt = stmt.order_by(LedgerEntryModel.occurred_at.desc(), LedgerEntryModel.id.desc())
        stmt = stmt.limit(limit)
        return [_entry_to_entity(row) for row in self._session.execute(stmt).scalars()]

    def sum_delta(
        self,
        tenant_id: str,
        *,
        kind: LedgerEntryKind | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> int:
        from sqlalchemy import func

        stmt = select(func.coalesce(func.sum(LedgerEntryModel.delta), 0)).where(
            LedgerEntryModel.tenant_id == tenant_id
        )
        if kind is not None:
            stmt = stmt.where(LedgerEntryModel.kind == str(kind))
        if since is not None:
            stmt = stmt.where(LedgerEntryModel.occurred_at >= since)
        if until is not None:
            stmt = stmt.where(LedgerEntryModel.occurred_at <= until)
        return int(self._session.execute(stmt).scalar_one())

    def count_applied(
        self,
        tenant_id: str,
        *,
        kind: LedgerEntryKind | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> int:
        from sqlalchemy import func

        stmt = select(func.count(LedgerEntryModel.id)).where(
            LedgerEntryModel.tenant_id == tenant_id,
            LedgerEntryModel.status == str(LedgerEntryStatus.APPLIED),
        )
        if kind is not None:
            stmt = stmt.where(LedgerEntryModel.kind == str(kind))
        if since is not None:
            stmt = stmt.where(LedgerEntryModel.occurred_at >= since)
        if until is not None:
            stmt = stmt.where(LedgerEntryModel.occurred_at <= until)
        return int(self._session.execute(stmt).scalar_one())

    def usage_totals(
        self,
        tenant_id: str,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> tuple[int, int]:
        """(消息数, token 总数)——本月计费消息与 token 合计（配额面板口径）。

        只计 applied 的计量扣减，且排除 outcome=failed（失败尝试不计费
        也不占用量——与 is_billable 语义一致）。
        """
        from sqlalchemy import func

        stmt = select(
            func.count(LedgerEntryModel.id),
            func.coalesce(func.sum(LedgerEntryModel.total_tokens), 0),
        ).where(
            LedgerEntryModel.tenant_id == tenant_id,
            LedgerEntryModel.kind == str(LedgerEntryKind.DEBIT),
            LedgerEntryModel.status == str(LedgerEntryStatus.APPLIED),
            LedgerEntryModel.outcome.is_not(None),
            LedgerEntryModel.outcome != "failed",
        )
        if since is not None:
            stmt = stmt.where(LedgerEntryModel.occurred_at >= since)
        if until is not None:
            stmt = stmt.where(LedgerEntryModel.occurred_at <= until)
        messages, tokens = self._session.execute(stmt).one()
        return int(messages), int(tokens)

    def all_request_ids(self, tenant_id: str) -> list[str]:
        """对账用：某租户全部计量扣减的 request_id（含 blocked 留痕）。"""
        stmt = select(LedgerEntryModel.request_id).where(
            LedgerEntryModel.tenant_id == tenant_id,
            LedgerEntryModel.kind == str(LedgerEntryKind.DEBIT),
        )
        return [str(r) for r in self._session.execute(stmt).scalars()]

    def tenant_ids_with_debits(self) -> list[str]:
        """对账用：存在计量扣减流水的租户（DISTINCT 全量扫描入口）。"""
        from sqlalchemy import func

        stmt = (
            select(LedgerEntryModel.tenant_id)
            .where(LedgerEntryModel.kind == str(LedgerEntryKind.DEBIT))
            .group_by(LedgerEntryModel.tenant_id)
            .order_by(func.min(LedgerEntryModel.id))
        )
        return [str(t) for t in self._session.execute(stmt).scalars()]


def _entry_to_entity(row: LedgerEntryModel) -> LedgerEntry:
    from linkai_billing.domain.ledger import LedgerSource

    return LedgerEntry(
        entry_id=row.entry_id,
        tenant_id=row.tenant_id,
        request_id=row.request_id,
        kind=LedgerEntryKind(row.kind),
        source=LedgerSource(row.source),
        delta=int(row.delta),
        status=LedgerEntryStatus(row.status),
        balance_after=None if row.balance_after is None else int(row.balance_after),
        app_code=row.app_code,
        model_code=row.model_code,
        provider=row.provider,
        prompt_tokens=int(row.prompt_tokens),
        completion_tokens=int(row.completion_tokens),
        total_tokens=int(row.total_tokens),
        credits_charged=int(row.credits_charged),
        latency_ms=int(row.latency_ms),
        outcome=row.outcome,
        trace_id=row.trace_id,
        event_id=row.event_id,
        conversation_id=row.conversation_id,
        row_id=int(row.id),
        occurred_at=ensure_aware(row.occurred_at),
        created_at=ensure_aware(row.created_at),
    )

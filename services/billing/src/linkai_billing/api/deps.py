"""FastAPI 依赖：每请求组装（AppContext）、事务边界与鉴权依赖。

三层身份边界：
1. **控制台面**（/v1/**, /quota/summary）：Bearer JWT（与 platform 共享
   密钥）→ Principal；X-Tenant-Id 与令牌 tid 不一致即拒（铁律 6）；
2. **内部面**（/internal/v1/**）：X-Internal-Token 共享密钥（服务间调用：
   metering 消费 / plan 同步 / 支付回调 / 对账触发）；
3. **支付回调**（/internal/v1/recharge/callback）：内部令牌 + HMAC 验签
   双闸门（渠道回调经网关转发时带内部令牌）。

事务边界：get_context 内正常返回 commit、异常 rollback、 finally close——
资金写路径（ledger.apply / order.mark_paid）与请求同生同灭。
"""

from __future__ import annotations

import hmac
from collections.abc import Iterator
from dataclasses import dataclass

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from linkai_billing.domain.auth import Principal
from linkai_billing.domain.errors import InvalidToken, TenantMismatch
from linkai_billing.domain.ports import MeteringEventStream
from linkai_billing.infra.config import Settings
from linkai_billing.infra.jwt_service import PyJwtVerifier
from linkai_billing.infra.memory_stream import InMemoryMeteringStream
from linkai_billing.infra.order_repo import (
    SqlAlchemyCheckInRepository,
    SqlAlchemyOrderRepository,
)
from linkai_billing.infra.payment_mock import MockPaymentProvider
from linkai_billing.infra.recon_run_store import SqlAlchemyReconciliationRunStore
from linkai_billing.infra.wallet_repo import (
    SqlAlchemyLedgerQuery,
    SqlAlchemyWalletLedger,
)
from linkai_billing.services.metering_service import (
    MeteringIngestService,
    MeteringService,
)
from linkai_billing.services.order_service import OrderService
from linkai_billing.services.quota_service import QuotaService
from linkai_billing.services.reconciliation_service import ReconciliationService
from linkai_billing.services.usage_service import UsageService
from linkai_billing.services.wallet_service import WalletService

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AppContext:
    """单次请求的应用组装体（每请求新建 DB 会话；无状态件从 app.state 共享）。"""

    settings: Settings
    session: Session
    verifier: PyJwtVerifier
    stream: MeteringEventStream
    payment: MockPaymentProvider
    wallet_service: WalletService
    metering_service: MeteringService
    metering_ingest: MeteringIngestService
    order_service: OrderService
    quota_service: QuotaService
    usage_service: UsageService
    reconciliation_service: ReconciliationService


def get_context(request: Request) -> Iterator[AppContext]:
    """请求级组装 + 事务边界：正常返回 commit，异常 rollback，最后关会话。"""
    state = request.app.state
    settings: Settings = state.settings
    session: Session = state.session_factory()
    try:
        wallet_ledger = SqlAlchemyWalletLedger(session)
        ledger_query = SqlAlchemyLedgerQuery(session)
        orders = SqlAlchemyOrderRepository(session)
        checkins = SqlAlchemyCheckInRepository(session)
        run_store = SqlAlchemyReconciliationRunStore(session)
        stream: MeteringEventStream = state.stream
        payment: MockPaymentProvider = state.payment
        metering = MeteringService(ledger=wallet_ledger)
        yield AppContext(
            settings=settings,
            session=session,
            verifier=state.verifier,
            stream=stream,
            payment=payment,
            wallet_service=WalletService(
                wallets=wallet_ledger, ledger=wallet_ledger, checkins=checkins
            ),
            metering_service=metering,
            metering_ingest=MeteringIngestService(stream=stream, processor=metering.process),
            order_service=OrderService(
                orders=orders, ledger=wallet_ledger, payment=payment
            ),
            quota_service=QuotaService(wallets=wallet_ledger, ledger=ledger_query),
            usage_service=UsageService(ledger=ledger_query),
            reconciliation_service=ReconciliationService(
                stream=stream, ledger=ledger_query, run_store=run_store
            ),
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    ctx: AppContext = Depends(get_context),
) -> Principal:
    """解析 Bearer → Principal；有 X-Tenant-Id 时必须与令牌 tid 一致（铁律 6）。"""
    if credentials is None:
        raise InvalidToken("缺少 Bearer 令牌")
    principal = ctx.verifier.verify(credentials.credentials)
    if x_tenant_id is not None and x_tenant_id != principal.tenant_id:
        raise TenantMismatch("X-Tenant-Id 与令牌租户不一致")
    return principal


def require_internal(
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
    ctx: AppContext = Depends(get_context),
) -> None:
    """内部面鉴权：共享密钥常量时间比较（防时序侧信道）。"""
    expected = ctx.settings.internal_token
    if x_internal_token is None or not hmac.compare_digest(x_internal_token, expected):
        raise InvalidToken("内部令牌缺失或不正确")


def build_stream(settings: Settings) -> MeteringEventStream:
    """按配置选事件流水实现：REDIS_URL 有值用 Redis Streams，否则内存实现。"""
    if settings.redis_url:
        from redis import Redis

        from linkai_billing.infra.redis_stream import RedisMeteringStream

        client = Redis.from_url(settings.redis_url, decode_responses=False)
        return RedisMeteringStream(client, key=settings.stream_key, group=settings.stream_group)
    return InMemoryMeteringStream(group=settings.stream_group)

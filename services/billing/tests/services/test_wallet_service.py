"""钱包应用层单测：签到幂等（含并发）/ 余额提醒 / plan 同步。"""

from __future__ import annotations

from linkai_billing.domain.pricing import CHECKIN_REWARD_CREDITS
from linkai_billing.infra.order_repo import SqlAlchemyCheckInRepository
from linkai_billing.infra.wallet_repo import SqlAlchemyWalletLedger
from linkai_billing.services.wallet_service import WalletService
from tests.conftest import run_in_threads


def _service(session: object) -> WalletService:
    ledger = SqlAlchemyWalletLedger(session)  # type: ignore[arg-type]
    return WalletService(
        wallets=ledger,
        ledger=ledger,
        checkins=SqlAlchemyCheckInRepository(session),  # type: ignore[arg-type]
    )


def _balance(session_factory: object, tenant_id: str = "t-1") -> int:
    from sqlalchemy.orm import sessionmaker

    factory: sessionmaker = session_factory  # type: ignore[assignment]
    with factory() as session:
        wallet = SqlAlchemyWalletLedger(session).get(tenant_id)
        session.commit()
        assert wallet is not None
        return wallet.balance


def test_checkin_same_day_twice_grants_once(file_session_factory: object) -> None:
    """签到幂等：同日第二次 already=True，不重复加分（工单验收③）。"""
    from sqlalchemy.orm import sessionmaker

    factory: sessionmaker = file_session_factory  # type: ignore[assignment]
    with factory() as session:
        service = _service(session)
        first = service.check_in("t-1", today="2026-10-14")
        session.commit()
    assert not first.already
    assert first.credits_granted == CHECKIN_REWARD_CREDITS == 57
    assert first.balance_after == 57

    with factory() as session:
        service = _service(session)
        second = service.check_in("t-1", today="2026-10-14")
        session.commit()
    assert second.already
    assert second.credits_granted == 0
    assert second.balance_after == 57
    assert _balance(file_session_factory) == 57


def test_checkin_next_day_grants_again(file_session_factory: object) -> None:
    from sqlalchemy.orm import sessionmaker

    factory: sessionmaker = file_session_factory  # type: ignore[assignment]
    with factory() as session:
        service = _service(session)
        service.check_in("t-1", today="2026-10-14")
        session.commit()
    with factory() as session:
        service = _service(session)
        result = service.check_in("t-1", today="2026-10-15")
        session.commit()
    assert not result.already
    assert result.balance_after == 57 * 2


def test_concurrent_checkin_same_day_grants_once(file_session_factory: object) -> None:
    """★并发★ 同日 10 线程并发签到：只有一次加分（唯一约束硬保证）。"""
    from sqlalchemy.orm import sessionmaker

    factory: sessionmaker = file_session_factory  # type: ignore[assignment]

    def worker(_index: int) -> bool:
        with factory() as session:
            service = _service(session)
            result = service.check_in("t-1", today="2026-10-14")
            session.commit()
            return result.already

    results = run_in_threads(10, worker)
    granted = [r for r in results if r is False]
    assert len(granted) == 1, f"应恰好一次签到成功: {results}"
    assert _balance(file_session_factory) == 57


def test_reminder_threshold_and_low_balance_flag(file_session_factory: object) -> None:
    from sqlalchemy.orm import sessionmaker

    factory: sessionmaker = file_session_factory  # type: ignore[assignment]
    with factory() as session:
        service = _service(session)
        # 未开户：零值视图（查询无副作用）
        view = service.get_wallet("t-unknown")
        session.commit()
    assert view.balance == 0
    assert view.low_balance is True

    with factory() as session:
        service = _service(session)
        service.set_reminder_threshold("t-1", 500)
        session.commit()
    with factory() as session:
        service = _service(session)
        view = service.get_wallet("t-1")
        session.commit()
    assert view.reminder_threshold == 500
    assert view.low_balance is True  # 0 < 500
    assert view.should_remind is True


def test_reminder_marks_notified_once_per_day(file_session_factory: object) -> None:
    from sqlalchemy.orm import sessionmaker

    from linkai_billing.domain.ids import date_key, utcnow

    factory: sessionmaker = file_session_factory  # type: ignore[assignment]
    today = date_key(utcnow())  # UTC 日期口径（与领域层一致，避免时区依赖）
    with factory() as session:
        service = _service(session)
        service.check_in("t-1", today=today)
        service.mark_reminded("t-1", today=today)
        session.commit()
    with factory() as session:
        service = _service(session)
        view = service.get_wallet("t-1")
        session.commit()
    assert view.balance == 57
    assert view.should_remind is False  # 今日已提醒


def test_set_plan_syncs_read_model(file_session_factory: object) -> None:
    from sqlalchemy.orm import sessionmaker

    factory: sessionmaker = file_session_factory  # type: ignore[assignment]
    with factory() as session:
        service = _service(session)
        view = service.set_plan("t-1", "pro")
        session.commit()
    assert view.plan == "pro"

    with factory() as session:
        service = _service(session)
        try:
            service.set_plan("t-1", "platinum")
            session.commit()
        except ValueError as exc:
            session.rollback()
            assert "未知版本" in str(exc)
        else:
            raise AssertionError("非法版本名应被拒绝")

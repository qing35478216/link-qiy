"""对账运行留痕的 SQLAlchemy 实现（infra；services 只经端口）。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from linkai_billing.domain.ids import utcnow
from linkai_billing.infra.models import ReconciliationRunModel


class SqlAlchemyReconciliationRunStore:
    def __init__(self, session: Session) -> None:
        self._session = session

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
    ) -> int:
        row = ReconciliationRunModel(
            run_scope=scope,
            stream_count=stream_count,
            db_count=db_count,
            matched=matched,
            diff_count=diff_count,
            diff_ratio=str(diff_ratio),
            alert=alert,
            detail_json=detail,
            created_at=utcnow(),
        )
        self._session.add(row)
        self._session.flush()
        return int(row.id)

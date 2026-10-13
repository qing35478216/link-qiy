"""AccountDirectory 的 SQLAlchemy 实现。

phone/openid 为全局唯一自然键（建表时 UniqueConstraint），
查询恒为等值过滤，天然防裸查询；详见 domain/repositories.py 说明。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from linkai_platform.domain.repositories import AccountRef
from linkai_platform.infra.models import AccountIndexModel


def _to_ref(row: AccountIndexModel) -> AccountRef:
    return AccountRef(tenant_id=row.tenant_id, user_id=row.user_id)


class SqlAlchemyAccountDirectory:
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_phone(self, phone: str) -> AccountRef | None:
        stmt = select(AccountIndexModel).where(AccountIndexModel.phone == phone)
        row = self._session.execute(stmt).scalar_one_or_none()
        return None if row is None else _to_ref(row)

    def find_by_openid(self, openid: str) -> AccountRef | None:
        stmt = select(AccountIndexModel).where(AccountIndexModel.openid == openid)
        row = self._session.execute(stmt).scalar_one_or_none()
        return None if row is None else _to_ref(row)

    def register(self, *, phone: str | None, openid: str | None, ref: AccountRef) -> None:
        self._session.add(
            AccountIndexModel(
                phone=phone, openid=openid, tenant_id=ref.tenant_id, user_id=ref.user_id
            )
        )

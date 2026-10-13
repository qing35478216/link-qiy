"""RefreshTokenStore 的 SQLAlchemy 实现（登出/轮换状态持久化，重启不复活会话）。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from linkai_platform.domain.repositories import RefreshTokenRecord
from linkai_platform.infra.db import ensure_aware
from linkai_platform.infra.models import RefreshTokenModel


class SqlAlchemyRefreshTokenStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, record: RefreshTokenRecord) -> None:
        self._session.add(
            RefreshTokenModel(
                jti=record.jti,
                user_id=record.user_id,
                expires_at=record.expires_at,
                revoked=record.revoked,
            )
        )

    def get(self, jti: str) -> RefreshTokenRecord | None:
        row = self._session.get(RefreshTokenModel, jti)
        if row is None:
            return None
        return RefreshTokenRecord(
            jti=row.jti,
            user_id=row.user_id,
            expires_at=ensure_aware(row.expires_at),
            revoked=row.revoked,
        )

    def revoke(self, jti: str) -> None:
        row = self._session.get(RefreshTokenModel, jti)
        if row is not None:
            row.revoked = True

    def revoke_all_for_user(self, user_id: str) -> None:
        from sqlalchemy import update

        stmt = (
            update(RefreshTokenModel)
            .where(RefreshTokenModel.user_id == user_id, RefreshTokenModel.revoked.is_(False))
            .values(revoked=True)
        )
        self._session.execute(stmt)

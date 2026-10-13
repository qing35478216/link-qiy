"""UserRepository 的 SQLAlchemy 实现：tenant_id 强制过滤（铁律 6）。

实现约束：任何 select/update 都必须带 tenant_id 条件，单测
tests/infra/test_tenant_isolation.py 证明跨租户读取返回 None。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from linkai_platform.domain.users import Plan, User
from linkai_platform.infra.models import UserModel


def _to_entity(row: UserModel) -> User:
    return User(
        id=row.id,
        tenant_id=row.tenant_id,
        nickname=row.nickname,
        avatar_url=row.avatar_url,
        phone=row.phone,
        wechat_openid=row.wechat_openid,
        plan=Plan(row.plan),
        agreement_accepted_at=row.agreement_accepted_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_row(user: User) -> UserModel:
    return UserModel(
        id=user.id,
        tenant_id=user.tenant_id,
        nickname=user.nickname,
        avatar_url=user.avatar_url,
        phone=user.phone,
        wechat_openid=user.wechat_openid,
        plan=user.plan.value,
        agreement_accepted_at=user.agreement_accepted_at,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


class SqlAlchemyUserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, tenant_id: str, user_id: str) -> User | None:
        stmt = select(UserModel).where(
            UserModel.tenant_id == tenant_id,
            UserModel.id == user_id,  # 强制租户过滤
        )
        row = self._session.execute(stmt).scalar_one_or_none()
        return None if row is None else _to_entity(row)

    def add(self, user: User) -> None:
        self._session.add(_to_row(user))

    def save(self, user: User) -> None:
        # 全字段覆盖：tenant_id 进入 WHERE，保证不能借 save 跨租户搬家
        stmt = (
            self._session.query(UserModel)
            .filter(UserModel.tenant_id == user.tenant_id, UserModel.id == user.id)
            .one()
        )
        stmt.nickname = user.nickname
        stmt.avatar_url = user.avatar_url
        stmt.phone = user.phone
        stmt.wechat_openid = user.wechat_openid
        stmt.plan = user.plan.value
        stmt.agreement_accepted_at = user.agreement_accepted_at
        stmt.updated_at = user.updated_at

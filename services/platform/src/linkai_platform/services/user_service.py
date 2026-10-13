"""用户资料编排（应用层）：GET/PATCH /me。"""

from __future__ import annotations

from linkai_platform.domain.repositories import UserRepository
from linkai_platform.domain.users import User, UserNotFound


class UserService:
    def __init__(self, *, users: UserRepository) -> None:
        self._users = users

    def get_profile(self, *, tenant_id: str, user_id: str) -> User:
        """读取个人资料；tenant 过滤在仓储层强制（铁律 6）。"""
        user = self._users.get(tenant_id, user_id)
        if user is None:
            raise UserNotFound("用户不存在或不属于当前租户")
        return user

    def update_profile(
        self,
        *,
        tenant_id: str,
        user_id: str,
        nickname: str | None = None,
        avatar_url: str | None = None,
        phone: str | None = None,
    ) -> User:
        user = self.get_profile(tenant_id=tenant_id, user_id=user_id)
        user.update_profile(nickname=nickname, avatar_url=avatar_url, phone=phone)
        self._users.save(user)
        return user

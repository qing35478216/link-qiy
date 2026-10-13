"""仓储接口（domain 定义，infra 实现；铁律 2/6）。

tenant_id 过滤说明：
- UserRepository 的所有方法签名都带 tenant_id，infra 实现必须将其写入 WHERE，
  禁止裸查询——这是"仓库层强制过滤"的契约化表达。
- AccountDirectory 是账户目录（auth 查找）：手机号/微信 openid 是全局唯一自然键，
  天然即分区键（WHERE phone = :phone 恒等过滤），账户归属在注册时确定，
  不属于跨租户数据访问。工作租户隔离由 UserRepository 与 JWT tid 保证。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from linkai_platform.domain.users import User


@dataclass(frozen=True)
class AccountRef:
    """账户目录条目：自然键 → 工作租户 + 用户 ID。"""

    tenant_id: str
    user_id: str


class UserRepository(Protocol):
    """用户仓储：全部查询强制 tenant_id 过滤（铁律 6）。"""

    def get(self, tenant_id: str, user_id: str) -> User | None:
        """按 ID 取用户；tenant 不匹配返回 None（防跨租户越读）。"""
        ...

    def add(self, user: User) -> None:
        """新增用户。"""
        ...

    def save(self, user: User) -> None:
        """更新用户（全字段覆盖，由领域实体保证一致性）。"""
        ...


class AccountDirectory(Protocol):
    """账户目录：登录时按自然键定位账户，返回其工作租户。"""

    def find_by_phone(self, phone: str) -> AccountRef | None: ...

    def find_by_openid(self, openid: str) -> AccountRef | None: ...

    def register(self, *, phone: str | None, openid: str | None, ref: AccountRef) -> None:
        """注册自然键 → 账户映射（phone/openid 至少一个非空）。"""
        ...


@dataclass(frozen=True)
class RefreshTokenRecord:
    """刷新令牌记录（jti 维度），支持登出吊销与刷新轮换。"""

    jti: str
    user_id: str
    expires_at: datetime
    revoked: bool = False


class RefreshTokenStore(Protocol):
    """刷新令牌状态存储（Phase 0 内存/SQLAlchemy；重启不复活会话）。"""

    def save(self, record: RefreshTokenRecord) -> None: ...

    def get(self, jti: str) -> RefreshTokenRecord | None: ...

    def revoke(self, jti: str) -> None: ...

    def revoke_all_for_user(self, user_id: str) -> None:
        """吊销某用户全部刷新令牌（登出场景：契约 logout 仅带 access token）。"""
        ...


class SmsCodeStore(Protocol):
    """短信验证码存储：TTL + 尝试次数上限（防爆破）。"""

    def save(self, phone: str, code: str, ttl_seconds: int) -> None: ...

    def verify(self, phone: str, code: str) -> bool:
        """校验验证码：不匹配记一次尝试；达到上限或过期后失效。成功后清除。"""
        ...

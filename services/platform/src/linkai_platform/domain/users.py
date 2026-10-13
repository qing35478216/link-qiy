"""用户实体与值对象（账户域）。

多租户（铁律 6）：用户数据行归属"工作租户"（Phase 0 为个人租户，tenant_id == user_id；
Phase 2 团队域引入后映射到团队空间）。所有仓储查询必须带 tenant_id 过滤。
账户目录查询（手机号/微信 openid）走 AccountDirectory，以全局自然键为分区键，
不属于租户数据访问，见 repositories.py 说明。
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

# 中国大陆手机号：1 开头，共 11 位（契约示例 13800138000）
_PHONE_RE = re.compile(r"^1[3-9]\d{9}$")


class Plan(StrEnum):
    """四档版本（docs/01 第十部分；配额矩阵由 billing/配额域消费）。"""

    BASIC = "basic"
    STANDARD = "standard"
    PRO = "pro"
    ENTERPRISE = "enterprise"


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


def validate_phone(phone: str) -> str:
    """校验手机号（严格匹配，不静默清洗输入）；非法时抛 InvalidPhone。纯函数，无 IO。"""
    if not _PHONE_RE.fullmatch(phone):
        raise InvalidPhone(f"手机号格式非法: {phone!r}")
    return phone


@dataclass
class User:
    """用户聚合根。tenant_id 为其工作租户（Phase 0 个人租户）。"""

    id: str
    tenant_id: str
    nickname: str
    plan: Plan = Plan.BASIC
    avatar_url: str | None = None
    phone: str | None = None
    wechat_openid: str | None = None
    agreement_accepted_at: datetime | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)

    @classmethod
    def register_with_phone(cls, phone: str, *, nickname: str | None = None) -> User:
        """手机号注册：工作租户初始化为个人租户（tenant_id == user_id）。"""
        user_id = new_id()
        now = utcnow()
        return cls(
            id=user_id,
            tenant_id=user_id,  # 个人租户；Phase 2 团队域再引入企业空间
            nickname=nickname or f"用户{phone[-4:]}",
            phone=validate_phone(phone),
            created_at=now,
            updated_at=now,
        )

    @classmethod
    def register_with_wechat(cls, openid: str, *, nickname: str | None = None) -> User:
        """微信扫码注册：openid 为微信侧唯一标识（Mock 阶段为 mock 前缀字符串）。"""
        if not openid or len(openid) > 128:
            raise InvalidOpenid(f"openid 非法: {openid!r}")
        user_id = new_id()
        now = utcnow()
        return cls(
            id=user_id,
            tenant_id=user_id,
            nickname=nickname or "微信用户",
            wechat_openid=openid,
            created_at=now,
            updated_at=now,
        )

    def accept_agreement(self) -> None:
        """勾选协议：记录首次接受时间（幂等）。"""
        if self.agreement_accepted_at is None:
            self.agreement_accepted_at = utcnow()
            self.updated_at = utcnow()

    def update_profile(
        self,
        *,
        nickname: str | None = None,
        avatar_url: str | None = None,
        phone: str | None = None,
    ) -> None:
        """更新个人资料（PATCH /me）。phone 为 None 表示不修改，传值则走格式校验。"""
        if nickname is not None:
            if not (1 <= len(nickname) <= 64):
                raise InvalidNickname("昵称长度须为 1-64 字符")
            self.nickname = nickname
        if avatar_url is not None:
            self.avatar_url = avatar_url
        if phone is not None:
            self.phone = validate_phone(phone)
        self.updated_at = utcnow()


class DomainError(Exception):
    """领域错误基类（api 层映射为 HTTP 响应，见 api/errors.py）。"""


class InvalidPhone(DomainError):
    pass


class InvalidOpenid(DomainError):
    pass


class InvalidNickname(DomainError):
    pass


class UserNotFound(DomainError):
    pass

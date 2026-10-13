"""API Key 归属解析（用户面鉴权：Bearer Key → tenant）。

**技术债（工单 T-004 记录，必须随 platform Key 体系落地移除）**：
契约 service-api.yaml 的 /api-keys 管理段（签发/吊销）归属 platform，
但 platform 尚未实现（T-003 范围为账户+应用域）。Phase 0 由 runtime 持有
`api_keys` 表占位：只存 SHA-256 哈希 + 展示前缀，绝不存明文；
就绪后切换为 PlatformApiKeyResolver（HTTP 调 platform 内部端点），本表下线。

安全约束：
- 不明文落库、不打印（observability.md：日志禁止出现密钥）；
- 解析失败统一返回 None（调用方转 401），不区分"不存在/已吊销"（防探测）。
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from linkai_runtime.domain.ports import TenantIdentity
from linkai_runtime.infra.models import ApiKeyModel


def hash_api_key(key: str) -> str:
    """SHA-256 十六进制（Key 归属解析的自然键）。"""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def key_prefix(key: str) -> str:
    """展示前缀（前 6 + 后 4，如 sk-li…abcd）。"""
    if len(key) <= 10:
        return key[:3] + "…"
    return f"{key[:6]}…{key[-4:]}"


def parse_dev_api_keys(raw: str) -> list[tuple[str, str, str | None]]:
    """解析 dev 种子："key:tenant[:user],key:tenant[:user]"。"""
    out: list[tuple[str, str, str | None]] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        pieces = part.split(":")
        if len(pieces) < 2 or not pieces[0] or not pieces[1]:
            continue
        key, tenant = pieces[0], pieces[1]
        user = pieces[2] if len(pieces) >= 3 and pieces[2] else None
        out.append((key, tenant, user))
    return out


def seed_dev_api_keys(session_factory: sessionmaker[Session], raw: str) -> int:
    """把 env 种子写入 api_keys 表（已存在的哈希跳过；返回新增条数）。"""
    entries = parse_dev_api_keys(raw)
    if not entries:
        return 0
    added = 0
    with session_factory() as session:
        for key, tenant, user in entries:
            digest = hash_api_key(key)
            exists = (
                session.query(ApiKeyModel).filter(ApiKeyModel.key_hash == digest).first()
                is not None
            )
            if exists:
                continue
            now = datetime.now(UTC)
            session.add(
                ApiKeyModel(
                    id=_new_id(),
                    tenant_id=tenant,
                    user_id=user,
                    name="dev-seed",
                    key_hash=digest,
                    prefix=key_prefix(key),
                    revoked=False,
                    created_at=now,
                )
            )
            added += 1
        session.commit()
    return added


def _new_id() -> str:
    from uuid import uuid4

    return str(uuid4())


class DbApiKeyResolver:
    """DB 实现的 Key 归属解析（实现 domain.ports.ApiKeyResolver 协议）。"""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def resolve(self, key: str) -> TenantIdentity | None:
        if not key:
            return None
        digest = hash_api_key(key)
        with self._session_factory() as session:
            row = (
                session.query(ApiKeyModel)
                .filter(ApiKeyModel.key_hash == digest, ApiKeyModel.revoked.is_(False))
                .first()
            )
            if row is None:
                return None
            row.last_used_at = datetime.now(UTC)
            session.commit()
            return TenantIdentity(tenant_id=row.tenant_id, user_id=row.user_id, key_id=row.id)

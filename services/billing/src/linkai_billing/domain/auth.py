"""身份值对象（控制台面 JWT 校验产物；platform 为签发方，billing 只校验）。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Principal:
    """已认证主体。tenant_id 为工作租户（铁律 6：全链路数据隔离键）。"""

    user_id: str
    tenant_id: str

"""鉴权与租户上下文。

设计取舍：**不做**"网关自验用户 API Key"——用户 Key 的签发/吊销归 platform 服务，
model-proxy 只信任网关注入的租户身份。这是铁律 1（契约先行）与跨服务边界的必然结果：
model-proxy 若自己查库验 Key，就违反了"跨服务禁止直接查库"（docs/03 §3.1）。

因此本模块做两件事：
1. 解析**网关注入**的身份头（`X-Tenant-Id` / `X-Trace-Id` / `X-User-Id`）；
2. 校验"缺租户即拒"（铁律 6）——没有租户上下文的调用无法计量归属，直接 401/400。

生产部署时这些头由 Go gateway 强制注入并对外剥离（防止用户伪造 X-Tenant-Id）。

⚠️ **信任边界（安全关键，T-008 对齐时确认过一次）**：
本模块信任网关注入的身份头。这要求网关做到：① 转发前**剥离**外部传入的同名头
② 再注入真实值。若网关不剥离，客户端可伪造 `X-Tenant-Id` 造成跨租户串账。
**headername 与 T-008 已对齐为 `X-User-Id`**（Go 侧早期注入的是 `X-Subject-Id`，
两边名字不一致会让伪造值畅通无阻——这类"口头约定无契约"的坑已上报 T-015，
建议何约把网关注入头清单写进 `packages/contracts/schemas/common.yaml`）。

⚠️ **`user_id` 当前刻意不流入任何计费字段**：`CallerIdentity.user_id` 只到api 层，
不进 `InvocationContext`、不进 `MeteringEvent`。原因：它来自可被客户端影响的请求头，
一旦参与计量归属就是跨租户串账的入口。
`tests/unit/test_auth_trust_boundary.py` 锁定了这条不变量——
将来若有人要把user_id 接入计费，该测试会失败并提醒先解决可信来源问题。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Header

from linkai_model_proxy.domain.errors import TenantContextError
from linkai_model_proxy.domain.routing import InvocationContext

#: 网关注入身份头的标准名。
#: 名称必须与 T-008 Go 网关实际注入的一致——不一致会让客户端伪造值被当真。
TENANT_HEADER = "X-Tenant-Id"
TRACE_HEADER = "X-Trace-Id"
USER_HEADER = "X-User-Id"
#: 网关签名头——存在时 model-proxy 可校验请求确实来自 gateway（Phase 1 落地）。
#: 注意：这是纵深防御，不能替代"网关剥离外部头"——签名校验本身也依赖头部完整性。
GATEWAY_SIGNATURE_HEADER = "X-Gateway-Signature"

#: 租户 ID 长度上限——超长直接拒（防注入/内存放大）
MAX_TENANT_ID_LEN = 64


@dataclass(frozen=True, slots=True)
class CallerIdentity:
    """调用方身份。"""

    tenant_id: str
    trace_id: str
    user_id: str | None = None

    def to_context(
        self, *, app_code: str | None = None, conversation_id: str | None = None
    ) -> InvocationContext:
        return InvocationContext(
            tenant_id=self.tenant_id,
            trace_id=self.trace_id,
            app_code=app_code,
            conversation_id=conversation_id,
        )


async def resolve_caller(
    tenant_id: Annotated[str | None, Header(alias=TENANT_HEADER)] = None,
    trace_id: Annotated[str | None, Header(alias=TRACE_HEADER)] = None,
    user_id: Annotated[str | None, Header(alias=USER_HEADER)] = None,
) -> CallerIdentity:
    """解析调用方身份。

    缺 `X-Tenant-Id` 一律拒绝——**没有租户就没有计费归属**，
    静默放行会造成跨租户串账（铁律 6 的红线）。

    抛领域异常（而非 HTTPException）以保证错误体是契约 `Error` 形态，
    且与其他端点的错误处理路径唯一。
    """
    if not tenant_id or not tenant_id.strip():
        raise TenantContextError(f"缺少 {TENANT_HEADER}（由网关注入，调用方不得自设）")
    cleaned = tenant_id.strip()
    if len(cleaned) > MAX_TENANT_ID_LEN:
        raise TenantContextError("租户 ID 长度超限")
    return CallerIdentity(
        tenant_id=cleaned,
        trace_id=(trace_id or "").strip() or "-",
        user_id=user_id,
    )

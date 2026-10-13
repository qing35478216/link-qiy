"""Phase 0 已知契约缺口基线。

**为什么需要这个文件**：AGENTS.md 明确规定 Phase 0 是「进度优先」的轻量门禁，
若干契约规则被甲方指令降级（如错误响应 4xx 覆盖率：spectral 侧已从 error 降为 warn）。
如果 QA 侧对同一条规则用硬断言，会出现两种坏结果：
要么 CI 常红、团队学会忽略门禁；要么为了让 CI 变绿而放松断言——后者更糟，
因为它让门禁变成了摆设。

所以采用**缺口基线（gap baseline）**模式：

- 每条已知缺口登记在此处（含发现工单与责任人）。
- 检查函数比对「实际缺口」与「基线缺口」：**新增缺口 → FAIL**，**存量缺口 → 记入报告**。
- 缺口消失或被修复后，从本文件删除对应条目即可（基线只减不增是硬约束，
  任何新增条目必须写明来源工单，否则测试失败）。

这样既尊重甲方「进度优先」的降级指令，又保证缺口不会悄悄扩大——
这比单纯放宽阈值要严格得多。
"""

from __future__ import annotations

#: 写操作缺少 4xx 响应声明。契约 v0.1.1 现状：13 个写操作全部未声明 4xx。
#: 处置：T-014 已将 spectral 规则降为 warn；契约侧补齐由 Contract Engineer 排期。
GAP_WRITE_OPS_MISSING_4XX = "GAP-CONTRACT-001"

#: 契约从未引用 common.yaml#Error 统一错误信封。
#: 现状：console-api / service-api 的 components.schemas 中无 Error，
#: 也无任何 `../schemas/common.yaml#/Error` 的 $ref 引用，
#: 即前端拿不到统一错误形状，链路上拿不到 requestId。
#: 上报：工单 T-010「契约缺口上报」节，已提请 Contract Engineer（何约）处理。
GAP_ERROR_ENVELOPE_UNREFERENCED = "GAP-CONTRACT-002"

#: console-api 的 POST /auth/logout 未声明任何 parameters（含 X-Tenant-Id）。
#: 影响：登出会写刷新令牌吊销记录，属数据写操作；缺租户标识意味着实现层
#: 可能写成裸查询/裸更新，与铁律 6「所有数据操作带 tenant_id」冲突。
#: 该端点 204 无响应体，不影响 SDK 生成，但影响服务端实现约束。
GAP_LOGOUT_MISSING_TENANT_HEADER = "GAP-CONTRACT-003"

#: 微信扫码登录路径缺少协议勾选约束。
#: 现状：POST /auth/phone/login 有 required: [phone, smsCode, agreementAccepted]
#: 且 403 AGREEMENT_NOT_ACCEPTED；但扫码路径完全没有等价约束——
#:   - POST /auth/wechat/qrcode      → 无 required，properties 只有 scene
#:   - GET  /auth/wechat/qrcode/{ticket} → 无任何请求参数
#: 后果：协议签署只在短信登录被强制，走微信扫码可完全绕过。
#: 这不只是合规问题，还是**可被利用的绕过路径**：用户在网页勾选过协议，
#: 之后用微信扫码登录时服务端不再校验，等于协议同意状态可被跨通道绕过。
#: 与 channel-engineer 在 T-008 发现的同一问题（#26），此处统一登记避免重复上报。
GAP_WECHAT_LOGIN_MISSING_AGREEMENT = "GAP-CONTRACT-004"

#: 「缺失租户标识」的错误状态码在各服务间不一致。
#: 实测（Wave 1 各服务自测结果）：
#:   - T-005 model-proxy 缺 X-Tenant-Id → 400 Bad Request
#:   - T-008 gateway    缺租户        → 500 Internal Server Error
#: 两者语义相同（都是「拒绝非法请求」），但状态码不同：
#:   - 400 是正确的（请求方的问题）
#:   - 500 会被客户端与监控归类为「服务端故障」，污染错误率指标与告警
#: 根因同类于GAP-CONTRACT-004：契约没定义，各服务各自决定。
#: 本条不在 Phase 1 前强改——**状态码归属是契约决定，只能何约定**。
#: QA 侧的处置：断言写成「必须落在 4xx 族」而非钉死某个码，
# 这样两种实现都通过；何约定码后再把断言收紧为精确匹配。
GAP_TENANT_MISSING_STATUS_INCONSISTENT = "GAP-CONTRACT-005"

#: 网关注入的身份头清单未在契约中定义。
#: 实测：packages/contracts/schemas/common.yaml 只有 X-Tenant-Id（第 25 行），
#: X-User-Id / X-Trace-Id / X-Gateway-Surface 均无定义，全靠服务间口头约定。
#: 后果：客户端可伪造这些头直连下游（T-008 已实测出 X-User-Id 穿透并修复），
#: 但「哪些 X-* 归网关管」没有单一事实源，新增下游服务时必然漏加。
#: 由 channel-engineer 在 T-008 独立发现并上报，与 GAP-CONTRACT-004 根因同类。
GAP_IDENTITY_HEADERS_UNDEFINED = "GAP-CONTRACT-006"

#: 网关未剥离客户端凭证头（Authorization / Cookie / Proxy-Authorization）。
#:
#: **为什么独立编号而不并入006**：根因虽同为「契约没定义」，但影响面更重——
#: 006 是「身份头没定义」（契约缺一份清单）；本条是「凭证头**本就必须剥离**
#: 却没剥离」，属实现层安全缺陷而非契约缺项。何约改 common.yaml 不会自动
#: 让 T-008 的 routing.go 安全，这正是本项目已吃过的亏（契约改了但没人改实现）。
#: 因此处置路径不同：006 是「补契约清单」，本条是「契约 + 实现双改」，
#: 必须各自独立验收，故独立编号并交叉引用 006。
#:
#: 实测（发现人 qa-reviewer，2026-10-13；channel-engineer 在 T-008 独立复现确认）：
#: 客户端 `Authorization: Bearer client-original-jwt` 与 `Cookie: session=abc123`
#: 原样到达下游——Go 侧 `httputil.ReverseProxy` 默认转发所有头，
#: `routing.go` / `proxy.go` 全文检索 `Authorization` 零命中。
#:
#: 后果：**鉴权双重入口**。网关已完成鉴权与配额裁决，但下游若自行校验，
#: 看到的是客户端原始凭证而非网关的裁决结论——可能出现
#: 「网关已封禁/限流，下游却按自己的判断放行」。这不是冗余校验问题，
#: 而是下游可能推翻网关的裁决。
#:
#: 修复与回归防护（T-008 commit 6899e88）：
#:   -新增 `clientCredentialHeaders`，在 `sanitizeIdentityHeaders` 中一并剥离，
#:     下游只认网关注入的身份头，网关成为唯一鉴权决策点；
#:   - 回归用例：`TestStripsClientCredentialHeaders`（含「剥离凭证头不影响
#:     网关注入的身份头」的反向断言，防止修过头把该注入的也删了）、
#:     `TestLegacyIdentityHeaderStillStripped`（防后人「清理无用代码」时删掉剥离逻辑）。
#:   - 注意：契约侧尚未定义「网关应剥离哪些头」，删除上述任一用例都会让
#:     回归防护消失——这是本条必须留在缺口基线里的理由。
GAP_CLIENT_CREDENTIAL_HEADERS_NOT_STRIPPED = "GAP-CONTRACT-007"

#: ── 何约补缺口时的写法约束（主理人 T-016 裁决，QA 侧记录以免后人来问我）────
#:
#: **禁止用 `default` 关键字**兜底未知错误码 / 未知取值。
#:
#: 理由：`default` 在 JSON Schema 里是「匹配不上任何 enum 时都算合法」，
#: 于是**新增错误码会静默通过校验**——而新增错误码恰恰是最需要被看见的变化
#: （新增错误码通常意味着新增业务语义或新增失败分支）。
#:
#: 正确写法（两条，按场景选）：
#:   1. `enum` 穷举已知 code，不用 default；未知值由调用方显式处理
#:   2. 确需允许扩展时用 `additionalProperties` 或显式的 `unknown` 分支兜底，
#:      但要让它**在文档/测试里可见**，而不是藏在 default 里
#:
#: 同理适用于任何「枚举 + 兜底」的场景，不限于错误码。
GAP_ENUM_NO_DEFAULT_RULE = "RULE-CONTRACT-001"

#: 本基线登记的缺口。**只允许减少**：新增条目必须在此处登记 issue 出处。
KNOWN_GAPS: dict[str, dict[str, str]] = {
    GAP_WRITE_OPS_MISSING_4XX: {
        "title": "写操作未声明 4xx 响应",
        "detail": "13 个 POST/PUT/PATCH 操作的 responses 中没有任何 4xx 条目。",
        "raised_in": "T-010（QA 基础设施，2026-10-13）",
        "owner": "Contract Engineer（何约）",
        "severity": "warn",
    },
    GAP_ERROR_ENVELOPE_UNREFERENCED: {
        "title": "统一错误信封未被任何操作引用",
        "detail": "common.yaml#Error 定义存在，但两份 OpenAPI 规范均无 $ref 引用。",
        "raised_in": "T-010（QA 基础设施，2026-10-13）",
        "owner": "Contract Engineer（何约）",
        "severity": "blocker-for-phase1",
    },
    GAP_LOGOUT_MISSING_TENANT_HEADER: {
        "title": "POST /auth/logout 缺少 X-Tenant-Id",
        "detail": "登出为数据写操作（吊销刷新令牌），按铁律 6 需带租户标识。",
        "raised_in": "T-010（QA 基础设施，2026-10-13）",
        "owner": "Contract Engineer（何约）",
        "severity": "blocker-for-phase1",
    },
    GAP_WECHAT_LOGIN_MISSING_AGREEMENT: {
        "title": "微信扫码登录路径缺少协议勾选强制",
        "detail": "协议勾选只在 POST /auth/phone/login 强制（required 含 "
                  "agreementAccepted + 403 AGREEMENT_NOT_ACCEPTED）；"
                  "扫码路径 /auth/wechat/qrcode 与 /auth/wechat/qrcode/{ticket} "
                  "无任何等价约束，协议同意状态可被跨通道绕过。",
        "raised_in": "T-010（QA 基础设施，2026-10-13）；"
                     "channel-engineer 在 T-008 独立发现同一问题（task #26）",
        "owner": "Contract Engineer（何约）",
        "severity": "blocker-for-phase1",
    },
    GAP_TENANT_MISSING_STATUS_INCONSISTENT: {
        "title": "缺失租户标识的错误状态码跨服务不一致",
        "detail": "T-005 model-proxy 返 400，T-008 gateway 返 500。语义相同、"
                  "状态码不同；500 会污染错误率指标与告警。"
                  "QA 侧断言暂用「4xx 族」，待何约定码后收紧为精确匹配。",
        "raised_in": "T-010（随访，2026-10-13）；由 channel-engineer 提出，"
                     "T-008/T-005 自测中实测发现",
        "owner": "Contract Engineer（何约）",
        "severity": "warn",
    },
    GAP_IDENTITY_HEADERS_UNDEFINED: {
        "title": "网关注入的身份头清单未在契约中定义",
        "detail": "common.yaml 只有 X-Tenant-Id；X-User-Id / X-Trace-Id / "
                  "X-Gateway-Surface 全无定义。客户端可伪造这些头直连下游"
                  "（T-008 已实测出 X-User-Id 穿透并修复），"
                  "且「新下游服务该纳管哪些头」没有单一事实源，必然漏加。",
        "raised_in": "T-008（channel-engineer 上报）；T-010 登记为契约层缺口",
        "owner": "Contract Engineer（何约）",
        "severity": "blocker-for-phase1",
    },
    GAP_CLIENT_CREDENTIAL_HEADERS_NOT_STRIPPED: {
        "title": "网关未剥离客户端凭证头（Authorization/Cookie/Proxy-Authorization）",
        "detail": "客户端 Authorization 与 Cookie 原样到达下游"
                  "（httputil.ReverseProxy 默认转发所有头；routing.go/proxy.go "
                  "全文检索 Authorization 零命中）。形成鉴权双重入口——"
                  "网关已裁决凭证状态，下游看到的却是客户端原始凭证，"
                  "可能推翻网关的封禁/限流结论。"
                  "实现侧已修（T-008 6899e88，回归用例 "
                  "TestStripsClientCredentialHeaders / "
                  "TestLegacyIdentityHeaderStillStripped）；"
                  "契约侧仍缺「网关应剥离哪些头」的声明。",
        "raised_in": "T-008 实测（发现路径）；发现人 qa-reviewer 主动发现"
                     "（超出其工单范围），channel-engineer 独立复现确认并修复",
        "owner": "Contract Engineer（何约）+ T-008 实现侧",
        "severity": "blocker-for-phase1",
    },
}
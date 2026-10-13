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
}
"""四档版本权益矩阵（docs/01 第十部分 `/console/price` 实测精确配额）。

矩阵是配额校验的单一事实源：
- **功能开关**（feature flags）：该版本能否用某能力（数据看板/渠道接入/团队空间…）；
- **用量上限**（usage caps）：该版本某维度的最大数量（应用数/工作流数/插件数…）；
- `None` = 不限（企业版"按需定制"）。

platform 的 `APP_LIMITS`（T-003）是本矩阵应用数维度的 Phase 0 副本；
后续 platform 创建应用前应经本服务 `POST /v1/quota/check` 校验（内部 API），
避免两处矩阵漂移——已记入 T-007 交付说明的下游注意。

错误码契约（控制台按 code 分流）：
- 超限 → `QUOTA_EXCEEDED`（403，details 带 dimension/limit/used/plan）
- 功能未开放 → `FEATURE_NOT_AVAILABLE`（403）
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from linkai_billing.domain.errors import FeatureNotAvailable, QuotaExceeded


class Plan(StrEnum):
    """四档版本（与 platform domain.users.Plan 同构；值为契约枚举）。"""

    BASIC = "basic"
    STANDARD = "standard"
    PRO = "pro"
    ENTERPRISE = "enterprise"


PLAN_BADGES: dict[Plan, str] = {
    Plan.BASIC: "基础版",
    Plan.STANDARD: "标准版",
    Plan.PRO: "专业版",
    Plan.ENTERPRISE: "企业版",
}

UPGRADE_URL = "/console/price"


class Dimension(StrEnum):
    """权益维度（用量上限类）。"""

    APPS = "apps"                      # 应用数
    WORKFLOWS = "workflows"            # 工作流数
    PLUGINS = "plugins"                # 自定义插件数
    SUPER_ASSISTANTS = "super_assistants"  # 超级 AI 助理数
    CLOUD_PCS = "cloud_pcs"            # 云电脑台数
    # 知识库文件数（容量口径为字节，另见 knowledge_file_bytes_limit）
    KNOWLEDGE_FILES = "knowledge_files"
    KNOWLEDGE_SEGMENTS = "knowledge_segments"  # 知识库条数
    DB_ROWS = "db_rows"                # 内置数据库行数
    TEAM_MEMBERS = "team_members"      # 团队空间人数
    IMPORT_PAGES = "import_pages"      # 知识库导入单次页数


class Feature(StrEnum):
    """权益维度（功能开关类）。"""

    CUSTOM_MODEL = "custom_model"          # 自定义 AI 大模型
    REMOTE_DATABASE = "remote_database"    # 远程数据库
    DATA_DASHBOARD = "data_dashboard"      # 数据看板
    CHANNEL_ACCESS = "channel_access"      # 渠道接入
    CLIENT_MANAGEMENT = "client_management"  # 客户端管理
    RATE_LIMIT_CONFIG = "rate_limit_config"  # 对话限流配置
    HUMAN_TRANSFER = "human_transfer"      # 智能转人工
    # 聚合对话管理
    AGGREGATED_CHAT = "aggregated_chat"
    TEAM_SPACE = "team_space"              # 团队空间
    OPEN_API_ADVANCED = "open_api_advanced"  # 开放 API 高级能力
    CLOUD_PC = "cloud_pc"                  # 云电脑


@dataclass(frozen=True, slots=True)
class PlanTier:
    """单档版本的权益定义。None = 不限（企业版按需定制）。"""

    plan: Plan
    badge: str
    # 用量上限（docs/01 第十部分实测；None = 不限）
    app_limit: int | None = 3
    workflow_limit: int | None = 2
    plugin_limit: int | None = 3
    super_assistant_limit: int | None = 0   # 基础版=免费试用（不占配额，0 表示不分配）
    cloud_pc_limit: int | None = 0          # 同上
    knowledge_file_limit: int | None = None
    knowledge_segment_limit: int | None = 2_000
    knowledge_file_bytes_limit: int | None = 100 * 1024 * 1024  # 100M
    db_row_limit: int | None = 5_000
    team_member_limit: int | None = 0       # 基础版无团队空间
    import_page_limit: int | None = 2_000
    # 功能开关（✗/✔）
    custom_model: bool = False
    remote_database: bool = False
    data_dashboard: bool = False
    channel_access: bool = False
    client_management: bool = False
    rate_limit_config: bool = False
    human_transfer: bool = False
    aggregated_chat: bool = False
    team_space: bool = False
    open_api_advanced: bool = False
    cloud_pc: bool = False
    # 月度积分额度（docs/01：基础版按签到；标准版 3 万；专业版 100 万；企业按需）
    monthly_credit_grant: int | None = None


TIERS: dict[Plan, PlanTier] = {
    Plan.BASIC: PlanTier(plan=Plan.BASIC, badge=PLAN_BADGES[Plan.BASIC]),
    Plan.STANDARD: PlanTier(
        plan=Plan.STANDARD,
        badge=PLAN_BADGES[Plan.STANDARD],
        app_limit=10,
        workflow_limit=6,
        plugin_limit=10,
        super_assistant_limit=3,
        cloud_pc_limit=1,
        cloud_pc=True,
        knowledge_segment_limit=20_000,
        knowledge_file_bytes_limit=500 * 1024 * 1024,  # 500M
        db_row_limit=50_000,
        import_page_limit=5_000,
        custom_model=True,
        remote_database=True,
        data_dashboard=True,
        channel_access=True,
        client_management=True,
        rate_limit_config=True,
        human_transfer=True,
        aggregated_chat=True,
        team_space=True,
        open_api_advanced=True,
        monthly_credit_grant=30_000,
    ),
    Plan.PRO: PlanTier(
        plan=Plan.PRO,
        badge=PLAN_BADGES[Plan.PRO],
        app_limit=30,
        workflow_limit=15,
        plugin_limit=30,
        super_assistant_limit=9,
        cloud_pc_limit=3,
        cloud_pc=True,
        knowledge_segment_limit=100_000,
        knowledge_file_bytes_limit=3 * 1024 * 1024 * 1024,  # 3G
        db_row_limit=200_000,
        import_page_limit=10_000,
        custom_model=True,
        remote_database=True,
        data_dashboard=True,
        channel_access=True,
        client_management=True,
        rate_limit_config=True,
        human_transfer=True,
        aggregated_chat=True,
        team_space=True,
        team_member_limit=10,
        open_api_advanced=True,
        monthly_credit_grant=1_000_000,
    ),
    Plan.ENTERPRISE: PlanTier(
        plan=Plan.ENTERPRISE,
        badge=PLAN_BADGES[Plan.ENTERPRISE],
        app_limit=None,
        workflow_limit=None,
        plugin_limit=None,
        super_assistant_limit=None,
        cloud_pc_limit=None,
        cloud_pc=True,
        knowledge_segment_limit=None,
        knowledge_file_bytes_limit=None,
        db_row_limit=None,
        team_member_limit=None,
        import_page_limit=None,
        custom_model=True,
        remote_database=True,
        data_dashboard=True,
        channel_access=True,
        client_management=True,
        rate_limit_config=True,
        human_transfer=True,
        aggregated_chat=True,
        team_space=True,
        open_api_advanced=True,
        monthly_credit_grant=None,
    ),
}

_DIMENSION_FIELDS: dict[Dimension, str] = {
    Dimension.APPS: "app_limit",
    Dimension.WORKFLOWS: "workflow_limit",
    Dimension.PLUGINS: "plugin_limit",
    Dimension.SUPER_ASSISTANTS: "super_assistant_limit",
    Dimension.CLOUD_PCS: "cloud_pc_limit",
    Dimension.KNOWLEDGE_FILES: "knowledge_file_limit",
    Dimension.KNOWLEDGE_SEGMENTS: "knowledge_segment_limit",
    Dimension.DB_ROWS: "db_row_limit",
    Dimension.TEAM_MEMBERS: "team_member_limit",
    Dimension.IMPORT_PAGES: "import_page_limit",
}

_FEATURE_FIELDS: dict[Feature, str] = {
    Feature.CUSTOM_MODEL: "custom_model",
    Feature.REMOTE_DATABASE: "remote_database",
    Feature.DATA_DASHBOARD: "data_dashboard",
    Feature.CHANNEL_ACCESS: "channel_access",
    Feature.CLIENT_MANAGEMENT: "client_management",
    Feature.RATE_LIMIT_CONFIG: "rate_limit_config",
    Feature.HUMAN_TRANSFER: "human_transfer",
    Feature.AGGREGATED_CHAT: "aggregated_chat",
    Feature.TEAM_SPACE: "team_space",
    Feature.OPEN_API_ADVANCED: "open_api_advanced",
    Feature.CLOUD_PC: "cloud_pc",
}


def tier_of(plan: str | Plan) -> PlanTier:
    """按版本取权益档位；非法版本名抛 ValueError（调用方转 400）。"""
    try:
        key = Plan(plan)
    except ValueError as exc:
        raise ValueError(f"未知版本: {plan!r}（可用: {[p.value for p in Plan]}）") from exc
    return TIERS[key]


def assert_quota(plan: str | Plan, dimension: Dimension, *, used: int, increment: int = 1) -> None:
    """用量上限校验：used + increment 超过上限抛 QuotaExceeded。

    `increment` 为本次操作将新增的数量（默认 1）——"还能不能再建一个"的
    正确问法是 used + increment > limit，而非 used >= limit。
    """
    tier = tier_of(plan)
    limit = getattr(tier, _DIMENSION_FIELDS[dimension])
    if limit is None:
        return  # 企业版按需定制，不限
    if used + increment > limit:
        raise QuotaExceeded(
            f"{tier.badge}的{_dimension_label(dimension)}上限为 {limit}，当前已用 {used}",
            details={
                "dimension": str(dimension),
                "limit": limit,
                "used": used,
                "increment": increment,
                "plan": str(tier.plan),
            },
        )


def assert_feature(plan: str | Plan, feature: Feature) -> None:
    """功能开关校验：未开放抛 FeatureNotAvailable。"""
    tier = tier_of(plan)
    if not getattr(tier, _FEATURE_FIELDS[feature]):
        raise FeatureNotAvailable(
            f"{tier.badge}未开放「{_feature_label(feature)}」，请升级后使用",
            details={"feature": str(feature), "plan": str(tier.plan)},
        )


def usage_limit_of(plan: str | Plan, dimension: Dimension) -> int | None:
    """取某维度上限（None = 不限）——配额面板/内部查询用。"""
    limit: int | None = getattr(tier_of(plan), _DIMENSION_FIELDS[dimension])
    return limit


_DIMENSION_LABELS: dict[Dimension, str] = {
    Dimension.APPS: "应用数",
    Dimension.WORKFLOWS: "工作流数",
    Dimension.PLUGINS: "自定义插件数",
    Dimension.SUPER_ASSISTANTS: "超级 AI 助理数",
    Dimension.CLOUD_PCS: "云电脑台数",
    Dimension.KNOWLEDGE_FILES: "知识库文件数",
    Dimension.KNOWLEDGE_SEGMENTS: "知识库条数",
    Dimension.DB_ROWS: "内置数据库行数",
    Dimension.TEAM_MEMBERS: "团队空间人数",
    Dimension.IMPORT_PAGES: "单次导入页数",
}

_FEATURE_LABELS: dict[Feature, str] = {
    Feature.CUSTOM_MODEL: "自定义 AI 大模型",
    Feature.REMOTE_DATABASE: "远程数据库",
    Feature.DATA_DASHBOARD: "数据看板",
    Feature.CHANNEL_ACCESS: "渠道接入",
    Feature.CLIENT_MANAGEMENT: "客户端管理",
    Feature.RATE_LIMIT_CONFIG: "对话限流配置",
    Feature.HUMAN_TRANSFER: "智能转人工",
    Feature.AGGREGATED_CHAT: "聚合对话管理",
    Feature.TEAM_SPACE: "团队空间",
    Feature.OPEN_API_ADVANCED: "开放 API 高级能力",
    Feature.CLOUD_PC: "云电脑",
}


def _dimension_label(dimension: Dimension) -> str:
    return _DIMENSION_LABELS[dimension]


def _feature_label(feature: Feature) -> str:
    return _FEATURE_LABELS[feature]

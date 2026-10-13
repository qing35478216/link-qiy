"""四档权益矩阵领域单测（docs/01 第十部分实测配额 + 错误码契约）。"""

from __future__ import annotations

import pytest

from linkai_billing.domain.errors import FeatureNotAvailable, QuotaExceeded
from linkai_billing.domain.quota import (
    Dimension,
    Feature,
    Plan,
    assert_feature,
    assert_quota,
    tier_of,
    usage_limit_of,
)


def test_matrix_matches_docs_measured_limits() -> None:
    """用量上限与 docs/01 第十部分实测一致。"""
    assert tier_of("basic").app_limit == 3
    assert tier_of("standard").app_limit == 10
    assert tier_of("pro").app_limit == 30
    assert tier_of("enterprise").app_limit is None  # 按需定制

    assert tier_of("basic").workflow_limit == 2
    assert tier_of("standard").workflow_limit == 6
    assert tier_of("pro").workflow_limit == 15

    assert tier_of("basic").plugin_limit == 3
    assert tier_of("standard").plugin_limit == 10
    assert tier_of("pro").plugin_limit == 30

    assert tier_of("standard").super_assistant_limit == 3
    assert tier_of("pro").super_assistant_limit == 9

    assert tier_of("standard").knowledge_segment_limit == 20_000
    assert tier_of("pro").knowledge_segment_limit == 100_000
    assert tier_of("standard").db_row_limit == 50_000
    assert tier_of("pro").db_row_limit == 200_000
    assert tier_of("pro").team_member_limit == 10

    # 月度积分额度：基础版按签到（None）；标准 3 万；专业 100 万
    assert tier_of("basic").monthly_credit_grant is None
    assert tier_of("standard").monthly_credit_grant == 30_000
    assert tier_of("pro").monthly_credit_grant == 1_000_000
    assert tier_of("enterprise").monthly_credit_grant is None


def test_matrix_matches_docs_feature_flags() -> None:
    """功能开关与 docs/01 第十部分一致（基础版全关；标准/专业开）。"""
    basic = tier_of("basic")
    assert not basic.custom_model
    assert not basic.remote_database
    assert not basic.data_dashboard
    assert not basic.channel_access
    assert not basic.team_space
    assert not basic.open_api_advanced

    standard = tier_of("standard")
    assert standard.custom_model
    assert standard.remote_database
    assert standard.data_dashboard
    assert standard.channel_access
    assert standard.client_management
    assert standard.rate_limit_config
    assert standard.human_transfer
    assert standard.aggregated_chat
    assert standard.team_space
    assert standard.open_api_advanced

    enterprise = tier_of("enterprise")
    assert enterprise.team_member_limit is None  # 按需定制人数


def test_plan_badges() -> None:
    assert tier_of("basic").badge == "基础版"
    assert tier_of("standard").badge == "标准版"
    assert tier_of("pro").badge == "专业版"
    assert tier_of("enterprise").badge == "企业版"


def test_assert_quota_allows_within_limit() -> None:
    assert_quota("basic", Dimension.APPS, used=2, increment=1)  # 2+1 <= 3 通过
    assert_quota("enterprise", Dimension.APPS, used=10_000, increment=1)  # 不限


def test_assert_quota_exceeded_error_contract() -> None:
    """超限 → QUOTA_EXCEEDED（403）+ details 契约字段。"""
    with pytest.raises(QuotaExceeded) as exc_info:
        assert_quota("basic", Dimension.APPS, used=3, increment=1)
    exc = exc_info.value
    assert exc.code == "QUOTA_EXCEEDED"
    assert exc.http_status == 403
    assert exc.details == {
        "dimension": "apps",
        "limit": 3,
        "used": 3,
        "increment": 1,
        "plan": "basic",
    }


def test_assert_feature_error_contract() -> None:
    with pytest.raises(FeatureNotAvailable) as exc_info:
        assert_feature("basic", Feature.DATA_DASHBOARD)
    exc = exc_info.value
    assert exc.code == "FEATURE_NOT_AVAILABLE"
    assert exc.http_status == 403
    assert exc.details == {"feature": "data_dashboard", "plan": "basic"}
    assert_feature("standard", Feature.DATA_DASHBOARD)  # 标准版开放


def test_usage_limit_of_none_means_unlimited() -> None:
    assert usage_limit_of("enterprise", Dimension.WORKFLOWS) is None
    assert usage_limit_of("pro", Dimension.WORKFLOWS) == 15


def test_unknown_plan_rejected() -> None:
    with pytest.raises(ValueError, match="未知版本"):
        tier_of("platinum")


def test_all_plan_enum_values_covered() -> None:
    for plan in Plan:
        assert tier_of(plan) is not None

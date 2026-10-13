"""配额矩阵与事件单测。"""

from __future__ import annotations

import pytest

from linkai_platform.domain import quota as quota_domain
from linkai_platform.domain.apps import AppLimitExceeded
from linkai_platform.domain.events import AppPublished, AppUnpublished
from linkai_platform.domain.users import Plan


@pytest.mark.parametrize(
    ("plan", "limit"),
    [
        (Plan.BASIC, 3),
        (Plan.STANDARD, 10),
        (Plan.PRO, 30),
        (Plan.ENTERPRISE, None),
    ],
)
def test_app_limits_matrix(plan: Plan, limit: int | None) -> None:
    """docs/01 第十部分四档应用数矩阵。"""
    assert quota_domain.APP_LIMITS[plan] == limit


def test_basic_plan_limit_enforced() -> None:
    quota_domain.assert_app_limit(Plan.BASIC, 2)  # 未满
    with pytest.raises(AppLimitExceeded):
        quota_domain.assert_app_limit(Plan.BASIC, 3)  # 已满


def test_enterprise_unlimited() -> None:
    quota_domain.assert_app_limit(Plan.ENTERPRISE, 10_000)


def test_plan_badges() -> None:
    assert quota_domain.plan_badge(Plan.BASIC) == "基础版"
    assert quota_domain.plan_badge(Plan.PRO) == "专业版"


def test_app_published_event_shape() -> None:
    event = AppPublished(app_id="a1", tenant_id="t1", version=3)
    assert event.event_type == "AppPublished"
    assert event.payload == {"app_id": "a1", "tenant_id": "t1", "version": 3}


def test_app_unpublished_event_shape() -> None:
    event = AppUnpublished(app_id="a1", tenant_id="t1", version=3)
    assert event.event_type == "AppUnpublished"
    assert event.payload["app_id"] == "a1"

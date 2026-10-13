"""应用实体领域规则单测。"""

from __future__ import annotations

import pytest

from linkai_platform.domain.apps import (
    App,
    AppConfig,
    BasicConfig,
    InvalidAppName,
    InvalidAppType,
    ModelPromptConfig,
    validate_app_name,
)


def test_create_app_defaults() -> None:
    app = App.create(tenant_id="t1", name="客服助手", type="lightweight")
    assert app.tenant_id == "t1"
    assert app.published is False
    assert app.current_version == 0
    assert app.current_config == AppConfig.empty()


@pytest.mark.parametrize("bad", ["", "x" * 65])
def test_create_app_name_bounds(bad: str) -> None:
    with pytest.raises(InvalidAppName):
        App.create(tenant_id="t1", name=bad, type="lightweight")


def test_create_app_type_must_be_valid() -> None:
    with pytest.raises(InvalidAppType):
        App.create(tenant_id="t1", name="x", type="all")
    with pytest.raises(InvalidAppType):
        App.create(tenant_id="t1", name="x", type="workflow")


def test_update_basic_partial() -> None:
    app = App.create(tenant_id="t1", name="旧名", type="lightweight")
    app.update_basic(description="新简介")
    assert app.name == "旧名"  # 未传字段不修改
    assert app.description == "新简介"


def test_replace_config_bumps_version() -> None:
    app = App.create(tenant_id="t1", name="x", type="lightweight")
    v1 = app.replace_config(AppConfig(basic=BasicConfig(welcomeMessage="你好")))
    v2 = app.replace_config(AppConfig(basic=BasicConfig(welcomeMessage="欢迎")))
    assert (v1, v2) == (1, 2)
    assert app.current_config.basic.welcomeMessage == "欢迎"


def test_full_replace_clears_unspecified_segments() -> None:
    """PUT 全量替换：第二次只给 basic，modelPrompt 应被清空。"""
    app = App.create(tenant_id="t1", name="x", type="lightweight")
    app.replace_config(AppConfig(modelPrompt=ModelPromptConfig(modelCode="gpt-4o")))
    assert app.current_config.modelPrompt is not None
    app.replace_config(AppConfig(basic=BasicConfig(welcomeMessage="hi")))
    assert app.current_config.modelPrompt is None  # 未提供段落视为清空


def test_snapshot_and_rollback_are_append_only() -> None:
    app = App.create(tenant_id="t1", name="x", type="lightweight")
    app.replace_config(AppConfig(basic=BasicConfig(welcomeMessage="v1")))
    snapshot_version = app.snapshot()
    assert snapshot_version == 2
    app.replace_config(AppConfig(basic=BasicConfig(welcomeMessage="v2")))
    rollback_version = app.rollback_to(AppConfig(basic=BasicConfig(welcomeMessage="v1")))
    assert rollback_version == 4  # 3 次 replace/snapshot + 1 次 rollback，单调递增
    assert app.current_config.basic.welcomeMessage == "v1"
    assert app.current_version == 4


def test_publish_unpublish() -> None:
    app = App.create(tenant_id="t1", name="x", type="lightweight")
    app.publish()
    assert app.published is True
    app.publish()  # 幂等
    assert app.published is True
    app.unpublish()
    assert app.published is False


def test_validate_app_name() -> None:
    validate_app_name("ok")
    with pytest.raises(InvalidAppName):
        validate_app_name("")

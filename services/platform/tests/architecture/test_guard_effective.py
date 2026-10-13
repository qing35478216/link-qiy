"""变异测试：验证架构守卫真的会失败（守卫能通过 ≠ 守卫有效）。

做法：把各层源码复制到临时目录，对副本注入违规 import，再让守卫去扫副本。
好处是**不碰真实工作区**——早先直接在源文件上注入时，进程被 SIGTERM 打断，
违规 import 残留在工作区里，必须手工还原才安全。
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tests.architecture import test_layering as guard


def _sandbox(tmp_path: Path) -> Path:
    """把 src/linkai_platform 整棵树复制到 tmp，供守卫扫描副本。

    注意 dirs_exist_ok=True：沙箱里 tmp_path 可能与源路径共享 inode 表现，
    不加这个参数 copytree 会因目标已存在同名目录而抛 FileExistsError。
    """
    dst = tmp_path / "linkai_platform"
    shutil.copytree(guard.SRC, dst, dirs_exist_ok=True)
    return dst


@pytest.mark.parametrize(
    ("layer", "inject", "expect_test"),
    [
        ("domain", "\nimport fastapi  # noqa\n", "test_domain_has_no_framework_import"),
        (
            "services",
            "\nfrom linkai_platform.api.errors import TenantMismatch  # noqa\n",
            "test_services_does_not_import_api",
        ),
    ],
)
def test_guard_fails_on_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, layer: str, inject: str, expect_test: str
) -> None:
    """注入违规后，对应守卫必须报错——否则守卫是摆设。"""
    sandbox = _sandbox(tmp_path)
    # 取该层第一个真实存在的文件，不写死文件名（各层文件名并不一致，
    # 早先写死 "users.py" 导致 services 层直接 FileNotFoundError）
    candidates = sorted((sandbox / layer).glob("*.py"))
    assert candidates, f"{layer} 层在沙箱里没有可注入的源文件"
    target = candidates[0]
    target.write_text(target.read_text(encoding="utf-8") + inject, encoding="utf-8")

    monkeypatch.setattr(guard, "SRC", sandbox)
    func = getattr(guard, expect_test)
    with pytest.raises(AssertionError):
        func(target)

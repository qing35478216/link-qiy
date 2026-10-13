"""SmsProvider 的 Mock 实现（Phase 0；真实短信厂商接入时新增对应 Provider）。

行为：验证码写入结构化日志（本地开发可见），不落真实短信通道。
"""

from __future__ import annotations

import structlog

from linkai_platform.domain.auth import SmsProvider

logger = structlog.get_logger(__name__)


class MockSmsProvider(SmsProvider):
    def send_code(self, phone: str, code: str, scene: str) -> None:
        # 脱敏：日志只打手机号后 4 位（docs/observability.md：禁止隐私原文）
        logger.info("mock_sms_sent", phone_tail=phone[-4:], scene=scene, code=code)

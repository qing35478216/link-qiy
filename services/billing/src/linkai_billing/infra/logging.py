"""结构化日志初始化（docs/observability.md：JSON + trace_id/span_id 贯通）。

与 platform 同构（同仓同规范）；单独复制而非抽包——Phase 0 各服务
自包含优先，observability 统一 bootstrap 属 Phase 1 工程化项。
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Mapping, MutableMapping
from typing import Any

import structlog
from opentelemetry import trace


def _add_trace_ids(
    logger: logging.Logger, method_name: str, event_dict: MutableMapping[str, Any]
) -> Mapping[str, Any]:
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx is not None and ctx.is_valid:
        event_dict["trace_id"] = f"{ctx.trace_id:032x}"
        event_dict["span_id"] = f"{ctx.span_id:016x}"
    return event_dict


def setup_logging(service_name: str, level: str = "info") -> None:
    """生产/CI 输出 JSON；LOG_FORMAT=text 时输出可读格式（本地开发）。"""
    log_level = getattr(logging, level.upper(), logging.INFO)
    json_format = os.getenv("LOG_FORMAT", "json") != "text"
    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if json_format
        else structlog.dev.ConsoleRenderer(colors=True)
    )
    logging.basicConfig(stream=sys.stdout, level=log_level, format="%(message)s")
    structlog.contextvars.bind_contextvars(service=service_name)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _add_trace_ids,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

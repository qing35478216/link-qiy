"""MeteringEventIn 消费侧 DTO 单测（跨服务边界只信标量）。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from linkai_billing.domain.metering import MeteringEventIn, MeteringOutcome


def test_payload_roundtrip_from_model_proxy_shape() -> None:
    """生产方 to_payload() 的形状可无损构造（跨服务友好）。"""
    payload = {
        "event_id": "evt-1",
        "tenant_id": "t-1",
        "app_code": "app-1",
        "conversation_id": "conv-1",
        "trace_id": "trace-1",
        "provider": "openai",
        "model_code": "gpt-4o-mini",
        "outcome": "success",
        "prompt_tokens": 120,
        "completion_tokens": 80,
        "total_tokens": 200,
        "credits": 100,
        "latency_ms": 850,
        "attempt": 1,
        "occurred_at": "2026-10-14T12:00:00+00:00",
        "error_code": None,
        "fallback_from": None,
    }
    event = MeteringEventIn.from_payload(payload)
    assert event.event_id == "evt-1"
    assert event.request_id == "evt-1"  # 幂等键 = event_id
    assert event.credits == 100
    assert event.occurred_at == datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
    assert event.is_billable


def test_failed_outcome_not_billable() -> None:
    event = MeteringEventIn(
        event_id="evt-2",
        tenant_id="t-1",
        credits=0,
        outcome=MeteringOutcome.FAILED,
        provider="openai",
        model_code="gpt-4o-mini",
    )
    assert not event.is_billable


def test_fallback_succeeded_is_billable() -> None:
    event = MeteringEventIn(
        event_id="evt-3",
        tenant_id="t-1",
        credits=50,
        outcome=MeteringOutcome.FALLBACK_SUCCEEDED,
        provider="deepseek",
        model_code="deepseek-chat",
        fallback_from="gpt-4o",
    )
    assert event.is_billable


def test_missing_required_fields_rejected() -> None:
    with pytest.raises(ValueError, match="tenant_id"):
        MeteringEventIn.from_payload(
            {
                "event_id": "e",
                "credits": 1,
                "outcome": "success",
                "provider": "p",
                "model_code": "m",
            }
        )
    with pytest.raises(ValueError, match="event_id"):
        MeteringEventIn.from_payload(
            {
                "tenant_id": "t",
                "credits": 1,
                "outcome": "success",
                "provider": "p",
                "model_code": "m",
            }
        )


def test_non_integer_credits_rejected() -> None:
    with pytest.raises(ValueError, match="credits"):
        MeteringEventIn.from_payload(
            {
                "event_id": "e",
                "tenant_id": "t",
                "credits": "abc",
                "outcome": "success",
                "provider": "p",
                "model_code": "m",
            }
        )


def test_string_integers_accepted_for_redis_stream_transport() -> None:
    """Redis Stream 全字符串传输：数值以十进制字符串承载，必须兼容。"""
    event = MeteringEventIn.from_payload(
        {
            "event_id": "e",
            "tenant_id": "t",
            "credits": "100",
            "outcome": "success",
            "provider": "p",
            "model_code": "m",
            "prompt_tokens": "120",
            "attempt": "2",
        }
    )
    assert event.credits == 100
    assert event.prompt_tokens == 120
    assert event.attempt == 2


def test_negative_credits_rejected() -> None:
    with pytest.raises(ValueError, match="credits"):
        MeteringEventIn.from_payload(
            {
                "event_id": "e",
                "tenant_id": "t",
                "credits": -5,
                "outcome": "success",
                "provider": "p",
                "model_code": "m",
            }
        )


def test_naive_occurred_at_normalized_to_utc() -> None:
    event = MeteringEventIn.from_payload(
        {
            "event_id": "e",
            "tenant_id": "t",
            "credits": 1,
            "outcome": "success",
            "provider": "p",
            "model_code": "m",
            "occurred_at": "2026-10-14T12:00:00",
        }
    )
    assert event.occurred_at is not None
    assert event.occurred_at.tzinfo is UTC

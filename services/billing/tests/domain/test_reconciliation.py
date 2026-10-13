"""对账纯函数单测（差异分类 / 告警阈值 / blocked 口径）。"""

from __future__ import annotations

from linkai_billing.domain.reconciliation import (
    RECONCILIATION_ALERT_RATIO,
    DbRecord,
    StreamRecord,
    reconcile,
)


def test_perfect_match_no_alert() -> None:
    report = reconcile(
        stream=[
            StreamRecord(request_id="t-1:e1", credits=100),
            StreamRecord(request_id="t-1:e2", credits=50),
        ],
        db=[
            DbRecord(request_id="t-1:e1", credits=100, applied=True),
            DbRecord(request_id="t-1:e2", credits=50, applied=True),
        ],
    )
    assert report.matched == 2
    assert report.diff_count == 0
    assert not report.alert
    assert report.summary_line().startswith("stream=2 db=2 matched=2")


def test_missing_in_db_detected_and_alerts() -> None:
    """流水有 DB 无——危险信号；差异率超 0.01% 告警。"""
    stream = [StreamRecord(request_id=f"t-1:e{i}", credits=10) for i in range(10)]
    db = [DbRecord(request_id=f"t-1:e{i}", credits=10, applied=True) for i in range(9)]
    report = reconcile(stream=stream, db=db)
    assert report.missing_in_db == ("t-1:e9",)
    assert report.alert
    assert report.diff_ratio == 0.1


def test_missing_in_stream_detected() -> None:
    report = reconcile(
        stream=[StreamRecord(request_id="t-1:e1", credits=10)],
        db=[
            DbRecord(request_id="t-1:e1", credits=10, applied=True),
            DbRecord(request_id="t-1:e2", credits=10, applied=True),
        ],
    )
    assert report.missing_in_stream == ("t-1:e2",)


def test_amount_mismatch_highest_priority() -> None:
    report = reconcile(
        stream=[StreamRecord(request_id="t-1:e1", credits=100)],
        db=[DbRecord(request_id="t-1:e1", credits=90, applied=True)],
    )
    assert report.amount_mismatch == (("t-1:e1", 100, 90),)
    assert report.matched == 0
    assert report.alert


def test_blocked_entries_not_amount_compared() -> None:
    """blocked（余额不足留痕）：DB 侧存在即对齐，金额不比对。"""
    report = reconcile(
        stream=[StreamRecord(request_id="t-1:e1", credits=100)],
        db=[DbRecord(request_id="t-1:e1", credits=100, applied=False)],
    )
    assert report.matched == 1
    assert report.blocked_count == 1
    assert report.diff_count == 0


def test_duplicate_entries_deduped() -> None:
    """双侧各自去重（MQ 重投/重复回调痕迹不误报）。"""
    report = reconcile(
        stream=[
            StreamRecord(request_id="t-1:e1", credits=10),
            StreamRecord(request_id="t-1:e1", credits=10),
        ],
        db=[DbRecord(request_id="t-1:e1", credits=10, applied=True)],
    )
    assert report.stream_count == 1
    assert report.db_count == 1
    assert report.diff_count == 0


def test_small_diff_below_threshold_not_alerted() -> None:
    """差异率 <= 0.01% 不告警（1/20000 = 0.005%）。"""
    stream = [StreamRecord(request_id=f"t-1:e{i}", credits=1) for i in range(20_000)]
    db = [DbRecord(request_id=f"t-1:e{i}", credits=1, applied=True) for i in range(19_999)]
    report = reconcile(stream=stream, db=db)
    assert report.diff_count == 1
    assert report.diff_ratio <= RECONCILIATION_ALERT_RATIO
    assert not report.alert


def test_empty_both_sides_ok() -> None:
    report = reconcile(stream=[], db=[])
    assert report.diff_count == 0
    assert not report.alert

from datetime import datetime, timedelta, timezone

from app.wire_feed.pipeline import WirePipelineResult
from app.wire_feed.policy import WireFeedSettings, WirePostRecord, plan_wire_queue


def _candidate(
    title: str,
    score: int,
    event_type: str = "earnings",
    ticker: str | None = "ABC",
    subject_key: str | None = None,
) -> WirePipelineResult:
    return WirePipelineResult(
        external_id=f"{ticker or 'market'}-{title}",
        source_name="tradient_market_news",
        title=title,
        event_type=event_type,
        dedupe_key=f"{event_type}|{(ticker or 'market').lower()}|{(subject_key or title).lower()}",
        subject_key=subject_key,
        ticker=ticker,
        importance_score=score,
        confidence_score=0.95,
        would_auto_post=True,
        review_reason=None,
        draft_text=title,
        safety_flags={},
        published_at=datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc),
    )


def test_plan_wire_queue_spaces_candidates_by_priority() -> None:
    now = datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc)
    candidates = [
        _candidate("Breaking penalty", 100, event_type="default_fraud", ticker="AAA"),
        _candidate("High score turnover", 88, event_type="earnings", ticker="BBB"),
        _candidate("Normal order", 70, event_type="order_win", ticker="CCC"),
    ]

    decisions = plan_wire_queue(candidates, now=now)

    assert decisions[0].action == "post_now"
    assert decisions[0].scheduled_for == now
    assert decisions[1].action == "queue"
    assert decisions[1].scheduled_for == now + timedelta(minutes=8)
    assert decisions[2].scheduled_for == now + timedelta(minutes=20)


def test_plan_wire_queue_skips_recent_duplicate() -> None:
    now = datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc)
    candidate = _candidate("Hyundai sales", 90, ticker="HYUNDAI", subject_key="sales")
    recent = [WirePostRecord(dedupe_key="earnings|hyundai|sales", posted_at=now - timedelta(minutes=30))]

    decisions = plan_wire_queue([candidate], recent_posts=recent, now=now)

    assert decisions[0].action == "skip"
    assert decisions[0].reason == "duplicate_cooldown"


def test_plan_wire_queue_respects_hourly_limit() -> None:
    now = datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc)
    recent = [
        WirePostRecord(dedupe_key=f"earnings|t{i}|k", posted_at=now - timedelta(minutes=5 * i))
        for i in range(6)
    ]
    candidate = _candidate("Another update", 90, ticker="NEWS")

    decisions = plan_wire_queue([candidate], recent_posts=recent, now=now, settings=WireFeedSettings(max_posts_per_hour=6))

    assert decisions[0].action == "skip"
    assert decisions[0].reason == "hourly_limit"


def test_plan_wire_queue_moves_item_to_next_window_when_outside_ist_window() -> None:
    now = datetime(2026, 4, 1, 20, 30, tzinfo=timezone.utc)  # 02:00 IST on Apr 2
    candidate = _candidate("Overnight update", 95, event_type="default_fraud", ticker="NEWS")

    decisions = plan_wire_queue([candidate], now=now)

    assert decisions[0].action == "queue"
    assert decisions[0].scheduled_for == datetime(2026, 4, 2, 2, 30, tzinfo=timezone.utc)  # 08:00 IST


def test_plan_wire_queue_posts_now_inside_ist_window() -> None:
    now = datetime(2026, 4, 1, 5, 0, tzinfo=timezone.utc)  # 10:30 IST
    candidate = _candidate("In-window update", 95, event_type="default_fraud", ticker="NEWS")

    decisions = plan_wire_queue([candidate], now=now)

    assert decisions[0].action == "post_now"
    assert decisions[0].scheduled_for == now

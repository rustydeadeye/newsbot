from datetime import datetime, timedelta, timezone

from app.wire_feed.pipeline import WirePipelineResult
from app.wire_feed.policy import WireFeedSettings, WirePostRecord, plan_wire_queue


def _candidate(
    title: str,
    score: int,
    event_type: str = "earnings",
    ticker: str | None = "ABC",
    subject_key: str | None = None,
    source_family: str = "base",
) -> WirePipelineResult:
    return WirePipelineResult(
        external_id=f"{ticker or 'market'}-{title}",
        source_name="tradient_market_news",
        source_family=source_family,
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
        raw_payload={"source_family": source_family},
        published_at=datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc),
    )


def test_plan_wire_queue_spaces_candidates_by_priority() -> None:
    now = datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc)
    candidates = [
        _candidate("Breaking penalty", 100, event_type="default_fraud", ticker="AAA"),
        _candidate("High score turnover", 88, event_type="earnings", ticker="BBB"),
        _candidate("Normal order", 70, event_type="order_win", ticker="CCC"),
    ]

    decisions = plan_wire_queue(candidates, now=now, settings=WireFeedSettings(max_posts_per_hour=10))

    assert decisions[0].action == "post_now"
    assert decisions[0].scheduled_for == now
    assert decisions[1].action == "queue"
    assert decisions[1].scheduled_for == now + timedelta(minutes=45)
    assert decisions[2].scheduled_for == now + timedelta(minutes=105)


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
        for i in range(2)
    ]
    candidate = _candidate("Another update", 90, ticker="NEWS")

    decisions = plan_wire_queue([candidate], recent_posts=recent, now=now, settings=WireFeedSettings(max_posts_per_hour=2))

    assert decisions[0].action == "skip"
    assert decisions[0].reason == "hourly_limit"


def test_plan_wire_queue_delays_non_breaking_items_during_quiet_hours() -> None:
    now = datetime(2026, 4, 1, 20, 30, tzinfo=timezone.utc)  # 02:00 IST on Apr 2
    candidate = _candidate("Overnight update", 90, event_type="earnings", ticker="NEWS")
    candidate = candidate.__class__(**{**candidate.__dict__, "published_at": now - timedelta(hours=1)})

    decisions = plan_wire_queue([candidate], now=now)

    assert decisions[0].action == "queue"
    assert decisions[0].scheduled_for == datetime(2026, 4, 2, 1, 30, tzinfo=timezone.utc)  # 07:00 IST


def test_plan_wire_queue_allows_web_items_during_quiet_hours() -> None:
    now = datetime(2026, 4, 1, 20, 30, tzinfo=timezone.utc)  # 02:00 IST on Apr 2
    candidate = _candidate("Overnight web update", 90, event_type="macro_release", ticker=None, source_family="web")
    candidate = candidate.__class__(**{**candidate.__dict__, "published_at": now - timedelta(hours=1)})

    decisions = plan_wire_queue([candidate], now=now)

    assert decisions[0].action == "post_now"
    assert decisions[0].scheduled_for == now


def test_plan_wire_queue_allows_breaking_items_during_quiet_hours() -> None:
    now = datetime(2026, 4, 1, 20, 30, tzinfo=timezone.utc)  # 02:00 IST on Apr 2
    candidate = _candidate("Overnight breaking", 95, event_type="default_fraud", ticker="NEWS")

    decisions = plan_wire_queue([candidate], now=now)

    assert decisions[0].action == "post_now"
    assert decisions[0].scheduled_for == now


def test_plan_wire_queue_skips_stale_normal_candidate() -> None:
    now = datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc)
    candidate = _candidate("Old normal item", 75, event_type="order_win", ticker="OLD")
    stale_candidate = candidate.__class__(**{**candidate.__dict__, "published_at": now - timedelta(hours=5)})

    decisions = plan_wire_queue([stale_candidate], now=now)

    assert decisions[0].action == "skip"
    assert decisions[0].reason == "stale_candidate"


def test_plan_wire_queue_skips_stale_high_candidate() -> None:
    now = datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc)
    candidate = _candidate("Old high item", 90, event_type="earnings", ticker="HIGH")
    stale_candidate = candidate.__class__(**{**candidate.__dict__, "published_at": now - timedelta(hours=7)})

    decisions = plan_wire_queue([stale_candidate], now=now)

    assert decisions[0].action == "skip"
    assert decisions[0].reason == "stale_candidate"


def test_plan_wire_queue_posts_now_outside_quiet_hours() -> None:
    now = datetime(2026, 4, 1, 5, 0, tzinfo=timezone.utc)  # 10:30 IST
    candidate = _candidate("In-window update", 95, event_type="default_fraud", ticker="NEWS")

    decisions = plan_wire_queue([candidate], now=now)

    assert decisions[0].action == "post_now"
    assert decisions[0].scheduled_for == now


def test_plan_wire_queue_prioritizes_web_candidates_when_scores_are_close() -> None:
    now = datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc)
    candidates = [
        _candidate("Base candidate", 88, ticker="BASE", source_family="base"),
        _candidate("Web candidate", 86, ticker="WEB", source_family="web"),
    ]

    decisions = plan_wire_queue(candidates, now=now, settings=WireFeedSettings(max_posts_per_hour=10))

    assert decisions[0].result.title == "Web candidate"
    assert decisions[0].action == "post_now"


def test_plan_wire_queue_respects_per_family_daily_caps() -> None:
    now = datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc)
    recent = [
        WirePostRecord(
            dedupe_key=f"macro|web{i}",
            posted_at=now - timedelta(hours=i + 2),
            source_family="web",
            source_name="tavily_web_india_close",
        )
        for i in range(10)
    ]

    candidate = _candidate("One more web", 90, ticker="WEB", source_family="web")
    decisions = plan_wire_queue([candidate], recent_posts=recent, now=now)

    assert decisions[0].action == "skip"
    assert decisions[0].reason == "web_daily_limit"

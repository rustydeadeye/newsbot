from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.wire_feed.pipeline import WirePipelineResult


@dataclass(frozen=True)
class WireFeedSettings:
    max_posts_per_hour: int = 6
    max_posts_per_day: int = 30
    breaking_gap_minutes: int = 3
    high_gap_minutes: int = 8
    normal_gap_minutes: int = 12
    duplicate_cooldown_minutes: int = 180
    timezone: str = "Asia/Kolkata"
    posting_window_start_hour: int = 8
    posting_window_end_hour: int = 20


@dataclass(frozen=True)
class WirePostRecord:
    dedupe_key: str
    posted_at: datetime


@dataclass(frozen=True)
class WireQueueDecision:
    result: WirePipelineResult
    action: str
    priority: str
    scheduled_for: datetime | None = None
    reason: str | None = None


def plan_wire_queue(
    candidates: list[WirePipelineResult],
    recent_posts: list[WirePostRecord] | None = None,
    now: datetime | None = None,
    settings: WireFeedSettings | None = None,
) -> list[WireQueueDecision]:
    settings = settings or WireFeedSettings()
    now = now or datetime.now(timezone.utc)
    recent_posts = list(recent_posts or [])

    ordered = sorted(candidates, key=lambda item: (item.importance_score, item.published_at or now), reverse=True)
    decisions: list[WireQueueDecision] = []
    planned_posts: list[WirePostRecord] = list(recent_posts)
    last_scheduled = max((record.posted_at for record in planned_posts), default=None)

    for candidate in ordered:
        dedupe_key = _wire_dedupe_key(candidate)
        priority = _priority_bucket(candidate)

        if _is_duplicate_recent(dedupe_key, planned_posts, now, settings):
            decisions.append(WireQueueDecision(result=candidate, action="skip", priority=priority, reason="duplicate_cooldown"))
            continue

        if _count_since(planned_posts, now - timedelta(hours=1)) >= settings.max_posts_per_hour:
            decisions.append(WireQueueDecision(result=candidate, action="skip", priority=priority, reason="hourly_limit"))
            continue

        if _count_since(planned_posts, now - timedelta(days=1)) >= settings.max_posts_per_day:
            decisions.append(WireQueueDecision(result=candidate, action="skip", priority=priority, reason="daily_limit"))
            continue

        gap_minutes = _gap_minutes(priority, settings)
        earliest = now if last_scheduled is None else max(now, last_scheduled + timedelta(minutes=gap_minutes))
        if not _in_posting_window(earliest, settings):
            earliest = _next_window_open(earliest, settings)
        action = "post_now" if earliest <= now else "queue"
        decisions.append(WireQueueDecision(result=candidate, action=action, priority=priority, scheduled_for=earliest))
        planned_posts.append(WirePostRecord(dedupe_key=dedupe_key, posted_at=earliest))
        last_scheduled = earliest

    return decisions


def _priority_bucket(candidate: WirePipelineResult) -> str:
    if candidate.event_type in {"rbi_policy", "rbi_penalty", "sebi_circular", "sebi_enforcement", "default_fraud"}:
        return "breaking"
    if candidate.importance_score >= 85:
        return "high"
    return "normal"


def _gap_minutes(priority: str, settings: WireFeedSettings) -> int:
    if priority == "breaking":
        return settings.breaking_gap_minutes
    if priority == "high":
        return settings.high_gap_minutes
    return settings.normal_gap_minutes


def _is_duplicate_recent(
    dedupe_key: str,
    records: list[WirePostRecord],
    now: datetime,
    settings: WireFeedSettings,
) -> bool:
    cutoff = now - timedelta(minutes=settings.duplicate_cooldown_minutes)
    return any(record.dedupe_key == dedupe_key and record.posted_at >= cutoff for record in records)


def _count_since(records: list[WirePostRecord], cutoff: datetime) -> int:
    return sum(1 for record in records if record.posted_at >= cutoff)


def _wire_dedupe_key(candidate: WirePipelineResult) -> str:
    ticker = (candidate.ticker or "market").lower()
    subject = (candidate.subject_key or candidate.title).lower()
    return f"{candidate.event_type}|{ticker}|{subject}"


def _in_posting_window(current: datetime, settings: WireFeedSettings) -> bool:
    tz = ZoneInfo(settings.timezone)
    local_hour = current.astimezone(tz).hour
    start = settings.posting_window_start_hour
    end = settings.posting_window_end_hour
    if start == end:
        return True
    if start < end:
        return start <= local_hour < end
    return local_hour >= start or local_hour < end


def _next_window_open(current: datetime, settings: WireFeedSettings) -> datetime:
    tz = ZoneInfo(settings.timezone)
    local_current = current.astimezone(tz)
    next_open = local_current.replace(
        hour=settings.posting_window_start_hour,
        minute=0,
        second=0,
        microsecond=0,
    )
    if next_open <= local_current:
        next_open = next_open + timedelta(days=1)
    return next_open.astimezone(timezone.utc)

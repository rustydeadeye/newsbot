from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.wire_feed.pipeline import WirePipelineResult


@dataclass(frozen=True)
class WireFeedSettings:
    product: str = "finance"
    shadow_mode: bool = False
    max_posts_per_hour: int = 2
    max_posts_per_day: int = 15
    base_max_posts_per_day: int = 5
    web_max_posts_per_day: int = 10
    breaking_gap_minutes: int = 10
    high_gap_minutes: int = 45
    normal_gap_minutes: int = 60
    duplicate_cooldown_minutes: int = 180
    high_ttl_hours: int = 6
    normal_ttl_hours: int = 4
    timezone: str = "Asia/Kolkata"
    quiet_hours_start_hour: int = 23
    quiet_hours_end_hour: int = 7


@dataclass(frozen=True)
class WirePostRecord:
    dedupe_key: str
    posted_at: datetime
    priority: str = "normal"
    status: str = "posted"
    job_id: int | None = None
    source_family: str = "base"
    source_name: str | None = None


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

    ordered = sorted(candidates, key=lambda item: _candidate_order_key(item, now), reverse=True)
    decisions: list[WireQueueDecision] = []
    planned_posts: list[WirePostRecord] = list(recent_posts)
    last_scheduled = max((record.posted_at for record in planned_posts), default=None)

    for candidate in ordered:
        if settings.shadow_mode and candidate.product == "ai":
            band = str((candidate.raw_payload or {}).get("quality_band") or "C").upper()
            decisions.append(
                WireQueueDecision(
                    result=candidate,
                    action="skip",
                    priority=_priority_bucket(candidate),
                    reason=f"shadow_mode_{band.lower()}",
                )
            )
            continue

        if candidate.fetch_error:
            decisions.append(
                WireQueueDecision(
                    result=candidate,
                    action="skip",
                    priority="normal",
                    reason="fetch_error",
                )
            )
            continue

        if not candidate.draft_text.strip():
            decisions.append(
                WireQueueDecision(
                    result=candidate,
                    action="skip",
                    priority="normal",
                    reason="empty_draft",
                )
            )
            continue

        dedupe_key = _wire_dedupe_key(candidate)
        priority = _priority_bucket(candidate)

        if _is_stale(candidate, priority, now, settings):
            decisions.append(WireQueueDecision(result=candidate, action="skip", priority=priority, reason="stale_candidate"))
            continue

        if _is_duplicate_recent(dedupe_key, planned_posts, now, settings):
            decisions.append(WireQueueDecision(result=candidate, action="skip", priority=priority, reason="duplicate_cooldown"))
            continue

        if _count_since(planned_posts, now - timedelta(hours=1)) >= settings.max_posts_per_hour:
            decisions.append(WireQueueDecision(result=candidate, action="skip", priority=priority, reason="hourly_limit"))
            continue

        if _count_since(planned_posts, now - timedelta(days=1)) >= settings.max_posts_per_day:
            decisions.append(WireQueueDecision(result=candidate, action="skip", priority=priority, reason="daily_limit"))
            continue

        if _count_since_family(planned_posts, candidate.source_family, now - timedelta(days=1)) >= _family_daily_limit(candidate.source_family, settings):
            decisions.append(
                WireQueueDecision(
                    result=candidate,
                    action="skip",
                    priority=priority,
                    reason=f"{candidate.source_family}_daily_limit",
                )
            )
            continue

        gap_minutes = _gap_minutes(priority, settings)
        if priority == "breaking":
            last_breaking = max((record.posted_at for record in planned_posts if record.priority == "breaking"), default=None)
            earliest = now if last_breaking is None else max(now, last_breaking + timedelta(minutes=gap_minutes))
        else:
            earliest = now if last_scheduled is None else max(now, last_scheduled + timedelta(minutes=gap_minutes))
        if _uses_quiet_hours(candidate, priority) and _in_quiet_hours(earliest, settings):
            earliest = _next_quiet_end(earliest, settings)
        action = "post_now" if earliest <= now else "queue"
        decisions.append(WireQueueDecision(result=candidate, action=action, priority=priority, scheduled_for=earliest))
        planned_posts.append(
            WirePostRecord(
                dedupe_key=dedupe_key,
                posted_at=earliest,
                priority=priority,
                status="queued",
                source_family=candidate.source_family,
                source_name=candidate.source_name,
            )
        )
        last_scheduled = earliest

    return decisions


def _priority_bucket(candidate: WirePipelineResult) -> str:
    if candidate.product == "ai":
        if candidate.event_type in {"policy_regulation", "security_incident"}:
            return "breaking"
        if candidate.event_type in {"model_launch", "api_update"} or candidate.importance_score >= 88:
            return "high"
        return "normal"
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


def _candidate_order_key(candidate: WirePipelineResult, now: datetime) -> tuple[int, int, datetime]:
    return (
        candidate.importance_score + _family_priority_bonus(candidate.source_family),
        _family_priority_bonus(candidate.source_family),
        candidate.published_at or now,
    )


def _family_priority_bonus(source_family: str) -> int:
    if source_family == "web":
        return 8
    return 0


def _uses_quiet_hours(candidate: WirePipelineResult, priority: str) -> bool:
    if candidate.source_family == "web":
        return False
    return priority != "breaking"


def _is_stale(
    candidate: WirePipelineResult,
    priority: str,
    now: datetime,
    settings: WireFeedSettings,
) -> bool:
    if candidate.published_at is None or priority == "breaking":
        return False
    ttl_hours = settings.high_ttl_hours if priority == "high" else settings.normal_ttl_hours
    return candidate.published_at < now - timedelta(hours=ttl_hours)


def is_stale_published_at(
    published_at: datetime | None,
    priority: str,
    now: datetime,
    settings: WireFeedSettings,
) -> bool:
    if published_at is None or priority == "breaking":
        return False
    ttl_hours = settings.high_ttl_hours if priority == "high" else settings.normal_ttl_hours
    return published_at < now - timedelta(hours=ttl_hours)


def _is_duplicate_recent(
    dedupe_key: str,
    records: list[WirePostRecord],
    now: datetime,
    settings: WireFeedSettings,
) -> bool:
    cutoff = now - timedelta(minutes=settings.duplicate_cooldown_minutes)
    legacy_key = dedupe_key.removeprefix("finance|")
    return any(
        record.posted_at >= cutoff and record.dedupe_key in {dedupe_key, legacy_key}
        for record in records
    )


def _count_since(records: list[WirePostRecord], cutoff: datetime) -> int:
    return sum(1 for record in records if record.posted_at >= cutoff)


def _count_since_family(records: list[WirePostRecord], source_family: str, cutoff: datetime) -> int:
    return sum(1 for record in records if record.posted_at >= cutoff and record.source_family == source_family)


def _family_daily_limit(source_family: str, settings: WireFeedSettings) -> int:
    if source_family == "web":
        return settings.web_max_posts_per_day
    return settings.base_max_posts_per_day


def _wire_dedupe_key(candidate: WirePipelineResult) -> str:
    ticker = (candidate.ticker or "market").lower()
    subject = (candidate.subject_key or candidate.title).lower()
    return f"{candidate.product}|{candidate.event_type}|{ticker}|{subject}"


def _in_quiet_hours(current: datetime, settings: WireFeedSettings) -> bool:
    tz = ZoneInfo(settings.timezone)
    local_hour = current.astimezone(tz).hour
    start = settings.quiet_hours_start_hour
    end = settings.quiet_hours_end_hour
    if start == end:
        return False
    if start < end:
        return start <= local_hour < end
    return local_hour >= start or local_hour < end


def _next_quiet_end(current: datetime, settings: WireFeedSettings) -> datetime:
    tz = ZoneInfo(settings.timezone)
    local_current = current.astimezone(tz)
    next_open = local_current.replace(
        hour=settings.quiet_hours_end_hour,
        minute=0,
        second=0,
        microsecond=0,
    )
    if not _in_quiet_hours(current, settings) or next_open <= local_current:
        next_open = next_open + timedelta(days=1)
    return next_open.astimezone(timezone.utc)

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.wire_feed.pipeline import AI_LANE_MAX_AGE_HOURS, WirePipelineResult


@dataclass(frozen=True)
class WireFeedSettings:
    product: str = "finance"
    shadow_mode: bool = False
    target_posts_per_hour: int = 2
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

        earliest, defer_reason = _next_slot_for_candidate(
            candidate,
            priority=priority,
            planned_posts=planned_posts,
            now=now,
            last_scheduled=last_scheduled,
            settings=settings,
        )
        if earliest is None:
            decisions.append(WireQueueDecision(result=candidate, action="skip", priority=priority, reason="capacity_unavailable"))
            continue
        if _is_stale(candidate, priority, earliest, settings):
            decisions.append(
                WireQueueDecision(
                    result=candidate,
                    action="skip",
                    priority=priority,
                    reason="expired_before_next_slot" if defer_reason else "stale_candidate",
                )
            )
            continue
        action = "post_now" if earliest <= now and not defer_reason else ("defer" if defer_reason else "queue")
        decisions.append(
            WireQueueDecision(
                result=candidate,
                action=action,
                priority=priority,
                scheduled_for=earliest,
                reason=defer_reason,
            )
        )
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


def _next_slot_for_candidate(
    candidate: WirePipelineResult,
    *,
    priority: str,
    planned_posts: list[WirePostRecord],
    now: datetime,
    last_scheduled: datetime | None,
    settings: WireFeedSettings,
) -> tuple[datetime | None, str | None]:
    gap_minutes = _gap_minutes(priority, settings)
    if priority == "breaking":
        last_breaking = max((record.posted_at for record in planned_posts if record.priority == "breaking"), default=None)
        slot = now if last_breaking is None else max(now, last_breaking + timedelta(minutes=gap_minutes))
    else:
        slot = now if last_scheduled is None else max(now, last_scheduled + timedelta(minutes=gap_minutes))

    defer_reason: str | None = None
    for _ in range(48):
        if _uses_quiet_hours(candidate, priority) and _in_quiet_hours(slot, settings):
            slot = _next_quiet_end(slot, settings)

        hourly_count = _count_since(planned_posts, slot - timedelta(hours=1), as_of=slot)
        if hourly_count >= settings.max_posts_per_hour:
            slot = _next_hourly_capacity_time(planned_posts, slot, settings)
            defer_reason = defer_reason or "deferred_hourly_capacity"
            continue

        daily_count = _count_since(planned_posts, slot - timedelta(days=1), as_of=slot)
        if daily_count >= settings.max_posts_per_day:
            slot = _next_daily_capacity_time(planned_posts, slot, settings.max_posts_per_day)
            defer_reason = defer_reason or "deferred_daily_capacity"
            continue

        family_limit = _family_daily_limit(candidate.source_family, settings)
        family_count = _count_since_family(planned_posts, candidate.source_family, slot - timedelta(days=1), as_of=slot)
        if family_count >= family_limit:
            slot = _next_family_capacity_time(planned_posts, candidate.source_family, slot, family_limit)
            defer_reason = defer_reason or f"deferred_{candidate.source_family}_capacity"
            continue

        return slot, defer_reason

    return None, defer_reason


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
    return is_stale_candidate(candidate, priority, now, settings)


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


def is_stale_candidate(
    candidate: Any,
    priority: str,
    now: datetime,
    settings: WireFeedSettings,
) -> bool:
    published_at = getattr(candidate, "published_at", None)
    if published_at is None or priority == "breaking":
        return False
    raw_payload = dict(getattr(candidate, "raw_payload", {}) or {})
    if str(getattr(candidate, "product", raw_payload.get("product") or "")) == "ai":
        if bool(raw_payload.get("is_evergreen")):
            return False
        lane = str(raw_payload.get("lane") or "ai_news")
        ttl_hours = AI_LANE_MAX_AGE_HOURS.get(
            lane,
            settings.high_ttl_hours if priority == "high" else settings.normal_ttl_hours,
        )
        return published_at < now - timedelta(hours=ttl_hours)
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


def _count_since(records: list[WirePostRecord], cutoff: datetime, as_of: datetime | None = None) -> int:
    if as_of is None:
        return sum(1 for record in records if record.posted_at > cutoff)
    return sum(1 for record in records if cutoff < record.posted_at <= as_of)


def _count_since_family(
    records: list[WirePostRecord],
    source_family: str,
    cutoff: datetime,
    as_of: datetime | None = None,
) -> int:
    if as_of is None:
        return sum(1 for record in records if record.posted_at > cutoff and record.source_family == source_family)
    return sum(
        1
        for record in records
        if cutoff < record.posted_at <= as_of and record.source_family == source_family
    )


def _next_hourly_capacity_time(records: list[WirePostRecord], slot: datetime, settings: WireFeedSettings) -> datetime:
    window_records = [record for record in records if slot - timedelta(hours=1) < record.posted_at <= slot]
    if not window_records:
        return slot
    oldest = min(record.posted_at for record in window_records)
    return max(slot, oldest + timedelta(hours=1))


def _next_daily_capacity_time(records: list[WirePostRecord], slot: datetime, daily_limit: int) -> datetime:
    window_records = sorted((record.posted_at for record in records if slot - timedelta(days=1) < record.posted_at <= slot))
    if len(window_records) < daily_limit:
        return slot
    return max(slot, window_records[0] + timedelta(days=1))


def _next_family_capacity_time(records: list[WirePostRecord], source_family: str, slot: datetime, family_limit: int) -> datetime:
    window_records = sorted(
        record.posted_at
        for record in records
        if record.source_family == source_family and slot - timedelta(days=1) < record.posted_at <= slot
    )
    if len(window_records) < family_limit:
        return slot
    return max(slot, window_records[0] + timedelta(days=1))


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

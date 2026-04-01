from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer import CustomerProfile
from app.models.event import DraftPost, Event
from app.models.job import PublishJob
from app.models.review import ReviewQueueItem

ACTIVE_DRAFT_STATUSES = {"draft", "approved", "queued", "publishing"}
HISTORY_DRAFT_STATUSES = {"posted", "expired", "superseded", "rejected", "failed"}
AUTO_POST_ALLOWLIST = {"rbi_policy", "rbi_penalty", "sebi_circular", "sebi_enforcement", "macro_release"}


def event_reference_time(event: Event) -> datetime:
    dt = event.occurred_at or event.created_at or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def fresh_until_for_event(event: Event, freshness_window_hours: int) -> datetime:
    return event_reference_time(event) + timedelta(hours=freshness_window_hours)


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def story_family_key(event: Event) -> str:
    facts = event.summary_facts or {}
    subject_key = str(facts.get("subject_key") or "").strip().lower()
    if subject_key:
        return f"{event.event_type}:{subject_key}"
    entity = (event.ticker or event.entity_name or "market").strip().lower()
    return f"{event.event_type}:{entity}"


def _mark_review_items(db: Session, workspace_user_id: int, event_id: int, status: str, actor: str) -> None:
    stmt = select(ReviewQueueItem).where(
        ReviewQueueItem.workspace_user_id == workspace_user_id,
        ReviewQueueItem.event_id == event_id,
        ReviewQueueItem.status == "open",
    )
    for item in db.scalars(stmt):
        item.status = status
        item.assigned_to = actor


def _set_inactive(draft: DraftPost, status: str, reason: str, when: datetime) -> None:
    flags = dict(draft.safety_flags or {})
    flags["inactive_reason"] = reason
    flags["inactive_at"] = when.isoformat()
    draft.safety_flags = flags
    draft.needs_review = False
    draft.status = status


def apply_customer_lifecycle(db: Session, profile: CustomerProfile) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    stmt = (
        select(DraftPost, Event)
        .join(Event, Event.id == DraftPost.event_id)
        .where(DraftPost.workspace_user_id == profile.workspace_user_id)
        .order_by(DraftPost.updated_at.desc())
    )
    rows = list(db.execute(stmt).all())
    latest_by_story: dict[str, tuple[datetime, int]] = {}
    for draft, event in rows:
        if draft.status in {"expired", "superseded", "rejected", "failed"}:
            continue
        family = story_family_key(event)
        ref_time = event_reference_time(event)
        current = latest_by_story.get(family)
        if current is None or ref_time > current[0] or (ref_time == current[0] and draft.id > current[1]):
            latest_by_story[family] = (ref_time, draft.id)

    counts = Counter()
    for draft, event in rows:
        fresh_until = fresh_until_for_event(event, profile.freshness_window_hours or 12)
        family = story_family_key(event)
        latest = latest_by_story.get(family)
        publish_job = db.scalar(
            select(PublishJob).where(PublishJob.draft_post_id == draft.id).order_by(PublishJob.updated_at.desc()).limit(1)
        )

        if draft.status in ACTIVE_DRAFT_STATUSES and latest and latest[1] != draft.id and latest[0] > event_reference_time(event):
            _set_inactive(draft, "superseded", "superseded_by_newer_update", now)
            _mark_review_items(db, profile.workspace_user_id, event.id, "superseded", "system")
            if publish_job and publish_job.status in {"queued", "publishing"}:
                publish_job.status = "superseded"
                publish_job.result_message = "superseded_by_newer_update"
            counts["superseded"] += 1
            continue

        if draft.status in ACTIVE_DRAFT_STATUSES and fresh_until <= now:
            _set_inactive(draft, "expired", "expired_by_age", now)
            _mark_review_items(db, profile.workspace_user_id, event.id, "expired", "system")
            if publish_job and publish_job.status in {"queued", "publishing"}:
                publish_job.status = "expired"
                publish_job.result_message = "expired_before_publish"
            counts["expired"] += 1

    db.flush()
    return dict(counts)


def lifecycle_metadata(
    draft: DraftPost,
    event: Event,
    profile: CustomerProfile,
    publish_job: PublishJob | None = None,
    review_item: ReviewQueueItem | None = None,
) -> dict[str, Any]:
    fresh_until = fresh_until_for_event(event, profile.freshness_window_hours or 12)
    flags = draft.safety_flags or {}
    lifecycle_state = draft.status
    inactive_reason = flags.get("inactive_reason")
    scheduled_for = _as_utc(publish_job.scheduled_for) if publish_job else None
    if draft.status == "draft":
        lifecycle_state = "overdue" if review_item and review_item._is_overdue() else "fresh"
    elif draft.status == "queued" and scheduled_for and scheduled_for > datetime.now(timezone.utc):
        lifecycle_state = "scheduled"
    return {
        "lifecycle_state": lifecycle_state,
        "inactive_reason": inactive_reason,
        "fresh_until": fresh_until.isoformat(),
    }


def summarize_recent_activity(drafts: list[dict], last_seen_at: datetime | None) -> tuple[dict[str, int], list[dict]]:
    activity_items: list[dict] = []
    counts = Counter()
    for draft in drafts:
        status = draft.get("lifecycle_state") or draft.get("status")
        timestamp = draft.get("updated_at")
        if last_seen_at and timestamp:
            try:
                if datetime.fromisoformat(timestamp) <= last_seen_at:
                    continue
            except ValueError:
                pass
        if status in {"posted", "expired", "superseded", "failed", "rejected"}:
            counts[status] += 1
            activity_items.append(
                {
                    "draft_id": draft.get("id"),
                    "status": status,
                    "headline": ((draft.get("event") or {}).get("summary_facts") or {}).get("headline") or draft.get("draft_text"),
                    "updated_at": timestamp,
                    "inactive_reason": draft.get("inactive_reason"),
                }
            )
    activity_items.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    return dict(counts), activity_items[:8]

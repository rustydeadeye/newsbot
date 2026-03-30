from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging

from sqlalchemy.orm import Session

from app.models.creator import CreatorSettings
from app.models.event import DraftPost, Event
from app.models.job import PublishJob, PublishLog
from app.models.review import ReviewQueueItem
from app.repositories.creators import CreatorSettingsRepository
from app.repositories.drafts import DraftRepository
from app.repositories.events import EventRepository
from app.repositories.jobs import PublishJobRepository
from app.repositories.review import ReviewQueueRepository
from app.repositories.sources import SourceRepository
from app.services.drafting.service import DraftingService
from app.services.normalization.dedupe import make_dedupe_key
from app.services.normalization.extractors import extract_facts
from app.services.publishing.x_client import XPublisher
from app.services.scoring import SOURCE_PRIORITY, score_event

logger = logging.getLogger(__name__)

MAX_PUBLISH_ATTEMPTS = 3
_RETRY_BACKOFF_MINUTES = [5, 15]  # delay before attempt 2 and 3


def normalize_pending_items(db: Session, watchlist: set[str] | None = None) -> int:
    source_repo = SourceRepository(db)
    event_repo = EventRepository(db)
    created = 0
    sources = {source.id: source for source in source_repo.list_enabled()}
    for item in source_repo.list_unprocessed_items():
        source = sources[item.source_id]
        facts = extract_facts(source, item)
        if facts.get("is_stale"):
            logger.debug("Skipping stale source item id=%s title=%s", item.id, item.title)
            item.processed = True
            continue
        dedupe_key = make_dedupe_key(
            event_type=facts["event_class"],
            ticker=facts.get("ticker"),
            entity_name=facts.get("company"),
            occurred_at=item.published_at,
            key_number=facts.get("subject_key"),
        )
        latest_date = _event_latest_date(facts, item)
        existing = event_repo.get_by_dedupe_key(dedupe_key)
        if existing:
            if SOURCE_PRIORITY.get(source.name, 0) > existing.source_priority:
                logger.debug("Upgrading event dedupe_key=%s from source=%s", dedupe_key, source.name)
                existing.source_item_id = item.id
                existing.source_priority = SOURCE_PRIORITY.get(source.name, 0)
                existing.occurred_at = item.published_at
                existing.summary_facts = facts
                existing.confidence_score = 0.95 if source.name in SOURCE_PRIORITY else 0.70
                existing.importance_score = score_event(
                    source.name,
                    facts["event_class"],
                    facts.get("ticker"),
                    watchlist,
                    latest_date=latest_date,
                )
                existing.status = "normalized"
            item.processed = True
            continue

        event = Event(
            source_item_id=item.id,
            event_type=facts["event_class"],
            entity_type="company" if facts.get("ticker") else "market",
            entity_name=facts.get("company"),
            ticker=facts.get("ticker"),
            source_priority=SOURCE_PRIORITY.get(source.name, 0),
            occurred_at=item.published_at,
            summary_facts=facts,
            importance_score=score_event(
                source.name,
                facts["event_class"],
                facts.get("ticker"),
                watchlist,
                latest_date=latest_date,
            ),
            confidence_score=0.95 if source.name in SOURCE_PRIORITY else 0.70,
            dedupe_key=dedupe_key,
            status="normalized",
        )
        event_repo.add(event)
        item.processed = True
        created += 1
    db.commit()
    logger.info("normalize_pending_items created=%d events", created)
    return created


def draft_pending_events(db: Session, auto_post_threshold: int) -> int:
    event_repo = EventRepository(db)
    draft_repo = DraftRepository(db)
    review_repo = ReviewQueueRepository(db)
    drafting_service = DraftingService()
    created = 0

    for event in event_repo.list_for_drafting():
        if draft_repo.latest_for_event(event.id) is not None:
            logger.debug("event_id=%s already has a draft, skipping", event.id)
            event.status = "drafted"
            continue
        draft = drafting_service.make_draft_post(event)
        should_review = draft.needs_review or event.importance_score < auto_post_threshold or event.confidence_score < 0.85
        if should_review:
            draft.status = "draft"
            draft.needs_review = True
            review_repo.add(ReviewQueueItem(event_id=event.id, reason=_review_reason(event, draft)))
            logger.debug("event_id=%s queued for review reason=%s", event.id, _review_reason(event, draft))
        else:
            draft.status = "approved"
            draft.needs_review = False
            logger.debug("event_id=%s auto-approved for publishing", event.id)
        draft_repo.add(draft)
        event.status = "drafted"
        created += 1
    db.commit()
    logger.info("draft_pending_events created=%d drafts", created)
    return created


def queue_publish_jobs(db: Session) -> int:
    draft_repo = DraftRepository(db)
    created = 0
    for draft in draft_repo.list_publishable():
        if enqueue_approved_draft(db, draft.id):
            created += 1
    db.commit()
    return created


def publish_ready_jobs(db: Session) -> int:
    job_repo = PublishJobRepository(db)
    publisher = XPublisher()
    published = 0
    for job in job_repo.list_ready():
        draft = db.get(DraftPost, job.draft_post_id)
        if draft is None:
            job.status = "failed"
            job.last_error = "missing_draft"
            logger.error("job_id=%s has no associated draft", job.id)
            continue
        try:
            response = publisher.publish(draft.draft_text)
            result_status = response.get("status")
            if result_status == "skipped":
                job.status = "skipped"
                job.result_message = response.get("reason")
                logger.warning("job_id=%s skipped: %s", job.id, response.get("reason"))
                continue
            job.status = "posted"
            job.result_message = None
            db.add(PublishLog(publish_job_id=job.id, platform_post_id=response.get("data", {}).get("id"), response_payload=response))
            published += 1
            logger.info("job_id=%s published successfully", job.id)
        except RuntimeError as exc:
            job.attempt_count += 1
            job.last_error = str(exc)
            if job.attempt_count < MAX_PUBLISH_ATTEMPTS:
                backoff = _RETRY_BACKOFF_MINUTES[min(job.attempt_count - 1, len(_RETRY_BACKOFF_MINUTES) - 1)]
                job.status = "queued"
                job.scheduled_for = datetime.now(timezone.utc) + timedelta(minutes=backoff)
                logger.warning("job_id=%s publish failed (attempt %d/%d), retrying in %dm: %s", job.id, job.attempt_count, MAX_PUBLISH_ATTEMPTS, backoff, exc)
            else:
                job.status = "failed"
                logger.error("job_id=%s publish failed permanently after %d attempts: %s", job.id, job.attempt_count, exc)
    db.commit()
    logger.info("publish_ready_jobs published=%d", published)
    return published


def _review_reason(event: Event, draft) -> str:
    if draft.safety_flags.get("needs_review"):
        return "blocked_phrase"
    if event.importance_score < 80:
        return "below_auto_post_threshold"
    if event.confidence_score < 0.85:
        return "low_confidence"
    return "manual_review"


def _queue_decision(
    job_repo: PublishJobRepository,
    creator_settings: CreatorSettings,
    event: Event,
    draft: DraftPost,
) -> str:
    if job_repo.exists_for_draft(draft.id):
        return "duplicate_draft_job"

    now = datetime.now(timezone.utc)
    recent_post_window = now - timedelta(hours=1)
    if job_repo.count_recent_posted(recent_post_window) >= creator_settings.max_posts_per_hour:
        return "rate_limit_hourly"

    cooldown_minutes = _cooldown_minutes(event)
    cooldown_since = now - timedelta(minutes=cooldown_minutes)
    recent_conflict = job_repo.find_recent_conflict(
        event.dedupe_key,
        event.summary_facts.get("subject_key"),
        cooldown_since,
    )
    if recent_conflict:
        return "cooldown_duplicate"

    return "queue"


def _cooldown_minutes(event: Event) -> int:
    if event.event_type in {"rbi_policy", "macro_release", "sebi_circular", "sebi_enforcement"}:
        return 120
    if event.event_type in {"earnings", "dividend", "bonus_split", "fundraise", "order_win"}:
        return 45
    return 30


def enqueue_approved_draft(db: Session, draft_id: int) -> bool:
    creator_settings = CreatorSettingsRepository(db).get_or_create_default()
    draft_repo = DraftRepository(db)
    job_repo = PublishJobRepository(db)
    review_repo = ReviewQueueRepository(db)
    draft = draft_repo.get(draft_id)
    if draft is None:
        return False
    event = draft_repo.get_event(draft)
    if event is None:
        draft.status = "failed"
        return False
    decision = _queue_decision(job_repo, creator_settings, event, draft)
    if decision != "queue":
        draft.status = "draft"
        draft.needs_review = True
        draft.safety_flags = {**draft.safety_flags, "guardrail_reason": decision}
        review_repo.add(ReviewQueueItem(event_id=event.id, reason=decision))
        return False
    job_repo.add(PublishJob(draft_post_id=draft.id))
    draft.status = "queued"
    return True


def _event_latest_date(facts: dict, item) -> datetime.date | None:
    for key in ("broadcast_date", "event_date", "effective_date"):
        raw = facts.get(key)
        if not raw or not isinstance(raw, str):
            continue
        for fmt in ("%d-%b-%Y", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                continue
    if item.published_at:
        return item.published_at.date()
    return None

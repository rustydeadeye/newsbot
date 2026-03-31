from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
_DEFAULT_TZ = "Asia/Kolkata"


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


_DRAFT_MAX_WORKERS = 5


def draft_pending_events(db: Session, auto_post_threshold: int) -> int:
    event_repo = EventRepository(db)
    draft_repo = DraftRepository(db)
    review_repo = ReviewQueueRepository(db)
    creator_settings = CreatorSettingsRepository(db).get_or_create_default()
    workspace_openai_key = (creator_settings.token_store or {}).get("openai_api_key")
    drafting_service = DraftingService(api_key=workspace_openai_key)

    events_to_draft = []
    for event in event_repo.list_for_drafting():
        if draft_repo.latest_for_event(event.id) is not None:
            logger.debug("event_id=%s already has a draft, skipping", event.id)
            event.status = "drafted"
        else:
            events_to_draft.append(event)

    if not events_to_draft:
        db.commit()
        return 0

    # Run OpenAI calls concurrently; DB writes happen sequentially after
    results: dict[int, tuple[str, dict, float]] = {}
    with ThreadPoolExecutor(max_workers=_DRAFT_MAX_WORKERS) as executor:
        future_to_event = {executor.submit(drafting_service.build_draft, event): event for event in events_to_draft}
        for future in as_completed(future_to_event):
            event = future_to_event[future]
            try:
                results[event.id] = future.result()
            except Exception:
                logger.warning("build_draft failed for event_id=%s; using fallback", event.id, exc_info=True)
                fallback = drafting_service._fallback_text(event.summary_facts)
                results[event.id] = (fallback, drafting_service._safety_flags(fallback), 0.0)

    created = 0
    for event in events_to_draft:
        draft_text, safety_flags, ai_confidence = results[event.id]
        if ai_confidence > 0:
            safety_flags["ai_confidence"] = round(ai_confidence, 3)
        from app.services.drafting.prompts import PROMPT_VERSION
        draft = DraftPost(
            event_id=event.id,
            platform="x",
            draft_text=draft_text,
            safety_flags=safety_flags,
            needs_review=safety_flags.get("needs_review", False),
            prompt_version=PROMPT_VERSION,
        )
        should_review = draft.needs_review or event.importance_score < auto_post_threshold or event.confidence_score < 0.85
        if should_review:
            draft.status = "draft"
            draft.needs_review = True
            review_repo.add(ReviewQueueItem(event_id=event.id, reason=_review_reason(event, draft, auto_post_threshold)))
            logger.debug("event_id=%s queued for review reason=%s", event.id, _review_reason(event, draft))
        else:
            draft.status = "approved"
            draft.needs_review = False
            logger.debug("event_id=%s auto-approved for publishing", event.id)
        draft_repo.add(draft)
        event.status = "drafted"
        created += 1

    db.commit()
    logger.info("draft_pending_events created=%d drafts (parallel workers=%d)", created, _DRAFT_MAX_WORKERS)
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

    # Release any jobs stuck in "publishing" (e.g. from a crashed worker)
    stuck = job_repo.find_stuck_publishing()
    for job in stuck:
        job.status = "failed"
        job.last_error = "timeout_stuck_in_publishing"
        logger.error("job_id=%s stuck in publishing; marking failed", job.id)
    if stuck:
        db.commit()

    # Load live tokens from DB so refreshes survive process restarts
    creator_settings = CreatorSettingsRepository(db).get_or_create_default()
    token_store = creator_settings.token_store or {}

    def _save_tokens(access_token: str, refresh_token: str) -> None:
        creator_settings.token_store = {
            **creator_settings.token_store,
            "x_access_token": access_token,
            "x_refresh_token": refresh_token,
        }
        db.flush()
        logger.info("Refreshed X tokens persisted to DB")

    publisher = XPublisher(token_store=token_store, on_token_refresh=_save_tokens)
    published = 0
    jobs = job_repo.claim_ready()
    db.commit()

    for job in jobs:
        draft = db.get(DraftPost, job.draft_post_id)
        if draft is None:
            job.status = "failed"
            job.last_error = "missing_draft"
            logger.error("job_id=%s has no associated draft", job.id)
            continue
        try:
            response = publisher.publish(draft.draft_text, idempotency_key=job.idempotency_key)
            result_status = response.get("status")

            if result_status == "skipped":
                job.status = "skipped"
                job.result_message = response.get("reason")
                logger.warning("job_id=%s skipped: %s", job.id, response.get("reason"))
                continue

            if result_status == "rate_limited":
                retry_after = response.get("retry_after_seconds", 900)
                job.status = "queued"
                job.scheduled_for = datetime.now(timezone.utc) + timedelta(seconds=retry_after)
                # Do NOT increment attempt_count — rate limits are not failures
                logger.warning("job_id=%s rate limited by X; retrying in %ds", job.id, retry_after)
                continue

            job.status = "posted"
            job.result_message = None
            draft.status = "posted"
            event = db.get(Event, draft.event_id)
            if event is not None:
                event.status = "posted"
            db.add(
                PublishLog(
                    publish_job_id=job.id,
                    platform_post_id=response.get("data", {}).get("id"),
                    posted_at=datetime.now(timezone.utc),
                    response_payload=response,
                )
            )
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


def _review_reason(event: Event, draft, auto_post_threshold: int = 80) -> str:
    flags = draft.safety_flags or {}
    if flags.get("needs_review"):
        return "blocked_phrase"
    if event.importance_score < auto_post_threshold:
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

    if not _in_posting_window(creator_settings, now):
        return "outside_posting_window"

    return "queue"


def _in_posting_window(creator_settings: CreatorSettings, now_utc: datetime) -> bool:
    start = creator_settings.posting_window_start
    end = creator_settings.posting_window_end
    if start is None or end is None:
        return True  # no restriction set
    if start == end:
        return True  # degenerate window — treat as no restriction rather than blocking all posts
    try:
        tz = ZoneInfo(creator_settings.timezone or _DEFAULT_TZ)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo(_DEFAULT_TZ)
    local_hour = now_utc.astimezone(tz).hour
    if start < end:
        return start <= local_hour < end
    # overnight window e.g. 22–6
    return local_hour >= start or local_hour < end


def _next_window_open(creator_settings: CreatorSettings, now_utc: datetime) -> datetime:
    start = creator_settings.posting_window_start
    if start is None:
        return now_utc
    try:
        tz = ZoneInfo(creator_settings.timezone or _DEFAULT_TZ)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo(_DEFAULT_TZ)
    local_now = now_utc.astimezone(tz)
    next_open = local_now.replace(hour=start, minute=0, second=0, microsecond=0)
    if next_open <= local_now:
        next_open = next_open + timedelta(days=1)
    return next_open.astimezone(timezone.utc)


def _cooldown_minutes(event: Event) -> int:
    if event.event_type in {"rbi_policy", "rbi_penalty", "macro_release", "sebi_circular", "sebi_enforcement", "default_fraud"}:
        return 120
    if event.event_type in {"earnings", "dividend", "bonus_split", "fundraise", "order_win", "acquisition"}:
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

    if decision == "outside_posting_window":
        scheduled_for = _next_window_open(creator_settings, datetime.now(timezone.utc))
        job_repo.add(PublishJob(draft_post_id=draft.id, scheduled_for=scheduled_for))
        draft.status = "queued"
        logger.info("draft_id=%s scheduled for next posting window at %s", draft.id, scheduled_for.strftime("%H:%M UTC"))
        return True

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
        for fmt in (
            "%d-%b-%Y",
            "%d-%B-%Y",
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%d %b %Y",
            "%d %B %Y",
            "%d-%m-%y",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d",
        ):
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                continue
    if item.published_at:
        return item.published_at.date()
    return None

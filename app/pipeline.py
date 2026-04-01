from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import logging
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.models.creator import CreatorSettings
from app.models.event import DraftPost, Event
from app.models.job import PublishJob, PublishLog
from app.models.review import ReviewQueueItem
from app.repositories.creators import CreatorSettingsRepository
from app.repositories.customers import CustomerProfileRepository
from app.repositories.drafts import DraftRepository
from app.repositories.events import EventRepository
from app.repositories.jobs import PublishJobRepository
from app.repositories.review import ReviewQueueRepository
from app.repositories.sources import SourceRepository
from app.repositories.pipeline_runs import PipelineRunRepository
from app.models.pipeline_run import PipelineRun
from app.services.drafting.service import DraftingService
from app.services.customer_lifecycle import AUTO_POST_ALLOWLIST, apply_customer_lifecycle
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
                    headline=facts.get("headline"),
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
                headline=facts.get("headline"),
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
_CUSTOMER_DRAFT_LIMIT = 6
_CUSTOMER_WATCHLIST_MIN_SCORE = 50
_CUSTOMER_FALLBACK_MIN_SCORE = 60
_CUSTOMER_FALLBACK_EVENT_TYPES = {
    "rbi_policy",
    "rbi_penalty",
    "sebi_circular",
    "sebi_enforcement",
    "macro_release",
    "earnings",
    "fundraise",
    "acquisition",
    "default_fraud",
    "dividend",
    "bonus_split",
    "order_win",
}
_CUSTOMER_WATCHLIST_EVENT_TYPES = _CUSTOMER_FALLBACK_EVENT_TYPES | {"management_change", "fund_notice"}
_CUSTOMER_AUTO_POST_ALLOWLIST = {
    "rbi_policy",
    "rbi_penalty",
    "sebi_circular",
    "sebi_enforcement",
    "macro_release",
}
_CUSTOMER_FUND_NOTICE_STOP_WORDS = {
    "fund",
    "funds",
    "fmp",
    "fixed",
    "maturity",
    "plan",
    "series",
    "direct",
    "regular",
    "growth",
    "option",
    "options",
    "dividend",
    "quarterly",
    "half",
    "halfyearly",
    "half-yearly",
    "yearly",
    "daily",
    "monthly",
    "idcw",
    "days",
    "payout",
    "yield",
}
_CUSTOMER_COMPANY_STOP_WORDS = {
    "limited",
    "ltd",
    "private",
    "pvt",
    "plc",
    "inc",
    "and",
    "company",
    "co",
}


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


def _event_matches_watchlist(event: Event, watchlist: set[str]) -> bool:
    if not watchlist:
        return False
    haystacks = [
        (event.entity_name or "").lower(),
        (event.ticker or "").lower(),
        str(event.summary_facts.get("headline", "")).lower(),
        str(event.summary_facts.get("subject_key", "")).lower(),
    ]
    return any(term in hay for term in watchlist for hay in haystacks)


def _event_has_material_facts(event: Event) -> bool:
    facts = event.summary_facts or {}
    if facts.get("period"):
        return True
    if facts.get("event_date") or facts.get("broadcast_date") or facts.get("effective_date"):
        return True

    numbers = facts.get("numbers") or []
    if isinstance(numbers, list) and any(isinstance(item, dict) and item.get("value") for item in numbers):
        return True

    filing_type = str(facts.get("filing_type") or "").lower()
    announcement_subtype = str(facts.get("announcement_subtype") or "").lower()
    release_type = str(facts.get("release_type") or "").lower()
    if any(value for value in (filing_type, announcement_subtype, release_type)):
        return True

    headline = str(facts.get("headline") or "").lower()
    material_terms = (
        "results",
        "quarter",
        "q1",
        "q2",
        "q3",
        "q4",
        "dividend",
        "bonus",
        "split",
        "fund raise",
        "fundraise",
        "qip",
        "preferential",
        "rights issue",
        "acquisition",
        "merger",
        "penalty",
        "order",
        "contract",
        "default",
        "fraud",
        "repo rate",
        "monetary policy",
        "auction",
        "circular",
    )
    return any(term in headline for term in material_terms)


def _event_text_blob(event: Event) -> str:
    facts = event.summary_facts or {}
    return " ".join(
        [
            str(event.entity_name or ""),
            str(event.ticker or ""),
            str(facts.get("headline") or ""),
            str(facts.get("subject_key") or ""),
        ]
    ).lower()


def _is_low_signal_fund_notice(event: Event) -> bool:
    if event.event_type not in {"dividend", "fund_notice"}:
        return False
    text = _event_text_blob(event)
    return any(
        term in text
        for term in (
            " mutual fund",
            " fixed maturity plan",
            " fmp ",
            " plan ",
            " idcw",
            " dividend payout option",
            " direct plan",
            " regular plan",
            " yield fund",
        )
    )


def _customer_family_key(event: Event) -> str:
    facts = event.summary_facts or {}
    headline = str(facts.get("headline") or "")
    entity_name = str(event.entity_name or facts.get("company") or "")
    if event.ticker and not _is_low_signal_fund_notice(event):
        return event.ticker.lower()

    base = (entity_name or headline).lower()
    tokens = [token for token in re.split(r"[^a-z0-9]+", base) if token]
    if not tokens:
        return event.ticker.lower() if event.ticker else "unknown"

    if _is_low_signal_fund_notice(event):
        family: list[str] = []
        for token in tokens:
            if token in _CUSTOMER_FUND_NOTICE_STOP_WORDS:
                if family:
                    break
                continue
            family.append(token)
            if len(family) >= 3:
                break
        return " ".join(family) if family else (event.ticker.lower() if event.ticker else "unknown")

    company_tokens = [token for token in tokens if token not in _CUSTOMER_COMPANY_STOP_WORDS]
    return " ".join(company_tokens[:3]) if company_tokens else (event.ticker.lower() if event.ticker else "unknown")


def _customer_family_limit(event: Event) -> int:
    if _is_low_signal_fund_notice(event):
        return 1
    if event.event_type in {"dividend", "bonus_split"}:
        return 1
    return 2


def _customer_draft_skip_reason(event: Event, watchlist_match: bool) -> str | None:
    if event.event_type == "general_update":
        return "filtered_event_type"

    if event.event_type == "fund_notice" and not watchlist_match:
        return "low_signal_fund_notice"

    if _is_low_signal_fund_notice(event) and not watchlist_match:
        return "low_signal_fund_notice"

    allowed_types = _CUSTOMER_WATCHLIST_EVENT_TYPES if watchlist_match else _CUSTOMER_FALLBACK_EVENT_TYPES
    if event.event_type not in allowed_types:
        return "filtered_event_type"

    minimum_score = _CUSTOMER_WATCHLIST_MIN_SCORE if watchlist_match else _CUSTOMER_FALLBACK_MIN_SCORE
    if event.importance_score < minimum_score:
        return "below_customer_threshold"

    if event.event_type == "management_change" and event.importance_score < 60:
        return "below_customer_threshold"

    if not _event_has_material_facts(event):
        return "no_material_facts"

    return None


def generate_drafts_for_customer(db: Session, workspace_user_id: int, auto_post_threshold: int) -> dict[str, int]:
    profile_repo = CustomerProfileRepository(db)
    event_repo = EventRepository(db)
    draft_repo = DraftRepository(db)
    review_repo = ReviewQueueRepository(db)
    job_repo = PublishJobRepository(db)

    profile = profile_repo.get_by_workspace_user_id(workspace_user_id)
    if profile is None:
        return {"drafted": 0, "review_items": 0, "matched_events": 0}

    apply_customer_lifecycle(db, profile)

    api_key = (profile.token_store or {}).get("openai_api_key")
    drafting_service = DraftingService(api_key=api_key)
    watchlist = {item.strip().lower() for item in (profile.watchlist or []) if isinstance(item, str) and item.strip()}

    candidates = []
    skip_counts = {
        "filtered_event_type": 0,
        "low_signal_fund_notice": 0,
        "below_customer_threshold": 0,
        "no_material_facts": 0,
        "already_drafted_for_customer": 0,
        "duplicate_family": 0,
    }
    for event in event_repo.list_recent(limit=200):
        if event.status not in {"normalized", "drafted", "approved", "queued", "posted"}:
            continue
        if draft_repo.latest_for_event(event.id, workspace_user_id) is not None:
            skip_counts["already_drafted_for_customer"] += 1
            continue
        watchlist_match = _event_matches_watchlist(event, watchlist)
        skip_reason = _customer_draft_skip_reason(event, watchlist_match)
        if skip_reason is not None:
            skip_counts[skip_reason] += 1
            continue
        candidates.append((event, watchlist_match))

    candidates.sort(
        key=lambda item: (
            0 if item[1] else 1,
            -(item[0].importance_score or 0),
            -(item[0].confidence_score or 0),
            -int(item[0].id or 0),
        )
    )

    if watchlist:
        ordered_events = [event for event, _ in candidates]
    else:
        ordered_events = [event for event, _ in candidates]

    diversified_events: list[Event] = []
    family_counts: dict[str, int] = {}
    for event in ordered_events:
        family_key = _customer_family_key(event)
        family_count = family_counts.get(family_key, 0)
        if family_count >= _customer_family_limit(event):
            skip_counts["duplicate_family"] += 1
            continue
        family_counts[family_key] = family_count + 1
        diversified_events.append(event)

    eligible_count = len(diversified_events)
    events_to_draft = diversified_events[:_CUSTOMER_DRAFT_LIMIT]
    if not events_to_draft:
        db.commit()
        return {
            "drafted": 0,
            "review_items": 0,
            "matched_events": 0,
            "eligible_events": eligible_count,
            **skip_counts,
        }

    created = 0
    review_items = 0
    auto_post_candidates = 0
    auto_queued = 0
    results: dict[int, tuple[str, dict, float]] = {}
    with ThreadPoolExecutor(max_workers=_DRAFT_MAX_WORKERS) as executor:
        future_to_event = {executor.submit(drafting_service.build_draft, event): event for event in events_to_draft}
        for future in as_completed(future_to_event):
            event = future_to_event[future]
            try:
                results[event.id] = future.result()
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("customer draft generation failed event_id=%s: %s", event.id, exc)

    for event in events_to_draft:
        result = results.get(event.id)
        if result is None:
            continue
        draft_text, safety_flags, _latency = result
        from app.services.drafting.prompts import PROMPT_VERSION
        draft = DraftPost(
            event_id=event.id,
            workspace_user_id=workspace_user_id,
            platform="x",
            draft_text=draft_text,
            safety_flags=safety_flags,
            needs_review=True,
            prompt_version=PROMPT_VERSION,
        )
        should_auto_post = (
            profile.automation_mode == "auto_generate_auto_post_high_confidence"
            and profile.auto_post_enabled
            and bool((profile.token_store or {}).get("x_access_token"))
            and event.event_type in AUTO_POST_ALLOWLIST
            and event.importance_score >= profile.auto_post_threshold
            and event.confidence_score >= 0.9
        )
        if should_auto_post:
            draft.status = "approved"
            draft.needs_review = False
            draft_repo.add(draft)
            auto_post_candidates += 1
            if enqueue_customer_approved_draft(db, draft.id, profile):
                auto_queued += 1
        else:
            draft.status = "draft"
            draft_repo.add(draft)
            review_repo.add(
                ReviewQueueItem(
                    event_id=event.id,
                    workspace_user_id=workspace_user_id,
                    reason=_review_reason(event, draft, auto_post_threshold),
                )
            )
            review_items += 1
        created += 1

    db.commit()
    return {
        "drafted": created,
        "review_items": review_items,
        "matched_events": len(events_to_draft),
        "eligible_events": eligible_count,
        "auto_post_candidates": auto_post_candidates,
        "auto_queued": auto_queued,
        **skip_counts,
    }


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
    creator_settings = CreatorSettingsRepository(db).get_or_create_default()
    customer_repo = CustomerProfileRepository(db)
    if hasattr(db, "scalars"):
        for profile in customer_repo.list_eligible_for_background_generation():
            apply_customer_lifecycle(db, profile)
        db.commit()

    # Release any jobs stuck in "publishing" (e.g. from a crashed worker)
    stuck = job_repo.find_stuck_publishing()
    for job in stuck:
        job.status = "failed"
        job.last_error = "timeout_stuck_in_publishing"
        logger.error("job_id=%s stuck in publishing; marking failed", job.id)
    if stuck:
        db.commit()
    jobs = job_repo.claim_ready()
    db.commit()

    published = _process_claimed_jobs(db, jobs, creator_settings, customer_repo)
    logger.info("publish_ready_jobs published=%d", published)
    return published


def publish_job_now(db: Session, job_id: int) -> bool:
    job_repo = PublishJobRepository(db)
    creator_settings = CreatorSettingsRepository(db).get_or_create_default()
    customer_repo = CustomerProfileRepository(db)
    job = job_repo.get(job_id)
    if job is None:
        return False
    if job.status != "queued":
        return job.status == "posted"
    if job.scheduled_for and job.scheduled_for > datetime.now(timezone.utc):
        return False

    job.status = "publishing"
    db.flush()
    published = _process_claimed_jobs(db, [job], creator_settings, customer_repo)
    return published > 0


def _process_claimed_jobs(
    db: Session,
    jobs: list[PublishJob],
    creator_settings: CreatorSettings,
    customer_repo: CustomerProfileRepository,
) -> int:
    published = 0

    for job in jobs:
        draft = db.get(DraftPost, job.draft_post_id)
        if draft is None:
            job.status = "failed"
            job.last_error = "missing_draft"
            logger.error("job_id=%s has no associated draft", job.id)
            continue

        token_store: dict = {}

        def _save_tokens(access_token: str, refresh_token: str) -> None:
            nonlocal token_store
            if draft.workspace_user_id:
                profile = customer_repo.get_or_create_for_workspace_user(draft.workspace_user_id)
                profile.token_store = {
                    **(profile.token_store or {}),
                    "x_access_token": access_token,
                    "x_refresh_token": refresh_token,
                }
                token_store = profile.token_store
            else:
                creator_settings.token_store = {
                    **creator_settings.token_store,
                    "x_access_token": access_token,
                    "x_refresh_token": refresh_token,
                }
                token_store = creator_settings.token_store
            db.flush()
            logger.info("Refreshed X tokens persisted to DB")

        if draft.workspace_user_id:
            profile = customer_repo.get_by_workspace_user_id(draft.workspace_user_id)
            token_store = dict((profile.token_store or {}) if profile else {})
        else:
            token_store = dict(creator_settings.token_store or {})

        publisher = XPublisher(token_store=token_store, on_token_refresh=_save_tokens)
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
    settings_owner,
    event: Event,
    draft: DraftPost,
) -> str:
    if job_repo.exists_for_draft(draft.id):
        return "duplicate_draft_job"

    now = datetime.now(timezone.utc)
    recent_post_window = now - timedelta(hours=1)
    recent_count = (
        job_repo.count_recent_posted_for_workspace_user(draft.workspace_user_id, recent_post_window)
        if draft.workspace_user_id
        else job_repo.count_recent_posted(recent_post_window)
    )
    if recent_count >= settings_owner.max_posts_per_hour:
        return "rate_limit_hourly"

    cooldown_minutes = _cooldown_minutes(event)
    cooldown_since = now - timedelta(minutes=cooldown_minutes)
    recent_conflict = (
        job_repo.find_recent_conflict_for_workspace_user(
            draft.workspace_user_id,
            event.dedupe_key,
            event.summary_facts.get("subject_key"),
            cooldown_since,
        )
        if draft.workspace_user_id
        else job_repo.find_recent_conflict(
            event.dedupe_key,
            event.summary_facts.get("subject_key"),
            cooldown_since,
        )
    )
    if recent_conflict:
        return "cooldown_duplicate"

    if not _in_posting_window(settings_owner, now):
        return "outside_posting_window"

    return "queue"


def _in_posting_window(settings_owner, now_utc: datetime) -> bool:
    start = settings_owner.posting_window_start
    end = settings_owner.posting_window_end
    if start is None or end is None:
        return True  # no restriction set
    if start == end:
        return True  # degenerate window — treat as no restriction rather than blocking all posts
    try:
        tz = ZoneInfo(settings_owner.timezone or _DEFAULT_TZ)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo(_DEFAULT_TZ)
    local_hour = now_utc.astimezone(tz).hour
    if start < end:
        return start <= local_hour < end
    # overnight window e.g. 22–6
    return local_hour >= start or local_hour < end


def _next_window_open(settings_owner, now_utc: datetime) -> datetime:
    start = settings_owner.posting_window_start
    if start is None:
        return now_utc
    try:
        tz = ZoneInfo(settings_owner.timezone or _DEFAULT_TZ)
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


def enqueue_customer_approved_draft(db: Session, draft_id: int, profile) -> bool:
    draft_repo = DraftRepository(db)
    job_repo = PublishJobRepository(db)
    draft = draft_repo.get(draft_id)
    if draft is None:
        return False
    event = draft_repo.get_event(draft)
    if event is None:
        draft.status = "failed"
        return False
    decision = _queue_decision(job_repo, profile, event, draft)
    if decision == "outside_posting_window":
        scheduled_for = _next_window_open(profile, datetime.now(timezone.utc))
        job_repo.add(PublishJob(draft_post_id=draft.id, scheduled_for=scheduled_for))
        draft.status = "queued"
        return True
    if decision != "queue":
        draft.status = "approved"
        draft.needs_review = False
        draft.safety_flags = {**draft.safety_flags, "guardrail_reason": decision}
        return False
    job_repo.add(PublishJob(draft_post_id=draft.id))
    draft.status = "queued"
    return True


def run_background_customer_generation(db: Session, auto_post_threshold: int) -> dict[str, int]:
    profile_repo = CustomerProfileRepository(db)
    run_repo = PipelineRunRepository(db)
    counts = {"customers_processed": 0, "drafted": 0, "review_items": 0, "auto_queued": 0}
    for profile in profile_repo.list_eligible_for_background_generation():
        if not (profile.token_store or {}).get("openai_api_key"):
            continue
        run = run_repo.add(
            PipelineRun(
                workspace_user_id=profile.workspace_user_id,
                requested_by="system",
                scope="scheduled_customer_generation",
                status="running",
                started_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        result = generate_drafts_for_customer(db, profile.workspace_user_id, auto_post_threshold)
        run.status = "completed" if result.get("drafted", 0) > 0 else "empty"
        run.result_counts = result
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        counts["customers_processed"] += 1
        counts["drafted"] += result.get("drafted", 0)
        counts["review_items"] += result.get("review_items", 0)
        counts["auto_queued"] += result.get("auto_queued", 0)
    return counts


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

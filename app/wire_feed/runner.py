from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from types import SimpleNamespace

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.wire_feed import WireCandidate, WireJob
from app.repositories.customers import CustomerProfileRepository
from app.repositories.wire_feed import WireCandidateRepository, WireJobRepository
from app.services.publishing.x_client import XPublisher
from app.services.drafting.service import DraftingService
from app.wire_feed.pipeline import fetch_and_process
from app.wire_feed.policy import plan_wire_queue
from app.wire_feed.products import normalize_wire_product, policy_for_product
from app.wire_feed.sources import get_wire_sources
from app.wire_feed.web_pipeline import fetch_web_breaking_candidates, get_due_web_runs

logger = logging.getLogger(__name__)
_WIRE_MAX_ATTEMPTS = 3
_BASE_FETCH_INTERVAL = timedelta(hours=1)


def run_wire_cycle() -> dict[str, list[dict] | int]:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    summary: dict[str, list[dict] | int] = {
        "sources_processed": 0,
        "candidates": 0,
        "post_now": 0,
        "queued": 0,
        "skipped": 0,
        "posted": 0,
        "failed": 0,
        "items": [],
    }
    with SessionLocal() as db:
        candidate_repo = WireCandidateRepository(db)
        job_repo = WireJobRepository(db)
        customer_repo = CustomerProfileRepository(db)
        list_active = getattr(customer_repo, "list_active_autopost_customers", None)
        if callable(list_active):
            active_profiles = list_active()
        else:
            get_active = getattr(customer_repo, "get_active_autopost_customer", None)
            profile = get_active() if callable(get_active) else None
            if profile is not None:
                active_profiles = [profile]
            elif getattr(customer_repo, "has_active_autopost_customer", lambda: False)():
                active_profiles = [SimpleNamespace(id=0, wire_product="finance", token_store={})]
            else:
                active_profiles = []

        for profile in active_profiles:
            product = normalize_wire_product(getattr(profile, "wire_product", "finance"))
            store = dict(getattr(profile, "token_store", {}) or {})
            drafting = DraftingService(api_key=store.get("openai_api_key"), model=settings.openai_model)
            policy = policy_for_product(product)
            try:
                expired = job_repo.expire_stale_jobs(now, policy, customer_profile_id=profile.id)
            except TypeError:
                expired = job_repo.expire_stale_jobs(now, policy)
            try:
                recent_records = job_repo.recent_post_records(now - timedelta(days=1), profile.id)
            except TypeError:
                recent_records = job_repo.recent_post_records(now - timedelta(days=1))
            summary["skipped"] += expired

            candidate_batches: list[tuple[str, list]] = []
            try:
                sources = get_wire_sources(product)
            except TypeError:
                sources = get_wire_sources()
                for source in sources:
                    source_name = getattr(source, "name", None) or f"{source.key}_feed"
                    has_source_since = getattr(candidate_repo, "has_source_candidate_since", None)
                    if callable(has_source_since):
                        try:
                            has_recent = has_source_since(profile.id, source_name, now - _BASE_FETCH_INTERVAL)
                        except TypeError:
                            has_recent = has_source_since(source_name, now - _BASE_FETCH_INTERVAL)
                    else:
                        has_recent = False
                    if has_recent:
                        continue
                candidate_batches.append((source.key, fetch_and_process(source, drafting)))

            if settings.wire_web_breaking_enabled:
                def _has_source_since(source_name, since):
                    try:
                        return candidate_repo.has_source_candidate_since(profile.id, source_name, since)
                    except TypeError:
                        return candidate_repo.has_source_candidate_since(source_name, since)

                due_runs = get_due_web_runs(
                    now,
                    _has_source_since,
                    product=product,
                )
                for run in due_runs:
                    candidate_batches.append(
                        (
                            run.key,
                            fetch_web_breaking_candidates(
                                run,
                                openai_api_key=store.get("openai_api_key"),
                                tavily_api_key=store.get("tavily_api_key"),
                            ),
                        )
                    )

            all_results = [result for _, results in candidate_batches for result in results]
            decisions = plan_wire_queue(all_results, recent_posts=recent_records, now=now, settings=policy)
            decisions_by_source: dict[str, list] = {source_key: [] for source_key, _ in candidate_batches}
            for decision in decisions:
                source_key = getattr(decision.result, "source_name", None) or (
                    candidate_batches[0][0] if len(candidate_batches) == 1 else "unknown"
                )
                if source_key == "tradient_market_news":
                    source_key = "tradient"
                if source_key.startswith("tavily_"):
                    source_key = source_key.removeprefix("tavily_")
                decisions_by_source.setdefault(source_key, []).append(decision)

            summary["sources_processed"] += len(candidate_batches)
            summary["candidates"] += len(all_results)

            for source_key, source_decisions in decisions_by_source.items():
                source_items: list[dict] = []
                for decision in source_decisions:
                    try:
                        candidate = candidate_repo.upsert_from_result(profile.id, decision.result)
                    except TypeError:
                        candidate = candidate_repo.upsert_from_result(decision.result)
                    if decision.priority == "breaking" and decision.action in {"post_now", "queue"} and decision.scheduled_for is not None:
                        try:
                            job_repo.bump_non_breaking_queue(decision.scheduled_for, policy, customer_profile_id=profile.id)
                        except TypeError:
                            job_repo.bump_non_breaking_queue(decision.scheduled_for, policy)
                    job_repo.record_decision(candidate, decision)
                    if decision.action == "post_now":
                        summary["post_now"] += 1
                    elif decision.action == "queue":
                        summary["queued"] += 1
                    else:
                        summary["skipped"] += 1
                    source_items.append(
                        {
                            "customer_profile_id": profile.id,
                            "product": product,
                            "action": decision.action,
                            "priority": decision.priority,
                            "scheduled_for": decision.scheduled_for.isoformat() if decision.scheduled_for else None,
                            "reason": decision.reason,
                            "title": decision.result.title,
                            "draft_text": decision.result.draft_text,
                            "score": decision.result.importance_score,
                        }
                    )
                cast_items = summary["items"]
                if isinstance(cast_items, list):
                    cast_items.append({"source": source_key, "customer_profile_id": profile.id, "product": product, "decisions": source_items})

            db.commit()
            try:
                publish_counts = _publish_due_jobs(db, profile, now)
            except TypeError:
                publish_counts = _publish_due_jobs(db, now)
            summary["posted"] += publish_counts["posted"]
            summary["failed"] += publish_counts["failed"]

    return summary


def _publish_due_jobs(db, profile, now: datetime | None = None) -> dict[str, int]:
    if now is None:
        now = profile
        customer_repo = CustomerProfileRepository(db)
        profile = customer_repo.get_active_autopost_customer()
    job_repo = WireJobRepository(db)
    if profile is None:
        logger.info("No active autopost customer with X tokens; skipping wire publish")
        return {"posted": 0, "failed": 0}

    def _save_tokens(access_token: str, refresh_token: str) -> None:
        store = dict(profile.token_store or {})
        store["x_access_token"] = access_token
        if refresh_token:
            store["x_refresh_token"] = refresh_token
        profile.token_store = store
        db.flush()

    publisher = XPublisher(token_store=dict(profile.token_store or {}), on_token_refresh=_save_tokens)
    # Only publish one due wire job per cycle so late resume/backlog states
    # do not flush multiple overdue posts at once.
    customer_profile_id = getattr(profile, "id", None)
    try:
        jobs = job_repo.claim_ready(now=now, limit=1, customer_profile_id=customer_profile_id)
    except TypeError:
        jobs = job_repo.claim_ready(now=now, limit=1)
    posted = 0
    failed = 0
    for job in jobs:
        candidate = db.get(WireCandidate, job.candidate_id)
        if candidate is None:
            job.status = "failed"
            job.last_error = "missing_candidate"
            failed += 1
            continue
        try:
            has_duplicate = job_repo.has_active_duplicate(candidate.dedupe_key, exclude_job_id=job.id, customer_profile_id=customer_profile_id)
        except TypeError:
            has_duplicate = job_repo.has_active_duplicate(candidate.dedupe_key, exclude_job_id=job.id)
        if has_duplicate:
            job.status = "skipped"
            job.result_message = "duplicate_active_job"
            job.last_error = None
            continue
        try:
            response = publisher.publish(candidate.draft_text, idempotency_key=job.idempotency_key)
            status = response.get("status")
            if status == "posted":
                job.status = "posted"
                job.last_error = None
                job.result_message = None
                job_repo.add_log(job.id, response, platform_post_id=response.get("data", {}).get("id"))
                posted += 1
            elif status == "rate_limited":
                retry_after = int(response.get("retry_after_seconds", 900))
                job.status = "queued"
                job.scheduled_for = now + timedelta(seconds=retry_after)
                job.result_message = "rate_limited"
                job.last_error = None
            else:
                job.status = "skipped"
                job.result_message = str(response.get("reason") or status or "skipped")
                job.last_error = None
        except RuntimeError as exc:
            job.last_error = str(exc)
            if job.attempt_count >= _WIRE_MAX_ATTEMPTS:
                job.status = "failed"
                failed += 1
            else:
                job.status = "queued"
                job.scheduled_for = now + timedelta(minutes=15)
                job.result_message = "retry_scheduled"
    db.commit()
    return {"posted": posted, "failed": failed}

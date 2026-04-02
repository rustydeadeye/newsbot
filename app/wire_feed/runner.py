from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.wire_feed import WireCandidate, WireJob
from app.repositories.customers import CustomerProfileRepository
from app.repositories.wire_feed import WireCandidateRepository, WireJobRepository
from app.services.publishing.x_client import XPublisher
from app.services.drafting.service import DraftingService
from app.wire_feed.pipeline import fetch_and_process
from app.wire_feed.policy import WireFeedSettings, plan_wire_queue
from app.wire_feed.sources import get_wire_sources

logger = logging.getLogger(__name__)
_WIRE_MAX_ATTEMPTS = 3


def run_wire_cycle() -> dict[str, list[dict] | int]:
    settings = get_settings()
    drafting = DraftingService()
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
    policy = WireFeedSettings()

    with SessionLocal() as db:
        candidate_repo = WireCandidateRepository(db)
        job_repo = WireJobRepository(db)
        expired = job_repo.expire_stale_jobs(now, policy)
        recent_records = job_repo.recent_post_records(now - timedelta(days=1))
        summary["skipped"] += expired

        for source in get_wire_sources():
            results = fetch_and_process(source, drafting)
            decisions = plan_wire_queue(results, recent_posts=recent_records, now=now, settings=policy)
            summary["sources_processed"] += 1
            summary["candidates"] += len(results)
            source_items: list[dict] = []
            for decision in decisions:
                candidate = candidate_repo.upsert_from_result(decision.result)
                if decision.priority == "breaking" and decision.action in {"post_now", "queue"} and decision.scheduled_for is not None:
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
                cast_items.append({"source": source.key, "decisions": source_items})

        db.commit()
        if CustomerProfileRepository(db).has_active_autopost_customer():
            publish_counts = _publish_due_jobs(db, now)
        else:
            publish_counts = {"posted": 0, "failed": 0}
        summary["posted"] = publish_counts["posted"]
        summary["failed"] = publish_counts["failed"]

    return summary


def _publish_due_jobs(db, now: datetime) -> dict[str, int]:
    job_repo = WireJobRepository(db)
    customer_repo = CustomerProfileRepository(db)
    profile = customer_repo.get_active_autopost_customer()
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
        if job_repo.has_active_duplicate(candidate.dedupe_key, exclude_job_id=job.id):
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

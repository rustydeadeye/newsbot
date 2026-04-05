from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.wire_feed import WireCandidate, WireJob, WirePublishLog
from app.wire_feed.pipeline import WirePipelineResult
from app.wire_feed.policy import WireFeedSettings, WirePostRecord, WireQueueDecision, is_stale_published_at


class WireCandidateRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def upsert_from_result(self, customer_profile_id: int, result: WirePipelineResult) -> WireCandidate:
        candidate = self.get_by_external_id(customer_profile_id, result.external_id)
        if candidate is None:
            candidate = WireCandidate(
                customer_profile_id=customer_profile_id,
                source_name=result.source_name,
                external_id=result.external_id,
                title=result.title,
                ticker=result.ticker,
                event_type=result.event_type,
                dedupe_key=result.dedupe_key,
                published_at=result.published_at,
                importance_score=result.importance_score,
                confidence_score=result.confidence_score,
                draft_text=result.draft_text,
                raw_payload={
                    **(result.raw_payload or {}),
                    "subject_key": result.subject_key,
                    "safety_flags": result.safety_flags,
                },
            )
            self.db.add(candidate)
            self.db.flush()
            return candidate

        candidate.title = result.title
        candidate.ticker = result.ticker
        candidate.event_type = result.event_type
        candidate.dedupe_key = result.dedupe_key
        candidate.published_at = result.published_at
        candidate.importance_score = result.importance_score
        candidate.confidence_score = result.confidence_score
        candidate.draft_text = result.draft_text
        candidate.raw_payload = {
            **(candidate.raw_payload or {}),
            **(result.raw_payload or {}),
            "subject_key": result.subject_key,
            "safety_flags": result.safety_flags,
        }
        self.db.flush()
        return candidate

    def get_by_external_id(self, customer_profile_id: int, external_id: str) -> WireCandidate | None:
        stmt = (
            select(WireCandidate)
            .where(WireCandidate.customer_profile_id == customer_profile_id, WireCandidate.external_id == external_id)
            .limit(1)
        )
        return self.db.scalar(stmt)

    def has_source_candidate_since(self, customer_profile_id: int, source_name: str, since: datetime) -> bool:
        stmt = (
            select(func.count())
            .select_from(WireCandidate)
            .where(
                WireCandidate.customer_profile_id == customer_profile_id,
                WireCandidate.source_name == source_name,
                WireCandidate.created_at >= since,
            )
        )
        count = self.db.scalar(stmt)
        return bool(count)


class WireJobRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def latest_for_candidate(self, candidate_id: int) -> WireJob | None:
        stmt = (
            select(WireJob)
            .where(WireJob.candidate_id == candidate_id)
            .order_by(WireJob.updated_at.desc(), WireJob.id.desc())
            .limit(1)
        )
        return self.db.scalar(stmt)

    def get(self, job_id: int) -> WireJob | None:
        return self.db.get(WireJob, job_id)

    def list_recent(self, limit: int = 50, customer_profile_id: int | None = None) -> list[WireJob]:
        stmt = select(WireJob)
        if customer_profile_id is not None:
            stmt = stmt.join(WireCandidate, WireCandidate.id == WireJob.candidate_id).where(
                WireCandidate.customer_profile_id == customer_profile_id
            )
        stmt = stmt.order_by(WireJob.updated_at.desc(), WireJob.id.desc()).limit(limit)
        return list(self.db.scalars(stmt))

    def list_upcoming(self, limit: int = 3, customer_profile_id: int | None = None) -> list[tuple[WireCandidate, WireJob]]:
        stmt: Select[tuple[WireCandidate, WireJob]] = (
            select(WireCandidate, WireJob)
            .join(WireJob, WireJob.candidate_id == WireCandidate.id)
            .where(WireJob.status.in_(("queued", "publishing")))
        )
        if customer_profile_id is not None:
            stmt = stmt.where(WireCandidate.customer_profile_id == customer_profile_id)
        stmt = stmt.order_by(func.coalesce(WireJob.scheduled_for, WireJob.updated_at).asc(), WireJob.id.asc()).limit(limit)
        return list(self.db.execute(stmt).all())

    def count_recent_failed(self, since: datetime, customer_profile_id: int | None = None) -> int:
        stmt = select(func.count()).select_from(WireJob)
        if customer_profile_id is not None:
            stmt = stmt.join(WireCandidate, WireCandidate.id == WireJob.candidate_id).where(
                WireCandidate.customer_profile_id == customer_profile_id
            )
        stmt = stmt.where(WireJob.status == "failed", WireJob.updated_at >= since)
        count = self.db.scalar(stmt)
        return int(count or 0)

    def record_decision(self, candidate: WireCandidate, decision: WireQueueDecision) -> WireJob:
        latest = self.latest_for_candidate(candidate.id)
        if latest and latest.status in {"queued", "publishing", "posted", "skipped", "failed", "cancelled"} and latest.result_message == decision.reason and latest.scheduled_for == decision.scheduled_for and latest.status == _decision_status(decision):
            candidate.last_action = decision.action
            candidate.last_reason = decision.reason
            candidate.last_scheduled_for = decision.scheduled_for
            self.db.flush()
            return latest

        if latest and latest.status in {"queued", "publishing"}:
            latest.priority = decision.priority
            latest.scheduled_for = decision.scheduled_for
            latest.result_message = decision.reason
            latest.status = _decision_status(decision)
            candidate.last_action = decision.action
            candidate.last_reason = decision.reason
            candidate.last_scheduled_for = decision.scheduled_for
            self.db.flush()
            return latest

        job = WireJob(
            candidate_id=candidate.id,
            status=_decision_status(decision),
            priority=decision.priority,
            scheduled_for=decision.scheduled_for,
            result_message=decision.reason,
        )
        self.db.add(job)
        candidate.last_action = decision.action
        candidate.last_reason = decision.reason
        candidate.last_scheduled_for = decision.scheduled_for
        self.db.flush()
        return job

    def bump_non_breaking_queue(self, earliest: datetime, settings: WireFeedSettings, customer_profile_id: int | None = None) -> int:
        stmt: Select[tuple[WireJob, WireCandidate]] = (
            select(WireJob, WireCandidate)
            .join(WireCandidate, WireCandidate.id == WireJob.candidate_id)
            .where(
                WireJob.status == "queued",
                WireJob.scheduled_for.is_not(None),
                WireJob.scheduled_for >= earliest,
                WireJob.priority.in_(("high", "normal")),
            )
            .order_by(WireJob.scheduled_for.asc(), WireJob.id.asc())
        )
        if customer_profile_id is not None:
            stmt = stmt.where(WireCandidate.customer_profile_id == customer_profile_id)
        rows = list(self.db.execute(stmt).all())
        if not rows:
            return 0

        cursor = earliest + timedelta(minutes=settings.breaking_gap_minutes)
        bumped = 0
        for job, candidate in rows:
            original_time = job.scheduled_for or cursor
            next_time = max(original_time, cursor)
            if next_time != job.scheduled_for:
                job.scheduled_for = next_time
                candidate.last_scheduled_for = next_time
                bumped += 1
            cursor = next_time + timedelta(minutes=_queue_gap_minutes(job.priority, settings))
        self.db.flush()
        return bumped

    def recent_post_records(self, since: datetime, customer_profile_id: int) -> list[WirePostRecord]:
        stmt: Select[tuple[WireCandidate, WireJob]] = (
            select(WireCandidate, WireJob)
            .join(WireJob, WireJob.candidate_id == WireCandidate.id)
            .where(
                WireCandidate.customer_profile_id == customer_profile_id,
                WireJob.status.in_(("queued", "posted", "publishing")),
                func.coalesce(WireJob.scheduled_for, WireJob.updated_at) >= since,
            )
        )
        rows = self.db.execute(stmt).all()
        return [
            WirePostRecord(
                dedupe_key=candidate.dedupe_key,
                posted_at=(job.scheduled_for or job.updated_at or datetime.now(timezone.utc)),
                priority=job.priority,
                status=job.status,
                job_id=job.id,
                source_family=str((candidate.raw_payload or {}).get("source_family") or "base"),
                source_name=candidate.source_name,
            )
            for candidate, job in rows
        ]

    def expire_stale_jobs(self, now: datetime, settings: WireFeedSettings, customer_profile_id: int | None = None) -> int:
        stmt: Select[tuple[WireJob, WireCandidate]] = (
            select(WireJob, WireCandidate)
            .join(WireCandidate, WireCandidate.id == WireJob.candidate_id)
            .where(WireJob.status == "queued")
        )
        if customer_profile_id is not None:
            stmt = stmt.where(WireCandidate.customer_profile_id == customer_profile_id)
        rows = list(self.db.execute(stmt).all())
        expired = 0
        for job, candidate in rows:
            if is_stale_published_at(candidate.published_at, job.priority, now, settings):
                job.status = "skipped"
                job.result_message = "stale_candidate"
                job.last_error = None
                candidate.last_action = "skip"
                candidate.last_reason = "stale_candidate"
                candidate.last_scheduled_for = None
                expired += 1
        if expired:
            self.db.flush()
        return expired

    def claim_ready(self, now: datetime, limit: int = 20, customer_profile_id: int | None = None) -> list[WireJob]:
        stmt = (
            select(WireJob)
            .join(WireCandidate, WireCandidate.id == WireJob.candidate_id)
            .where(WireJob.status == "queued", WireJob.scheduled_for.is_not(None), WireJob.scheduled_for <= now)
            .order_by(WireJob.scheduled_for.asc(), WireJob.id.asc())
            .with_for_update(skip_locked=True)
        )
        if customer_profile_id is not None:
            stmt = stmt.where(WireCandidate.customer_profile_id == customer_profile_id)
        stmt = stmt.limit(limit)
        jobs = list(self.db.scalars(stmt))
        for job in jobs:
            job.status = "publishing"
            job.attempt_count += 1
        self.db.flush()
        return jobs

    def has_active_duplicate(self, dedupe_key: str, exclude_job_id: int | None = None, customer_profile_id: int | None = None) -> bool:
        stmt = (
            select(func.count())
            .select_from(WireJob)
            .join(WireCandidate, WireCandidate.id == WireJob.candidate_id)
            .where(
                WireCandidate.dedupe_key == dedupe_key,
                WireJob.status.in_(("queued", "publishing", "posted")),
            )
        )
        if customer_profile_id is not None:
            stmt = stmt.where(WireCandidate.customer_profile_id == customer_profile_id)
        if exclude_job_id is not None:
            stmt = stmt.where(WireJob.id != exclude_job_id)
        count = self.db.scalar(stmt)
        return bool(count)

    def add_log(self, job_id: int, response_payload: dict, platform_post_id: str | None = None) -> WirePublishLog:
        log = WirePublishLog(
            wire_job_id=job_id,
            platform_post_id=platform_post_id,
            posted_at=datetime.now(timezone.utc),
            response_payload=response_payload,
        )
        self.db.add(log)
        self.db.flush()
        return log

    def list_logs_recent(self, limit: int = 50, customer_profile_id: int | None = None) -> list[WirePublishLog]:
        stmt = select(WirePublishLog)
        if customer_profile_id is not None:
            stmt = (
                stmt.join(WireJob, WireJob.id == WirePublishLog.wire_job_id)
                .join(WireCandidate, WireCandidate.id == WireJob.candidate_id)
                .where(WireCandidate.customer_profile_id == customer_profile_id)
            )
        stmt = stmt.order_by(WirePublishLog.posted_at.desc(), WirePublishLog.id.desc()).limit(limit)
        return list(self.db.scalars(stmt))

    def list_logs_with_candidates_recent(self, limit: int = 10, customer_profile_id: int | None = None) -> list[tuple[WirePublishLog, WireJob | None, WireCandidate | None]]:
        stmt = (
            select(WirePublishLog, WireJob, WireCandidate)
            .join(WireJob, WireJob.id == WirePublishLog.wire_job_id)
            .join(WireCandidate, WireCandidate.id == WireJob.candidate_id)
        )
        if customer_profile_id is not None:
            stmt = stmt.where(WireCandidate.customer_profile_id == customer_profile_id)
        stmt = stmt.order_by(WirePublishLog.posted_at.desc(), WirePublishLog.id.desc()).limit(limit)
        return list(self.db.execute(stmt).all())


def _decision_status(decision: WireQueueDecision) -> str:
    if decision.action == "skip":
        return "skipped"
    return "queued"


def _queue_gap_minutes(priority: str, settings: WireFeedSettings) -> int:
    if priority == "breaking":
        return settings.breaking_gap_minutes
    if priority == "high":
        return settings.high_gap_minutes
    return settings.normal_gap_minutes

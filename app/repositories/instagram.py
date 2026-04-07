from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models.instagram import InstagramCarouselDraft, InstagramPublishJob, InstagramPublishLog


class InstagramCarouselDraftRepository:
    def __init__(self, db: Session) -> None:
        self.db = db
        self._ensure_table()

    def _ensure_table(self) -> None:
        InstagramCarouselDraft.__table__.create(bind=self.db.get_bind(), checkfirst=True)
        InstagramPublishJob.__table__.create(bind=self.db.get_bind(), checkfirst=True)
        InstagramPublishLog.__table__.create(bind=self.db.get_bind(), checkfirst=True)

    def get(self, draft_id: int) -> InstagramCarouselDraft | None:
        return self.db.get(InstagramCarouselDraft, draft_id)

    def list_recent(
        self,
        *,
        limit: int = 50,
        customer_profile_id: int | None = None,
        review_status: str | None = None,
    ) -> list[InstagramCarouselDraft]:
        stmt: Select[tuple[InstagramCarouselDraft]] = select(InstagramCarouselDraft)
        if customer_profile_id is not None:
            stmt = stmt.where(InstagramCarouselDraft.customer_profile_id == customer_profile_id)
        if review_status is not None:
            stmt = stmt.where(InstagramCarouselDraft.review_status == review_status)
        stmt = stmt.order_by(InstagramCarouselDraft.updated_at.desc(), InstagramCarouselDraft.id.desc()).limit(limit)
        return list(self.db.scalars(stmt))

    def list_recent_story_clusters(self, customer_profile_id: int, *, within_days: int = 7) -> set[str]:
        since = datetime.now(timezone.utc) - timedelta(days=within_days)
        stmt = select(InstagramCarouselDraft.story_cluster).where(
            InstagramCarouselDraft.customer_profile_id == customer_profile_id,
            InstagramCarouselDraft.created_at >= since,
            InstagramCarouselDraft.review_status != "rejected",
        )
        return {cluster for cluster in self.db.scalars(stmt) if cluster}

    def add(self, draft: InstagramCarouselDraft) -> InstagramCarouselDraft:
        self.db.add(draft)
        self.db.flush()
        return draft

    def mark_review(
        self,
        draft: InstagramCarouselDraft,
        *,
        status: str,
        actor: str,
        notes: str | None = None,
    ) -> InstagramCarouselDraft:
        draft.review_status = status
        draft.review_notes = notes
        draft.reviewed_by = actor
        draft.reviewed_at = datetime.now(timezone.utc)
        self.db.flush()
        return draft

    def mark_render_state(
        self,
        draft: InstagramCarouselDraft,
        *,
        status: str,
        manifest: dict | None = None,
        error: str | None = None,
    ) -> InstagramCarouselDraft:
        draft.render_status = status
        draft.render_attempt_count = int(draft.render_attempt_count or 0) + 1
        draft.render_last_attempt_at = datetime.now(timezone.utc)
        if manifest is not None:
            draft.asset_manifest = manifest
        draft.last_error = error
        self.db.flush()
        return draft

    def mark_publish_state(
        self,
        draft: InstagramCarouselDraft,
        *,
        status: str,
        scheduled_for: datetime | None = None,
        published_at: datetime | None = None,
        error: str | None = None,
        media_container_id: str | None = None,
        publish_id: str | None = None,
    ) -> InstagramCarouselDraft:
        draft.publish_status = status
        draft.scheduled_for = scheduled_for
        draft.published_at = published_at
        draft.instagram_media_container_id = media_container_id
        draft.instagram_publish_id = publish_id
        draft.last_error = error
        if status in {"publishing", "published", "publish_failed"}:
            draft.publish_attempt_count = int(draft.publish_attempt_count or 0) + (1 if status in {"publishing", "publish_failed"} else 0)
            draft.publish_last_attempt_at = datetime.now(timezone.utc)
        self.db.flush()
        return draft

    def supersede(self, draft: InstagramCarouselDraft, *, actor: str) -> InstagramCarouselDraft:
        draft.review_status = "superseded"
        draft.publish_status = "superseded"
        draft.reviewed_by = actor
        draft.reviewed_at = datetime.now(timezone.utc)
        self.db.flush()
        return draft

    def get_publish_job(self, job_id: int) -> InstagramPublishJob | None:
        return self.db.get(InstagramPublishJob, job_id)

    def list_publish_jobs(self, *, limit: int = 50) -> list[InstagramPublishJob]:
        stmt = select(InstagramPublishJob).order_by(InstagramPublishJob.updated_at.desc(), InstagramPublishJob.id.desc()).limit(limit)
        return list(self.db.scalars(stmt))

    def list_publish_logs(self, *, limit: int = 50) -> list[InstagramPublishLog]:
        stmt = select(InstagramPublishLog).order_by(InstagramPublishLog.created_at.desc(), InstagramPublishLog.id.desc()).limit(limit)
        return list(self.db.scalars(stmt))

    def get_active_job_for_draft(self, draft_id: int) -> InstagramPublishJob | None:
        stmt = (
            select(InstagramPublishJob)
            .where(
                InstagramPublishJob.instagram_draft_id == draft_id,
                InstagramPublishJob.status.in_(("queued", "publishing")),
            )
            .order_by(InstagramPublishJob.id.desc())
            .limit(1)
        )
        return self.db.scalar(stmt)

    def add_publish_job(
        self,
        *,
        draft_id: int,
        scheduled_for: datetime | None,
        status: str = "queued",
    ) -> InstagramPublishJob:
        job = InstagramPublishJob(
            instagram_draft_id=draft_id,
            scheduled_for=scheduled_for,
            status=status,
        )
        self.db.add(job)
        self.db.flush()
        return job

    def list_due_publish_jobs(self, *, now: datetime | None = None, limit: int = 10) -> list[InstagramPublishJob]:
        current = now or datetime.now(timezone.utc)
        stmt = (
            select(InstagramPublishJob)
            .where(
                InstagramPublishJob.status == "queued",
                (InstagramPublishJob.scheduled_for.is_(None)) | (InstagramPublishJob.scheduled_for <= current),
            )
            .order_by(InstagramPublishJob.scheduled_for.asc().nullsfirst(), InstagramPublishJob.id.asc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt))

    def update_publish_job(
        self,
        job: InstagramPublishJob,
        *,
        status: str,
        error: str | None = None,
        result_message: str | None = None,
    ) -> InstagramPublishJob:
        job.status = status
        if status in {"publishing", "failed"}:
            job.attempt_count = int(job.attempt_count or 0) + (1 if status == "publishing" else 0)
        job.last_error = error
        job.result_message = result_message
        self.db.flush()
        return job

    def add_publish_log(
        self,
        *,
        job_id: int,
        platform_post_id: str | None,
        posted_at: datetime | None,
        response_payload: dict | None = None,
    ) -> InstagramPublishLog:
        log = InstagramPublishLog(
            instagram_publish_job_id=job_id,
            platform_post_id=platform_post_id,
            posted_at=posted_at,
            response_payload=response_payload or {},
        )
        self.db.add(log)
        self.db.flush()
        return log

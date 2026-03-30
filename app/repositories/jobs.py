from datetime import datetime, timezone

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models.event import DraftPost, Event
from app.models.job import PublishJob, PublishLog


class PublishJobRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, job: PublishJob) -> PublishJob:
        self.db.add(job)
        self.db.flush()
        return job

    def claim_ready(self, limit: int = 20) -> list[PublishJob]:
        now = datetime.now(timezone.utc)
        stmt: Select[tuple[PublishJob]] = (
            select(PublishJob)
            .where(PublishJob.status == "queued", or_(PublishJob.scheduled_for.is_(None), PublishJob.scheduled_for <= now))
            .with_for_update(skip_locked=True)
            .limit(limit)
        )
        jobs = list(self.db.scalars(stmt))
        for job in jobs:
            job.status = "publishing"
        self.db.flush()
        return jobs

    def list_recent(self, limit: int = 50) -> list[PublishJob]:
        stmt = select(PublishJob).order_by(PublishJob.updated_at.desc()).limit(limit)
        return list(self.db.scalars(stmt))

    def get(self, job_id: int) -> PublishJob | None:
        return self.db.get(PublishJob, job_id)

    def count_recent_posted(self, since: datetime) -> int:
        stmt = select(func.count(PublishJob.id)).where(
            PublishJob.status == "posted",
            PublishJob.updated_at >= since,
        )
        return int(self.db.scalar(stmt) or 0)

    def exists_for_draft(self, draft_post_id: int) -> bool:
        stmt = select(PublishJob.id).where(PublishJob.draft_post_id == draft_post_id).limit(1)
        return self.db.scalar(stmt) is not None

    def find_recent_conflict(
        self,
        dedupe_key: str,
        subject_key: str | None,
        since: datetime,
    ) -> int | None:
        key_conditions = [Event.dedupe_key == dedupe_key]
        if subject_key is not None:
            key_conditions.append(Event.summary_facts["subject_key"].as_string() == subject_key)
        stmt = (
            select(PublishJob.id)
            .join(DraftPost, DraftPost.id == PublishJob.draft_post_id)
            .join(Event, Event.id == DraftPost.event_id)
            .where(
                PublishJob.status.in_(("queued", "posted")),
                PublishJob.updated_at >= since,
                or_(*key_conditions),
            )
            .limit(1)
        )
        return self.db.scalar(stmt)


class PublishLogRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_recent(self, limit: int = 50) -> list[PublishLog]:
        stmt = select(PublishLog).order_by(PublishLog.created_at.desc()).limit(limit)
        return list(self.db.scalars(stmt))

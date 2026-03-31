from datetime import datetime
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin
from app.models.types import JSON_VARIANT


class PublishJob(Base, TimestampMixin):
    __tablename__ = "publish_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    draft_post_id: Mapped[int] = mapped_column(ForeignKey("draft_posts.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    result_message: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(String(36), unique=True, default=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "draft_post_id": self.draft_post_id,
            "status": self.status,
            "scheduled_for": self.scheduled_for.isoformat() if self.scheduled_for else None,
            "attempt_count": self.attempt_count,
            "last_error": self.last_error,
            "result_message": self.result_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class PublishLog(Base, TimestampMixin):
    __tablename__ = "publish_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    publish_job_id: Mapped[int] = mapped_column(ForeignKey("publish_jobs.id", ondelete="CASCADE"))
    platform_post_id: Mapped[str | None] = mapped_column(String(255))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_payload: Mapped[dict] = mapped_column(JSON_VARIANT, default=dict)
    engagement_stats: Mapped[dict] = mapped_column(JSON_VARIANT, default=dict)
    engagement_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "publish_job_id": self.publish_job_id,
            "platform_post_id": self.platform_post_id,
            "posted_at": self.posted_at.isoformat() if self.posted_at else None,
            "response_payload": self.response_payload,
            "engagement_stats": self.engagement_stats,
            "engagement_fetched_at": self.engagement_fetched_at.isoformat() if self.engagement_fetched_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

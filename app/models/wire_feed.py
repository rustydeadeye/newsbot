from datetime import datetime
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin
from app.models.types import JSON_VARIANT


class WireCandidate(Base, TimestampMixin):
    __tablename__ = "wire_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_name: Mapped[str] = mapped_column(String(100), index=True)
    external_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    title: Mapped[str] = mapped_column(Text)
    ticker: Mapped[str | None] = mapped_column(String(50), index=True)
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    dedupe_key: Mapped[str] = mapped_column(String(255), index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    importance_score: Mapped[int] = mapped_column(Integer, default=0)
    confidence_score: Mapped[float] = mapped_column(default=0.0)
    draft_text: Mapped[str] = mapped_column(Text)
    raw_payload: Mapped[dict] = mapped_column(JSON_VARIANT, default=dict)
    last_action: Mapped[str | None] = mapped_column(String(30))
    last_reason: Mapped[str | None] = mapped_column(Text)
    last_scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WireJob(Base, TimestampMixin):
    __tablename__ = "wire_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("wire_candidates.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    priority: Mapped[str] = mapped_column(String(20), default="normal")
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    result_message: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(String(36), unique=True, default=lambda: str(uuid.uuid4()))


class WirePublishLog(Base, TimestampMixin):
    __tablename__ = "wire_publish_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    wire_job_id: Mapped[int] = mapped_column(ForeignKey("wire_jobs.id", ondelete="CASCADE"))
    platform_post_id: Mapped[str | None] = mapped_column(String(255))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_payload: Mapped[dict] = mapped_column(JSON_VARIANT, default=dict)

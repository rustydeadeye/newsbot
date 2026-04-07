from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin
from app.models.types import JSON_VARIANT


class InstagramCarouselDraft(Base, TimestampMixin):
    __tablename__ = "instagram_carousel_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_profile_id: Mapped[int] = mapped_column(ForeignKey("customer_profiles.id", ondelete="CASCADE"), index=True)
    lane: Mapped[str] = mapped_column(String(50), index=True)
    seed_key: Mapped[str] = mapped_column(String(255), index=True)
    story_cluster: Mapped[str] = mapped_column(String(255), index=True)
    seed_source_name: Mapped[str] = mapped_column(String(100), index=True)
    seed_source_family: Mapped[str] = mapped_column(String(30), index=True)
    title: Mapped[str] = mapped_column(Text)
    angle: Mapped[str] = mapped_column(Text)
    hook: Mapped[str] = mapped_column(Text)
    carousel_type: Mapped[str] = mapped_column(String(80))
    slide_count: Mapped[int] = mapped_column(Integer, default=0)
    slides: Mapped[list[dict]] = mapped_column(JSON_VARIANT, default=list)
    caption: Mapped[dict] = mapped_column(JSON_VARIANT, default=dict)
    review_status: Mapped[str] = mapped_column(String(30), default="pending_review", index=True)
    review_notes: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[str | None] = mapped_column(String(255))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quality_band: Mapped[str | None] = mapped_column(String(5), index=True)
    generation_notes: Mapped[dict] = mapped_column(JSON_VARIANT, default=dict)
    template_bundle_version: Mapped[str] = mapped_column(String(50), default="instagram_template_bundle_v1")
    template_version: Mapped[str] = mapped_column(String(50), default="instagram_templates_v1")
    schema_version: Mapped[str] = mapped_column(String(50), default="instagram_carousel_schema_v1")
    render_status: Mapped[str] = mapped_column(String(30), default="render_pending", index=True)
    asset_manifest: Mapped[dict] = mapped_column(JSON_VARIANT, default=dict)
    publish_status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    instagram_media_container_id: Mapped[str | None] = mapped_column(String(255))
    instagram_publish_id: Mapped[str | None] = mapped_column(String(255))
    last_error: Mapped[str | None] = mapped_column(Text)
    render_attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    render_last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    publish_attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    publish_last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_payload: Mapped[dict] = mapped_column(JSON_VARIANT, default=dict)


class InstagramPublishJob(Base, TimestampMixin):
    __tablename__ = "instagram_publish_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instagram_draft_id: Mapped[int] = mapped_column(ForeignKey("instagram_carousel_drafts.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    result_message: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(String(36), unique=True, default=lambda: str(uuid.uuid4()))


class InstagramPublishLog(Base, TimestampMixin):
    __tablename__ = "instagram_publish_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instagram_publish_job_id: Mapped[int] = mapped_column(ForeignKey("instagram_publish_jobs.id", ondelete="CASCADE"), index=True)
    platform_post_id: Mapped[str | None] = mapped_column(String(255))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_payload: Mapped[dict] = mapped_column(JSON_VARIANT, default=dict)

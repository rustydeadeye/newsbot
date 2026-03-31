from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Event(Base, TimestampMixin):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_item_id: Mapped[int | None] = mapped_column(ForeignKey("source_items.id", ondelete="SET NULL"))
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_name: Mapped[str | None] = mapped_column(String(255), index=True)
    ticker: Mapped[str | None] = mapped_column(String(20), index=True)
    source_priority: Mapped[int] = mapped_column(Integer, default=0)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary_facts: Mapped[dict] = mapped_column(JSONB)
    importance_score: Mapped[float] = mapped_column(Float, default=0)
    confidence_score: Mapped[float] = mapped_column(Float, default=0)
    dedupe_key: Mapped[str] = mapped_column(String(255), unique=True)
    status: Mapped[str] = mapped_column(String(30), default="new")

    entities: Mapped[list["EventEntity"]] = relationship(back_populates="event")
    drafts: Mapped[list["DraftPost"]] = relationship(back_populates="event")
    review_items: Mapped[list["ReviewQueueItem"]] = relationship(back_populates="event")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "event_type": self.event_type,
            "entity_name": self.entity_name,
            "ticker": self.ticker,
            "importance_score": self.importance_score,
            "confidence_score": self.confidence_score,
            "dedupe_key": self.dedupe_key,
            "summary_facts": self.summary_facts,
            "status": self.status,
        }


class EventEntity(Base, TimestampMixin):
    __tablename__ = "event_entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_name: Mapped[str] = mapped_column(String(255))
    ticker: Mapped[str | None] = mapped_column(String(20))

    event: Mapped[Event] = relationship(back_populates="entities")


class DraftPost(Base, TimestampMixin):
    __tablename__ = "draft_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    platform: Mapped[str] = mapped_column(String(20), default="x")
    status: Mapped[str] = mapped_column(String(30), default="draft")
    prompt_version: Mapped[str] = mapped_column(String(30), default="v1")
    draft_text: Mapped[str] = mapped_column(Text)
    safety_flags: Mapped[dict] = mapped_column(JSONB, default=dict)
    needs_review: Mapped[bool] = mapped_column(default=True)

    event: Mapped[Event] = relationship(back_populates="drafts")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "event_id": self.event_id,
            "platform": self.platform,
            "status": self.status,
            "prompt_version": self.prompt_version,
            "draft_text": self.draft_text,
            "safety_flags": self.safety_flags,
            "needs_review": self.needs_review,
        }

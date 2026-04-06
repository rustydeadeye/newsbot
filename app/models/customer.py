from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin
from app.models.types import JSON_VARIANT


class CustomerProfile(Base, TimestampMixin):
    __tablename__ = "customer_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_user_id: Mapped[int] = mapped_column(ForeignKey("workspace_users.id", ondelete="CASCADE"), unique=True)
    display_name: Mapped[str | None] = mapped_column(String(255))
    tone: Mapped[str] = mapped_column(String(100), default="neutral")
    language: Mapped[str] = mapped_column(String(20), default="en")
    watchlist: Mapped[list[str]] = mapped_column(JSON_VARIANT, default=list)
    blocked_phrases: Mapped[list[str]] = mapped_column(JSON_VARIANT, default=list)
    token_store: Mapped[dict] = mapped_column(JSON_VARIANT, default=dict)
    wire_product: Mapped[str] = mapped_column(String(30), default="finance")
    automation_mode: Mapped[str] = mapped_column(String(60), default="auto_generate_manual_review")
    freshness_window_hours: Mapped[int] = mapped_column(Integer, default=12)
    max_posts_per_hour: Mapped[int] = mapped_column(Integer, default=6)
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Kolkata")
    posting_window_start: Mapped[int | None] = mapped_column(Integer)
    posting_window_end: Mapped[int | None] = mapped_column(Integer)
    auto_post_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_post_threshold: Mapped[int] = mapped_column(Integer, default=85)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def to_dict(self) -> dict:
        store = self.token_store or {}
        display_name = self.display_name.strip() if self.display_name else None
        source_families = store.get("source_families") or ["base", "web"]
        source_families = [family for family in source_families if family in {"base", "web"}]
        if not source_families:
            source_families = ["base", "web"]
        return {
            "id": self.id,
            "workspace_user_id": self.workspace_user_id,
            "display_name": display_name,
            "primary_platform": "x",
            "tone": self.tone,
            "language": self.language,
            "wire_product": self.wire_product,
            "automation_mode": self.automation_mode,
            "freshness_window_hours": self.freshness_window_hours,
            "max_posts_per_hour": self.max_posts_per_hour,
            "watchlist": self.watchlist,
            "blocked_phrases": self.blocked_phrases,
            "timezone": self.timezone,
            "posting_window_start": self.posting_window_start,
            "posting_window_end": self.posting_window_end,
            "openai_configured": bool(store.get("openai_api_key")),
            "tavily_configured": bool(store.get("tavily_api_key")),
            "x_connected": bool(store.get("x_access_token")),
            "source_families": source_families,
            "base_source_enabled": "base" in source_families,
            "web_source_enabled": "web" in source_families,
            "auto_post_enabled": self.auto_post_enabled,
            "auto_post_threshold": self.auto_post_threshold,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
            "onboarding_completed": self.onboarding_completed_at is not None,
            "onboarding_completed_at": self.onboarding_completed_at.isoformat() if self.onboarding_completed_at else None,
            "publishing_ready": bool(store.get("x_access_token")) and bool(store.get("openai_api_key")) and bool(store.get("tavily_api_key")),
        }

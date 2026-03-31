from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
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
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def to_dict(self) -> dict:
        store = self.token_store or {}
        display_name = self.display_name.strip() if self.display_name else None
        return {
            "id": self.id,
            "workspace_user_id": self.workspace_user_id,
            "display_name": display_name,
            "primary_platform": "x",
            "tone": self.tone,
            "language": self.language,
            "max_posts_per_hour": 6,
            "watchlist": self.watchlist,
            "blocked_phrases": self.blocked_phrases,
            "timezone": "Asia/Kolkata",
            "posting_window_start": None,
            "posting_window_end": None,
            "openai_configured": bool(store.get("openai_api_key")),
            "x_connected": bool(store.get("x_access_token")),
            "onboarding_completed": self.onboarding_completed_at is not None,
            "onboarding_completed_at": self.onboarding_completed_at.isoformat() if self.onboarding_completed_at else None,
            "publishing_ready": bool(store.get("x_access_token")),
        }

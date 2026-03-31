from sqlalchemy import Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class CreatorSettings(Base, TimestampMixin):
    __tablename__ = "creator_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    display_name: Mapped[str] = mapped_column(String(255))
    primary_platform: Mapped[str] = mapped_column(String(50), default="x")
    tone: Mapped[str] = mapped_column(String(100), default="neutral")
    language: Mapped[str] = mapped_column(String(20), default="en")
    max_posts_per_hour: Mapped[int] = mapped_column(Integer, default=6)
    watchlist: Mapped[list[str]] = mapped_column(JSONB, default=list)
    blocked_phrases: Mapped[list[str]] = mapped_column(JSONB, default=list)
    # OAuth token persistence — stores {"x_access_token": "...", "x_refresh_token": "..."}
    token_store: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Posting window — IST hour integers (0–23), None means no restriction
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Kolkata")
    posting_window_start: Mapped[int | None] = mapped_column(Integer)
    posting_window_end: Mapped[int | None] = mapped_column(Integer)

    def to_dict(self) -> dict:
        store = self.token_store or {}
        return {
            "id": self.id,
            "display_name": self.display_name,
            "primary_platform": self.primary_platform,
            "tone": self.tone,
            "language": self.language,
            "max_posts_per_hour": self.max_posts_per_hour,
            "watchlist": self.watchlist,
            "blocked_phrases": self.blocked_phrases,
            "timezone": self.timezone,
            "posting_window_start": self.posting_window_start,
            "posting_window_end": self.posting_window_end,
            "x_connected": bool(store.get("x_access_token")),
            "openai_configured": bool(store.get("openai_api_key")),
        }

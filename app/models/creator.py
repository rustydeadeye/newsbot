from sqlalchemy import JSON, Integer, String
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
    watchlist: Mapped[list[str]] = mapped_column(JSON, default=list)
    blocked_phrases: Mapped[list[str]] = mapped_column(JSON, default=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "primary_platform": self.primary_platform,
            "tone": self.tone,
            "language": self.language,
            "max_posts_per_hour": self.max_posts_per_hour,
            "watchlist": self.watchlist,
            "blocked_phrases": self.blocked_phrases,
        }

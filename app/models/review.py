from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class ReviewQueueItem(Base, TimestampMixin):
    __tablename__ = "review_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    reason: Mapped[str] = mapped_column(String(255))
    assigned_to: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30), default="open")

    event: Mapped["Event"] = relationship(back_populates="review_items")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "event_id": self.event_id,
            "reason": self.reason,
            "assigned_to": self.assigned_to,
            "status": self.status,
        }

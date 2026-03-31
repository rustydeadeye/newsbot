from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

_DEFAULT_SLA_HOURS = 2


class ReviewQueueItem(Base, TimestampMixin):
    __tablename__ = "review_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    reason: Mapped[str] = mapped_column(String(255))
    assigned_to: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30), default="open")
    sla_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    event: Mapped["Event"] = relationship(back_populates="review_items")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "event_id": self.event_id,
            "reason": self.reason,
            "assigned_to": self.assigned_to,
            "status": self.status,
            "sla_due_at": self.sla_due_at.isoformat() if self.sla_due_at else None,
            "overdue": self._is_overdue(),
        }

    def _is_overdue(self) -> bool:
        from datetime import timezone
        if self.status != "open" or self.sla_due_at is None:
            return False
        return datetime.now(timezone.utc) > self.sla_due_at

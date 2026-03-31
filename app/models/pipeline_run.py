from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin
from app.models.types import JSON_VARIANT


class PipelineRun(Base, TimestampMixin):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_user_id: Mapped[int | None] = mapped_column(ForeignKey("workspace_users.id", ondelete="SET NULL"))
    requested_by: Mapped[str] = mapped_column(String(255))
    scope: Mapped[str] = mapped_column(String(50), default="customer_generate_drafts")
    status: Mapped[str] = mapped_column(String(30), default="queued")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_counts: Mapped[dict] = mapped_column(JSON_VARIANT, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "workspace_user_id": self.workspace_user_id,
            "requested_by": self.requested_by,
            "scope": self.scope,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "result_counts": self.result_counts or {},
            "error_message": self.error_message,
        }

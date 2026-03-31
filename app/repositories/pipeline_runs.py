from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.pipeline_run import PipelineRun


class PipelineRunRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, run: PipelineRun) -> PipelineRun:
        self.db.add(run)
        self.db.flush()
        return run

    def latest_for_workspace_user(self, workspace_user_id: int) -> PipelineRun | None:
        stmt = (
            select(PipelineRun)
            .where(PipelineRun.workspace_user_id == workspace_user_id)
            .order_by(desc(PipelineRun.created_at))
            .limit(1)
        )
        return self.db.scalar(stmt)

    def active_for_workspace_user(self, workspace_user_id: int) -> PipelineRun | None:
        stmt = (
            select(PipelineRun)
            .where(
                PipelineRun.workspace_user_id == workspace_user_id,
                PipelineRun.status.in_(("queued", "running")),
            )
            .order_by(desc(PipelineRun.created_at))
            .limit(1)
        )
        return self.db.scalar(stmt)

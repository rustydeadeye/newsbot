from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.api.security import ViewerContext, get_current_viewer, require_admin
from app.db.session import get_db
from app.models.pipeline_run import PipelineRun
from app.repositories.pipeline_runs import PipelineRunRepository
from app.workers.runner import run_cycle
from app.workers.runner import run_customer_generation
from sqlalchemy.orm import Session

router = APIRouter()


@router.post("/run", dependencies=[Depends(require_admin)])
def trigger_pipeline_run() -> dict:
    """Manually trigger a full pipeline cycle. Returns ingestion and processing counts."""
    return run_cycle()


@router.post("/generate-drafts", dependencies=[])
def generate_customer_drafts(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    viewer: ViewerContext = Depends(get_current_viewer),
) -> dict:
    if not viewer.is_customer:
        raise HTTPException(status_code=403, detail="Customer access required")
    run_repo = PipelineRunRepository(db)
    active = run_repo.active_for_workspace_user(viewer.workspace_user_id)
    if active is not None:
        return active.to_dict()
    run = run_repo.add(
        PipelineRun(
            workspace_user_id=viewer.workspace_user_id,
            requested_by=viewer.email,
            scope="customer_generate_drafts",
            status="queued",
        )
    )
    db.commit()
    background_tasks.add_task(run_customer_generation, run.id, viewer.workspace_user_id)
    return run.to_dict()


@router.get("/runs/current", dependencies=[])
def get_current_pipeline_run(
    db: Session = Depends(get_db),
    viewer: ViewerContext = Depends(get_current_viewer),
) -> dict | None:
    if viewer.is_admin:
        return None
    run_repo = PipelineRunRepository(db)
    active = run_repo.active_for_workspace_user(viewer.workspace_user_id)
    if active is not None:
        return active.to_dict()
    latest = run_repo.latest_for_workspace_user(viewer.workspace_user_id)
    return latest.to_dict() if latest is not None else None

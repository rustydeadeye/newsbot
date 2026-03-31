from fastapi import APIRouter, Depends

from app.api.security import require_admin
from app.workers.runner import run_cycle

router = APIRouter(dependencies=[Depends(require_admin)])


@router.post("/run")
def trigger_pipeline_run() -> dict:
    """Manually trigger a full pipeline cycle. Returns ingestion and processing counts."""
    return run_cycle()

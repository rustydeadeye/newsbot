from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.schemas import PublishJobRetryAction, PublishJobScheduleAction
from app.api.security import ViewerContext, get_current_viewer
from app.db.session import get_db
from app.repositories.drafts import DraftRepository
from app.repositories.events import EventRepository
from app.repositories.jobs import PublishJobRepository, PublishLogRepository

router = APIRouter()


@router.get("")
def list_publish_jobs(
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
    viewer: ViewerContext = Depends(get_current_viewer),
) -> list[dict]:
    job_repo = PublishJobRepository(db)
    event_repo = EventRepository(db)
    draft_repo = DraftRepository(db)
    payload: list[dict] = []
    jobs = job_repo.list_recent_for_workspace_user(viewer.workspace_user_id, limit=limit) if viewer.is_customer else job_repo.list_recent(limit=limit)
    for job in jobs:
        draft = draft_repo.get(job.draft_post_id)
        event = event_repo.get(draft.event_id) if draft else None
        payload.append(
            {
                **job.to_dict(),
                "draft": draft.to_dict() if draft else None,
                "event": event.to_dict() if event else None,
            }
        )
    return payload


@router.get("/logs")
def list_publish_logs(
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
    viewer: ViewerContext = Depends(get_current_viewer),
) -> list[dict]:
    if viewer.is_customer:
        raise HTTPException(status_code=403, detail="Admin access required")
    return [log.to_dict() for log in PublishLogRepository(db).list_recent(limit=limit)]


@router.post("/{job_id}/cancel")
def cancel_publish_job(
    job_id: int,
    db: Session = Depends(get_db),
    viewer: ViewerContext = Depends(get_current_viewer),
) -> dict:
    job_repo = PublishJobRepository(db)
    job = job_repo.get_for_workspace_user(job_id, viewer.workspace_user_id) if viewer.is_customer else job_repo.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Publish job not found")

    if job.status not in ("queued", "skipped"):
        raise HTTPException(status_code=409, detail="Only queued or skipped jobs can be cancelled")

    draft = DraftRepository(db).get(job.draft_post_id)
    job.status = "cancelled"
    job.result_message = "cancelled_by_customer" if viewer.is_customer else "cancelled_by_admin"
    if draft is not None and viewer.is_customer:
        draft.status = "approved"
        draft.needs_review = False
    db.commit()
    return job.to_dict()


@router.post("/{job_id}/retry")
def retry_publish_job(
    job_id: int,
    action: PublishJobRetryAction,
    db: Session = Depends(get_db),
    viewer: ViewerContext = Depends(get_current_viewer),
) -> dict:
    job_repo = PublishJobRepository(db)
    job = job_repo.get_for_workspace_user(job_id, viewer.workspace_user_id) if viewer.is_customer else job_repo.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Publish job not found")

    if job.status not in ("failed", "skipped"):
        raise HTTPException(status_code=409, detail="Only failed or skipped jobs can be retried")

    job.status = "queued"
    job.last_error = None
    if action.scheduled_for:
        job.scheduled_for = action.scheduled_for
    db.commit()
    return job.to_dict()


@router.post("/{job_id}/schedule")
def reschedule_publish_job(
    job_id: int,
    action: PublishJobScheduleAction,
    db: Session = Depends(get_db),
    viewer: ViewerContext = Depends(get_current_viewer),
) -> dict:
    job_repo = PublishJobRepository(db)
    job = job_repo.get_for_workspace_user(job_id, viewer.workspace_user_id) if viewer.is_customer else job_repo.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Publish job not found")
    if job.status not in ("queued", "failed", "skipped", "cancelled"):
        raise HTTPException(status_code=409, detail="This publish job cannot be rescheduled")
    job.status = "queued"
    job.scheduled_for = action.scheduled_for
    job.last_error = None
    draft = DraftRepository(db).get(job.draft_post_id)
    if draft is not None:
        draft.status = "queued"
        draft.needs_review = False
    db.commit()
    return job.to_dict()

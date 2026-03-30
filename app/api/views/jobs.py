from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.schemas import PublishJobRetryAction
from app.db.session import get_db
from app.models.event import DraftPost
from app.repositories.drafts import DraftRepository
from app.repositories.events import EventRepository
from app.repositories.jobs import PublishJobRepository, PublishLogRepository

router = APIRouter()


@router.get("")
def list_publish_jobs(limit: int = Query(default=50, le=200), db: Session = Depends(get_db)) -> list[dict]:
    job_repo = PublishJobRepository(db)
    event_repo = EventRepository(db)
    draft_repo = DraftRepository(db)
    payload: list[dict] = []
    for job in job_repo.list_recent(limit=limit):
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
def list_publish_logs(limit: int = Query(default=50, le=200), db: Session = Depends(get_db)) -> list[dict]:
    return [log.to_dict() for log in PublishLogRepository(db).list_recent(limit=limit)]


@router.post("/{job_id}/retry")
def retry_publish_job(job_id: int, action: PublishJobRetryAction, db: Session = Depends(get_db)) -> dict:
    job_repo = PublishJobRepository(db)
    job = job_repo.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Publish job not found")

    job.status = "queued"
    job.last_error = None
    if action.scheduled_for:
        job.scheduled_for = datetime.fromisoformat(action.scheduled_for)
    db.commit()
    return job.to_dict()

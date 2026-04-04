from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.schemas import PublishJobRetryAction
from app.api.security import ViewerContext, require_admin
from app.db.session import get_db
from app.models.wire_feed import WireCandidate
from app.repositories.wire_feed import WireJobRepository

router = APIRouter()


@router.get("/wire")
def list_wire_jobs(
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
    _viewer: ViewerContext = Depends(require_admin),
) -> list[dict]:
    job_repo = WireJobRepository(db)
    payload: list[dict] = []
    for job in job_repo.list_recent(limit=limit):
        candidate = db.get(WireCandidate, job.candidate_id)
        payload.append(
            {
                "id": job.id,
                "candidate_id": job.candidate_id,
                "status": job.status,
                "priority": job.priority,
                "scheduled_for": job.scheduled_for.isoformat() if job.scheduled_for else None,
                "attempt_count": job.attempt_count,
                "last_error": job.last_error,
                "result_message": job.result_message,
                "idempotency_key": job.idempotency_key,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "updated_at": job.updated_at.isoformat() if job.updated_at else None,
                "candidate": {
                    "id": candidate.id,
                    "source_name": candidate.source_name,
                    "external_id": candidate.external_id,
                    "title": candidate.title,
                    "ticker": candidate.ticker,
                    "event_type": candidate.event_type,
                    "dedupe_key": candidate.dedupe_key,
                    "importance_score": candidate.importance_score,
                    "confidence_score": candidate.confidence_score,
                    "draft_text": candidate.draft_text,
                    "published_at": candidate.published_at.isoformat() if candidate.published_at else None,
                    "last_action": candidate.last_action,
                    "last_reason": candidate.last_reason,
                    "last_scheduled_for": candidate.last_scheduled_for.isoformat() if candidate.last_scheduled_for else None,
                } if candidate else None,
            }
        )
    return payload


@router.get("/wire/logs")
def list_wire_logs(
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
    _viewer: ViewerContext = Depends(require_admin),
) -> list[dict]:
    job_repo = WireJobRepository(db)
    payload: list[dict] = []
    for log in job_repo.list_logs_recent(limit=limit):
        job = job_repo.get(log.wire_job_id)
        candidate = db.get(WireCandidate, job.candidate_id) if job else None
        payload.append(
            {
                "id": log.id,
                "wire_job_id": log.wire_job_id,
                "platform_post_id": log.platform_post_id,
                "posted_at": log.posted_at.isoformat() if log.posted_at else None,
                "response_payload": log.response_payload,
                "created_at": log.created_at.isoformat() if log.created_at else None,
                "job": {
                    "id": job.id,
                    "status": job.status,
                    "priority": job.priority,
                    "scheduled_for": job.scheduled_for.isoformat() if job and job.scheduled_for else None,
                } if job else None,
                "candidate": {
                    "id": candidate.id,
                    "title": candidate.title,
                    "ticker": candidate.ticker,
                    "draft_text": candidate.draft_text,
                    "source_name": candidate.source_name,
                } if candidate else None,
            }
        )
    return payload


@router.post("/wire/{job_id}/retry")
def retry_wire_job(
    job_id: int,
    action: PublishJobRetryAction,
    db: Session = Depends(get_db),
    _viewer: ViewerContext = Depends(require_admin),
) -> dict:
    job_repo = WireJobRepository(db)
    job = job_repo.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Wire job not found")
    if job.status not in ("failed", "skipped", "cancelled"):
        raise HTTPException(status_code=409, detail="Only failed, skipped, or cancelled wire jobs can be retried")
    job.status = "queued"
    job.last_error = None
    job.result_message = "manual_retry"
    if action.scheduled_for:
        job.scheduled_for = action.scheduled_for
    db.commit()
    candidate = db.get(WireCandidate, job.candidate_id)
    return {
        "id": job.id,
        "status": job.status,
        "scheduled_for": job.scheduled_for.isoformat() if job.scheduled_for else None,
        "attempt_count": job.attempt_count,
        "last_error": job.last_error,
        "result_message": job.result_message,
        "candidate": {
            "id": candidate.id,
            "title": candidate.title,
            "ticker": candidate.ticker,
            "draft_text": candidate.draft_text,
        } if candidate else None,
    }


@router.post("/wire/{job_id}/cancel")
def cancel_wire_job(
    job_id: int,
    db: Session = Depends(get_db),
    _viewer: ViewerContext = Depends(require_admin),
) -> dict:
    job_repo = WireJobRepository(db)
    job = job_repo.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Wire job not found")
    if job.status not in ("queued", "publishing"):
        raise HTTPException(status_code=409, detail="Only queued or publishing wire jobs can be cancelled")
    job.status = "cancelled"
    job.result_message = "cancelled_by_admin"
    job.last_error = None
    db.commit()
    candidate = db.get(WireCandidate, job.candidate_id)
    return {
        "id": job.id,
        "status": job.status,
        "scheduled_for": job.scheduled_for.isoformat() if job.scheduled_for else None,
        "attempt_count": job.attempt_count,
        "last_error": job.last_error,
        "result_message": job.result_message,
        "candidate": {
            "id": candidate.id,
            "title": candidate.title,
            "ticker": candidate.ticker,
            "draft_text": candidate.draft_text,
        } if candidate else None,
    }

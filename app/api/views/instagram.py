from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.schemas import InstagramDraftGenerateRequest, InstagramDraftReviewAction, InstagramDraftScheduleAction
from app.api.security import ViewerContext, require_admin
from app.db.session import get_db
from app.instagram_pipeline.runtime import (
    publish_instagram_job,
    render_instagram_draft,
    schedule_instagram_draft,
    serialize_instagram_publish_job,
    serialize_instagram_publish_log,
)
from app.instagram_pipeline.service import (
    generate_instagram_drafts_for_profile,
    list_instagram_generation_profiles,
    regenerate_instagram_draft,
    serialize_instagram_draft,
)
from app.models.customer import CustomerProfile
from app.repositories.instagram import InstagramCarouselDraftRepository

router = APIRouter()


@router.get("/drafts")
def list_instagram_drafts(
    limit: int = Query(default=50, le=200),
    review_status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _viewer: ViewerContext = Depends(require_admin),
) -> list[dict]:
    repo = InstagramCarouselDraftRepository(db)
    return [serialize_instagram_draft(draft) for draft in repo.list_recent(limit=limit, review_status=review_status)]


@router.get("/publish-jobs")
def list_instagram_publish_jobs(
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
    _viewer: ViewerContext = Depends(require_admin),
) -> list[dict]:
    repo = InstagramCarouselDraftRepository(db)
    jobs = repo.list_publish_jobs(limit=limit)
    drafts = {draft.id: draft for draft in repo.list_recent(limit=limit * 2)}
    return [serialize_instagram_publish_job(job, drafts.get(job.instagram_draft_id)) for job in jobs]


@router.get("/publish-logs")
def list_instagram_publish_logs(
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
    _viewer: ViewerContext = Depends(require_admin),
) -> list[dict]:
    repo = InstagramCarouselDraftRepository(db)
    return [serialize_instagram_publish_log(log) for log in repo.list_publish_logs(limit=limit)]


@router.post("/drafts/generate")
def generate_instagram_drafts(
    action: InstagramDraftGenerateRequest,
    db: Session = Depends(get_db),
    _viewer: ViewerContext = Depends(require_admin),
) -> list[dict]:
    profiles: list[CustomerProfile]
    if action.customer_profile_id is not None:
        profile = db.get(CustomerProfile, action.customer_profile_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="Customer profile not found")
        profiles = [profile]
    else:
        profiles = list_instagram_generation_profiles(db)
    generated: list[dict] = []
    for profile in profiles:
        drafts = generate_instagram_drafts_for_profile(db, profile, limit_per_lane=action.limit_per_lane)
        generated.extend(serialize_instagram_draft(draft) for draft in drafts)
    db.commit()
    return generated


@router.post("/drafts/{draft_id}/approve")
def approve_instagram_draft(
    draft_id: int,
    action: InstagramDraftReviewAction,
    db: Session = Depends(get_db),
    viewer: ViewerContext = Depends(require_admin),
) -> dict:
    repo = InstagramCarouselDraftRepository(db)
    draft = repo.get(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Instagram draft not found")
    repo.mark_review(draft, status="approved", actor=viewer.actor_name, notes=action.notes)
    db.commit()
    return serialize_instagram_draft(draft)


@router.post("/drafts/{draft_id}/reject")
def reject_instagram_draft(
    draft_id: int,
    action: InstagramDraftReviewAction,
    db: Session = Depends(get_db),
    viewer: ViewerContext = Depends(require_admin),
) -> dict:
    repo = InstagramCarouselDraftRepository(db)
    draft = repo.get(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Instagram draft not found")
    repo.mark_review(draft, status="rejected", actor=viewer.actor_name, notes=action.notes)
    db.commit()
    return serialize_instagram_draft(draft)


@router.post("/drafts/{draft_id}/regenerate")
def regenerate_instagram_draft_view(
    draft_id: int,
    action: InstagramDraftReviewAction,
    db: Session = Depends(get_db),
    viewer: ViewerContext = Depends(require_admin),
) -> dict:
    repo = InstagramCarouselDraftRepository(db)
    draft = repo.get(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Instagram draft not found")
    regenerated = regenerate_instagram_draft(db, draft, actor=viewer.actor_name)
    if regenerated is None:
        raise HTTPException(status_code=409, detail="Instagram draft could not be regenerated from its saved seed")
    if action.notes:
        regenerated.review_notes = action.notes
    db.commit()
    return serialize_instagram_draft(regenerated)


@router.post("/drafts/{draft_id}/render")
def render_instagram_draft_view(
    draft_id: int,
    db: Session = Depends(get_db),
    _viewer: ViewerContext = Depends(require_admin),
) -> dict:
    repo = InstagramCarouselDraftRepository(db)
    draft = repo.get(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Instagram draft not found")
    rendered = render_instagram_draft(db, draft)
    db.commit()
    return serialize_instagram_draft(rendered)


@router.post("/drafts/render-approved")
def render_approved_instagram_drafts(
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    _viewer: ViewerContext = Depends(require_admin),
) -> list[dict]:
    repo = InstagramCarouselDraftRepository(db)
    rendered: list[dict] = []
    for draft in repo.list_recent(limit=limit):
        if draft.review_status != "approved":
            continue
        rendered.append(serialize_instagram_draft(render_instagram_draft(db, draft)))
    db.commit()
    return rendered


@router.post("/drafts/{draft_id}/schedule")
def schedule_instagram_draft_view(
    draft_id: int,
    action: InstagramDraftScheduleAction,
    db: Session = Depends(get_db),
    _viewer: ViewerContext = Depends(require_admin),
) -> dict:
    repo = InstagramCarouselDraftRepository(db)
    draft = repo.get(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Instagram draft not found")
    try:
        schedule_instagram_draft(db, draft, scheduled_for=action.scheduled_for or datetime.now(timezone.utc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return serialize_instagram_draft(draft)


@router.post("/drafts/{draft_id}/publish-now")
def publish_instagram_draft_now_view(
    draft_id: int,
    db: Session = Depends(get_db),
    _viewer: ViewerContext = Depends(require_admin),
) -> dict:
    repo = InstagramCarouselDraftRepository(db)
    draft = repo.get(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Instagram draft not found")
    try:
        job = schedule_instagram_draft(db, draft, scheduled_for=datetime.now(timezone.utc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    publish_instagram_job(db, job)
    db.commit()
    refreshed = repo.get(draft_id)
    return serialize_instagram_draft(refreshed or draft)

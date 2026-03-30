from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import DraftRejectAction, DraftReviewAction, ReviewResolveAction
from app.api.security import ViewerContext, get_current_viewer
from app.db.session import get_db
from app.pipeline import enqueue_approved_draft
from app.repositories.drafts import DraftRepository
from app.repositories.events import EventRepository
from app.repositories.review import ReviewQueueRepository

router = APIRouter()


@router.get("")
def list_review_queue(
    db: Session = Depends(get_db),
    viewer: ViewerContext = Depends(get_current_viewer),
) -> list[dict]:
    review_repo = ReviewQueueRepository(db)
    event_repo = EventRepository(db)
    draft_repo = DraftRepository(db)
    payload: list[dict] = []
    for item in review_repo.list_open():
        event = event_repo.get(item.event_id)
        draft = draft_repo.latest_for_event(item.event_id)
        event_payload = event.to_dict() if event else None
        if event_payload and viewer.is_customer:
            event_payload.pop("dedupe_key", None)
            event_payload.pop("status", None)
        payload.append(
            {
                **item.to_dict(),
                "event": event_payload,
                "draft": draft.to_dict() if draft else None,
            }
        )
    return payload


@router.get("/drafts")
def list_review_drafts(
    db: Session = Depends(get_db),
    viewer: ViewerContext = Depends(get_current_viewer),
) -> list[dict]:
    draft_repo = DraftRepository(db)
    event_repo = EventRepository(db)
    drafts = []
    for draft in draft_repo.list_needing_review():
        event = event_repo.get(draft.event_id)
        event_payload = event.to_dict() if event else None
        if event_payload and viewer.is_customer:
            event_payload.pop("dedupe_key", None)
            event_payload.pop("status", None)
        drafts.append({**draft.to_dict(), "event": event_payload})
    return drafts


@router.post("/drafts/{draft_id}/approve")
def approve_draft(
    draft_id: int,
    action: DraftReviewAction,
    db: Session = Depends(get_db),
    viewer: ViewerContext = Depends(get_current_viewer),
) -> dict:
    draft_repo = DraftRepository(db)
    review_repo = ReviewQueueRepository(db)
    draft = draft_repo.get(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")

    if action.edited_text:
        draft.draft_text = action.edited_text.strip()
    draft.needs_review = False
    draft.status = "approved"
    reviewer = action.reviewer or viewer.actor_name
    draft.safety_flags = {**draft.safety_flags, "reviewed_by": reviewer}

    for item in review_repo.list_open_for_event(draft.event_id):
        item.status = "resolved"
        item.assigned_to = reviewer

    queued = False
    if action.auto_queue and viewer.is_admin:
        queued = enqueue_approved_draft(db, draft.id)

    db.commit()
    return {"draft": draft.to_dict(), "queued": queued}


@router.post("/drafts/{draft_id}/reject")
def reject_draft(
    draft_id: int,
    action: DraftRejectAction,
    db: Session = Depends(get_db),
    viewer: ViewerContext = Depends(get_current_viewer),
) -> dict:
    draft_repo = DraftRepository(db)
    review_repo = ReviewQueueRepository(db)
    draft = draft_repo.get(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")

    reviewer = action.reviewer or viewer.actor_name
    draft.status = "rejected"
    draft.needs_review = False
    draft.safety_flags = {**draft.safety_flags, "rejected_by": reviewer, "rejection_reason": action.reason}

    for item in review_repo.list_open_for_event(draft.event_id):
        item.status = "rejected"
        item.assigned_to = reviewer

    db.commit()
    return {"draft": draft.to_dict()}


@router.post("/items/{review_id}/resolve")
def resolve_review_item(
    review_id: int,
    action: ReviewResolveAction,
    db: Session = Depends(get_db),
    viewer: ViewerContext = Depends(get_current_viewer),
) -> dict:
    review_repo = ReviewQueueRepository(db)
    item = review_repo.get(review_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Review item not found")

    item.status = action.status
    item.assigned_to = action.reviewer or viewer.email
    db.commit()
    return item.to_dict()

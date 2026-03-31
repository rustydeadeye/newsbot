from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import DraftRejectAction, DraftReviewAction, ReviewResolveAction
from app.api.security import ViewerContext, get_current_viewer
from app.db.session import get_db
from app.models.job import PublishJob
from app.models.review import ReviewQueueItem
from app.pipeline import enqueue_approved_draft
from app.repositories.creators import CreatorSettingsRepository
from app.repositories.customers import CustomerProfileRepository
from app.repositories.drafts import DraftRepository
from app.repositories.events import EventRepository
from app.repositories.jobs import PublishJobRepository
from app.repositories.review import ReviewQueueRepository

router = APIRouter()


def _serialize_event(event, viewer: ViewerContext) -> dict | None:
    if event is None:
        return None
    payload = event.to_dict()
    if viewer.is_customer:
        payload.pop("dedupe_key", None)
        payload.pop("status", None)
    return payload


def _viewer_draft(draft_repo: DraftRepository, event_id: int, viewer: ViewerContext):
    return draft_repo.latest_for_event(event_id, viewer.workspace_user_id if viewer.is_customer else None)


def _serialize_draft(draft, job_repo: PublishJobRepository | None = None) -> dict:
    payload = draft.to_dict()
    if job_repo is not None:
        publish_job = job_repo.latest_for_draft(draft.id)
        payload["publish_job"] = publish_job.to_dict() if publish_job else None
    return payload


def _review_queue_payload(db: Session, viewer: ViewerContext) -> list[dict]:
    review_repo = ReviewQueueRepository(db)
    event_repo = EventRepository(db)
    draft_repo = DraftRepository(db)
    items = review_repo.list_open_for_workspace_user(viewer.workspace_user_id) if viewer.is_customer else review_repo.list_open()
    payload: list[dict] = []
    for item in items:
        event = event_repo.get(item.event_id)
        draft = _viewer_draft(draft_repo, item.event_id, viewer)
        payload.append({**item.to_dict(), "event": _serialize_event(event, viewer), "draft": draft.to_dict() if draft else None})
    return payload


def _review_drafts_payload(db: Session, viewer: ViewerContext) -> list[dict]:
    draft_repo = DraftRepository(db)
    event_repo = EventRepository(db)
    drafts = (
        draft_repo.list_needing_review_for_workspace_user(viewer.workspace_user_id)
        if viewer.is_customer
        else draft_repo.list_needing_review()
    )
    payload = []
    for draft in drafts:
        event = event_repo.get(draft.event_id)
        payload.append({**draft.to_dict(), "event": _serialize_event(event, viewer)})
    return payload


def _approved_drafts_payload(db: Session, viewer: ViewerContext) -> list[dict]:
    draft_repo = DraftRepository(db)
    event_repo = EventRepository(db)
    job_repo = PublishJobRepository(db)
    drafts = (
        draft_repo.list_customer_post_approval_for_workspace_user(viewer.workspace_user_id)
        if viewer.is_customer
        else []
    )
    payload = []
    for draft in drafts:
        event = event_repo.get(draft.event_id)
        payload.append({**_serialize_draft(draft, job_repo), "event": _serialize_event(event, viewer)})
    return payload


def _rejected_drafts_payload(db: Session, viewer: ViewerContext) -> list[dict]:
    draft_repo = DraftRepository(db)
    event_repo = EventRepository(db)
    drafts = (
        draft_repo.list_rejected_for_workspace_user(viewer.workspace_user_id)
        if viewer.is_customer
        else draft_repo.list_rejected()
    )
    payload = []
    for draft in drafts:
        event = event_repo.get(draft.event_id)
        payload.append({**draft.to_dict(), "event": _serialize_event(event, viewer)})
    return payload


@router.get("")
def list_review_queue(
    db: Session = Depends(get_db),
    viewer: ViewerContext = Depends(get_current_viewer),
) -> list[dict]:
    return _review_queue_payload(db, viewer)


@router.get("/overdue")
def list_overdue_review_items(
    db: Session = Depends(get_db),
    viewer: ViewerContext = Depends(get_current_viewer),
) -> list[dict]:
    review_repo = ReviewQueueRepository(db)
    event_repo = EventRepository(db)
    draft_repo = DraftRepository(db)
    items = review_repo.list_overdue_for_workspace_user(viewer.workspace_user_id) if viewer.is_customer else review_repo.list_overdue()
    payload: list[dict] = []
    for item in items:
        event = event_repo.get(item.event_id)
        draft = _viewer_draft(draft_repo, item.event_id, viewer)
        payload.append({**item.to_dict(), "event": _serialize_event(event, viewer), "draft": draft.to_dict() if draft else None})
    return payload


@router.get("/drafts")
def list_review_drafts(
    db: Session = Depends(get_db),
    viewer: ViewerContext = Depends(get_current_viewer),
) -> list[dict]:
    return _review_drafts_payload(db, viewer)


@router.get("/drafts/approved")
def list_approved_drafts(
    db: Session = Depends(get_db),
    viewer: ViewerContext = Depends(get_current_viewer),
) -> list[dict]:
    return _approved_drafts_payload(db, viewer)


@router.post("/drafts/{draft_id}/approve")
def approve_draft(
    draft_id: int,
    action: DraftReviewAction,
    db: Session = Depends(get_db),
    viewer: ViewerContext = Depends(get_current_viewer),
) -> dict:
    draft_repo = DraftRepository(db)
    review_repo = ReviewQueueRepository(db)
    job_repo = PublishJobRepository(db)
    draft = draft_repo.get(draft_id)
    if draft is None or (viewer.is_customer and draft.workspace_user_id != viewer.workspace_user_id):
        raise HTTPException(status_code=404, detail="Draft not found")

    if action.edited_text:
        draft.draft_text = action.edited_text.strip()
    draft.needs_review = False
    draft.status = "approved"
    reviewer = action.reviewer or viewer.actor_name
    flags = draft.safety_flags or {}
    draft.safety_flags = {**flags, "reviewed_by": reviewer}

    for item in review_repo.list_open_for_event(draft.event_id):
        if viewer.is_customer and item.workspace_user_id != viewer.workspace_user_id:
            continue
        item.status = "resolved"
        item.assigned_to = reviewer

    queued = False
    warning: str | None = None
    publish_job: PublishJob | None = None
    if action.auto_queue and viewer.is_admin:
        creator_settings = CreatorSettingsRepository(db).get_or_create_default()
        if not creator_settings.to_dict().get("x_connected"):
            warning = "x_account_not_connected"
        else:
            queued = enqueue_approved_draft(db, draft.id)
    elif action.auto_queue and viewer.is_customer:
        profile = CustomerProfileRepository(db).get_or_create_for_workspace_user(viewer.workspace_user_id)
        if not profile.to_dict().get("x_connected"):
            warning = "x_account_not_connected"
        elif action.scheduled_for and action.scheduled_for <= datetime.now(timezone.utc):
            raise HTTPException(status_code=422, detail="scheduled_for must be in the future")
        elif job_repo.exists_for_draft(draft.id):
            queued = True
            publish_job = job_repo.latest_for_draft(draft.id)
        else:
            publish_job = job_repo.add(PublishJob(draft_post_id=draft.id, scheduled_for=action.scheduled_for))
            draft.status = "queued"
            queued = True

    db.commit()
    result = {"draft": _serialize_draft(draft, job_repo), "queued": queued}
    if publish_job:
        result["publish_job"] = publish_job.to_dict()
    if warning:
        result["warning"] = warning
    return result


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
    if draft is None or (viewer.is_customer and draft.workspace_user_id != viewer.workspace_user_id):
        raise HTTPException(status_code=404, detail="Draft not found")

    reviewer = action.reviewer or viewer.actor_name
    draft.status = "rejected"
    draft.needs_review = False
    flags = draft.safety_flags or {}
    draft.safety_flags = {**flags, "rejected_by": reviewer, "rejection_reason": action.reason}

    for item in review_repo.list_open_for_event(draft.event_id):
        if viewer.is_customer and item.workspace_user_id != viewer.workspace_user_id:
            continue
        item.status = "rejected"
        item.assigned_to = reviewer

    db.commit()
    return {"draft": draft.to_dict()}


@router.get("/drafts/rejected")
def list_rejected_drafts(
    db: Session = Depends(get_db),
    viewer: ViewerContext = Depends(get_current_viewer),
) -> list[dict]:
    return _rejected_drafts_payload(db, viewer)


@router.get("/workspace/home")
def get_customer_home_workspace(
    db: Session = Depends(get_db),
    viewer: ViewerContext = Depends(get_current_viewer),
) -> dict:
    if not viewer.is_customer:
        raise HTTPException(status_code=403, detail="Customer access required")
    settings = CustomerProfileRepository(db).get_or_create_for_workspace_user(
        viewer.workspace_user_id,
        default_display_name=viewer.display_name,
    )
    return {
        "queue": _review_queue_payload(db, viewer),
        "approved_drafts": _approved_drafts_payload(db, viewer),
        "settings": settings.to_dict(),
    }


@router.get("/workspace/drafts")
def get_customer_drafts_workspace(
    db: Session = Depends(get_db),
    viewer: ViewerContext = Depends(get_current_viewer),
) -> dict:
    if not viewer.is_customer:
        raise HTTPException(status_code=403, detail="Customer access required")
    settings = CustomerProfileRepository(db).get_or_create_for_workspace_user(
        viewer.workspace_user_id,
        default_display_name=viewer.display_name,
    )
    return {
        "drafts": _review_drafts_payload(db, viewer),
        "approved_drafts": _approved_drafts_payload(db, viewer),
        "rejected_drafts": _rejected_drafts_payload(db, viewer),
        "settings": settings.to_dict(),
    }


@router.post("/drafts/{draft_id}/reopen")
def reopen_draft(
    draft_id: int,
    db: Session = Depends(get_db),
    viewer: ViewerContext = Depends(get_current_viewer),
) -> dict:
    draft_repo = DraftRepository(db)
    review_repo = ReviewQueueRepository(db)
    draft = draft_repo.get(draft_id)
    if draft is None or (viewer.is_customer and draft.workspace_user_id != viewer.workspace_user_id):
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft.status != "rejected":
        raise HTTPException(status_code=409, detail="Only rejected drafts can be re-opened")

    draft.status = "draft"
    draft.needs_review = True
    flags = draft.safety_flags or {}
    draft.safety_flags = {**flags, "reopened_by": viewer.actor_name}
    review_repo.add(
        ReviewQueueItem(
            event_id=draft.event_id,
            workspace_user_id=draft.workspace_user_id,
            reason="manual_review",
        )
    )
    db.commit()
    return draft.to_dict()


@router.post("/items/{review_id}/resolve")
def resolve_review_item(
    review_id: int,
    action: ReviewResolveAction,
    db: Session = Depends(get_db),
    viewer: ViewerContext = Depends(get_current_viewer),
) -> dict:
    review_repo = ReviewQueueRepository(db)
    item = review_repo.get(review_id)
    if item is None or (viewer.is_customer and item.workspace_user_id != viewer.workspace_user_id):
        raise HTTPException(status_code=404, detail="Review item not found")

    item.status = action.status
    item.assigned_to = action.reviewer or viewer.email
    db.commit()
    return item.to_dict()

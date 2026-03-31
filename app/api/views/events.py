from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.security import ViewerContext, get_current_viewer
from app.db.session import get_db
from app.repositories.drafts import DraftRepository
from app.repositories.events import EventRepository

router = APIRouter()


@router.get("")
def list_events(
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
    viewer: ViewerContext = Depends(get_current_viewer),
) -> list[dict]:
    draft_repo = DraftRepository(db)
    payload = []
    for event in EventRepository(db).list_recent(limit=limit):
        serialized = event.to_dict()
        if viewer.is_customer:
            serialized.pop("dedupe_key", None)
            serialized.pop("status", None)
        draft = draft_repo.latest_for_event(event.id, viewer.workspace_user_id if viewer.is_customer else None)
        if viewer.is_customer and draft is None:
            continue
        serialized["draft_id"] = draft.id if draft else None
        serialized["draft_status"] = draft.status if draft else None
        payload.append(serialized)
    return payload

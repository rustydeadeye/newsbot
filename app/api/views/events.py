from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.security import ViewerContext, get_current_viewer
from app.db.session import get_db
from app.repositories.events import EventRepository

router = APIRouter()


@router.get("")
def list_events(
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
    viewer: ViewerContext = Depends(get_current_viewer),
) -> list[dict]:
    payload = []
    for event in EventRepository(db).list_recent(limit=limit):
        serialized = event.to_dict()
        if viewer.is_customer:
            serialized.pop("dedupe_key", None)
            serialized.pop("status", None)
        payload.append(serialized)
    return payload

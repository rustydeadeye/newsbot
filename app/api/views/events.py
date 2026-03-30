from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.events import EventRepository

router = APIRouter()


@router.get("")
def list_events(limit: int = Query(default=50, le=200), db: Session = Depends(get_db)) -> list[dict]:
    return [event.to_dict() for event in EventRepository(db).list_recent(limit=limit)]

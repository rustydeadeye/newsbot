from sqlalchemy import Select, desc, select
from sqlalchemy.orm import Session

from app.models.event import Event


class EventRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_recent(self, limit: int = 50) -> list[Event]:
        stmt: Select[tuple[Event]] = select(Event).order_by(desc(Event.created_at)).limit(limit)
        return list(self.db.scalars(stmt))

    def get_by_dedupe_key(self, dedupe_key: str) -> Event | None:
        stmt = select(Event).where(Event.dedupe_key == dedupe_key)
        return self.db.scalar(stmt)

    def add(self, event: Event) -> Event:
        self.db.add(event)
        self.db.flush()
        return event

    def get(self, event_id: int) -> Event | None:
        return self.db.get(Event, event_id)

    def list_for_drafting(self) -> list[Event]:
        stmt = select(Event).where(Event.status == "normalized").order_by(desc(Event.importance_score))
        return list(self.db.scalars(stmt))

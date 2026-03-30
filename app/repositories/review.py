from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models.review import ReviewQueueItem


class ReviewQueueRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_open(self) -> list[ReviewQueueItem]:
        stmt: Select[tuple[ReviewQueueItem]] = select(ReviewQueueItem).where(ReviewQueueItem.status == "open")
        return list(self.db.scalars(stmt))

    def add(self, item: ReviewQueueItem) -> ReviewQueueItem:
        self.db.add(item)
        self.db.flush()
        return item

    def get(self, review_id: int) -> ReviewQueueItem | None:
        return self.db.get(ReviewQueueItem, review_id)

    def list_open_for_event(self, event_id: int) -> list[ReviewQueueItem]:
        stmt = select(ReviewQueueItem).where(
            ReviewQueueItem.event_id == event_id,
            ReviewQueueItem.status == "open",
        )
        return list(self.db.scalars(stmt))

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models.source import Source, SourceItem


class SourceRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_enabled(self) -> list[Source]:
        stmt: Select[tuple[Source]] = select(Source).where(Source.enabled.is_(True)).order_by(Source.id)
        return list(self.db.scalars(stmt))

    def add_item(self, item: SourceItem) -> SourceItem:
        self.db.add(item)
        self.db.flush()
        return item

    def get_item_by_checksum(self, checksum: str) -> SourceItem | None:
        stmt = select(SourceItem).where(SourceItem.checksum == checksum)
        return self.db.scalar(stmt)

    def list_unprocessed_items(self, limit: int = 500) -> list[SourceItem]:
        stmt = select(SourceItem).where(SourceItem.processed.is_(False)).order_by(SourceItem.id).limit(limit)
        return list(self.db.scalars(stmt))

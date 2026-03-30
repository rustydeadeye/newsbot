from __future__ import annotations

import hashlib
import logging

from sqlalchemy.orm import Session

from app.models.source import Source, SourceItem
from app.repositories.sources import SourceRepository
from app.services.ingestion.adapters import get_adapter

logger = logging.getLogger(__name__)


class IngestionService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = SourceRepository(db)

    def ingest_source(self, source: Source) -> int:
        adapter = get_adapter(source)
        created = 0
        fetched_items = adapter.fetch()
        logger.debug("source=%s fetched=%d items", source.name, len(fetched_items))
        for fetched in fetched_items:
            checksum = _checksum(source.name, fetched.external_id, fetched.title, fetched.url)
            if self.repo.get_item_by_checksum(checksum):
                continue
            self.repo.add_item(
                SourceItem(
                    source_id=source.id,
                    external_id=fetched.external_id,
                    url=fetched.url,
                    title=fetched.title,
                    published_at=fetched.published_at,
                    raw_payload=fetched.raw_payload,
                    checksum=checksum,
                )
            )
            created += 1
        self.db.commit()
        logger.info("source=%s created=%d new items", source.name, created)
        return created

    def ingest_all(self) -> dict[str, int | str]:
        counts: dict[str, int | str] = {}
        for source in self.repo.list_enabled():
            try:
                counts[source.name] = self.ingest_source(source)
            except Exception as exc:
                logger.exception("ingestion failed for source=%s", source.name)
                counts[source.name] = f"error:{type(exc).__name__}"
        return counts


def _checksum(*parts: str) -> str:
    value = "||".join(parts).encode("utf-8")
    return hashlib.sha256(value).hexdigest()

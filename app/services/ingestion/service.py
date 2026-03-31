from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.source import Source, SourceItem
from app.repositories.sources import SourceRepository
from app.services.ingestion.adapters import get_adapter
from app.services.ingestion.base import FetchedItem

logger = logging.getLogger(__name__)

_CIRCUIT_FAILURE_THRESHOLD = 3   # consecutive failures before opening circuit
_CIRCUIT_COOLDOWN_MINUTES = 15   # minutes to skip a tripped source
_FETCH_MAX_WORKERS = 5           # concurrent source fetches


def _is_circuit_open(source: Source) -> bool:
    meta = source.metadata_json or {}
    open_until_str = meta.get("circuit_open_until")
    if not open_until_str:
        return False
    try:
        open_until = datetime.fromisoformat(open_until_str)
        return datetime.now(timezone.utc) < open_until
    except (ValueError, TypeError):
        return False


def _record_success(source: Source) -> None:
    meta = dict(source.metadata_json or {})
    meta.pop("consecutive_failures", None)
    meta.pop("circuit_open_until", None)
    source.metadata_json = meta


def _record_failure(source: Source) -> None:
    meta = dict(source.metadata_json or {})
    failures = meta.get("consecutive_failures", 0) + 1
    meta["consecutive_failures"] = failures
    if failures >= _CIRCUIT_FAILURE_THRESHOLD:
        from datetime import timedelta
        open_until = datetime.now(timezone.utc) + timedelta(minutes=_CIRCUIT_COOLDOWN_MINUTES)
        meta["circuit_open_until"] = open_until.isoformat()
        logger.warning(
            "Circuit opened for source=%s after %d failures; skipping until %s",
            source.name, failures, open_until.strftime("%H:%M UTC"),
        )
    source.metadata_json = meta


def _fetch_source(source: Source) -> tuple[Source, list[FetchedItem] | Exception]:
    """Fetch one source in a worker thread. No DB access — pure I/O."""
    try:
        items = get_adapter(source).fetch()
        return source, items
    except Exception as exc:
        return source, exc


class IngestionService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = SourceRepository(db)

    def ingest_all(self) -> dict[str, int | str]:
        # Phase 1: decide which sources to fetch (sequential, needs DB for circuit state)
        sources_to_fetch: list[Source] = []
        counts: dict[str, int | str] = {}
        for source in self.repo.list_enabled():
            if _is_circuit_open(source):
                meta = source.metadata_json or {}
                logger.info(
                    "Circuit open for source=%s; skipping (open until %s)",
                    source.name, meta.get("circuit_open_until"),
                )
                counts[source.name] = "circuit_open"
            else:
                sources_to_fetch.append(source)

        if not sources_to_fetch:
            return counts

        # Phase 2: fetch all eligible sources concurrently (no DB in threads)
        fetch_results: dict[int, list[FetchedItem] | Exception] = {}
        workers = min(_FETCH_MAX_WORKERS, len(sources_to_fetch))
        logger.info("Fetching %d sources concurrently (workers=%d)", len(sources_to_fetch), workers)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_source = {executor.submit(_fetch_source, src): src for src in sources_to_fetch}
            for future in as_completed(future_to_source):
                src, result = future.result()
                fetch_results[src.id] = result
                if isinstance(result, Exception):
                    logger.warning("source=%s fetch failed: %s", src.name, result)
                else:
                    logger.debug("source=%s fetched=%d items", src.name, len(result))

        # Phase 3: write results sequentially (DB writes + circuit breaker updates)
        for source in sources_to_fetch:
            result = fetch_results[source.id]
            if isinstance(result, Exception):
                _record_failure(source)
                self.db.commit()
                counts[source.name] = f"error:{type(result).__name__}"
            else:
                counts[source.name] = self._store_items(source, result)
                _record_success(source)
                self.db.commit()

        return counts

    def _store_items(self, source: Source, fetched_items: list[FetchedItem]) -> int:
        created = 0
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

    def ingest_source(self, source: Source) -> int:
        """Fetch and store a single source. Used for targeted re-ingestion."""
        _, result = _fetch_source(source)
        if isinstance(result, Exception):
            _record_failure(source)
            self.db.commit()
            raise result
        count = self._store_items(source, result)
        _record_success(source)
        self.db.commit()
        return count


def _checksum(*parts: str) -> str:
    value = "||".join(parts).encode("utf-8")
    return hashlib.sha256(value).hexdigest()

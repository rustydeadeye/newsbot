from app.core.config import get_settings
from app.db.session import SessionLocal
from app.pipeline import draft_pending_events, normalize_pending_items, publish_ready_jobs, queue_publish_jobs
from app.services.ingestion.service import IngestionService
from app.services.publishing.engagement import fetch_pending_engagement


def run_cycle() -> dict[str, int | dict[str, int]]:
    settings = get_settings()
    with SessionLocal() as db:
        ingest_counts = IngestionService(db).ingest_all()
        normalized = normalize_pending_items(db)
        drafted = draft_pending_events(db, settings.auto_post_threshold)
        queued = queue_publish_jobs(db)
        posted = publish_ready_jobs(db)
        return {
            "ingested": ingest_counts,
            "normalized": normalized,
            "drafted": drafted,
            "queued": queued,
            "posted": posted,
        }


def run_engagement_fetch() -> int:
    with SessionLocal() as db:
        return fetch_pending_engagement(db)

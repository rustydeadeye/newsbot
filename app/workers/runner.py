from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.pipeline_run import PipelineRun
from app.pipeline import (
    draft_pending_events,
    generate_drafts_for_customer,
    normalize_pending_items,
    publish_ready_jobs,
    queue_publish_jobs,
)
from app.repositories.pipeline_runs import PipelineRunRepository
from app.services.ingestion.service import IngestionService
from app.services.publishing.engagement import fetch_pending_engagement
from datetime import datetime, timezone


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


def run_customer_generation(run_id: int, workspace_user_id: int) -> None:
    settings = get_settings()
    with SessionLocal() as db:
        run_repo = PipelineRunRepository(db)
        run = db.get(PipelineRun, run_id)
        if run is None:
            return
        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        db.commit()
        try:
            counts = generate_drafts_for_customer(db, workspace_user_id, settings.auto_post_threshold)
            run.result_counts = counts
            run.finished_at = datetime.now(timezone.utc)
            run.status = "completed" if counts["drafted"] > 0 else "empty"
            run.error_message = None
            db.commit()
        except Exception as exc:  # pragma: no cover - defensive
            run.status = "failed"
            run.finished_at = datetime.now(timezone.utc)
            run.error_message = str(exc)
            db.commit()

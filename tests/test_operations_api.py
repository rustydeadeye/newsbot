from datetime import datetime, timezone
import os

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.models.creator import CreatorSettings
from app.models.event import DraftPost, Event
from app.models.job import PublishJob, PublishLog


def _build_client() -> tuple[TestClient, Session]:
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False)()
    app = create_app()

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), session


def test_publish_jobs_endpoint_returns_job_with_event() -> None:
    client, db = _build_client()
    event = Event(
        event_type="earnings",
        entity_type="company",
        entity_name="TCS",
        ticker="TCS",
        source_priority=95,
        occurred_at=datetime.now(timezone.utc),
        summary_facts={"headline": "TCS Results"},
        importance_score=90,
        confidence_score=0.95,
        dedupe_key="earnings|tcs|2026-03-28|na",
        status="drafted",
    )
    draft = DraftPost(event=event, draft_text="Draft text", status="queued", needs_review=False)
    job = PublishJob(draft_post_id=1, status="queued")
    db.add_all([event, draft])
    db.flush()
    job.draft_post_id = draft.id
    db.add(job)
    db.commit()

    response = client.get("/publish-jobs")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["event"]["ticker"] == "TCS"
    assert body[0]["draft"]["draft_text"] == "Draft text"


def test_publish_job_retry_requeues_failed_job() -> None:
    client, db = _build_client()
    event = Event(
        event_type="dividend",
        entity_type="company",
        entity_name="TVSMOTOR",
        ticker="TVSMOTOR",
        source_priority=95,
        occurred_at=datetime.now(timezone.utc),
        summary_facts={"headline": "Dividend"},
        importance_score=90,
        confidence_score=0.95,
        dedupe_key="dividend|tvsmotor|2026-03-28|na",
        status="drafted",
    )
    draft = DraftPost(event=event, draft_text="Dividend draft", status="queued", needs_review=False)
    db.add_all([event, draft])
    db.flush()
    job = PublishJob(draft_post_id=draft.id, status="failed", last_error="timeout")
    db.add(job)
    db.commit()

    response = client.post(f"/publish-jobs/{job.id}/retry", json={})

    assert response.status_code == 200
    db.refresh(job)
    assert job.status == "queued"
    assert job.last_error is None


def test_creator_settings_read_and_update() -> None:
    client, db = _build_client()
    db.add(CreatorSettings(display_name="Desk", max_posts_per_hour=6, watchlist=["TCS"], blocked_phrases=["buy now"]))
    db.commit()

    read_response = client.get("/settings/creator")
    update_response = client.put(
        "/settings/creator",
        json={"display_name": "Desk 2", "max_posts_per_hour": 8, "watchlist": ["TCS", "INFY"]},
    )

    assert read_response.status_code == 200
    assert update_response.status_code == 200
    assert update_response.json()["display_name"] == "Desk 2"
    assert update_response.json()["watchlist"] == ["TCS", "INFY"]


def test_publish_logs_endpoint_returns_logs() -> None:
    client, db = _build_client()
    event = Event(
        event_type="macro_release",
        entity_type="market",
        entity_name="Market",
        source_priority=100,
        occurred_at=datetime.now(timezone.utc),
        summary_facts={"headline": "RBI Update"},
        importance_score=95,
        confidence_score=0.95,
        dedupe_key="macro_release|market|2026-03-28|na",
        status="drafted",
    )
    draft = DraftPost(event=event, draft_text="Macro draft", status="queued", needs_review=False)
    db.add_all([event, draft])
    db.flush()
    job = PublishJob(draft_post_id=draft.id, status="posted")
    db.add(job)
    db.flush()
    db.add(PublishLog(publish_job_id=job.id, platform_post_id="12345", posted_at=datetime.now(timezone.utc), response_payload={"ok": True}))
    db.commit()

    response = client.get("/publish-jobs/logs")

    assert response.status_code == 200
    assert response.json()[0]["platform_post_id"] == "12345"

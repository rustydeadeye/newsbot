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
from app.api.security import ViewerContext, get_current_viewer
from app.models.event import DraftPost, Event
from app.models.review import ReviewQueueItem


def _build_client(role: str = "admin") -> tuple[TestClient, Session]:
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

    def override_get_current_viewer():
        return ViewerContext(user_id="user-1", email=f"{role}@example.com", role=role, display_name=role.title())

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_viewer] = override_get_current_viewer
    return TestClient(app), session


def test_list_review_queue_includes_event_and_draft() -> None:
    client, db = _build_client(role="customer")
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
    draft = DraftPost(event=event, draft_text="TCS results draft", status="draft", needs_review=True)
    item = ReviewQueueItem(event=event, reason="manual_review")
    db.add_all([event, draft, item])
    db.commit()

    response = client.get("/review")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["event"]["ticker"] == "TCS"
    assert body[0]["draft"]["draft_text"] == "TCS results draft"


def test_approve_draft_updates_status_and_resolves_items() -> None:
    client, db = _build_client()
    event = Event(
        event_type="earnings",
        entity_type="company",
        entity_name="TCS",
        ticker="TCS",
        source_priority=95,
        occurred_at=datetime.now(timezone.utc),
        summary_facts={"headline": "TCS Results", "subject_key": "financial-results"},
        importance_score=90,
        confidence_score=0.95,
        dedupe_key="earnings|tcs|2026-03-28|financial-results",
        status="drafted",
    )
    draft = DraftPost(event=event, draft_text="Old text", status="draft", needs_review=True)
    item = ReviewQueueItem(event=event, reason="manual_review")
    db.add_all([event, draft, item])
    db.commit()

    response = client.post(
        f"/review/drafts/{draft.id}/approve",
        json={"reviewer": "editor", "edited_text": "New text", "auto_queue": False},
    )

    assert response.status_code == 200
    db.refresh(draft)
    db.refresh(item)
    assert draft.status == "approved"
    assert draft.draft_text == "New text"
    assert item.status == "resolved"


def test_customer_approve_draft_does_not_auto_queue() -> None:
    client, db = _build_client(role="customer")
    event = Event(
        event_type="earnings",
        entity_type="company",
        entity_name="TCS",
        ticker="TCS",
        source_priority=95,
        occurred_at=datetime.now(timezone.utc),
        summary_facts={"headline": "TCS Results", "subject_key": "financial-results"},
        importance_score=90,
        confidence_score=0.95,
        dedupe_key="earnings|tcs|2026-03-28|financial-results",
        status="drafted",
    )
    draft = DraftPost(event=event, draft_text="Old text", status="draft", needs_review=True)
    item = ReviewQueueItem(event=event, reason="manual_review")
    db.add_all([event, draft, item])
    db.commit()

    response = client.post(
        f"/review/drafts/{draft.id}/approve",
        json={"reviewer": "customer-a", "edited_text": "New text", "auto_queue": True},
    )

    assert response.status_code == 200
    assert response.json()["queued"] is False
    db.refresh(draft)
    assert draft.status == "approved"


def test_reject_draft_marks_rejected() -> None:
    client, db = _build_client(role="customer")
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
    draft = DraftPost(event=event, draft_text="Dividend draft", status="draft", needs_review=True)
    item = ReviewQueueItem(event=event, reason="manual_review")
    db.add_all([event, draft, item])
    db.commit()

    response = client.post(
        f"/review/drafts/{draft.id}/reject",
        json={"reviewer": "editor", "reason": "Not clear enough"},
    )

    assert response.status_code == 200
    db.refresh(draft)
    db.refresh(item)
    assert draft.status == "rejected"
    assert item.status == "rejected"


def test_customer_review_queue_hides_admin_event_fields() -> None:
    client, db = _build_client(role="customer")
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
    draft = DraftPost(event=event, draft_text="Dividend draft", status="draft", needs_review=True)
    item = ReviewQueueItem(event=event, reason="manual_review")
    db.add_all([event, draft, item])
    db.commit()

    response = client.get("/review")

    assert response.status_code == 200
    payload = response.json()[0]["event"]
    assert "dedupe_key" not in payload
    assert "status" not in payload

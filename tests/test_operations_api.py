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
from app.api.security import ViewerContext, get_current_viewer, require_admin
from app.models.creator import CreatorSettings
from app.models.event import DraftPost, Event
from app.models.source import Source
from app.models.job import PublishJob, PublishLog
from app.models.wire_feed import WireCandidate, WireJob, WirePublishLog
from app.models.customer import CustomerProfile


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
        return ViewerContext(workspace_user_id=1, user_id="user-1", email=f"{role}@example.com", role=role, display_name=role.title())

    def override_require_admin():
        viewer = override_get_current_viewer()
        if viewer.role != "admin":
            from fastapi import HTTPException

            raise HTTPException(status_code=403, detail="Admin access required")
        return viewer

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_viewer] = override_get_current_viewer
    app.dependency_overrides[require_admin] = override_require_admin
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


def test_customer_settings_update_can_change_customer_automation_fields() -> None:
    client, db = _build_client(role="customer")
    db.add(CreatorSettings(display_name="Desk", max_posts_per_hour=6, watchlist=["TCS"], blocked_phrases=["buy now"]))
    db.commit()

    response = client.put(
        "/settings/creator",
        json={"display_name": "Desk 2", "max_posts_per_hour": 12, "watchlist": ["INFY"]},
    )

    assert response.status_code == 200
    assert response.json()["display_name"] == "Desk 2"
    assert response.json()["watchlist"] == ["INFY"]
    assert response.json()["max_posts_per_hour"] == 12


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


def test_customer_cannot_access_publish_jobs() -> None:
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
    own_draft = DraftPost(event=event, workspace_user_id=1, draft_text="Own draft", status="queued", needs_review=False)
    other_draft = DraftPost(event=event, workspace_user_id=2, draft_text="Other draft", status="queued", needs_review=False)
    db.add_all([event, own_draft, other_draft])
    db.flush()
    db.add_all([
        PublishJob(draft_post_id=own_draft.id, status="queued"),
        PublishJob(draft_post_id=other_draft.id, status="queued"),
    ])
    db.commit()

    response = client.get("/publish-jobs")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["draft"]["draft_text"] == "Own draft"


def test_customer_cannot_access_publish_logs() -> None:
    client, _db = _build_client(role="customer")

    response = client.get("/publish-jobs/logs")

    assert response.status_code == 403


def test_wire_jobs_endpoint_returns_candidate() -> None:
    client, db = _build_client()
    candidate = WireCandidate(
        source_name="tradient_market_news",
        external_id="tradient:1",
        title="Eicher Motors CV Sales Rise 10% to 13,311 Units",
        ticker="EICHERMOT",
        event_type="earnings",
        dedupe_key="earnings|eichermot|sales",
        importance_score=100,
        confidence_score=0.95,
        draft_text="EICHER MOTORS: SALES UP 10% TO 13,311 UNITS",
        raw_payload={},
    )
    db.add(candidate)
    db.flush()
    job = WireJob(candidate_id=candidate.id, status="queued", priority="high")
    db.add(job)
    db.commit()

    response = client.get("/publish-jobs/wire")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["candidate"]["ticker"] == "EICHERMOT"
    assert body[0]["candidate"]["draft_text"] == "EICHER MOTORS: SALES UP 10% TO 13,311 UNITS"


def test_wire_logs_endpoint_returns_candidate_context() -> None:
    client, db = _build_client()
    candidate = WireCandidate(
        source_name="tradient_market_news",
        external_id="tradient:2",
        title="Finolex Cables Receives GST Demand of ₹29.46 Crores",
        ticker="FINCABLES",
        event_type="default_fraud",
        dedupe_key="default_fraud|fincables|gst",
        importance_score=90,
        confidence_score=0.95,
        draft_text="FINOLEX CABLES: GST DEMAND ORDER OF RS 29.46 CRORE",
        raw_payload={},
    )
    db.add(candidate)
    db.flush()
    job = WireJob(candidate_id=candidate.id, status="posted", priority="breaking")
    db.add(job)
    db.flush()
    db.add(WirePublishLog(wire_job_id=job.id, platform_post_id="wire-123", posted_at=datetime.now(timezone.utc), response_payload={"ok": True}))
    db.commit()

    response = client.get("/publish-jobs/wire/logs")

    assert response.status_code == 200
    assert response.json()[0]["candidate"]["ticker"] == "FINCABLES"
    assert response.json()[0]["platform_post_id"] == "wire-123"


def test_wire_job_retry_requeues_failed_job() -> None:
    client, db = _build_client()
    candidate = WireCandidate(
        source_name="tradient_market_news",
        external_id="tradient:3",
        title="Coal India March 2026 Offtake Up 0.7% to 69.5 MT",
        ticker="COALINDIA",
        event_type="earnings",
        dedupe_key="earnings|coalindia|offtake",
        importance_score=100,
        confidence_score=0.95,
        draft_text="COAL INDIA: MARCH OFFTAKE UP 0.7% TO 69.5 MT",
        raw_payload={},
    )
    db.add(candidate)
    db.flush()
    job = WireJob(candidate_id=candidate.id, status="failed", priority="high", last_error="x_api_request_error:ConnectError")
    db.add(job)
    db.commit()

    response = client.post(f"/publish-jobs/wire/{job.id}/retry", json={})

    assert response.status_code == 200
    db.refresh(job)
    assert job.status == "queued"
    assert job.last_error is None


def test_wire_job_cancel_marks_job_cancelled() -> None:
    client, db = _build_client()
    candidate = WireCandidate(
        source_name="tradient_market_news",
        external_id="tradient:4",
        title="ICRA Projects 11-12% Bank Loan Growth for FY27",
        ticker="BANKING",
        event_type="earnings",
        dedupe_key="earnings|banking|loan-growth",
        importance_score=100,
        confidence_score=0.95,
        draft_text="ICRA: FY27 LOAN GROWTH SEEN AT 11-12%",
        raw_payload={},
    )
    db.add(candidate)
    db.flush()
    job = WireJob(candidate_id=candidate.id, status="queued", priority="high")
    db.add(job)
    db.commit()

    response = client.post(f"/publish-jobs/wire/{job.id}/cancel")

    assert response.status_code == 200
    db.refresh(job)
    assert job.status == "cancelled"


def test_customer_cannot_access_wire_jobs() -> None:
    client, _db = _build_client(role="customer")

    response = client.get("/publish-jobs/wire")

    assert response.status_code == 403


def test_customer_autopost_dashboard_returns_safe_payload() -> None:
    client, db = _build_client(role="customer")
    profile = CustomerProfile(
        workspace_user_id=1,
        display_name="Ritesh",
        auto_post_enabled=True,
        token_store={"x_access_token": "token"},
    )
    db.add(profile)
    db.flush()
    candidate = WireCandidate(
        source_name="tradient_market_news",
        external_id="tradient:auto-1",
        title="Eicher Motors CV Sales Rise 10% to 13,311 Units",
        ticker="EICHERMOT",
        event_type="earnings",
        dedupe_key="earnings|eichermot|sales",
        importance_score=100,
        confidence_score=0.95,
        draft_text="EICHER MOTORS: SALES UP 10% TO 13,311 UNITS",
        raw_payload={},
    )
    db.add(candidate)
    db.flush()
    db.add(WireJob(candidate_id=candidate.id, status="queued", priority="high"))
    db.commit()

    response = client.get("/settings/autopost")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "active"
    assert body["x_connected"] is True
    assert body["next_posts"][0]["tweet_text"] == "EICHER MOTORS: SALES UP 10% TO 13,311 UNITS"
    assert "dedupe_key" not in str(body)
    assert "idempotency_key" not in str(body)


def test_customer_can_pause_and_resume_autopost() -> None:
    client, db = _build_client(role="customer")
    profile = CustomerProfile(
        workspace_user_id=1,
        display_name="Ritesh",
        auto_post_enabled=True,
        token_store={"x_access_token": "token"},
    )
    db.add(profile)
    db.commit()

    pause_response = client.post("/settings/autopost/pause")
    assert pause_response.status_code == 200
    db.refresh(profile)
    assert profile.auto_post_enabled is False

    resume_response = client.post("/settings/autopost/resume")
    assert resume_response.status_code == 200
    db.refresh(profile)
    assert profile.auto_post_enabled is True


def test_customer_can_disconnect_x_from_autopost_surface() -> None:
    client, db = _build_client(role="customer")
    profile = CustomerProfile(
        workspace_user_id=1,
        display_name="Ritesh",
        auto_post_enabled=True,
        token_store={"x_access_token": "token", "x_refresh_token": "refresh"},
    )
    db.add(profile)
    db.commit()

    response = client.post("/settings/x/disconnect")

    assert response.status_code == 200
    db.refresh(profile)
    assert profile.auto_post_enabled is False
    assert profile.token_store == {}


def test_customer_cannot_access_sources() -> None:
    client, db = _build_client(role="customer")
    db.add(Source(name="RBI", type="rss", base_url="https://example.com", poll_interval_sec=300, enabled=True))
    db.commit()

    response = client.get("/sources")

    assert response.status_code == 403


def test_customer_events_hide_admin_fields() -> None:
    client, db = _build_client(role="customer")
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
    db.add(event)
    db.flush()
    db.add(DraftPost(event_id=event.id, workspace_user_id=1, draft_text="Macro draft", status="draft", needs_review=True))
    db.commit()

    response = client.get("/events")

    assert response.status_code == 200
    payload = response.json()[0]
    assert "dedupe_key" not in payload
    assert "status" not in payload


def test_auth_me_returns_current_viewer() -> None:
    client, _db = _build_client(role="customer")

    response = client.get("/auth/me")

    assert response.status_code == 200
    assert response.json()["viewer"]["role"] == "customer"

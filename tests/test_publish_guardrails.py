from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models.creator import CreatorSettings
from app.models.event import DraftPost, Event
from app.models.job import PublishJob
from app.pipeline import _cooldown_minutes, _queue_decision
from app.repositories.jobs import PublishJobRepository


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False)()


def test_queue_decision_rate_limit() -> None:
    db = _session()
    settings = CreatorSettings(display_name="Creator", max_posts_per_hour=1)
    existing_event = Event(
        event_type="earnings",
        entity_type="company",
        entity_name="INFY",
        ticker="INFY",
        source_priority=95,
        occurred_at=datetime.now(timezone.utc),
        summary_facts={"subject_key": "financial-results"},
        importance_score=90,
        confidence_score=0.95,
        dedupe_key="earnings|infy|2026-03-28|financial-results",
        status="normalized",
    )
    existing_draft = DraftPost(event=existing_event, draft_text="INFY results", status="queued", needs_review=False)
    event = Event(
        event_type="earnings",
        entity_type="company",
        entity_name="TCS",
        ticker="TCS",
        source_priority=95,
        occurred_at=datetime.now(timezone.utc),
        summary_facts={"subject_key": "financial-results"},
        importance_score=90,
        confidence_score=0.95,
        dedupe_key="earnings|tcs|2026-03-28|financial-results",
        status="normalized",
    )
    draft = DraftPost(event=event, draft_text="TCS results", status="approved", needs_review=False)
    db.add_all([settings, existing_event, existing_draft, event, draft])
    db.flush()
    db.add(PublishJob(draft_post_id=existing_draft.id, status="posted"))
    db.commit()

    decision = _queue_decision(PublishJobRepository(db), settings, event, draft)

    assert decision == "rate_limit_hourly"


def test_queue_decision_cooldown_duplicate() -> None:
    db = _session()
    settings = CreatorSettings(display_name="Creator", max_posts_per_hour=5)
    event1 = Event(
        event_type="dividend",
        entity_type="company",
        entity_name="TVSMOTOR",
        ticker="TVSMOTOR",
        source_priority=95,
        occurred_at=datetime.now(timezone.utc),
        summary_facts={"subject_key": "interim-dividend-rs-12-per-share"},
        importance_score=90,
        confidence_score=0.95,
        dedupe_key="dividend|tvsmotor|2026-03-28|interim-dividend-rs-12-per-share",
        status="normalized",
    )
    draft1 = DraftPost(event=event1, draft_text="TVS dividend", status="queued", needs_review=False)
    event2 = Event(
        event_type="dividend",
        entity_type="company",
        entity_name="TVSMOTOR",
        ticker="TVSMOTOR",
        source_priority=90,
        occurred_at=datetime.now(timezone.utc),
        summary_facts={"subject_key": "interim-dividend-rs-12-per-share"},
        importance_score=88,
        confidence_score=0.95,
        dedupe_key="dividend|tvsmotor|2026-03-28|interim-dividend-re-12-per-share",
        status="normalized",
    )
    draft2 = DraftPost(event=event2, draft_text="TVS dividend again", status="approved", needs_review=False)
    db.add_all([settings, event1, draft1, event2, draft2])
    db.flush()
    existing_job = PublishJob(draft_post_id=draft1.id, status="posted")
    existing_job.updated_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    db.add(existing_job)
    db.commit()

    decision = _queue_decision(PublishJobRepository(db), settings, event2, draft2)

    assert decision == "cooldown_duplicate"


def test_cooldown_minutes_by_event_type() -> None:
    macro_event = Event(
        event_type="rbi_policy",
        entity_type="market",
        source_priority=100,
        summary_facts={},
        importance_score=100,
        confidence_score=0.95,
        dedupe_key="rbi_policy|market|2026-03-28|na",
        status="normalized",
    )
    company_event = Event(
        event_type="earnings",
        entity_type="company",
        source_priority=95,
        summary_facts={},
        importance_score=85,
        confidence_score=0.95,
        dedupe_key="earnings|tcs|2026-03-28|na",
        status="normalized",
    )

    assert _cooldown_minutes(macro_event) == 120
    assert _cooldown_minutes(company_event) == 45

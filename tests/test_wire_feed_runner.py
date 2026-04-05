import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://dryrun:dryrun@localhost/dryrun")

from app.wire_feed.runner import run_wire_cycle


def test_publish_due_jobs_requeues_runtime_errors_before_fail(monkeypatch) -> None:
    from datetime import datetime, timezone

    from app.wire_feed.runner import _publish_due_jobs

    class Candidate:
        id = 1
        dedupe_key = "earnings|coalindia|offtake"
        draft_text = "COAL INDIA: MARCH OFFTAKE UP 0.7% TO 69.5 MT"

    class Job:
        id = 10
        candidate_id = 1
        attempt_count = 1
        status = "publishing"
        scheduled_for = None
        last_error = None
        result_message = None
        idempotency_key = "abc"

    class FakeJobRepo:
        def __init__(self, db):
            self.db = db

        def claim_ready(self, now, limit=20):
            assert limit == 1
            return [job]

        def has_active_duplicate(self, dedupe_key, exclude_job_id=None):
            return False

        def add_log(self, job_id, response, platform_post_id=None):
            return None

    class FakePublisher:
        def publish(self, text, idempotency_key=None):
            raise RuntimeError("x_api_request_error:ConnectError")

    class FakeDb:
        def get(self, model, ident):
            return candidate if ident == 1 else None

        def commit(self):
            return None

        def flush(self):
            return None

    class FakeProfile:
        token_store = {"x_access_token": "token", "x_refresh_token": "refresh"}

    candidate = Candidate()
    job = Job()

    monkeypatch.setattr("app.wire_feed.runner.WireJobRepository", FakeJobRepo)
    monkeypatch.setattr(
        "app.wire_feed.runner.CustomerProfileRepository",
        lambda db: type("Repo", (), {"get_active_autopost_customer": lambda self: FakeProfile()})(),
    )
    monkeypatch.setattr("app.wire_feed.runner.XPublisher", lambda token_store=None, on_token_refresh=None: FakePublisher())

    result = _publish_due_jobs(FakeDb(), datetime.now(timezone.utc))

    assert result == {"posted": 0, "failed": 0}
    assert job.status == "queued"
    assert job.result_message == "retry_scheduled"
    assert job.last_error == "x_api_request_error:ConnectError"


def test_apply_customer_branding_appends_sebi_suffix() -> None:
    from app.wire_feed.runner import _apply_customer_branding

    result = type(
        "Result",
        (),
        {
            "draft_text": "Bank stocks fell after oil prices jumped and traders turned cautious.",
            "raw_payload": {},
        },
    )()
    profile = type(
        "Profile",
        (),
        {
            "display_name": "AngryTraders",
            "token_store": {
                "brand_name": "AngryTraders",
                "sebi_registration": "INH000023506",
                "cta_short": "Follow us and stay updated with stock reports and updates.",
            },
        },
    )()

    _apply_customer_branding([result], profile)

    assert "AngryTraders | SEBI Registered RA (INH000023506)" in result.draft_text
    assert "Follow us and stay updated with stock reports and updates." in result.draft_text
    assert (
        result.raw_payload["brand_suffix"]
        == "AngryTraders | SEBI Registered RA (INH000023506)\nFollow us and stay updated with stock reports and updates."
    )


def test_publish_due_jobs_skips_active_duplicate(monkeypatch) -> None:
    from datetime import datetime, timezone

    from app.wire_feed.runner import _publish_due_jobs

    class Candidate:
        id = 1
        dedupe_key = "earnings|coalindia|offtake"
        draft_text = "COAL INDIA: MARCH OFFTAKE UP 0.7% TO 69.5 MT"

    class Job:
        id = 11
        candidate_id = 1
        attempt_count = 1
        status = "publishing"
        scheduled_for = None
        last_error = None
        result_message = None
        idempotency_key = "def"

    class FakeJobRepo:
        def __init__(self, db):
            self.db = db

        def claim_ready(self, now, limit=20):
            assert limit == 1
            return [job]

        def has_active_duplicate(self, dedupe_key, exclude_job_id=None):
            return True

        def add_log(self, job_id, response, platform_post_id=None):
            return None

    class FakeDb:
        def get(self, model, ident):
            return candidate if ident == 1 else None

        def commit(self):
            return None

        def flush(self):
            return None

    class FakeProfile:
        token_store = {"x_access_token": "token", "x_refresh_token": "refresh"}

    candidate = Candidate()
    job = Job()

    monkeypatch.setattr("app.wire_feed.runner.WireJobRepository", FakeJobRepo)
    monkeypatch.setattr(
        "app.wire_feed.runner.CustomerProfileRepository",
        lambda db: type("Repo", (), {"get_active_autopost_customer": lambda self: FakeProfile()})(),
    )
    monkeypatch.setattr("app.wire_feed.runner.XPublisher", lambda token_store=None, on_token_refresh=None: None)

    result = _publish_due_jobs(FakeDb(), datetime.now(timezone.utc))

    assert result == {"posted": 0, "failed": 0}
    assert job.status == "skipped"
    assert job.result_message == "duplicate_active_job"


def test_publish_due_jobs_skips_without_active_autopost_customer(monkeypatch) -> None:
    from datetime import datetime, timezone

    from app.wire_feed.runner import _publish_due_jobs

    class FakeDb:
        def commit(self):
            return None

    class FakeJobRepo:
        def __init__(self, db):
            self.db = db

    monkeypatch.setattr("app.wire_feed.runner.WireJobRepository", FakeJobRepo)
    monkeypatch.setattr(
        "app.wire_feed.runner.CustomerProfileRepository",
        lambda db: type("Repo", (), {"get_active_autopost_customer": lambda self: None})(),
    )

    result = _publish_due_jobs(FakeDb(), datetime.now(timezone.utc))

    assert result == {"posted": 0, "failed": 0}


def test_run_wire_cycle_does_not_publish_when_customer_autopost_disabled(monkeypatch) -> None:
    class StubSource:
        key = "tradient"

    class StubDrafting:
        pass

    monkeypatch.setattr("app.wire_feed.runner.get_wire_sources", lambda: [StubSource()])
    monkeypatch.setattr("app.wire_feed.runner.DraftingService", lambda: StubDrafting())
    monkeypatch.setattr(
        "app.wire_feed.runner.fetch_and_process",
        lambda source, drafting: [],
    )
    monkeypatch.setattr("app.wire_feed.runner.plan_wire_queue", lambda results, recent_posts, now, settings: [])

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def commit(self):
            return None

        def get(self, model, ident):
            return None

    class FakeCandidateRepo:
        def __init__(self, db):
            self.db = db

    class FakeJobRepo:
        def __init__(self, db):
            self.db = db

        def expire_stale_jobs(self, now, settings):
            return 0

        def recent_post_records(self, since):
            return []

    class FakeCustomerRepo:
        def __init__(self, db):
            self.db = db

        def has_active_autopost_customer(self):
            return False

    monkeypatch.setattr("app.wire_feed.runner.SessionLocal", lambda: FakeSession())
    monkeypatch.setattr("app.wire_feed.runner.WireCandidateRepository", FakeCandidateRepo)
    monkeypatch.setattr("app.wire_feed.runner.WireJobRepository", FakeJobRepo)
    monkeypatch.setattr("app.wire_feed.runner.CustomerProfileRepository", FakeCustomerRepo)
    publish_calls = {"count": 0}

    def fake_publish_due_jobs(db, now):
        publish_calls["count"] += 1
        return {"posted": 0, "failed": 0}

    monkeypatch.setattr("app.wire_feed.runner._publish_due_jobs", fake_publish_due_jobs)

    summary = run_wire_cycle()

    assert publish_calls["count"] == 0
    assert summary["posted"] == 0


def test_run_wire_cycle_returns_summary(monkeypatch) -> None:
    class StubSource:
        key = "tradient"

    class StubDrafting:
        pass

    monkeypatch.setattr("app.wire_feed.runner.get_wire_sources", lambda: [StubSource()])
    monkeypatch.setattr("app.wire_feed.runner.DraftingService", lambda: StubDrafting())
    monkeypatch.setattr(
        "app.wire_feed.runner.fetch_and_process",
        lambda source, drafting: [
            type(
                "Result",
                (),
                {
                    "external_id": "tradient:1",
                    "source_name": "tradient_market_news",
                    "title": "JK Tyre update",
                    "event_type": "default_fraud",
                    "dedupe_key": "default_fraud|jktyre|gst",
                    "subject_key": "gst",
                    "ticker": "JKTYRE",
                    "importance_score": 100,
                    "confidence_score": 0.95,
                    "would_auto_post": True,
                    "review_reason": None,
                    "draft_text": "JK TYRE: GST DEMAND ORDER OF RS 1.39 CRORE",
                    "safety_flags": {},
                    "published_at": None,
                },
            )()
        ],
    )
    monkeypatch.setattr(
        "app.wire_feed.runner.plan_wire_queue",
        lambda results, recent_posts, now, settings: [
            type(
                "Decision",
                (),
                {
                    "action": "post_now",
                    "priority": "breaking",
                    "scheduled_for": now,
                    "reason": None,
                    "result": type(
                        "QueuedResult",
                        (),
                        {
                            "title": "JK Tyre update",
                            "draft_text": "JK TYRE: GST DEMAND ORDER OF RS 1.39 CRORE",
                            "importance_score": 100,
                        },
                    )(),
                },
            )()
        ],
    )
    monkeypatch.setattr("app.wire_feed.runner._publish_due_jobs", lambda db, now: {"posted": 1, "failed": 0})

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def commit(self):
            return None

        def get(self, model, ident):
            return None

    monkeypatch.setattr("app.wire_feed.runner.SessionLocal", lambda: FakeSession())

    class FakeCandidateRepo:
        def __init__(self, db):
            self.db = db

        def upsert_from_result(self, result):
            return type("Candidate", (), {"id": 1})()

    class FakeJobRepo:
        def __init__(self, db):
            self.db = db

        def expire_stale_jobs(self, now, settings):
            return 0

        def recent_post_records(self, since):
            return []

        def bump_non_breaking_queue(self, earliest, settings):
            return 0

        def record_decision(self, candidate, decision):
            return None

    monkeypatch.setattr("app.wire_feed.runner.WireCandidateRepository", FakeCandidateRepo)
    monkeypatch.setattr("app.wire_feed.runner.WireJobRepository", FakeJobRepo)
    monkeypatch.setattr(
        "app.wire_feed.runner.CustomerProfileRepository",
        lambda db: type("CustomerRepo", (), {"has_active_autopost_customer": lambda self: True})(),
    )

    summary = run_wire_cycle()

    assert summary["sources_processed"] == 1
    assert summary["post_now"] == 1
    assert summary["queued"] == 0
    assert summary["skipped"] == 0
    assert summary["posted"] == 1


def test_run_wire_cycle_bumps_non_breaking_jobs_for_breaking_item(monkeypatch) -> None:
    class StubSource:
        key = "tradient"

    class StubDrafting:
        pass

    monkeypatch.setattr("app.wire_feed.runner.get_wire_sources", lambda: [StubSource()])
    monkeypatch.setattr("app.wire_feed.runner.DraftingService", lambda: StubDrafting())
    monkeypatch.setattr(
        "app.wire_feed.runner.fetch_and_process",
        lambda source, drafting: [
            type(
                "Result",
                (),
                {
                    "external_id": "tradient:breaking-1",
                    "source_name": "tradient_market_news",
                    "title": "Breaking penalty",
                    "event_type": "default_fraud",
                    "dedupe_key": "default_fraud|abc|penalty",
                    "subject_key": "penalty",
                    "ticker": "ABC",
                    "importance_score": 100,
                    "confidence_score": 0.95,
                    "would_auto_post": True,
                    "review_reason": None,
                    "draft_text": "ABC: PENALTY IMPOSED",
                    "safety_flags": {},
                    "published_at": None,
                },
            )()
        ],
    )

    bump_calls = {"count": 0}

    def fake_plan(results, recent_posts, now, settings):
        return [
            type(
                "Decision",
                (),
                {
                    "action": "post_now",
                    "priority": "breaking",
                    "scheduled_for": now,
                    "reason": None,
                    "result": results[0],
                },
            )()
        ]

    monkeypatch.setattr("app.wire_feed.runner.plan_wire_queue", fake_plan)
    monkeypatch.setattr("app.wire_feed.runner._publish_due_jobs", lambda db, now: {"posted": 0, "failed": 0})

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def commit(self):
            return None

        def get(self, model, ident):
            return None

    monkeypatch.setattr("app.wire_feed.runner.SessionLocal", lambda: FakeSession())

    class FakeCandidateRepo:
        def __init__(self, db):
            self.db = db

        def upsert_from_result(self, result):
            return type("Candidate", (), {"id": 1})()

    class FakeJobRepo:
        def __init__(self, db):
            self.db = db

        def expire_stale_jobs(self, now, settings):
            return 0

        def recent_post_records(self, since):
            return []

        def bump_non_breaking_queue(self, earliest, settings):
            bump_calls["count"] += 1
            return 1

        def record_decision(self, candidate, decision):
            return None

    monkeypatch.setattr("app.wire_feed.runner.WireCandidateRepository", FakeCandidateRepo)
    monkeypatch.setattr("app.wire_feed.runner.WireJobRepository", FakeJobRepo)
    monkeypatch.setattr(
        "app.wire_feed.runner.CustomerProfileRepository",
        lambda db: type("CustomerRepo", (), {"has_active_autopost_customer": lambda self: True})(),
    )

    run_wire_cycle()

    assert bump_calls["count"] == 1


def test_run_wire_cycle_skips_base_fetch_when_recent_base_candidates_exist(monkeypatch) -> None:
    class StubSource:
        key = "tradient"
        name = "tradient_market_news"

    class StubDrafting:
        pass

    fetch_calls = {"count": 0}

    monkeypatch.setattr("app.wire_feed.runner.get_wire_sources", lambda: [StubSource()])
    monkeypatch.setattr("app.wire_feed.runner.DraftingService", lambda: StubDrafting())

    def fake_fetch(source, drafting):
        fetch_calls["count"] += 1
        return []

    monkeypatch.setattr("app.wire_feed.runner.fetch_and_process", fake_fetch)
    monkeypatch.setattr("app.wire_feed.runner.plan_wire_queue", lambda results, recent_posts, now, settings: [])

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def commit(self):
            return None

        def get(self, model, ident):
            return None

    class FakeCandidateRepo:
        def __init__(self, db):
            self.db = db

        def has_source_candidate_since(self, source_name, since):
            return source_name == "tradient_market_news"

    class FakeJobRepo:
        def __init__(self, db):
            self.db = db

        def expire_stale_jobs(self, now, settings):
            return 0

        def recent_post_records(self, since):
            return []

    class FakeCustomerRepo:
        def __init__(self, db):
            self.db = db

        def has_active_autopost_customer(self):
            return False

    monkeypatch.setattr("app.wire_feed.runner.SessionLocal", lambda: FakeSession())
    monkeypatch.setattr("app.wire_feed.runner.WireCandidateRepository", FakeCandidateRepo)
    monkeypatch.setattr("app.wire_feed.runner.WireJobRepository", FakeJobRepo)
    monkeypatch.setattr("app.wire_feed.runner.CustomerProfileRepository", FakeCustomerRepo)

    summary = run_wire_cycle()

    assert fetch_calls["count"] == 0
    assert summary["sources_processed"] == 0

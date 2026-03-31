from types import SimpleNamespace

from app.pipeline import publish_ready_jobs


class _FakeDB:
    def __init__(self, job, draft):
        self._job = job
        self._draft = draft
        self.added = []

    def get(self, model, key):
        return self._draft

    def add(self, value):
        self.added.append(value)

    def commit(self):
        return None

    def flush(self):
        return None


class _FakeRepo:
    def __init__(self, job):
        self._job = job

    def claim_ready(self):
        return [self._job]

    def find_stuck_publishing(self):
        return []


_FAKE_CREATOR = SimpleNamespace(token_store={}, max_posts_per_hour=6)
_FAKE_CREATOR_REPO = SimpleNamespace(get_or_create_default=lambda: _FAKE_CREATOR)


def test_publish_ready_jobs_marks_skipped(monkeypatch) -> None:
    job = SimpleNamespace(
        id=1, draft_post_id=1, status="publishing", result_message=None,
        last_error=None, attempt_count=0, idempotency_key="test-key-1",
    )
    draft = SimpleNamespace(draft_text="Hello")
    db = _FakeDB(job, draft)

    monkeypatch.setattr("app.pipeline.PublishJobRepository", lambda db_arg: _FakeRepo(job))
    monkeypatch.setattr("app.pipeline.CreatorSettingsRepository", lambda db_arg: _FAKE_CREATOR_REPO)
    monkeypatch.setattr(
        "app.pipeline.XPublisher",
        lambda token_store, on_token_refresh: SimpleNamespace(
            publish=lambda text, idempotency_key=None: {"status": "skipped", "reason": "missing_token", "text": text}
        ),
    )

    published = publish_ready_jobs(db)

    assert published == 0
    assert job.status == "skipped"
    assert job.result_message == "missing_token"


def test_publish_ready_jobs_marks_posted_and_logs(monkeypatch) -> None:
    job = SimpleNamespace(
        id=1, draft_post_id=1, status="publishing", result_message=None,
        last_error=None, attempt_count=0, idempotency_key="test-key-2",
    )
    draft = SimpleNamespace(draft_text="Hello", status="queued", event_id=10)
    event = SimpleNamespace(status="drafted")

    class _PostedDB(_FakeDB):
        def get(self, model, key):
            if key == 1:
                return draft
            if key == 10:
                return event
            return None

    db = _PostedDB(job, draft)

    monkeypatch.setattr("app.pipeline.PublishJobRepository", lambda db_arg: _FakeRepo(job))
    monkeypatch.setattr("app.pipeline.CreatorSettingsRepository", lambda db_arg: _FAKE_CREATOR_REPO)
    monkeypatch.setattr(
        "app.pipeline.XPublisher",
        lambda token_store, on_token_refresh: SimpleNamespace(
            publish=lambda text, idempotency_key=None: {"status": "posted", "data": {"id": "abc123"}}
        ),
    )

    published = publish_ready_jobs(db)

    assert published == 1
    assert job.status == "posted"
    assert draft.status == "posted"
    assert event.status == "posted"
    assert db.added


def test_publish_ready_jobs_handles_rate_limit(monkeypatch) -> None:
    job = SimpleNamespace(
        id=1, draft_post_id=1, status="publishing", result_message=None,
        last_error=None, attempt_count=0, idempotency_key="test-key-3",
        scheduled_for=None,
    )
    draft = SimpleNamespace(draft_text="Hello", status="queued", event_id=10)
    db = _FakeDB(job, draft)

    monkeypatch.setattr("app.pipeline.PublishJobRepository", lambda db_arg: _FakeRepo(job))
    monkeypatch.setattr("app.pipeline.CreatorSettingsRepository", lambda db_arg: _FAKE_CREATOR_REPO)
    monkeypatch.setattr(
        "app.pipeline.XPublisher",
        lambda token_store, on_token_refresh: SimpleNamespace(
            publish=lambda text, idempotency_key=None: {"status": "rate_limited", "retry_after_seconds": 900}
        ),
    )

    published = publish_ready_jobs(db)

    assert published == 0
    assert job.status == "queued"
    assert job.attempt_count == 0  # must not be incremented on rate limit
    assert job.scheduled_for is not None


def test_publish_ready_jobs_releases_stuck_jobs(monkeypatch) -> None:
    stuck_job = SimpleNamespace(
        id=99, status="publishing", last_error=None,
    )
    live_job = SimpleNamespace(
        id=1, draft_post_id=1, status="publishing", result_message=None,
        last_error=None, attempt_count=0, idempotency_key="test-key-4",
    )
    draft = SimpleNamespace(draft_text="Hello", status="queued", event_id=10)
    db = _FakeDB(live_job, draft)

    class _RepoWithStuck(_FakeRepo):
        def find_stuck_publishing(self):
            return [stuck_job]

    monkeypatch.setattr("app.pipeline.PublishJobRepository", lambda db_arg: _RepoWithStuck(live_job))
    monkeypatch.setattr("app.pipeline.CreatorSettingsRepository", lambda db_arg: _FAKE_CREATOR_REPO)
    monkeypatch.setattr(
        "app.pipeline.XPublisher",
        lambda token_store, on_token_refresh: SimpleNamespace(
            publish=lambda text, idempotency_key=None: {"status": "skipped", "reason": "missing_token", "text": text}
        ),
    )

    publish_ready_jobs(db)

    assert stuck_job.status == "failed"
    assert stuck_job.last_error == "timeout_stuck_in_publishing"

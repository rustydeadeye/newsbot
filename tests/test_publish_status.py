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


class _FakeRepo:
    def __init__(self, job):
        self._job = job

    def claim_ready(self):
        return [self._job]


def test_publish_ready_jobs_marks_skipped(monkeypatch) -> None:
    job = SimpleNamespace(id=1, draft_post_id=1, status="publishing", result_message=None, last_error=None, attempt_count=0)
    draft = SimpleNamespace(draft_text="Hello")
    db = _FakeDB(job, draft)

    monkeypatch.setattr("app.pipeline.PublishJobRepository", lambda db_arg: _FakeRepo(job))
    monkeypatch.setattr("app.pipeline.XPublisher", lambda: SimpleNamespace(publish=lambda text: {"status": "skipped", "reason": "missing_token", "text": text}))

    published = publish_ready_jobs(db)

    assert published == 0
    assert job.status == "skipped"
    assert job.result_message == "missing_token"


def test_publish_ready_jobs_marks_posted_and_logs(monkeypatch) -> None:
    job = SimpleNamespace(id=1, draft_post_id=1, status="publishing", result_message=None, last_error=None, attempt_count=0)
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
    monkeypatch.setattr(
        "app.pipeline.XPublisher",
        lambda: SimpleNamespace(publish=lambda text: {"status": "posted", "data": {"id": "abc123"}}),
    )

    published = publish_ready_jobs(db)

    assert published == 1
    assert job.status == "posted"
    assert draft.status == "posted"
    assert event.status == "posted"
    assert db.added

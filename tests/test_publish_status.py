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

    def list_ready(self):
        return [self._job]


def test_publish_ready_jobs_marks_skipped(monkeypatch) -> None:
    job = SimpleNamespace(id=1, draft_post_id=1, status="queued", result_message=None, last_error=None, attempt_count=0)
    draft = SimpleNamespace(draft_text="Hello")
    db = _FakeDB(job, draft)

    monkeypatch.setattr("app.pipeline.PublishJobRepository", lambda db_arg: _FakeRepo(job))
    monkeypatch.setattr("app.pipeline.XPublisher", lambda: SimpleNamespace(publish=lambda text: {"status": "skipped", "reason": "missing_token", "text": text}))

    published = publish_ready_jobs(db)

    assert published == 0
    assert job.status == "skipped"
    assert job.result_message == "missing_token"

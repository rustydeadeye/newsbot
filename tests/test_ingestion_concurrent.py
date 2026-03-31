"""Tests for concurrent source fetching in IngestionService.ingest_all()."""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.services.ingestion.service import IngestionService


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

def _make_source(name: str, sid: int = 1, enabled: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        id=sid,
        name=name,
        type="rss",
        base_url="http://example.com/feed.xml",
        enabled=enabled,
        metadata_json={},
    )


def _fetched_item(title: str = "Test") -> SimpleNamespace:
    return SimpleNamespace(
        external_id=title,
        url="http://example.com/item",
        title=title,
        published_at=datetime.now(timezone.utc),
        raw_payload={},
    )


class _FakeRepo:
    def __init__(self, sources):
        self._sources = sources
        self.added_items = []

    def list_enabled(self):
        return self._sources

    def get_item_by_checksum(self, checksum):
        return None  # always new

    def add_item(self, item):
        self.added_items.append(item)


class _FakeDB:
    def commit(self):
        pass


class _FakeService(IngestionService):
    """IngestionService with injected fake repo and controllable adapter."""

    def __init__(self, sources, adapter_fn):
        self.db = _FakeDB()
        self.repo = _FakeRepo(sources)
        self._adapter_fn = adapter_fn

    def _get_adapter(self, source):
        return self._adapter_fn(source)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_ingest_all_fetches_concurrently(monkeypatch):
    """All sources should be fetched concurrently — fetches overlap in time."""
    fetch_times: list[float] = []
    lock = threading.Lock()
    import time

    source_a = _make_source("source_a", sid=1)
    source_b = _make_source("source_b", sid=2)

    def slow_adapter(source):
        start = time.monotonic()
        time.sleep(0.05)  # 50ms simulated network delay
        end = time.monotonic()
        with lock:
            fetch_times.append((start, end))
        return SimpleNamespace(fetch=lambda: [_fetched_item(source.name)])

    service = _FakeService([source_a, source_b], slow_adapter)

    # Patch get_adapter used inside _fetch_source
    import app.services.ingestion.service as svc_module
    monkeypatch.setattr(svc_module, "get_adapter", slow_adapter)

    t0 = time.monotonic()
    counts = service.ingest_all()
    elapsed = time.monotonic() - t0

    # Two 50ms fetches concurrently should finish well under 90ms
    assert elapsed < 0.09, f"Expected concurrent fetch ~50ms, got {elapsed*1000:.0f}ms"
    assert counts["source_a"] == 1
    assert counts["source_b"] == 1


def test_ingest_all_isolates_source_failure(monkeypatch):
    """A failure in one source should not prevent other sources from being stored."""
    source_ok = _make_source("source_ok", sid=1)
    source_bad = _make_source("source_bad", sid=2)

    def adapter_fn(source):
        if source.name == "source_bad":
            raise RuntimeError("fetch failed")
        return SimpleNamespace(fetch=lambda: [_fetched_item("good item")])

    service = _FakeService([source_ok, source_bad], adapter_fn)

    import app.services.ingestion.service as svc_module
    monkeypatch.setattr(svc_module, "get_adapter", adapter_fn)

    counts = service.ingest_all()

    assert counts["source_ok"] == 1
    assert "error:" in counts["source_bad"]
    # Good source's items were stored
    assert any(item.title == "good item" for item in service.repo.added_items)


def test_ingest_all_skips_open_circuit(monkeypatch):
    """Sources with an open circuit should be skipped without fetching."""
    from datetime import timedelta

    source_tripped = _make_source("source_tripped", sid=1)
    source_tripped.metadata_json = {
        "circuit_open_until": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    }
    source_ok = _make_source("source_ok", sid=2)

    fetch_calls: list[str] = []

    def adapter_fn(source):
        fetch_calls.append(source.name)
        return SimpleNamespace(fetch=lambda: [_fetched_item("item")])

    service = _FakeService([source_tripped, source_ok], adapter_fn)

    import app.services.ingestion.service as svc_module
    monkeypatch.setattr(svc_module, "get_adapter", adapter_fn)

    counts = service.ingest_all()

    assert counts["source_tripped"] == "circuit_open"
    assert counts["source_ok"] == 1
    assert "source_tripped" not in fetch_calls

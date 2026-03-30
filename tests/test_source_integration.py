from pathlib import Path

import httpx

from app.models.source import Source, SourceItem
from app.services.ingestion.adapters import BSEMultiRSSAdapter, NSECorporateFilingsAdapter, RSSSourceAdapter
from app.services.normalization.extractors import extract_facts


FIXTURES = Path(__file__).parent / "fixtures"


class _FakeResponse:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=None)


class _FakeClient:
    def __init__(self, html: str) -> None:
        self.html = html

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def get(self, url: str) -> _FakeResponse:
        if url == "https://www.nseindia.com":
            return _FakeResponse("<html></html>")
        return _FakeResponse(self.html)


def test_rbi_rss_fixture_parses_and_normalizes(monkeypatch) -> None:
    xml = (FIXTURES / "rbi_press_releases_rss.xml").read_text(encoding="utf-8")

    def fake_get(url: str, **kwargs) -> _FakeResponse:
        return _FakeResponse(xml)

    monkeypatch.setattr(httpx, "get", fake_get)

    source = Source(name="rbi_press_releases", type="rss", base_url="https://rbi.org.in/pressreleases_rss.xml")
    items = RSSSourceAdapter(source).fetch()

    assert len(items) == 1
    item = SourceItem(
        source_id=1,
        external_id=items[0].external_id,
        url=items[0].url,
        title=items[0].title,
        published_at=items[0].published_at,
        raw_payload=items[0].raw_payload,
        checksum="x",
    )
    facts = extract_facts(source, item)

    assert facts["release_type"] == "press_release"
    assert facts["source_ref"] == "123/2025-26"
    assert facts["document_url"].endswith("prid=60500")


def test_bse_fixture_parses_multi_feed_and_normalizes(monkeypatch) -> None:
    xml = (FIXTURES / "bse_announcements.xml").read_text(encoding="utf-8")

    def fake_get(url: str, **kwargs) -> _FakeResponse:
        return _FakeResponse(xml)

    monkeypatch.setattr(httpx, "get", fake_get)

    source = Source(name="bse_announcements", type="rss", base_url="https://www.bseindia.com/data/xml/announcements.xml")
    items = BSEMultiRSSAdapter(source).fetch()

    assert len(items) == 4
    action_item = next(item for item in items if item.raw_payload["section"] == "corporate_actions")
    source_item = SourceItem(
        source_id=1,
        external_id=action_item.external_id,
        url=action_item.url,
        title=action_item.title,
        published_at=action_item.published_at,
        raw_payload=action_item.raw_payload,
        checksum="x",
    )
    facts = extract_facts(source, source_item)

    assert facts["exchange"] == "BSE"
    assert facts["announcement_subtype"] == "dividend"
    assert facts["document_url"].endswith("abc.pdf")


def test_nse_fixture_parses_table_metadata(monkeypatch) -> None:
    html = (FIXTURES / "nse_corporate_filings.html").read_text(encoding="utf-8")

    def fake_client(*args, **kwargs) -> _FakeClient:
        return _FakeClient(html)

    monkeypatch.setattr(httpx, "Client", fake_client)

    source = Source(name="nse_corporate_filings", type="html", base_url="https://www.nseindia.com/companies-listing/corporate-filings-application")
    items = NSECorporateFilingsAdapter(source).fetch()

    assert len(items) == 3
    action_item = next(item for item in items if item.raw_payload["section"] == "corporate_actions")
    source_item = SourceItem(
        source_id=1,
        external_id=action_item.external_id,
        url=action_item.url,
        title=action_item.title,
        published_at=action_item.published_at,
        raw_payload=action_item.raw_payload,
        checksum="x",
    )
    facts = extract_facts(source, source_item)

    assert facts["ticker"] == "IRB"
    assert facts["announcement_subtype"] == "bonus_split"
    assert facts["broadcast_date"] == "30-Mar-2026"

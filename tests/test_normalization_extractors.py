from datetime import datetime, timezone

from app.models.source import Source, SourceItem
from app.services.normalization.extractors import extract_facts


def test_extract_nse_financial_results_facts() -> None:
    source = Source(name="nse_corporate_filings", type="html", base_url="https://example.com")
    item = SourceItem(
        source_id=1,
        external_id="financial_results:TCS:28-Mar-2026:Financial Results",
        url="https://example.com/tcs",
        title="TCS Financial Results",
        published_at=datetime(2026, 3, 28, tzinfo=timezone.utc),
        raw_payload={"section": "financial_results", "symbol": "TCS", "subject": "Financial Results"},
        checksum="x",
    )

    facts = extract_facts(source, item)

    assert facts["ticker"] == "TCS"
    assert facts["exchange"] == "NSE"
    assert facts["event_class"] == "earnings"
    assert facts["filing_type"] == "financial_results"
    assert facts["document_url"] == "https://example.com/tcs"
    assert facts["event_date"] == "2026-03-28T00:00:00+00:00"
    assert facts["is_stale"] is False


def test_extract_bse_bonus_ratio() -> None:
    source = Source(name="bse_announcements", type="rss", base_url="https://example.com")
    item = SourceItem(
        source_id=1,
        external_id="corporate_actions:IRB:30-Mar-2026:Bonus 1:1",
        url="https://example.com/irb",
        title="IRB Bonus 1:1",
        published_at=datetime(2026, 3, 30, tzinfo=timezone.utc),
        raw_payload={
            "section": "corporate_actions",
            "symbol": "IRB",
            "subject": "Bonus 1:1",
            "document_url": "https://example.com/irb-doc",
            "announcement_subtype": "bonus_split",
            "broadcast_date": "30-Mar-2026",
        },
        checksum="x",
    )

    facts = extract_facts(source, item)

    assert facts["event_class"] == "bonus_split"
    assert facts["numbers"] == [{"type": "ratio", "value": "1:1"}]
    assert facts["subject_key"] == "bonus-1-1"
    assert facts["document_url"] == "https://example.com/irb-doc"
    assert facts["broadcast_date"] == "30-Mar-2026"
    assert facts["is_stale"] is False


def test_stale_exchange_earnings_flagged() -> None:
    source = Source(name="nse_corporate_filings", type="html", base_url="https://example.com")
    item = SourceItem(
        source_id=1,
        external_id="financial_results:BLUEBLENDS:19-Feb-2026:30-Sep-2024",
        url="https://example.com/blueblends",
        title="BLUEBLENDS 30-Sep-2024",
        published_at=datetime(2026, 2, 19, tzinfo=timezone.utc),
        raw_payload={"section": "financial_results", "symbol": "BLUEBLENDS", "subject": "30-Sep-2024", "broadcast_date": "19-Feb-2026"},
        checksum="x",
    )

    facts = extract_facts(source, item)

    assert facts["event_class"] == "earnings"
    assert facts["is_stale"] is True

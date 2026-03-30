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


def test_extract_bse_dates_support_additional_live_formats() -> None:
    source = Source(name="bse_announcements", type="rss", base_url="https://example.com")
    item = SourceItem(
        source_id=1,
        external_id="corporate_actions:UTI:31 March 2026:Bonus",
        url="https://example.com/uti",
        title="UTI Bonus 1:1",
        published_at=datetime(2026, 3, 30, tzinfo=timezone.utc),
        raw_payload={
            "section": "corporate_actions",
            "symbol": "UTI",
            "subject": "Bonus 1:1",
            "broadcast_date": "31 March 2026",
            "event_date": "29/03/2026",
        },
        checksum="x",
    )

    facts = extract_facts(source, item)

    assert facts["broadcast_date"] == "31 March 2026"
    assert facts["event_date"] == "29/03/2026"
    assert facts["is_stale"] is False


def test_rbi_macro_subject_key_collapses_auction_variants() -> None:
    source = Source(name="rbi_press_releases", type="rss", base_url="https://example.com")
    result_item = SourceItem(
        source_id=1,
        external_id="result",
        url="https://example.com/result",
        title="Result of the Second 3-day Variable Rate Repo (VRR) auction held on March 30, 2026",
        published_at=datetime(2026, 3, 30, tzinfo=timezone.utc),
        raw_payload={},
        checksum="x",
    )
    conduct_item = SourceItem(
        source_id=1,
        external_id="conduct",
        url="https://example.com/conduct",
        title="RBI to conduct Second 3-day Variable Rate Repo (VRR) auction under LAF on March 30, 2026",
        published_at=datetime(2026, 3, 30, tzinfo=timezone.utc),
        raw_payload={},
        checksum="y",
    )

    result_facts = extract_facts(source, result_item)
    conduct_facts = extract_facts(source, conduct_item)

    assert result_facts["event_class"] == "macro_release"
    assert conduct_facts["event_class"] == "macro_release"
    assert result_facts["subject_key"] == conduct_facts["subject_key"]


def test_bse_bonus_subject_key_collapses_plan_variants() -> None:
    source = Source(name="bse_announcements", type="rss", base_url="https://example.com")
    regular_item = SourceItem(
        source_id=1,
        external_id="regular",
        url="https://example.com/regular",
        title="UTI Low Duration Fund Regular Plan Bonus (9002611)",
        published_at=datetime(2026, 3, 30, tzinfo=timezone.utc),
        raw_payload={"section": "corporate_actions", "symbol": "UTI", "subject": "UTI Low Duration Fund Regular Plan Bonus (9002611)"},
        checksum="x1",
    )
    units_item = SourceItem(
        source_id=1,
        external_id="units",
        url="https://example.com/units",
        title="UTI Low Duration Fund Bonus Units Bonus (9002591)",
        published_at=datetime(2026, 3, 30, tzinfo=timezone.utc),
        raw_payload={"section": "corporate_actions", "symbol": "UTI", "subject": "UTI Low Duration Fund Bonus Units Bonus (9002591)"},
        checksum="x2",
    )

    regular_facts = extract_facts(source, regular_item)
    units_facts = extract_facts(source, units_item)

    assert regular_facts["event_class"] == "bonus_split"
    assert units_facts["event_class"] == "bonus_split"
    assert regular_facts["subject_key"] == units_facts["subject_key"]


def test_bse_bonus_subject_key_collapses_announcement_variants() -> None:
    source = Source(name="bse_announcements", type="rss", base_url="https://example.com")
    regular_item = SourceItem(
        source_id=1,
        external_id="regular-ann",
        url="https://example.com/regular-ann",
        title="UTI Low Duration Fund Regular Plan Bonus (9002611)",
        published_at=None,
        raw_payload={"section": "announcements", "symbol": "UTI", "subject": "UTI Low Duration Fund Regular Plan Bonus (9002611)"},
        checksum="xa1",
    )
    units_item = SourceItem(
        source_id=1,
        external_id="units-ann",
        url="https://example.com/units-ann",
        title="UTI Low Duration Fund Bonus Units Bonus (9002591)",
        published_at=None,
        raw_payload={"section": "announcements", "symbol": "UTI", "subject": "UTI Low Duration Fund Bonus Units Bonus (9002591)"},
        checksum="xa2",
    )

    regular_facts = extract_facts(source, regular_item)
    units_facts = extract_facts(source, units_item)

    assert regular_facts["event_class"] == "bonus_split"
    assert units_facts["event_class"] == "bonus_split"
    assert regular_facts["subject_key"] == units_facts["subject_key"]

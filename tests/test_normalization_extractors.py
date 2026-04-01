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


def test_extract_tradient_market_news_facts() -> None:
    source = Source(name="tradient_market_news", type="json", base_url="https://api.tradient.org/v1/api/market/news")
    item = SourceItem(
        source_id=1,
        external_id="tradient:JKTYRE:2026-04-01T09-15-00+05-30:JK Tyre Receives GST Demand Order Worth Rs 1.39 Crore",
        url="https://api.tradient.org/v1/api/market/news",
        title="JK Tyre Receives GST Demand Order Worth Rs 1.39 Crore",
        published_at=datetime(2026, 4, 1, 3, 45, tzinfo=timezone.utc),
        raw_payload={
            "company": "JK Tyre & Industries",
            "display_symbol": "JK Tyre & Industries",
            "ticker": "JKTYRE",
            "symbol": "JKTYRE",
            "category": "Corporate",
            "sub_category": "Tax",
            "text": "GST demand order issued.",
            "news_type": "tradient_market_news",
            "release_type": "market_news",
        },
        checksum="tradient-x",
    )

    facts = extract_facts(source, item)

    assert facts["ticker"] == "JKTYRE"
    assert facts["company"] == "JK Tyre & Industries"
    assert facts["display_symbol"] == "JK Tyre & Industries"
    assert facts["filing_type"] == "market_news"
    assert facts["release_type"] == "market_news"
    assert facts["event_class"] == "default_fraud"
    assert facts["is_stale"] is False


def test_extract_tradient_wire_facts_for_sales_update() -> None:
    source = Source(name="tradient_market_news", type="json", base_url="https://api.tradient.org/v1/api/market/news")
    item = SourceItem(
        source_id=1,
        external_id="tradient:sales",
        url="https://api.tradient.org/v1/api/market/news",
        title="Maruti Suzuki March sales update",
        published_at=datetime(2026, 4, 1, 3, 45, tzinfo=timezone.utc),
        raw_payload={
            "company": "Maruti Suzuki",
            "display_symbol": "Maruti Suzuki",
            "ticker": "MARUTI",
            "text": "March total sales 225,251 units vs 192,984 units (YoY); est 209,600. Domestic sales 198,000 units.",
            "news_type": "tradient_market_news",
            "release_type": "market_news",
        },
        checksum="tradient-sales",
    )

    facts = extract_facts(source, item)

    assert facts["wire_facts"] == {
        "kind": "sales_update",
        "subject_label": "MARUTI SUZUKI",
        "period": "MARCH",
        "metric_label": "TOTAL SALES",
        "current_value": "225,251",
        "prior_value": "192,984",
        "unit": "UNITS",
        "comparison_label": "YOY",
        "estimate_value": "209,600",
        "secondary_metric_label": "DOMESTIC SALES",
        "secondary_metric_value": "198,000",
        "secondary_metric_unit": "UNITS",
    }


def test_extract_tradient_wire_facts_for_tax_demand() -> None:
    source = Source(name="tradient_market_news", type="json", base_url="https://api.tradient.org/v1/api/market/news")
    item = SourceItem(
        source_id=1,
        external_id="tradient:tax",
        url="https://api.tradient.org/v1/api/market/news",
        title="Finolex Cables Receives GST Demand of ₹29.46 Crores",
        published_at=datetime(2026, 4, 1, 3, 45, tzinfo=timezone.utc),
        raw_payload={
            "company": "Finolex Cables",
            "display_symbol": "Finolex Cables",
            "ticker": "FINCABLES",
            "text": "GST demand of ₹29.46 crore received by the company.",
            "news_type": "tradient_market_news",
            "release_type": "market_news",
        },
        checksum="tradient-tax",
    )

    facts = extract_facts(source, item)

    assert facts["wire_facts"] == {
        "kind": "tax_demand",
        "subject_label": "FINOLEX CABLES",
        "amount_value": "RS 29.46 CRORE",
        "metric_label": "GST DEMAND ORDER",
    }


def test_extract_tradient_entity_name_from_title_when_company_missing() -> None:
    source = Source(name="tradient_market_news", type="json", base_url="https://api.tradient.org/v1/api/market/news")
    item = SourceItem(
        source_id=1,
        external_id="tradient:icra",
        url="https://api.tradient.org/v1/api/market/news",
        title="ICRA Projects 11-12% Bank Loan Growth for FY27",
        published_at=datetime(2026, 4, 1, 3, 45, tzinfo=timezone.utc),
        raw_payload={
            "company": "BANKING",
            "ticker": "BANKING",
            "symbol": "BANKING",
            "text": "ICRA projects 11-12% bank loan growth for FY27.",
            "news_type": "tradient_market_news",
            "release_type": "market_news",
        },
        checksum="tradient-icra",
    )

    facts = extract_facts(source, item)

    assert facts["company"] == "ICRA"
    assert facts["wire_facts"]["subject_label"] == "ICRA"


def test_extract_tradient_wire_facts_for_offtake_update() -> None:
    source = Source(name="tradient_market_news", type="json", base_url="https://api.tradient.org/v1/api/market/news")
    item = SourceItem(
        source_id=1,
        external_id="tradient:offtake",
        url="https://api.tradient.org/v1/api/market/news",
        title="Coal India March 2026 Offtake Up 0.7% to 69.5 MT",
        published_at=datetime(2026, 4, 1, 3, 45, tzinfo=timezone.utc),
        raw_payload={
            "company": "Coal India",
            "display_symbol": "Coal India",
            "ticker": "COALINDIA",
            "text": "Coal India March 2026 offtake up 0.7% to 69.5 MT.",
            "news_type": "tradient_market_news",
            "release_type": "market_news",
        },
        checksum="tradient-offtake",
    )

    facts = extract_facts(source, item)

    assert facts["wire_facts"] == {
        "kind": "offtake_update",
        "subject_label": "COAL INDIA",
        "period": "MARCH",
        "metric_label": "OFFTAKE",
        "change_pct": "0.7%",
        "current_value": "69.5 MT",
    }


def test_extract_tradient_wire_facts_for_generic_production_update() -> None:
    source = Source(name="tradient_market_news", type="json", base_url="https://api.tradient.org/v1/api/market/news")
    item = SourceItem(
        source_id=1,
        external_id="tradient:production",
        url="https://api.tradient.org/v1/api/market/news",
        title="Coal India Reports March 2026 Production at 84.5 Million Tonnes",
        published_at=datetime(2026, 4, 1, 3, 45, tzinfo=timezone.utc),
        raw_payload={
            "company": "Coal India",
            "display_symbol": "Coal India",
            "ticker": "COALINDIA",
            "text": "Coal India reports March 2026 production at 84.5 million tonnes.",
            "news_type": "tradient_market_news",
            "release_type": "market_news",
        },
        checksum="tradient-production",
    )

    facts = extract_facts(source, item)

    assert facts["wire_facts"] == {
        "kind": "production_update",
        "subject_label": "COAL INDIA",
        "period": "MARCH",
        "metric_label": "PRODUCTION",
        "current_value": "84.5 MILLION TONNES",
    }

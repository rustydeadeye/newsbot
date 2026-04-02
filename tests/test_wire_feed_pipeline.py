import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://dryrun:dryrun@localhost/dryrun")

from datetime import datetime, timezone

from app.wire_feed.pipeline import _should_drop_wire_candidate, fetch_and_process
from app.wire_feed.sources import WireSourceDef


def test_should_drop_wire_candidate_for_low_signal_promoter_and_compliance_items() -> None:
    assert _should_drop_wire_candidate(
        {
            "event_class": "general_update",
            "headline": "Embassy Developments Share Pledge Disclosure Filed",
            "article_text": "",
        }
    )
    assert _should_drop_wire_candidate(
        {
            "event_class": "management_change",
            "headline": "Panacea Biotec Independent Director Completes Tenure",
            "article_text": "",
        }
    )
    assert _should_drop_wire_candidate(
        {
            "event_class": "general_update",
            "headline": "IDBI Bank Files Q4FY26 SEBI Compliance Certificate",
            "article_text": "",
        }
    )
    assert _should_drop_wire_candidate(
        {
            "event_class": "sebi_enforcement",
            "headline": "Appeal No. 6790 of 2026 filed by Rohit Aggarwal",
            "article_text": "",
        }
    )
    assert _should_drop_wire_candidate(
        {
            "event_class": "earnings",
            "headline": "Capital Small Finance Bank Q4FY26 Results",
            "article_text": "",
            "wire_facts": None,
        }
    )


def test_should_not_drop_wire_candidate_for_sales_and_order_updates() -> None:
    assert not _should_drop_wire_candidate(
        {
            "event_class": "earnings",
            "headline": "Force Motors March Sales Rise 13.49% to 4,199 Units",
            "article_text": "",
        }
    )
    assert not _should_drop_wire_candidate(
        {
            "event_class": "order_win",
            "headline": "Astra Microwave JV Wins Rs 250.58 Cr HAL Order",
            "article_text": "",
        }
    )
    assert not _should_drop_wire_candidate(
        {
            "event_class": "earnings",
            "headline": "RBL Bank Gross Advances Seen At 1.15T Rupees Vs 948B (YOY)",
            "article_text": "Bank total deposits seen at 1.4T rupees vs 1.1T (YOY)",
            "wire_facts": None,
        }
    )
    assert not _should_drop_wire_candidate(
        {
            "event_class": "general_update",
            "headline": "Iran Deputy Foreign Minister Says Iran Will Set Tolls For Ships Traveling Through The Strait Of Hormuz",
            "article_text": "",
            "wire_facts": None,
        }
    )


def test_fetch_and_process_filters_low_signal_candidates(monkeypatch) -> None:
    class StubAdapter:
        def __init__(self, source):
            self.source = source

        def fetch(self):
            return [
                type(
                    "Fetched",
                    (),
                    {
                        "external_id": "1",
                        "title": "Embassy Developments Share Pledge Disclosure Filed",
                        "url": "https://example.com/1",
                        "published_at": datetime.now(timezone.utc),
                        "raw_payload": {},
                    },
                )(),
                type(
                    "Fetched",
                    (),
                    {
                        "external_id": "2",
                        "title": "Force Motors March Sales Rise 13.49% to 4,199 Units",
                        "url": "https://example.com/2",
                        "published_at": datetime.now(timezone.utc),
                        "raw_payload": {},
                    },
                )(),
            ]

    class StubDrafting:
        def make_draft_post(self, event):
            return type("Draft", (), {"draft_text": event.summary_facts["headline"], "safety_flags": {}})()

    source_def = WireSourceDef(
        key="tradient",
        name="tradient_market_news",
        type="api",
        url="https://example.com",
        adapter_cls=StubAdapter,
    )

    extracted = [
        {
            "event_class": "general_update",
            "headline": "Embassy Developments Share Pledge Disclosure Filed",
            "article_text": "",
            "ticker": None,
            "company": "Embassy Developments",
            "subject_key": "embassy",
            "category": "",
            "sub_category": "",
            "wire_facts": None,
        },
        {
            "event_class": "earnings",
            "headline": "Force Motors March Sales Rise 13.49% to 4,199 Units",
            "article_text": "",
            "ticker": "FORCEMOT",
            "company": "Force Motors",
            "subject_key": "force-motors",
            "category": "",
            "sub_category": "",
            "wire_facts": {"kind": "sales_update"},
        },
    ]

    monkeypatch.setattr("app.wire_feed.pipeline.extract_facts", lambda source, item: extracted.pop(0))
    monkeypatch.setattr("app.wire_feed.pipeline.score_event", lambda *args, **kwargs: 90)

    results = fetch_and_process(source_def, StubDrafting())

    assert len(results) == 1
    assert results[0].title == "Force Motors March Sales Rise 13.49% to 4,199 Units"


def test_fetch_and_process_filters_sebi_appeal_but_keeps_bank_metrics(monkeypatch) -> None:
    class StubAdapter:
        def __init__(self, source):
            self.source = source

        def fetch(self):
            return [
                type(
                    "Fetched",
                    (),
                    {
                        "external_id": "1",
                        "title": "Appeal No. 6790 of 2026 filed by Rohit Aggarwal",
                        "url": "https://example.com/1",
                        "published_at": datetime.now(timezone.utc),
                        "raw_payload": {},
                    },
                )(),
                type(
                    "Fetched",
                    (),
                    {
                        "external_id": "2",
                        "title": "RBL Bank Gross Advances Seen At 1.15T Rupees Vs 948B (YOY)",
                        "url": "https://example.com/2",
                        "published_at": datetime.now(timezone.utc),
                        "raw_payload": {},
                    },
                )(),
            ]

    class StubDrafting:
        def make_draft_post(self, event):
            return type("Draft", (), {"draft_text": event.summary_facts["headline"], "safety_flags": {}})()

    source_def = WireSourceDef(
        key="tradient",
        name="tradient_market_news",
        type="api",
        url="https://example.com",
        adapter_cls=StubAdapter,
    )

    extracted = [
        {
            "event_class": "sebi_enforcement",
            "headline": "Appeal No. 6790 of 2026 filed by Rohit Aggarwal",
            "article_text": "",
            "ticker": None,
            "company": None,
            "subject_key": "appeal-rohit",
            "category": "",
            "sub_category": "",
            "wire_facts": None,
        },
        {
            "event_class": "earnings",
            "headline": "RBL Bank Gross Advances Seen At 1.15T Rupees Vs 948B (YOY)",
            "article_text": "Bank total deposits seen at 1.4T rupees vs 1.1T (YOY)",
            "ticker": "RBLBANK",
            "company": "RBL Bank",
            "subject_key": "rbl-bank-business",
            "category": "",
            "sub_category": "",
            "wire_facts": None,
        },
    ]

    monkeypatch.setattr("app.wire_feed.pipeline.extract_facts", lambda source, item: extracted.pop(0))
    monkeypatch.setattr("app.wire_feed.pipeline.score_event", lambda *args, **kwargs: 90)

    results = fetch_and_process(source_def, StubDrafting())

    assert len(results) == 1
    assert results[0].title == "RBL Bank Gross Advances Seen At 1.15T Rupees Vs 948B (YOY)"

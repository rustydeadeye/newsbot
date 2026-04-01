from app.models.source import Source
from app.services.ingestion.adapters import (
    _nse_row_metadata,
    _parse_date,
    _parse_tradient_datetime,
    _rss_payload,
    _tradient_news_item,
    get_adapter,
)


def test_get_adapter_for_nse() -> None:
    source = Source(name="nse_corporate_filings", type="html", base_url="https://example.com")
    adapter = get_adapter(source)
    assert adapter.__class__.__name__ == "NSECorporateFilingsAdapter"


def test_get_adapter_for_bse() -> None:
    source = Source(name="bse_announcements", type="rss", base_url="https://example.com")
    adapter = get_adapter(source)
    assert adapter.__class__.__name__ == "BSEMultiRSSAdapter"


def test_get_adapter_for_tradient() -> None:
    source = Source(name="tradient_market_news", type="json", base_url="https://api.tradient.org/v1/api/market/news")
    adapter = get_adapter(source)
    assert adapter.__class__.__name__ == "TradientMarketNewsAdapter"


def test_parse_date_formats() -> None:
    parsed = _parse_date("28-Mar-2026")
    assert parsed is not None
    assert parsed.year == 2026


def test_parse_date_additional_live_formats() -> None:
    assert _parse_date("29/03/2026") is not None
    assert _parse_date("31 March 2026") is not None
    assert _parse_date("30-March-2026") is not None
    assert _parse_date("13-4-26") is not None


def test_parse_tradient_datetime_iso() -> None:
    parsed = _parse_tradient_datetime("2026-04-01T09:15:00+05:30")
    assert parsed is not None
    assert parsed.year == 2026
    assert parsed.tzinfo is not None


def test_parse_tradient_datetime_epoch_millis() -> None:
    parsed = _parse_tradient_datetime(1775033238949)
    assert parsed is not None
    assert parsed.year == 2026


def test_rss_payload_extracts_reference_and_subtype() -> None:
    payload = _rss_payload(
        "RBI Press Release: Monetary Policy Statement",
        "https://example.com/doc",
        "guid-1",
        "Fri, 28 Mar 2026 10:00:00 GMT",
        "PR No. 123/2026",
    )
    assert payload["document_url"] == "https://example.com/doc"
    assert payload["source_ref"] == "123/2026"
    assert payload["release_type"] == "press_release"


def test_nse_row_metadata_uses_headers() -> None:
    metadata = _nse_row_metadata(
        ["Symbol", "Purpose", "Ex-Date"],
        [{"text": "IRB", "href": "/irb"}, {"text": "Bonus 1:1", "href": None}, {"text": "30-Mar-2026", "href": None}],
    )
    assert metadata["ex_date"] == "30-Mar-2026"
    assert metadata["announcement_subtype"] == "bonus_split"


def test_tradient_news_item_maps_market_news_fields() -> None:
    item = _tradient_news_item(
        "https://api.tradient.org/v1/api/market/news",
        {
            "news_object": {
                "title": "JK Tyre Receives GST Demand Order Worth Rs 1.39 Crore",
                "text": "GST demand order issued.",
                "overall_sentiment": "negative",
            },
            "stock_name": "JK Tyre & Industries",
            "sm_symbol": "JKTYRE",
            "publish_date": 1775033238949,
            "category": "Corporate",
            "sub_category": "Tax",
            "article_id": 123,
            "article_slug": "jk-tyre-receives-gst-demand-order-worth-rs-1-39-crore",
            "display_symbol": "JK Tyre & Industries",
        },
    )
    assert item is not None
    assert item.raw_payload["ticker"] == "JKTYRE"
    assert item.raw_payload["company"] == "JK Tyre & Industries"
    assert item.raw_payload["release_type"] == "market_news"
    assert item.raw_payload["overall_sentiment"] == "negative"
    assert item.raw_payload["display_symbol"] == "JK Tyre & Industries"
    assert item.url == "https://tradient.org/news/jk-tyre-receives-gst-demand-order-worth-rs-1-39-crore"
    assert item.published_at is not None

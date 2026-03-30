from app.models.source import Source
from app.services.ingestion.adapters import _nse_row_metadata, _parse_date, _rss_payload, get_adapter


def test_get_adapter_for_nse() -> None:
    source = Source(name="nse_corporate_filings", type="html", base_url="https://example.com")
    adapter = get_adapter(source)
    assert adapter.__class__.__name__ == "NSECorporateFilingsAdapter"


def test_get_adapter_for_bse() -> None:
    source = Source(name="bse_announcements", type="rss", base_url="https://example.com")
    adapter = get_adapter(source)
    assert adapter.__class__.__name__ == "BSEMultiRSSAdapter"


def test_parse_date_formats() -> None:
    parsed = _parse_date("28-Mar-2026")
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

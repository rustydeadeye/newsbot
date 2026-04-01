from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
import logging
import random
import re
import time
from urllib.parse import urljoin
from xml.etree import ElementTree

import httpx

from app.models.source import Source
from app.services.ingestion.base import FetchedItem

logger = logging.getLogger(__name__)

_RETRY_BACKOFF = [2.0, 8.0]  # seconds between attempts 1→2, 2→3
_RETRY_JITTER = 0.2           # ±20% jitter


def _should_retry(exc: Exception) -> bool:
    if isinstance(exc, httpx.RequestError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False


def _http_get_with_retry(url: str, **kwargs) -> httpx.Response:
    last_exc: Exception | None = None
    for attempt, backoff in enumerate([0.0] + _RETRY_BACKOFF):
        if backoff > 0:
            jitter = backoff * _RETRY_JITTER * (2 * random.random() - 1)
            time.sleep(backoff + jitter)
            logger.info("Retrying fetch (attempt %d): %s", attempt + 1, url)
        try:
            response = httpx.get(url, **kwargs)
            response.raise_for_status()
            return response
        except Exception as exc:
            last_exc = exc
            if not _should_retry(exc):
                raise
    raise last_exc  # type: ignore[misc]


def _client_get_with_retry(client: httpx.Client, url: str, **kwargs) -> httpx.Response:
    last_exc: Exception | None = None
    for attempt, backoff in enumerate([0.0] + _RETRY_BACKOFF):
        if backoff > 0:
            jitter = backoff * _RETRY_JITTER * (2 * random.random() - 1)
            time.sleep(backoff + jitter)
            logger.info("Retrying fetch (attempt %d): %s", attempt + 1, url)
        try:
            response = client.get(url, **kwargs)
            response.raise_for_status()
            return response
        except Exception as exc:
            last_exc = exc
            if not _should_retry(exc):
                raise
    raise last_exc  # type: ignore[misc]

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

BSE_FEEDS = [
    ("announcements", "https://www.bseindia.com/data/xml/announcements.xml"),
    ("corporate_actions", "https://www.bseindia.com/data/XML/CorpActionFeed.xml"),
    ("board_meetings", "https://www.bseindia.com/Data/XML/BoardMeetingsFeed.xml"),
    ("financial_results", "https://www.bseindia.com/Data/XML/FinancialResultsFeed.xml"),
]


class SourceAdapter(ABC):
    def __init__(self, source: Source) -> None:
        self.source = source

    @abstractmethod
    def fetch(self) -> list[FetchedItem]:
        raise NotImplementedError


class RSSSourceAdapter(SourceAdapter):
    def fetch(self) -> list[FetchedItem]:
        return _fetch_rss_items(self.source.base_url)


class BSEMultiRSSAdapter(SourceAdapter):
    def fetch(self) -> list[FetchedItem]:
        items: list[FetchedItem] = []
        for section, feed_url in BSE_FEEDS:
            try:
                feed_items = _fetch_rss_items(feed_url)
            except (httpx.HTTPStatusError, httpx.RequestError):
                logger.warning("Skipping BSE feed section=%s due to fetch error", section)
                continue
            for item in feed_items:
                payload = dict(item.raw_payload)
                payload["section"] = section
                payload["exchange"] = "BSE"
                payload.setdefault("document_url", item.url)
                items.append(
                    FetchedItem(
                        external_id=f"{section}:{item.external_id}",
                        url=item.url,
                        title=item.title,
                        published_at=item.published_at,
                        raw_payload=payload,
                    )
                )
        return items


class NSECorporateFilingsAdapter(SourceAdapter):
    def fetch(self) -> list[FetchedItem]:
        try:
            with httpx.Client(headers=DEFAULT_HEADERS, timeout=20.0, follow_redirects=True) as client:
                client.get("https://www.nseindia.com")
                response = _client_get_with_retry(client, self.source.base_url)
        except httpx.HTTPStatusError as exc:
            logger.warning("NSE fetch returned HTTP %s", exc.response.status_code)
            raise
        except httpx.RequestError as exc:
            logger.warning("NSE fetch request failed (%s)", type(exc).__name__)
            raise

        heading_tables = _extract_heading_tables(response.text)
        if not heading_tables:
            logger.warning("NSE page returned no heading/table pairs — page markup may have changed")
        items: list[FetchedItem] = []
        for heading, table_html in heading_tables:
            section = _nse_section(heading)
            if not section:
                continue
            try:
                headers, rows = _extract_table(table_html)
            except Exception:
                logger.warning("NSE failed to parse table for section=%s; skipping", section, exc_info=True)
                continue
            for row in rows:
                if len(row) < 3:
                    continue
                symbol = row[0]["text"]
                subject = row[1]["text"]
                date_text = row[2]["text"]
                if not symbol or not subject:
                    continue
                url = urljoin(self.source.base_url, row[0]["href"]) if row[0]["href"] else self.source.base_url
                published_at = _parse_date(date_text)
                metadata = _nse_row_metadata(headers, row)
                items.append(
                    FetchedItem(
                        external_id=f"{section}:{symbol}:{date_text}:{subject}",
                        url=url,
                        title=f"{symbol} {subject}",
                        published_at=published_at,
                        raw_payload={
                            "section": section,
                            "symbol": symbol,
                            "subject": subject,
                            "date_text": date_text,
                            "exchange": "NSE",
                            "document_url": url,
                            **metadata,
                        },
                    )
                )
        return items


class MOSPIPressReleaseAdapter(SourceAdapter):
    def fetch(self) -> list[FetchedItem]:
        try:
            response = _http_get_with_retry(self.source.base_url, headers=DEFAULT_HEADERS, timeout=20.0, follow_redirects=True)
        except httpx.HTTPStatusError as exc:
            logger.warning("MOSPI fetch returned HTTP %s", exc.response.status_code)
            raise
        except httpx.RequestError as exc:
            logger.warning("MOSPI fetch request failed (%s)", type(exc).__name__)
            raise
        items: list[FetchedItem] = []

        for row in _extract_table_rows(response.text):
            if len(row) < 3:
                continue
            subject = row[1]["text"]
            date_text = row[2]["text"]
            if not subject or not date_text:
                continue
            url = urljoin(self.source.base_url, row[1]["href"]) if row[1]["href"] else self.source.base_url
            items.append(
                FetchedItem(
                    external_id=f"mospi:{date_text}:{subject}",
                    url=url,
                    title=subject,
                    published_at=_parse_date(date_text),
                    raw_payload={
                        "subject": subject,
                        "date_text": date_text,
                        "document_url": url,
                        "release_type": _mospi_release_type(subject),
                    },
                )
            )
        return items


class SEBIRSSAdapter(SourceAdapter):
    """Handles SEBI's RSS feed which has a non-standard date format and URL-based document types."""

    def fetch(self) -> list[FetchedItem]:
        try:
            response = _http_get_with_retry(self.source.base_url, headers=DEFAULT_HEADERS, timeout=20.0, follow_redirects=True)
        except httpx.HTTPStatusError as exc:
            logger.warning("SEBI RSS returned HTTP %s", exc.response.status_code)
            raise
        except httpx.RequestError as exc:
            logger.warning("SEBI RSS request failed (%s)", type(exc).__name__)
            raise

        root = ElementTree.fromstring(response.text)
        items: list[FetchedItem] = []
        for node in root.findall(".//item"):
            title = (node.findtext("title") or "").strip()
            link = (node.findtext("link") or "").strip()
            guid = (node.findtext("guid") or link or title).strip()
            pub_date_raw = node.findtext("pubDate")
            description = node.findtext("description")
            doc_type = _sebi_doc_type_from_url(link)
            payload = _rss_payload(title, link, guid, pub_date_raw, description)
            payload["sebi_document_type"] = doc_type
            if doc_type:
                payload["release_type"] = doc_type
            items.append(
                FetchedItem(
                    external_id=guid,
                    url=link,
                    title=title,
                    published_at=_parse_sebi_date(pub_date_raw),
                    raw_payload=payload,
                )
            )
        return items


class PlaceholderHtmlAdapter(SourceAdapter):
    def fetch(self) -> list[FetchedItem]:
        return []


class TradientMarketNewsAdapter(SourceAdapter):
    def fetch(self) -> list[FetchedItem]:
        try:
            response = _http_get_with_retry(
                self.source.base_url,
                headers={"Accept": "application/json", **DEFAULT_HEADERS},
                timeout=20.0,
                follow_redirects=True,
            )
        except httpx.HTTPStatusError as exc:
            logger.warning("Tradient market news returned HTTP %s", exc.response.status_code)
            raise
        except httpx.RequestError as exc:
            logger.warning("Tradient market news request failed (%s)", type(exc).__name__)
            raise

        payload = response.json()
        rows = ((payload.get("data") or {}).get("latest_news") or [])
        items: list[FetchedItem] = []
        for row in rows:
            item = _tradient_news_item(self.source.base_url, row)
            if item is not None:
                items.append(item)
        return items


def get_adapter(source: Source) -> SourceAdapter:
    if source.name == "bse_announcements":
        return BSEMultiRSSAdapter(source)
    if source.name == "nse_corporate_filings":
        return NSECorporateFilingsAdapter(source)
    if source.name == "mospi_releases":
        return MOSPIPressReleaseAdapter(source)
    if source.name == "sebi_releases":
        return SEBIRSSAdapter(source)
    if source.name == "tradient_market_news":
        return TradientMarketNewsAdapter(source)
    if source.type == "rss":
        return RSSSourceAdapter(source)
    logger.warning("No adapter implemented for source=%s type=%s; no items will be fetched", source.name, source.type)
    return PlaceholderHtmlAdapter(source)


def _parse_sebi_date(value: str | None) -> datetime | None:
    """Parse SEBI's non-standard pubDate: '30 Mar, 2026 +0530' → aware datetime."""
    if not value:
        return None
    # Normalize: strip comma after day, reformat timezone "+0530" → "+05:30"
    normalized = re.sub(
        r"(\d{1,2})\s+([A-Za-z]+),?\s+(\d{4})\s+([+-]\d{2})(\d{2})",
        r"\1 \2 \3 \4:\5",
        value.strip(),
    )
    for fmt in ("%d %b %Y %z", "%d %B %Y %z"):
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue
    # Fallback to generic parser
    result = _parse_datetime(value)
    if result is None:
        logger.warning("Could not parse SEBI date: %r", value)
    return result


def _sebi_doc_type_from_url(url: str) -> str | None:
    """Return a SEBI document type string based on the URL path."""
    lowered = url.lower()
    if "/enforcement/" in lowered:
        return "sebi_enforcement"
    if "/legal/circulars/" in lowered or "/circulars/" in lowered:
        return "sebi_circular"
    if "/media-and-notifications/press-releases/" in lowered:
        return "sebi_press_release"
    if "/legal/framework/" in lowered or "/legal/regulations/" in lowered:
        return "sebi_regulation"
    return None


def _fetch_rss_items(feed_url: str) -> list[FetchedItem]:
    try:
        response = _http_get_with_retry(feed_url, headers=DEFAULT_HEADERS, timeout=20.0, follow_redirects=True)
    except httpx.HTTPStatusError as exc:
        logger.warning("RSS feed returned HTTP %s: %s", exc.response.status_code, feed_url)
        raise
    except httpx.RequestError as exc:
        logger.warning("RSS feed request failed (%s): %s", type(exc).__name__, feed_url)
        raise
    root = ElementTree.fromstring(response.text)
    items: list[FetchedItem] = []

    for node in root.findall(".//item"):
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        guid = (node.findtext("guid") or link or title).strip()
        pub_date = node.findtext("pubDate")
        description = node.findtext("description")
        items.append(
            FetchedItem(
                external_id=guid,
                url=link,
                title=title,
                published_at=_parse_datetime(pub_date),
                raw_payload=_rss_payload(title, link, guid, pub_date, description),
            )
        )
    return items


def _tradient_news_item(default_url: str, row: dict) -> FetchedItem | None:
    news_object = row.get("news_object") if isinstance(row.get("news_object"), dict) else {}
    title = str(news_object.get("title") or row.get("title") or "").strip()
    if not title:
        return None
    stock_name = str(row.get("stock_name") or "").strip() or None
    symbol = str(row.get("sm_symbol") or "").strip().upper() or None
    publish_date = row.get("publish_date")
    article_url = (
        str(row.get("article_url") or row.get("url") or row.get("source_url") or "").strip()
        or _tradient_article_url(row)
        or default_url
    )
    raw_payload = {
        "company": stock_name,
        "ticker": symbol,
        "symbol": symbol,
        "article_url": article_url,
        "document_url": article_url,
        "source_ref": row.get("source") or row.get("category"),
        "release_type": "market_news",
        "category": row.get("category"),
        "sub_category": row.get("sub_category"),
        "text": news_object.get("text") or row.get("text"),
        "publish_date": publish_date,
        "nse_scrip_code": row.get("nse_scrip_code"),
        "bse_scrip_code": row.get("bse_scrip_code"),
        "display_symbol": row.get("display_symbol"),
        "overall_sentiment": news_object.get("overall_sentiment") or row.get("overall_sentiment"),
        "news_type": "tradient_market_news",
    }
    raw_payload = {key: value for key, value in raw_payload.items() if value not in (None, "", [])}
    external_id_parts = [str(row.get("article_id") or symbol or stock_name or "news"), str(publish_date or "undated"), title]
    external_id = "tradient:" + ":".join(part.replace(":", "-") for part in external_id_parts)
    return FetchedItem(
        external_id=external_id,
        url=article_url,
        title=title,
        published_at=_parse_tradient_datetime(publish_date),
        raw_payload=raw_payload,
    )


def _nse_section(title: str) -> str | None:
    lowered = title.lower()
    if "latest announcements" in lowered:
        return "announcements"
    if "corporate actions" in lowered:
        return "corporate_actions"
    if "board meetings" in lowered:
        return "board_meetings"
    if "financial results" in lowered:
        return "financial_results"
    return None


def _extract_heading_tables(html: str) -> list[tuple[str, str]]:
    pattern = re.compile(r"<h[23][^>]*>(?P<heading>.*?)</h[23]>(?P<body>.*?<table.*?</table>)", re.IGNORECASE | re.DOTALL)
    matches: list[tuple[str, str]] = []
    for match in pattern.finditer(html):
        heading = _clean_html_text(match.group("heading"))
        body = match.group("body")
        table_match = re.search(r"(<table.*?</table>)", body, re.IGNORECASE | re.DOTALL)
        if table_match:
            matches.append((heading, table_match.group(1)))
    return matches


def _extract_table(html: str) -> tuple[list[str], list[list[dict[str, str | None]]]]:
    headers: list[str] = []
    rows: list[list[dict[str, str | None]]] = []
    for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.IGNORECASE | re.DOTALL):
        if not headers:
            header_cells = re.findall(r"<th[^>]*>(.*?)</th>", row_html, re.IGNORECASE | re.DOTALL)
            if header_cells:
                headers = [_clean_html_text(cell) for cell in header_cells]
                continue
        row: list[dict[str, str | None]] = []
        for cell_html in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.IGNORECASE | re.DOTALL):
            href_match = re.search(r'href=["\']([^"\']+)["\']', cell_html, re.IGNORECASE)
            row.append({"text": _clean_html_text(cell_html), "href": href_match.group(1) if href_match else None})
        if row:
            rows.append(row)
    return headers, rows


def _extract_table_rows(html: str) -> list[list[dict[str, str | None]]]:
    _, rows = _extract_table(html)
    return rows


def _clean_html_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    text = unescape(text)
    return " ".join(text.split())


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    for fmt in (
        "%d-%b-%Y",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%d %b %Y",
        "%d %B %Y",
        "%d-%B-%Y",
        "%d-%m-%y",
    ):
        try:
            return datetime.strptime(normalized, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    result = _parse_datetime(normalized)
    if result is None:
        logger.warning("Unrecognised date format from source: %r", value)
    return result


def _parse_tradient_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            logger.warning("Unrecognised Tradient epoch datetime from source: %r", value)
            return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        parsed = _parse_datetime(normalized) or _parse_date(normalized)
    if parsed is None:
        logger.warning("Unrecognised Tradient datetime from source: %r", value)
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _tradient_article_url(row: dict) -> str | None:
    slug = str(row.get("article_slug") or "").strip()
    if not slug:
        return None
    return f"https://tradient.org/news/{slug}"


def _rss_payload(title: str, link: str, guid: str, pub_date: str | None, description: str | None) -> dict:
    payload = {
        "title": title,
        "link": link,
        "guid": guid,
        "pubDate": pub_date,
        "description": description,
        "document_url": link,
        "source_ref": _extract_source_ref(title, description),
        "release_type": _release_type_from_text(title, description),
        "announcement_subtype": _announcement_subtype_from_text(title),
    }
    payload.update(_structured_fields_from_text(title, description))
    return payload


def _structured_fields_from_text(title: str, description: str | None) -> dict:
    text = " ".join(part for part in [title, description or ""] if part)
    return {
        "company_name": _extract_company_name(title),
        "period": _extract_period(text),
        "event_date": _extract_date_fragment(text),
        "broadcast_date": _extract_date_fragment(title),
    }


def _extract_source_ref(title: str, description: str | None) -> str | None:
    text = " ".join(part for part in [title, description or ""] if part)
    match = re.search(r"\b(?:pr\s+no\.?|press release\s+no\.?|circular\s+no\.?|notification\s+no\.?)\s*[:\-]?\s*([A-Za-z0-9/-]+)", text, re.IGNORECASE)
    return match.group(1) if match else None


def _release_type_from_text(title: str, description: str | None) -> str | None:
    text = " ".join(part for part in [title, description or ""] if part).lower()
    if "press release" in text:
        return "press_release"
    if "circular" in text:
        return "circular"
    if "notification" in text:
        return "notification"
    return None


def _announcement_subtype_from_text(title: str) -> str | None:
    lowered = title.lower()
    if "dividend" in lowered:
        return "dividend"
    if "bonus" in lowered or "split" in lowered:
        return "bonus_split"
    if "financial result" in lowered or "results" in lowered:
        return "financial_results"
    if "board meeting" in lowered:
        return "board_meeting"
    if "director" in lowered or "key managerial personnel" in lowered:
        return "management_change"
    return None


def _extract_company_name(title: str) -> str | None:
    parts = re.split(r"\s[-:]\s|\s{2,}", title, maxsplit=1)
    if not parts:
        return None
    first = parts[0].strip()
    if first.isupper() and 2 <= len(first) <= 20:
        return first
    return None


def _extract_period(text: str) -> str | None:
    lowered = text.lower()
    if "q1" in lowered or "quarter ended june" in lowered:
        return "Q1"
    if "q2" in lowered or "quarter ended september" in lowered:
        return "Q2"
    if "q3" in lowered or "quarter ended december" in lowered:
        return "Q3"
    if "q4" in lowered or "year ended march" in lowered:
        return "Q4/FY"
    return None


def _extract_date_fragment(text: str) -> str | None:
    match = re.search(r"\b\d{1,2}[-/ ](?:[A-Za-z]{3,9}|\d{1,2})[-/ ]\d{2,4}\b", text)
    return match.group(0) if match else None


def _nse_row_metadata(headers: list[str], row: list[dict[str, str | None]]) -> dict:
    data: dict[str, str | None] = {}
    for index, header in enumerate(headers):
        if index >= len(row):
            continue
        key = re.sub(r"[^a-z0-9]+", "_", header.lower()).strip("_")
        data[key] = row[index]["text"]
    data["announcement_subtype"] = _announcement_subtype_from_text(row[1]["text"]) if len(row) > 1 else None
    data["broadcast_date"] = data.get("broadcast_date") or data.get("meeting_date") or data.get("ex_date") or data.get("date")
    data["event_date"] = data.get("period_ended") or data.get("meeting_date") or data.get("ex_date") or data.get("date")
    return data


def _mospi_release_type(subject: str) -> str:
    lowered = subject.lower()
    if "cpi" in lowered:
        return "cpi_release"
    if "iip" in lowered:
        return "iip_release"
    if "gdp" in lowered or "national accounts" in lowered:
        return "gdp_release"
    return "press_release"

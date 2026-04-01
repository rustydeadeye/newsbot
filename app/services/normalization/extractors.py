from __future__ import annotations

from datetime import datetime, timezone
import re

import logging

from app.models.source import Source, SourceItem
from app.services.normalization.classifier import classify_event_type
from app.services.normalization.dedupe import normalize_subject

logger = logging.getLogger(__name__)

_TICKER_RE = re.compile(r"\b([A-Z]{2,10})\b")
_PER_SHARE_RE = re.compile(r"(rs|re)\s*\.?\s*([\d]+(?:\.\d+)?)\s*per\s*share", re.IGNORECASE)
_RATIO_RE = re.compile(r"\b(\d+\s*:\s*\d+)\b")


def extract_facts(source: Source, item: SourceItem) -> dict:
    title = item.title.strip()
    section = item.raw_payload.get("section")
    ticker = _extract_ticker(source, item, title)
    entity_name = _extract_entity_name(item, ticker)
    sebi_doc_type = item.raw_payload.get("sebi_document_type") if source.name == "sebi_releases" else None
    event_type = classify_event_type(title, source.name, section, sebi_doc_type=sebi_doc_type)
    period = item.raw_payload.get("period") or _extract_period(title)
    numbers = _extract_numbers(title)
    filing_type = _extract_filing_type(item, event_type, section)
    subject_key = _subject_key(source, item, event_type, section)
    return {
        "headline": title,
        "source_name": source.name,
        "source_url": item.url,
        "source_ref": item.raw_payload.get("source_ref"),
        "document_url": item.raw_payload.get("document_url") or item.url,
        "company": entity_name,
        "ticker": ticker,
        "exchange": _exchange(source.name, ticker),
        "event_class": event_type,
        "section": section,
        "announcement_subtype": item.raw_payload.get("announcement_subtype"),
        "release_type": item.raw_payload.get("release_type"),
        "numbers": numbers,
        "currency": "INR",
        "period": period,
        "event_date": _coalesce_date(item.raw_payload.get("event_date"), item.published_at),
        "broadcast_date": _coalesce_date(item.raw_payload.get("broadcast_date"), item.published_at),
        "effective_date": item.published_at.isoformat() if item.published_at else None,
        "filing_type": filing_type,
        "subject_key": subject_key,
        "quote_excerpt": None,
        "attribution_required": True,
        "is_stale": _is_stale_event(source.name, event_type, item.raw_payload, item.published_at),
    }


def _extract_ticker(source: Source, item: SourceItem, title: str) -> str | None:
    for candidate in (item.raw_payload.get("symbol"), item.raw_payload.get("ticker")):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip().upper()
    if source.name in {"nse_corporate_filings", "bse_announcements"}:
        match = _TICKER_RE.search(title.upper())
        if match:
            return match.group(1)
    return None


def _extract_entity_name(item: SourceItem, ticker: str | None) -> str | None:
    for candidate in (item.raw_payload.get("company_name"), item.raw_payload.get("company")):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return ticker


def _extract_period(title: str) -> str | None:
    lowered = title.lower()
    if "q1" in lowered or "quarter ended june" in lowered:
        return "Q1"
    if "q2" in lowered or "quarter ended september" in lowered:
        return "Q2"
    if "q3" in lowered or "quarter ended december" in lowered:
        return "Q3"
    if "q4" in lowered or "year ended march" in lowered:
        return "Q4/FY"
    return None


def _extract_numbers(title: str) -> list[dict]:
    numbers: list[dict] = []
    per_share = _PER_SHARE_RE.search(title)
    if per_share:
        numbers.append({"type": "per_share", "currency": per_share.group(1).upper(), "value": per_share.group(2)})
    ratio = _RATIO_RE.search(title)
    if ratio:
        numbers.append({"type": "ratio", "value": ratio.group(1).replace(" ", "")})
    return numbers


def _extract_filing_type(item: SourceItem, event_type: str, section: str | None) -> str | None:
    raw = item.raw_payload.get("filing_type")
    if raw:
        return raw
    mapping = {
        "earnings": "financial_results",
        "fund_notice": "fund_notice",
        "dividend": "corporate_action",
        "bonus_split": "corporate_action",
        "fundraise": "corporate_announcement",
        "order_win": "corporate_announcement",
        "management_change": "board_meeting" if section == "board_meetings" else "corporate_announcement",
    }
    return mapping.get(event_type, section)


def _subject_key(source: Source, item: SourceItem, event_type: str, section: str | None) -> str:
    if source.name == "rbi_press_releases" and event_type == "macro_release":
        return _macro_subject_key(item.title)
    if source.name == "bse_announcements" and event_type in {"bonus_split", "dividend", "fund_notice"}:
        return _corporate_action_subject_key(source, item, event_type)
    if section == "corporate_actions":
        return _corporate_action_subject_key(source, item, event_type)
    if event_type == "earnings":
        return normalize_subject(f"{item.raw_payload.get('subject') or item.title}|{item.raw_payload.get('period') or _extract_period(item.title) or ''}")
    return normalize_subject(item.raw_payload.get("subject") or item.title)


def _macro_subject_key(title: str) -> str:
    lowered = title.lower().strip()
    lowered = re.sub(r"\bresult of (the )?", "", lowered)
    lowered = re.sub(r"\brbi to conduct\b", "", lowered)
    lowered = re.sub(r"\bauction held on\b.*$", "auction", lowered)
    lowered = re.sub(r"\bon\b.*$", "", lowered)
    lowered = re.sub(r"\b(first|second|third|fourth)\b", "", lowered)
    lowered = re.sub(r"\bunder\s+laf\b", "", lowered)
    return normalize_subject(lowered)


def _corporate_action_subject_key(source: Source, item: SourceItem, event_type: str) -> str:
    raw_subject = item.raw_payload.get("subject") or item.title
    normalized = str(raw_subject).lower().strip()
    normalized = re.sub(r"\([^)]*\)", "", normalized)
    if source.name == "bse_announcements":
        normalized = re.sub(
            r"\b(regular plan|direct plan|bonus plan|bonus units|growth plan|growth option|idcw option|daily dividend option)\b",
            " ",
            normalized,
        )
    preserved_action = normalize_subject(normalized)
    normalized = re.sub(r"\b(dividend|bonus|split)\b", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if normalized and re.fullmatch(r"[\d:\s.]+", normalized):
        return preserved_action
    return normalize_subject(f"{normalized}|{event_type}")


def _exchange(source_name: str, ticker: str | None) -> str | None:
    if not ticker:
        return None
    if source_name == "nse_corporate_filings":
        return "NSE"
    if source_name == "bse_announcements":
        return "BSE"
    return "NSE/BSE"


def _coalesce_date(raw_value: str | None, fallback) -> str | None:
    if isinstance(raw_value, str) and raw_value.strip():
        return raw_value.strip()
    if fallback:
        return fallback.isoformat()
    return None


def _is_stale_event(source_name: str, event_type: str, raw_payload: dict, published_at) -> bool:
    latest_date = _latest_relevant_date(raw_payload, published_at)
    if latest_date is None:
        return False
    today = datetime.now(timezone.utc).date()
    age_days = (today - latest_date).days

    if source_name in {"nse_corporate_filings", "bse_announcements"} and event_type == "earnings":
        return age_days > 30
    if source_name in {"nse_corporate_filings", "bse_announcements"} and event_type in {"general_update", "fund_notice"}:
        return age_days > 14
    return False


def _latest_relevant_date(raw_payload: dict, published_at) -> datetime.date | None:
    for key in ("broadcast_date", "event_date", "date_text"):
        parsed = _parse_date_like(raw_payload.get(key))
        if parsed:
            return parsed
    if published_at:
        return published_at.date()
    return None


def _parse_date_like(value: str | None) -> datetime.date | None:
    if not value or not isinstance(value, str):
        return None
    for fmt in (
        "%d-%b-%Y",
        "%d-%B-%Y",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%d %b %Y",
        "%d %B %Y",
        "%d-%m-%y",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    logger.warning("Unrecognised date format in source payload: %r", value)
    return None

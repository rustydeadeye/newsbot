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
_GENERIC_SUBJECT_VALUES = {
    "BANKING",
    "BANKS",
    "AUTO",
    "AUTOMOBILE",
    "METALS",
    "PHARMA",
    "IT",
    "ENERGY",
    "REALTY",
    "INFRA",
    "POWER",
}


def extract_facts(source: Source, item: SourceItem) -> dict:
    title = item.title.strip()
    article_text = _extract_article_text(item)
    section = item.raw_payload.get("section")
    ticker = _extract_ticker(source, item, title)
    entity_name = _extract_entity_name(item, ticker)
    sebi_doc_type = item.raw_payload.get("sebi_document_type") if source.name == "sebi_releases" else None
    category = item.raw_payload.get("category")
    sub_category = item.raw_payload.get("sub_category")
    event_type = classify_event_type(
        title,
        source.name,
        section,
        sebi_doc_type=sebi_doc_type,
        body_text=article_text,
        category=category,
        sub_category=sub_category,
    )
    period = item.raw_payload.get("period") or _extract_period(title)
    numbers = _extract_numbers(title)
    wire_facts = _extract_wire_facts(
        title=title,
        article_text=article_text,
        event_type=event_type,
        company=entity_name,
        display_symbol=item.raw_payload.get("display_symbol"),
    )
    filing_type = _extract_filing_type(item, event_type, section)
    subject_key = _subject_key(source, item, event_type, section)
    return {
        "headline": title,
        "article_text": article_text,
        "source_name": source.name,
        "source_url": item.url,
        "source_ref": item.raw_payload.get("source_ref"),
        "document_url": item.raw_payload.get("document_url") or item.url,
        "company": entity_name,
        "display_symbol": item.raw_payload.get("display_symbol"),
        "ticker": ticker,
        "exchange": _exchange(source.name, ticker),
        "event_class": event_type,
        "section": section,
        "category": category,
        "sub_category": sub_category,
        "announcement_subtype": item.raw_payload.get("announcement_subtype"),
        "release_type": item.raw_payload.get("release_type"),
        "numbers": numbers,
        "wire_facts": wire_facts,
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


def _extract_article_text(item: SourceItem) -> str | None:
    for key in ("text", "summary", "description"):
        value = item.raw_payload.get(key)
        if isinstance(value, str):
            cleaned = " ".join(value.split()).strip()
            if cleaned:
                return cleaned
    return None


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
    title = str(item.title or "").strip()
    derived = _derive_entity_name_from_title(title)
    for candidate in (item.raw_payload.get("company_name"), item.raw_payload.get("company")):
        if isinstance(candidate, str) and candidate.strip():
            cleaned = candidate.strip()
            if derived and _looks_like_generic_subject(cleaned):
                return derived
            return cleaned
    if derived:
        return derived
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


def _extract_wire_facts(
    title: str,
    article_text: str | None,
    event_type: str,
    company: str | None,
    display_symbol: str | None,
) -> dict | None:
    context = " ".join(part for part in [title, article_text or ""] if part).strip()
    if not context:
        return None
    subject_label = _wire_subject_label(display_symbol or company)
    derived_label = _wire_subject_label(_derive_entity_name_from_title(title))
    if (not subject_label or _looks_like_generic_subject(subject_label)) and derived_label:
        subject_label = derived_label

    sales_match = re.search(
        r"(?P<period>MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER|Q\d)\s+total\s+sales\s+(?:at\s+)?(?P<current>[\d,]+)\s+units?\s+vs\s+(?P<prior>[\d,]+)\s+units?(?:\s*\((?P<comp>YOY)\))?(?:;\s*est\.?\s*(?P<est>[\d,]+))?",
        context,
        re.IGNORECASE,
    )
    if sales_match:
        facts = {
            "kind": "sales_update",
            "subject_label": subject_label,
            "period": sales_match.group("period").upper(),
            "metric_label": "TOTAL SALES",
            "current_value": sales_match.group("current"),
            "prior_value": sales_match.group("prior"),
            "unit": "UNITS",
            "comparison_label": (sales_match.group("comp") or "YOY").upper(),
        }
        if sales_match.group("est"):
            facts["estimate_value"] = sales_match.group("est")
        domestic_match = re.search(r"domestic sales(?:\s+(?:at|of))?\s*([\d,]+)\s+units?", context, re.IGNORECASE)
        if domestic_match:
            facts["secondary_metric_label"] = "DOMESTIC SALES"
            facts["secondary_metric_value"] = domestic_match.group(1)
            facts["secondary_metric_unit"] = "UNITS"
        return facts

    sales_rise_match = re.search(
        r"(?P<period>MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)?\s*sales\s+(?:rise|up)\s+(?P<pct>[\d.]+%)\s+to\s+(?P<current>[\d,]+)\s+units?",
        context,
        re.IGNORECASE,
    )
    if sales_rise_match:
        return {
            "kind": "sales_update",
            "subject_label": subject_label,
            "period": (sales_rise_match.group("period") or "").upper() or None,
            "metric_label": "SALES",
            "change_pct": sales_rise_match.group("pct"),
            "current_value": sales_rise_match.group("current"),
            "unit": "UNITS",
        }

    outlook_match = re.search(
        r"(?P<pct>[\d.]+(?:-[\d.]+)?)%\s+(?:bank\s+)?loan growth\s+for\s+(?P<period>FY\d+)",
        context,
        re.IGNORECASE,
    )
    if outlook_match:
        return {
            "kind": "outlook_update",
            "subject_label": subject_label,
            "period": outlook_match.group("period").upper(),
            "metric_label": "LOAN GROWTH",
            "current_value": outlook_match.group("pct"),
            "unit": "%",
        }

    offtake_match = re.search(
        r"(?P<period>MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\s+\d{4}\s+offtake\s+up\s+(?P<pct>[\d.]+%)\s+to\s+(?P<current>[\d.,]+\s*(?:mt|mmt|ton|tons))",
        context,
        re.IGNORECASE,
    )
    if offtake_match:
        return {
            "kind": "offtake_update",
            "subject_label": subject_label,
            "period": offtake_match.group("period").upper(),
            "metric_label": "OFFTAKE",
            "change_pct": offtake_match.group("pct"),
            "current_value": offtake_match.group("current").upper(),
        }

    production_level_match = re.search(
        r"(?P<product>iron ore pellets?|iron ore|dri|steel|pellets?)\s+production\s+at\s+(?P<current>[\d.,]+\s*(?:mt|mmt|ton|tons|units?))(?:\s+vs\s+guidance(?:\s+of)?\s+(?P<guidance>[\d.,]+\s*(?:mt|mmt|ton|tons|units?)))?",
        context,
        re.IGNORECASE,
    )
    if production_level_match:
        facts = {
            "kind": "production_update",
            "subject_label": subject_label,
            "metric_label": f"{production_level_match.group('product').upper()} PRODUCTION",
            "current_value": production_level_match.group("current").upper(),
        }
        if production_level_match.group("guidance"):
            facts["guidance_value"] = production_level_match.group("guidance").upper()
        return facts

    generic_production_match = re.search(
        r"(?P<period>MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\s+\d{4}\s+production\s+at\s+(?P<current>[\d.,]+\s*(?:million\s+tonnes?|mt|mmt|ton|tons|units?))(?:\s+vs\s+guidance(?:\s+of)?\s+(?P<guidance>[\d.,]+\s*(?:million\s+tonnes?|mt|mmt|ton|tons|units?)))?",
        context,
        re.IGNORECASE,
    )
    if generic_production_match:
        facts = {
            "kind": "production_update",
            "subject_label": subject_label,
            "period": generic_production_match.group("period").upper(),
            "metric_label": "PRODUCTION",
            "current_value": generic_production_match.group("current").upper(),
        }
        if generic_production_match.group("guidance"):
            facts["guidance_value"] = generic_production_match.group("guidance").upper()
        return facts

    production_change_match = re.search(
        r"(?P<product>dri|iron ore pellets?|iron ore|steel|pellets?)\s+production\s+(?:surges|rises|up)\s+(?P<pct>[\d.]+%)\s+yoy",
        context,
        re.IGNORECASE,
    )
    if production_change_match:
        facts = {
            "kind": "production_update",
            "subject_label": subject_label,
            "metric_label": f"{production_change_match.group('product').upper()} PRODUCTION",
            "change_pct": production_change_match.group("pct"),
            "comparison_label": "YOY",
        }
        guidance_match = re.search(r"guidance(?:\s+of)?\s*([\d.,]+\s*(?:mt|mmt|ton|tons|units?))", context, re.IGNORECASE)
        if guidance_match:
            facts["guidance_value"] = guidance_match.group(1).upper()
        return facts

    tax_match = re.search(
        r"gst\s+demand(?:\s+order)?(?:\s+(?:worth|of))?\s+(?P<value>(?:₹|rs\.?\s*)?[\d.,]+\s*crore)",
        context,
        re.IGNORECASE,
    )
    if tax_match:
        return {
            "kind": "tax_demand",
            "subject_label": subject_label,
            "amount_value": _normalize_money_like(tax_match.group("value")),
            "metric_label": "GST DEMAND ORDER",
        }

    order_match = re.search(
        r"(?:wins?|secured?|receives?)\s+(?P<value>₹?[\d.,]+\s*cr)\s+(?P<body>.+?)\s+(?P<kind>order|contract|project)",
        context,
        re.IGNORECASE,
    )
    if order_match:
        return {
            "kind": "order_win",
            "subject_label": subject_label,
            "amount_value": _normalize_money_like(order_match.group("value")),
            "counterparty_or_body": order_match.group("body").upper().strip(" -,."),
            "metric_label": order_match.group("kind").upper(),
        }

    if event_type not in {"earnings", "order_win", "default_fraud"}:
        return None
    return None


def _wire_subject_label(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = str(value).strip()
    cleaned = re.sub(r"\s*&\s*INDUSTRIES\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"\b(LIMITED|LTD|LTD\.|INDUSTRIES|INDUSTRY|AND ENERGY|INFORMATION SECURITY L|INFORMATION SECURITY)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\bAND\s+ISPAT\b", "& ISPAT", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" -,.")
    return cleaned.upper() or None


def _derive_entity_name_from_title(title: str) -> str | None:
    if not title:
        return None
    patterns = (
        r"^(?P<name>.+?)\s+(?:reports|report|wins|receives|faces|projects|schedules|launches|maintains|withdraws|submits|files|publishes|sells|closes|acquires|approves)\b",
        r"^(?P<name>.+?):",
    )
    for pattern in patterns:
        match = re.match(pattern, title, re.IGNORECASE)
        if match:
            name = match.group("name").strip(" -,.")
            if name:
                return name
    return None


def _normalize_money_like(value: str) -> str:
    text = value.strip()
    text = text.replace("₹", "RS ")
    text = re.sub(r"(?i)\brs\b\.?", "RS", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.upper()


def _looks_like_generic_subject(value: str) -> bool:
    cleaned = re.sub(r"[^A-Za-z& ]+", "", value).upper().strip()
    return cleaned in _GENERIC_SUBJECT_VALUES


def _extract_filing_type(item: SourceItem, event_type: str, section: str | None) -> str | None:
    raw = item.raw_payload.get("filing_type")
    if raw:
        return raw
    if item.raw_payload.get("news_type") == "tradient_market_news":
        return "market_news"
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

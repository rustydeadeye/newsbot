from __future__ import annotations

from datetime import datetime
import re


def make_dedupe_key(
    event_type: str,
    ticker: str | None,
    entity_name: str | None,
    occurred_at: datetime | None,
    key_number: str | None = None,
) -> str:
    subject = normalize_subject(ticker or entity_name or "market")
    date_part = occurred_at.date().isoformat() if occurred_at else "undated"
    number_part = normalize_subject(key_number or "na")
    return f"{event_type}|{subject}|{date_part}|{number_part}"


def normalize_subject(value: str) -> str:
    lowered = value.lower().strip()
    lowered = lowered.replace("rs.", "rs").replace("re.", "re")
    lowered = re.sub(r"\b(xbrl|pdf|intimation|outcome of board meeting|disclosure)\b", " ", lowered)
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
    lowered = re.sub(r"-+", "-", lowered).strip("-")
    return lowered or "na"

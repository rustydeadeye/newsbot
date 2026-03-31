from __future__ import annotations
from datetime import date, datetime


SOURCE_PRIORITY = {
    "rbi_press_releases": 100,
    "sebi_releases": 90,
    "nse_corporate_filings": 95,
    "bse_announcements": 95,
    "pib_economy": 80,
    "mospi_releases": 85,
}

# Small credibility bonus added on top of the event base score.
# High-priority sources get +5; others get 0.
SOURCE_CREDIBILITY_BONUS = {
    "rbi_press_releases": 5,
    "sebi_releases": 5,
    "nse_corporate_filings": 3,
    "bse_announcements": 3,
    "pib_economy": 2,
    "mospi_releases": 3,
}

EVENT_BASE = {
    "rbi_policy": 95,
    "rbi_penalty": 72,
    "sebi_circular": 85,
    "sebi_enforcement": 85,
    "earnings": 70,
    "dividend": 65,
    "bonus_split": 70,
    "fundraise": 68,
    "order_win": 66,
    "management_change": 58,
    "acquisition": 78,
    "default_fraud": 88,
    "macro_release": 80,
    "general_update": 40,
}


def score_event(
    source_name: str,
    event_type: str,
    ticker: str | None,
    watchlist: set[str] | None = None,
    reference_date: date | None = None,
    latest_date: date | None = None,
) -> int:
    score = EVENT_BASE.get(event_type, 40)
    score += SOURCE_CREDIBILITY_BONUS.get(source_name, 0)
    if ticker and watchlist and ticker in watchlist:
        score += 5
    score += freshness_bonus(event_type, latest_date=latest_date, reference_date=reference_date)
    return min(score, 100)


def freshness_bonus(
    event_type: str,
    latest_date: date | None,
    reference_date: date | None = None,
) -> int:
    if latest_date is None:
        return 0
    reference = reference_date or datetime.utcnow().date()
    delta_days = (latest_date - reference).days
    abs_delta = abs(delta_days)

    if event_type in {"dividend", "bonus_split", "fundraise", "order_win", "management_change"}:
        if abs_delta <= 3:
            return 10
        if abs_delta <= 10:
            return 5
        return -10

    if event_type == "earnings":
        if abs_delta <= 7:
            return 10
        if abs_delta <= 30:
            return 3
        return -20

    if event_type in {"macro_release", "rbi_policy", "sebi_circular", "sebi_enforcement"}:
        if abs_delta <= 2:
            return 8
        if abs_delta <= 7:
            return 3
        return -8

    if abs_delta <= 7:
        return 3
    if abs_delta > 30:
        return -10
    return 0

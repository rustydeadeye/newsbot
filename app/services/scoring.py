from __future__ import annotations
from datetime import date, datetime


SOURCE_PRIORITY = {
    "rbi_press_releases": 100,
    "sebi_releases": 90,
    "nse_corporate_filings": 95,
    "bse_announcements": 95,
    "tradient_market_news": 78,
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
    "tradient_market_news": 1,
    "pib_economy": 2,
    "mospi_releases": 3,
}

EVENT_BASE = {
    "rbi_policy": 95,
    "rbi_penalty": 72,
    "sebi_circular": 85,
    "sebi_enforcement": 85,
    "earnings": 70,
    "fund_notice": 48,
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
    headline: str | None = None,
    body_text: str | None = None,
    category: str | None = None,
    sub_category: str | None = None,
    wire_facts: dict | None = None,
) -> int:
    score = EVENT_BASE.get(event_type, 40)
    score += SOURCE_CREDIBILITY_BONUS.get(source_name, 0)
    if ticker and watchlist and ticker in watchlist:
        score += 5
    score += freshness_bonus(event_type, latest_date=latest_date, reference_date=reference_date)
    score += headline_relevance_adjustment(headline, body_text=body_text, category=category, sub_category=sub_category)
    score += wire_facts_adjustment(wire_facts)
    return min(score, 100)


def headline_relevance_adjustment(
    headline: str | None,
    body_text: str | None = None,
    category: str | None = None,
    sub_category: str | None = None,
) -> int:
    if not headline and not body_text:
        return 0
    lowered = (headline or "").lower()
    body_lowered = (body_text or "").lower()
    combined = f"{lowered} {body_lowered}".strip()
    category = (category or "").lower()
    sub_category = (sub_category or "").lower()
    adjustment = 0

    strong_positive_terms = (
        "sales volume",
        "domestic sales",
        "turnover",
        "guidance",
        "record production",
        "production surges",
        "ebitda",
        "gst demand",
        "tax demand",
        "penalty",
        "commercial production",
        "letter of award",
        "contract value",
        "order worth",
        "receives order",
        "offtake",
        "million tonnes",
        "loan growth",
        "wins project",
        "project worth",
    )
    medium_positive_terms = (
        "sales",
        "volume",
        "production",
        "demand order",
        "capex",
        "expansion",
        "commissioning",
        "receives contract",
        "wins order",
        "sales rise",
        "sales up",
        "launch",
        "platform",
    )
    negative_terms = (
        "regulatory compliance",
        "non-applicability",
        "promoter reduces stake",
        "appoints",
        "appoints three key executives",
        "independent director",
        "warrant conversion",
        "disclosure",
        "stake by",
        "promoter pledged",
        "pledged shares",
        "price movement inquiry",
        "newspaper publication",
        "newspaper notice",
        "special window",
        "physical securities transfer",
        "postal ballot",
        "takeover regulations",
        "investor awareness drive",
        "saksham niveshak",
        "subsidiary stakes",
        "closes store",
        "closes ",
    )

    if any(term in combined for term in strong_positive_terms):
        adjustment += 10
    elif any(term in combined for term in medium_positive_terms):
        adjustment += 6

    if any(term in combined for term in negative_terms):
        adjustment -= 12

    if sub_category == "operational-updates":
        adjustment += 8
    elif sub_category == "indian-corporate-performance":
        adjustment += 6
    elif sub_category == "credit-rating-analyst-coverage":
        adjustment -= 8
    elif sub_category == "legal-compliance":
        adjustment -= 18

    if category == "indian-economy":
        adjustment += 5

    if "withdraws" in combined or "withdrawal of" in combined:
        adjustment -= 6

    if "record" in combined:
        adjustment += 3

    if "yoy" in combined or "%" in (headline or ""):
        adjustment += 4
    if "₹" in (headline or body_text or "") or "rs " in combined or "crore" in combined or "million" in combined:
        adjustment += 3

    return adjustment


def wire_facts_adjustment(wire_facts: dict | None) -> int:
    if not wire_facts:
        return 0
    adjustment = 0
    kind = str(wire_facts.get("kind") or "")

    if kind in {"sales_update", "production_update", "offtake_update", "tax_demand"}:
        adjustment += 6
    elif kind in {"order_win", "outlook_update"}:
        adjustment += 4

    if wire_facts.get("prior_value"):
        adjustment += 3
    if wire_facts.get("estimate_value"):
        adjustment += 2
    if wire_facts.get("guidance_value"):
        adjustment += 2
    if wire_facts.get("secondary_metric_value"):
        adjustment += 2
    if wire_facts.get("change_pct"):
        adjustment += 2

    return adjustment


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

    if event_type in {"dividend", "bonus_split", "fundraise", "order_win", "management_change", "fund_notice"}:
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

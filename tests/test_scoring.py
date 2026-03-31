from datetime import date
from types import SimpleNamespace

from app.pipeline import _customer_draft_skip_reason, _event_has_material_facts
from app.services.normalization.classifier import classify_event_type
from app.services.normalization.dedupe import make_dedupe_key
from app.services.scoring import freshness_bonus, score_event


def test_score_watchlist_bonus() -> None:
    assert score_event("nse_corporate_filings", "earnings", "TCS", {"TCS"}, reference_date=date(2026, 3, 30), latest_date=date(2026, 3, 30)) == 88


def test_classify_rbi_policy() -> None:
    assert classify_event_type("RBI announces monetary policy decision", "rbi_press_releases") == "rbi_policy"


def test_make_dedupe_key() -> None:
    key = make_dedupe_key("earnings", "INFY", None, None)
    assert key == "earnings|infy|undated|na"


def test_classify_corporate_action_dividend() -> None:
    assert classify_event_type("TVSMOTOR Interim Dividend - Rs 12 Per Share", "nse_corporate_filings", "corporate_actions") == "dividend"


def test_freshness_bonus_penalizes_stale_earnings() -> None:
    assert freshness_bonus("earnings", date(2024, 9, 30), reference_date=date(2026, 3, 30)) == -20


def test_classify_quarter_style_title_as_earnings() -> None:
    assert classify_event_type("KPIT Technologies Ltd Q4/FY update", "bse_announcements") == "earnings"


def test_customer_generation_filters_general_update() -> None:
    event = SimpleNamespace(
        event_type="general_update",
        importance_score=90,
        summary_facts={"headline": "Company announcement", "numbers": [{"type": "per_share", "value": "10"}]},
    )
    assert _customer_draft_skip_reason(event, watchlist_match=True) == "filtered_event_type"


def test_customer_generation_requires_material_facts() -> None:
    event = SimpleNamespace(
        event_type="earnings",
        importance_score=75,
        summary_facts={"headline": "Company announcement", "numbers": []},
    )
    assert _event_has_material_facts(event) is False
    assert _customer_draft_skip_reason(event, watchlist_match=True) == "no_material_facts"


def test_customer_generation_allows_watchlist_match_with_material_fact() -> None:
    event = SimpleNamespace(
        event_type="earnings",
        importance_score=55,
        summary_facts={"headline": "Company reports Q4 results", "period": "Q4/FY", "numbers": []},
    )
    assert _event_has_material_facts(event) is True
    assert _customer_draft_skip_reason(event, watchlist_match=True) is None

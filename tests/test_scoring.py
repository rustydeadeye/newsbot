from datetime import date

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

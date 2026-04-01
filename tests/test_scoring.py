from datetime import date
from types import SimpleNamespace

from app.pipeline import _customer_draft_skip_reason, _customer_family_key, _event_has_material_facts
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


def test_classify_idcw_notice_as_fund_notice() -> None:
    assert classify_event_type(
        "UTI Banking and PSU Fund Direct Plan Halfyearly Payout of IDCW (9002324)",
        "bse_announcements",
    ) == "fund_notice"


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


def test_customer_generation_skips_low_signal_fund_dividend_without_watchlist_match() -> None:
    event = SimpleNamespace(
        event_type="fund_notice",
        importance_score=78,
        entity_name="ICICI Prudential Fixed Maturity Plan Series 84 - 1288 Days Plan E",
        ticker=None,
        summary_facts={
            "headline": "ICICI Prudential Fixed Maturity Plan Series 84 - 1288 Days Plan E - Quarterly Dividend Payout Option",
            "numbers": [{"type": "per_share", "currency": "Rs", "value": "1.2"}],
            "event_date": "2026-03-30",
        },
    )
    assert _customer_draft_skip_reason(event, watchlist_match=False) == "low_signal_fund_notice"
    assert _customer_draft_skip_reason(event, watchlist_match=True) is None


def test_customer_family_key_collapses_same_fund_family() -> None:
    event = SimpleNamespace(
        event_type="dividend",
        entity_name="ICICI Prudential Multiple Yield Fund - Series 14 - Plan A 1228 Days Direct Plan",
        ticker=None,
        summary_facts={"headline": "ICICI Prudential Multiple Yield Fund - Series 14 - Plan A 1228 Days Direct Plan Dividend"},
    )
    assert _customer_family_key(event) == "icici prudential multiple"

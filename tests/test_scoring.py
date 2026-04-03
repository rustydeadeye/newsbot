from datetime import date
from types import SimpleNamespace

from app.pipeline import _customer_draft_skip_reason, _customer_family_key, _event_has_material_facts
from app.services.normalization.classifier import classify_event_type
from app.services.normalization.dedupe import make_dedupe_key
from app.services.scoring import freshness_bonus, headline_relevance_adjustment, score_event, wire_facts_adjustment


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


def test_classify_tradient_sales_update_as_earnings() -> None:
    assert classify_event_type(
        "APL Apollo Tubes: Q4FY26 sales volume of 924,881 ton (+9% YoY)",
        "tradient_market_news",
    ) == "earnings"


def test_classify_tradient_tax_demand_as_default_fraud() -> None:
    assert classify_event_type(
        "JK Tyre Receives GST Demand Order Worth Rs 1.39 Crore",
        "tradient_market_news",
    ) == "default_fraud"


def test_classify_tradient_compliance_update_as_general_update() -> None:
    assert classify_event_type(
        "We Win Limited Files Q4FY26 Regulatory Compliance",
        "tradient_market_news",
    ) == "general_update"


def test_classify_tradient_shareholding_disclosure_as_general_update_from_body() -> None:
    assert classify_event_type(
        "Canara Bank Update",
        "tradient_market_news",
        body_text="Canara Bank files SEBI shareholding disclosure for FY26.",
    ) == "general_update"


def test_classify_tradient_legal_compliance_subcategory_as_general_update() -> None:
    assert classify_event_type(
        "Mangalam Industrial Finance Promoter Pledges Shares",
        "tradient_market_news",
        body_text="Promoter pledged shares as collateral under SEBI regulations.",
        sub_category="legal-compliance",
    ) == "general_update"


def test_headline_relevance_adjustment_boosts_market_moving_terms() -> None:
    assert headline_relevance_adjustment("BEL Reports ₹26,750 Cr Turnover in FY26, Up 16.2%") > 0


def test_headline_relevance_adjustment_penalizes_low_signal_compliance_terms() -> None:
    assert headline_relevance_adjustment("Ambika Cotton Mills Confirms Non-Applicability of SEBI") < 0


def test_headline_relevance_adjustment_penalizes_tradient_legal_compliance() -> None:
    assert headline_relevance_adjustment(
        "Canara Bank Files SEBI Disclosure on Subsidiary Stakes",
        body_text="Disclosed shareholding in subsidiaries under takeover regulations.",
        sub_category="legal-compliance",
    ) < 0


def test_headline_relevance_adjustment_boosts_operational_updates() -> None:
    assert headline_relevance_adjustment(
        "Coal India Reports March 2026 Production at 84.5 Million Tonnes",
        body_text="Production stood at 84.5 million tonnes, down 1.5% year on year.",
        sub_category="operational-updates",
    ) > 0


def test_classify_tradient_sales_rise_as_earnings() -> None:
    assert classify_event_type(
        "Atul Auto March Sales Rise 14% to 4,212 Units",
        "tradient_market_news",
        body_text="March sales rose 14% to 4,212 units.",
    ) == "earnings"


def test_classify_tradient_project_win_as_order_win() -> None:
    assert classify_event_type(
        "Solarworld Energy Wins ₹267.53 Cr NTPC Solar Project",
        "tradient_market_news",
        body_text="Wins Rs 267.53 cr NTPC solar project.",
    ) == "order_win"


def test_classify_tradient_oil_futures_as_macro_release() -> None:
    assert classify_event_type(
        "US Oil Futures Surge Above $110 Per Barrel Mark",
        "tradient_market_news",
        body_text="US oil futures continue their upward trajectory, breaking through the significant $110 per barrel threshold amid ongoing market dynamics.",
    ) == "macro_release"


def test_wire_facts_adjustment_rewards_structured_sales_update() -> None:
    assert wire_facts_adjustment(
        {
            "kind": "sales_update",
            "current_value": "225,251",
            "prior_value": "192,984",
            "estimate_value": "209,600",
            "secondary_metric_value": "198,000",
        }
    ) > 0


def test_wire_facts_adjustment_penalizes_tiny_orders() -> None:
    assert wire_facts_adjustment(
        {
            "kind": "order_win",
            "amount_value": "RS 1.23 CRORE",
        }
    ) < 0


def test_score_event_uses_wire_facts() -> None:
    baseline = score_event("tradient_market_news", "earnings", "MARUTI", headline="Maruti sales")
    enriched = score_event(
        "tradient_market_news",
        "earnings",
        "MARUTI",
        headline="Maruti sales",
        wire_facts={
            "kind": "sales_update",
            "current_value": "225,251",
            "prior_value": "192,984",
            "estimate_value": "209,600",
            "secondary_metric_value": "198,000",
        },
    )
    assert enriched > baseline


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

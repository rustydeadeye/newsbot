from types import SimpleNamespace

from app.services.drafting.service import DraftingService


def test_fallback_text_uses_clean_source_name() -> None:
    service = DraftingService()
    text = service._fallback_text({"headline": "RBI keeps repo rate unchanged", "source_name": "rbi_press_releases"})
    assert text == "RBI keeps repo rate unchanged. Source: RBI."


def test_normalize_text_removes_filler_and_handles() -> None:
    service = DraftingService()
    text = service._normalize_text(
        "RBI keeps repo rate unchanged at 6.50%. Stay updated for more updates. @rbi_press_releases #India #RBI",
        {"source_name": "rbi_press_releases", "attribution_required": True},
    )
    assert "Stay updated" not in text
    assert "@rbi_press_releases" not in text
    assert "#" not in text
    assert text.endswith("Source: RBI.")


def test_normalize_text_prefers_headline_style() -> None:
    service = DraftingService()
    text = service._normalize_text(
        "RBI will conduct the second 3-day Variable Rate Repo auction on March 30, 2026.",
        {"source_name": "rbi_press_releases", "attribution_required": True},
    )
    assert text.startswith("RBI to conduct")


def test_make_draft_post_uses_fallback_without_openai() -> None:
    service = DraftingService()
    service.client = None
    event = SimpleNamespace(
        id=1,
        summary_facts={"headline": "IRB's bonus issue has an ex-date of 30 March 2026", "source_name": "nse_corporate_filings", "attribution_required": True},
    )
    draft = service.make_draft_post(event)
    assert "according to an NSE filing" in draft.draft_text or "Source: an NSE filing." in draft.draft_text


def test_macro_template_prefers_rbi_releases_language() -> None:
    service = DraftingService()
    text = service._fallback_text(
        {
            "headline": "Result of the Second 3-day Variable Rate Repo (VRR) auction held on March 30, 2026",
            "source_name": "rbi_press_releases",
            "event_class": "macro_release",
            "attribution_required": True,
        }
    )
    assert text == "RBI releases the second 3-day Variable Rate Repo (VRR) auction held on March 30, 2026. Source: RBI."


def test_bonus_template_uses_ratio_and_date() -> None:
    service = DraftingService()
    text = service._fallback_text(
        {
            "source_name": "nse_corporate_filings",
            "event_class": "bonus_split",
            "company": "IRB",
            "numbers": [{"type": "ratio", "value": "1:1"}],
            "event_date": "March 30, 2026",
            "attribution_required": True,
        }
    )
    assert text == "IRB: bonus issue ratio 1:1; ex-date March 30, 2026. Source: an NSE filing."


def test_fund_notice_template_stays_factual() -> None:
    service = DraftingService()
    text = service._fallback_text(
        {
            "source_name": "bse_announcements",
            "event_class": "fund_notice",
            "headline": "UTI Banking and PSU Fund Direct Plan Halfyearly Reinvestment of IDCW (9002325)",
            "attribution_required": True,
        }
    )
    assert "benefit from compounded returns" not in text
    assert text == "UTI Banking and PSU Fund Direct Plan Halfyearly IDCW reinvestment (9002325). Source: a BSE filing."


def test_earnings_template_preserves_wire_sales_headline() -> None:
    service = DraftingService()
    service.client = None
    draft = service.make_draft_post(
        SimpleNamespace(
            id=1,
            summary_facts={
                "source_name": "tradient_market_news",
                "event_class": "earnings",
                "headline": "Hyundai Motor India Achieves Record Q4 Domestic Sales",
                "company": "Hyundai Motor India",
                "period": "Q4/FY",
                "attribution_required": True,
            },
        )
    )
    assert draft.draft_text == "HYUNDAI MOTOR INDIA: RECORD Q4 DOMESTIC SALES"


def test_wire_template_formats_turnover_update() -> None:
    service = DraftingService()
    service.client = None
    draft = service.make_draft_post(
        SimpleNamespace(
            id=1,
            summary_facts={
                "source_name": "tradient_market_news",
                "event_class": "earnings",
                "headline": "BEL Reports ₹26,750 Cr Turnover in FY26, Up 16.2%",
                "company": "BEL",
                "attribution_required": True,
            },
        )
    )
    assert draft.draft_text == "BEL: FY26 TURNOVER AT RS 26,750 CR, UP 16.2%"


def test_wire_template_prefers_structured_wire_facts() -> None:
    service = DraftingService()
    service.client = None
    draft = service.make_draft_post(
        SimpleNamespace(
            id=1,
            summary_facts={
                "source_name": "tradient_market_news",
                "event_class": "earnings",
                "headline": "Noisy headline that should not drive formatting",
                "wire_facts": {
                    "kind": "sales_update",
                    "subject_label": "MARUTI SUZUKI",
                    "period": "MARCH",
                    "metric_label": "TOTAL SALES",
                    "current_value": "225,251",
                    "prior_value": "192,984",
                    "unit": "UNITS",
                    "comparison_label": "YOY",
                    "estimate_value": "209,600",
                },
                "attribution_required": True,
            },
        )
    )
    assert draft.draft_text == "MARUTI SUZUKI: MARCH TOTAL SALES 225,251 UNITS VS 192,984 UNITS (YOY); EST 209,600"


def test_wire_template_formats_outlook_update_with_specific_subject() -> None:
    service = DraftingService()
    service.client = None
    draft = service.make_draft_post(
        SimpleNamespace(
            id=1,
            summary_facts={
                "source_name": "tradient_market_news",
                "event_class": "earnings",
                "headline": "ICRA Projects 11-12% Bank Loan Growth for FY27",
                "wire_facts": {
                    "kind": "outlook_update",
                    "subject_label": "ICRA",
                    "period": "FY27",
                    "metric_label": "LOAN GROWTH",
                    "current_value": "11-12",
                    "unit": "%",
                },
                "attribution_required": True,
            },
        )
    )
    assert draft.draft_text == "ICRA: FY27 LOAN GROWTH SEEN AT 11-12%"


def test_wire_template_formats_generic_production_update() -> None:
    service = DraftingService()
    service.client = None
    draft = service.make_draft_post(
        SimpleNamespace(
            id=1,
            summary_facts={
                "source_name": "tradient_market_news",
                "event_class": "earnings",
                "headline": "Coal India Reports March 2026 Production at 84.5 Million Tonnes",
                "wire_facts": {
                    "kind": "production_update",
                    "subject_label": "COAL INDIA",
                    "period": "MARCH",
                    "metric_label": "PRODUCTION",
                    "current_value": "84.5 MILLION TONNES",
                },
                "attribution_required": True,
            },
        )
    )
    assert draft.draft_text == "COAL INDIA: MARCH PRODUCTION AT 84.5 MILLION TONNES"


def test_wire_template_formats_gst_demand_update() -> None:
    service = DraftingService()
    service.client = None
    draft = service.make_draft_post(
        SimpleNamespace(
            id=1,
            summary_facts={
                "source_name": "tradient_market_news",
                "event_class": "default_fraud",
                "headline": "JK Tyre Receives GST Demand Order Worth ₹1.39 Crore",
                "company": "JK Tyre & Industries",
                "attribution_required": True,
            },
        )
    )
    assert draft.draft_text == "JK TYRE: GST DEMAND ORDER OF RS 1.39 CRORE"


def test_wire_template_formats_production_update() -> None:
    service = DraftingService()
    service.client = None
    draft = service.make_draft_post(
        SimpleNamespace(
            id=1,
            summary_facts={
                "source_name": "tradient_market_news",
                "event_class": "earnings",
                "headline": "Lloyds Metals DRI Production Surges 57% YoY",
                "company": "Lloyds Metals",
                "attribution_required": True,
            },
        )
    )
    assert draft.draft_text == "LLOYDS METALS: DRI PRODUCTION UP 57% YOY"


def test_wire_template_formats_rights_issue_opening() -> None:
    service = DraftingService()
    service.client = None
    draft = service.make_draft_post(
        SimpleNamespace(
            id=1,
            summary_facts={
                "source_name": "tradient_market_news",
                "event_class": "fundraise",
                "headline": "Regal Entertainment Rights Issue Opens April 7, 2026",
                "company": "Regal Entertainment",
                "attribution_required": True,
            },
        )
    )
    assert draft.draft_text == "REGAL ENTERTAINMENT: RIGHTS ISSUE OPENS APRIL 7, 2026"


def test_wire_template_uses_article_text_for_sales_comparison() -> None:
    service = DraftingService()
    service.client = None
    draft = service.make_draft_post(
        SimpleNamespace(
            id=1,
            summary_facts={
                "source_name": "tradient_market_news",
                "event_class": "earnings",
                "headline": "Maruti Suzuki March sales update",
                "article_text": "March total sales 225,251 units vs 192,984 units (YoY); est 209,600. Domestic sales 198,000 units.",
                "company": "Maruti Suzuki",
                "attribution_required": True,
            },
        )
    )
    assert draft.draft_text == "MARUTI SUZUKI: MARCH TOTAL SALES 225,251 UNITS VS 192,984 UNITS (YOY); EST 209,600; DOMESTIC SALES 198,000 UNITS"


def test_wire_template_uses_article_text_for_gst_demand() -> None:
    service = DraftingService()
    service.client = None
    draft = service.make_draft_post(
        SimpleNamespace(
            id=1,
            summary_facts={
                "source_name": "tradient_market_news",
                "event_class": "default_fraud",
                "headline": "Bajaj Electricals tax matter",
                "article_text": "GST demand of Rs 5.75 crore raised against the company.",
                "company": "Bajaj Electricals",
                "attribution_required": True,
            },
        )
    )
    assert draft.draft_text == "BAJAJ ELECTRICALS: GST DEMAND ORDER OF RS 5.75 CRORE"


def test_wire_template_uses_guidance_extra_clause() -> None:
    service = DraftingService()
    service.client = None
    draft = service.make_draft_post(
        SimpleNamespace(
            id=1,
            summary_facts={
                "source_name": "tradient_market_news",
                "event_class": "earnings",
                "headline": "Godawari Power iron ore pellets production update",
                "article_text": "Iron ore pellets production at 2.86MT vs guidance of 3MT.",
                "company": "Godawari Power and Ispat",
                "attribution_required": True,
            },
        )
    )
    assert draft.draft_text == "GODAWARI POWER & ISPAT: IRON ORE PELLETS PRODUCTION AT 2.86MT VS GUIDANCE 3MT"


def test_wire_template_formats_sales_rise_update() -> None:
    service = DraftingService()
    service.client = None
    draft = service.make_draft_post(
        SimpleNamespace(
            id=1,
            summary_facts={
                "source_name": "tradient_market_news",
                "event_class": "earnings",
                "headline": "Atul Auto sales update",
                "article_text": "March sales rise 14% to 4,212 units.",
                "company": "Atul Auto",
                "attribution_required": True,
            },
        )
    )
    assert draft.draft_text == "ATUL AUTO: MARCH SALES UP 14% TO 4,212 UNITS"


def test_wire_template_formats_project_win_update() -> None:
    service = DraftingService()
    service.client = None
    draft = service.make_draft_post(
        SimpleNamespace(
            id=1,
            summary_facts={
                "source_name": "tradient_market_news",
                "event_class": "order_win",
                "headline": "Solarworld project win",
                "article_text": "Wins ₹267.53 Cr NTPC solar project.",
                "company": "Solarworld Energy",
                "attribution_required": True,
            },
        )
    )
    assert draft.draft_text == "SOLARWORLD ENERGY: WINS NTPC SOLAR PROJECT WORTH RS 267.53 CR"


def test_wire_template_formats_outlook_update() -> None:
    service = DraftingService()
    service.client = None
    draft = service.make_draft_post(
        SimpleNamespace(
            id=1,
            summary_facts={
                "source_name": "tradient_market_news",
                "event_class": "earnings",
                "headline": "ICRA banking outlook",
                "article_text": "ICRA projects 11-12% bank loan growth for FY27.",
                "company": "ICRA",
                "attribution_required": True,
            },
        )
    )
    assert draft.draft_text == "ICRA: FY27 LOAN GROWTH SEEN AT 11-12%"

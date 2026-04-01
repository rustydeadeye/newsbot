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

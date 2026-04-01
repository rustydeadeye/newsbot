from __future__ import annotations


def classify_event_type(
    title: str,
    source_name: str,
    section: str | None = None,
    sebi_doc_type: str | None = None,
    body_text: str | None = None,
    category: str | None = None,
    sub_category: str | None = None,
) -> str:
    lowered = title.lower()
    body_lowered = (body_text or "").lower()
    combined = f"{lowered} {body_lowered}".strip()
    section = (section or "").lower()
    category = (category or "").lower()
    sub_category = (sub_category or "").lower()
    is_fund_notice = any(term in combined for term in (
        " idcw",
        "income distribution cum capital withdrawal",
        "payout of idcw",
        "reinvestment of idcw",
        "dividend payout option",
        "quarterly payout",
        "halfyearly payout",
        "half-yearly payout",
        "monthly payout",
        "reinvestment option",
    ))

    if "monetary policy" in combined or "repo rate" in combined or "mpc" in combined:
        return "rbi_policy"
    if source_name.startswith("rbi") and ("defers" in combined or "postpones" in combined or "extends deadline" in combined):
        return "rbi_policy"
    if source_name.startswith("rbi") and ("imposes" in combined and "penalty" in combined):
        return "rbi_penalty"
    if source_name.startswith("rbi") and ("monetary penalty" in combined or "penalty on" in combined):
        return "rbi_penalty"
    if source_name.startswith("rbi") and ("auction" in combined or "g-sec" in combined or "treasury bill" in combined):
        return "macro_release"
    if source_name.startswith("rbi") and any(kw in combined for kw in (
        "lending", "deposit rates", "bank credit", "sectoral deployment",
        "international trade in services", "international investment position", "iip",
        "invisibles", "finances of", "foreign exchange", "forex reserves",
        "money supply", "currency", "inflation", "cpi", "wpi", "gdp",
        "balance of payments", "external debt",
    )):
        return "macro_release"

    # SEBI: use URL-based document type when available, fall back to title keywords
    if source_name.startswith("sebi"):
        if sebi_doc_type == "sebi_circular" or "circular" in combined:
            return "sebi_circular"
        if sebi_doc_type in {"sebi_enforcement", "sebi_regulation"} or any(kw in combined for kw in (
            "order", "penalty", "adjudication", "settlement", "recovery certificate",
            "directions", "debarment", "suspension", "cancellation of", "front running",
        )):
            return "sebi_enforcement"
        if sebi_doc_type == "sebi_press_release":
            return "sebi_circular"  # treat SEBI press releases as policy circulars
        return "sebi_circular"  # default for SEBI items not otherwise classifiable
    if source_name == "tradient_market_news":
        if sub_category == "legal-compliance" and not any(
            term in combined for term in ("gst demand", "tax demand", "penalty", "order worth", "contract", "letter of award")
        ):
            return "general_update"
        if any(term in combined for term in (
            "price movement inquiry",
            "newspaper publication",
            "newspaper notice",
            "special window",
            "physical securities transfer",
            "takeover regulations",
            "postal ballot newspaper publication",
            "investor awareness drive",
            "saksham niveshak",
            "promoter pledged",
            "promoter pledges",
            "pledged shares",
            "shareholding in three subsidiaries",
            "margin limits",
            "closes ",
            "investor conference",
            "investor meet",
        )):
            return "general_update"
    if is_fund_notice:
        return "fund_notice"
    if any(term in combined for term in (
        "regulatory compliance",
        "files q4fy",
        "files q4 fy",
        "confirms non-applicability",
        "non-applicability of sebi",
        "shareholding disclosure",
        "corporate governance report",
        "scheme of arrangement effective",
        "re-appoints internal auditor",
        "director retires on superannuation",
        "promoter increases stake",
        "promoter reduces stake",
        "pledge",
        "postal ballot",
        "investor conference",
        "investor meet",
    )):
        return "general_update"
    if any(term in combined for term in (
        "sales volume",
        "sales rise",
        "sales up",
        "loan growth",
        "passenger vehicles",
        "production",
        "offtake",
        "dispatches",
        "dispatch",
        "ton",
        "units vs",
        "yoy",
        "turnover",
        "ebitda",
        "guidance",
    )):
        return "earnings"
    if any(term in combined for term in ("quarter ended", "year ended", "q1", "q2", "q3", "q4", "fy", "financial results", "results for")):
        return "earnings"
    if section == "financial_results" or "results" in combined or "financial results" in combined:
        return "earnings"
    if any(term in combined for term in ("gst demand", "tax demand", "penalizes", "penalised", "penalty", "compliance breach")):
        return "default_fraud"
    if section == "corporate_actions" and "dividend" in combined:
        return "dividend"
    if section == "corporate_actions" and ("bonus" in combined or "split" in combined):
        return "bonus_split"
    if section == "board_meetings" and "financial results" in combined:
        return "earnings"
    if section == "board_meetings":
        return "management_change"
    if "dividend" in combined:
        return "dividend"
    if "bonus" in combined or "split" in combined:
        return "bonus_split"
    if "fund raise" in combined or "fundraise" in combined or "qip" in combined or "preferential" in combined or "rights issue" in combined:
        return "fundraise"
    if "order" in combined or "contract" in combined or "work order" in combined or "letter of award" in combined or ("wins" in combined and "project" in combined) or "project worth" in combined:
        return "order_win"
    if any(term in combined for term in ("capex", "commencement of commercial production", "commercial production", "expansion")):
        return "order_win"
    if "director" in combined or "key managerial personnel" in combined or "ceo" in combined or "cfo" in combined:
        return "management_change"
    if "acquisition" in combined or "merger" in combined or "scheme of arrangement" in combined:
        return "acquisition"
    if "default" in combined or "fraud" in combined:
        return "default_fraud"
    if source_name.startswith("mospi") or source_name.startswith("pib"):
        return "macro_release"
    return "general_update"

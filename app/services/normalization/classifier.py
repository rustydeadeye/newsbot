from __future__ import annotations


def classify_event_type(
    title: str,
    source_name: str,
    section: str | None = None,
    sebi_doc_type: str | None = None,
) -> str:
    lowered = title.lower()
    section = (section or "").lower()

    if "monetary policy" in lowered or "repo rate" in lowered or "mpc" in lowered:
        return "rbi_policy"
    if source_name.startswith("rbi") and ("defers" in lowered or "postpones" in lowered or "extends deadline" in lowered):
        return "rbi_policy"
    if source_name.startswith("rbi") and ("imposes" in lowered and "penalty" in lowered):
        return "rbi_penalty"
    if source_name.startswith("rbi") and ("monetary penalty" in lowered or "penalty on" in lowered):
        return "rbi_penalty"
    if source_name.startswith("rbi") and ("auction" in lowered or "g-sec" in lowered or "treasury bill" in lowered):
        return "macro_release"
    if source_name.startswith("rbi") and any(kw in lowered for kw in (
        "lending", "deposit rates", "bank credit", "sectoral deployment",
        "international trade in services", "international investment position", "iip",
        "invisibles", "finances of", "foreign exchange", "forex reserves",
        "money supply", "currency", "inflation", "cpi", "wpi", "gdp",
        "balance of payments", "external debt",
    )):
        return "macro_release"

    # SEBI: use URL-based document type when available, fall back to title keywords
    if source_name.startswith("sebi"):
        if sebi_doc_type == "sebi_circular" or "circular" in lowered:
            return "sebi_circular"
        if sebi_doc_type in {"sebi_enforcement", "sebi_regulation"} or any(kw in lowered for kw in (
            "order", "penalty", "adjudication", "settlement", "recovery certificate",
            "directions", "debarment", "suspension", "cancellation of", "front running",
        )):
            return "sebi_enforcement"
        if sebi_doc_type == "sebi_press_release":
            return "sebi_circular"  # treat SEBI press releases as policy circulars
        return "sebi_circular"  # default for SEBI items not otherwise classifiable
    if section == "financial_results" or "results" in lowered or "financial results" in lowered:
        return "earnings"
    if section == "corporate_actions" and "dividend" in lowered:
        return "dividend"
    if section == "corporate_actions" and ("bonus" in lowered or "split" in lowered):
        return "bonus_split"
    if section == "board_meetings" and "financial results" in lowered:
        return "earnings"
    if section == "board_meetings":
        return "management_change"
    if "dividend" in lowered:
        return "dividend"
    if "bonus" in lowered or "split" in lowered:
        return "bonus_split"
    if "fund raise" in lowered or "fundraise" in lowered or "qip" in lowered or "preferential" in lowered or "rights issue" in lowered:
        return "fundraise"
    if "order" in lowered or "contract" in lowered or "work order" in lowered:
        return "order_win"
    if "director" in lowered or "key managerial personnel" in lowered or "ceo" in lowered or "cfo" in lowered:
        return "management_change"
    if "acquisition" in lowered or "merger" in lowered or "scheme of arrangement" in lowered:
        return "acquisition"
    if "default" in lowered or "fraud" in lowered:
        return "default_fraud"
    if source_name.startswith("mospi") or source_name.startswith("pib"):
        return "macro_release"
    return "general_update"

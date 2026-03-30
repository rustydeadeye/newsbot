from __future__ import annotations


def classify_event_type(title: str, source_name: str, section: str | None = None) -> str:
    lowered = title.lower()
    section = (section or "").lower()

    if "monetary policy" in lowered or "repo rate" in lowered or "mpc" in lowered:
        return "rbi_policy"
    if source_name.startswith("rbi") and ("auction" in lowered or "g-sec" in lowered or "treasury bill" in lowered):
        return "macro_release"
    if "circular" in lowered and source_name.startswith("sebi"):
        return "sebi_circular"
    if source_name.startswith("sebi") and ("order" in lowered or "penalty" in lowered or "adjudication" in lowered):
        return "sebi_enforcement"
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

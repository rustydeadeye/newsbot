from __future__ import annotations
import json
import logging
import re
import time

try:
    from openai import OpenAI, RateLimitError, APIStatusError
except ModuleNotFoundError:  # pragma: no cover - optional dependency in test env
    OpenAI = None
    RateLimitError = Exception
    APIStatusError = Exception

logger = logging.getLogger(__name__)

from app.core.config import get_settings
from app.models.event import DraftPost, Event
from app.prompts import SAFETY_BLOCKLIST, STYLE_BLOCKLIST
from app.services.drafting.prompts import POST_GENERATION_PROMPT, PROMPT_VERSION


class DraftingService:
    def __init__(self, api_key: str | None = None) -> None:
        settings = get_settings()
        self.model = settings.openai_model
        resolved_key = api_key or settings.openai_api_key
        self.client = OpenAI(api_key=resolved_key) if resolved_key and OpenAI else None

    def build_draft(self, event: Event) -> tuple[str, dict, float]:
        facts = event.summary_facts
        fallback = self._fallback_text(facts)
        if not self.client:
            return fallback, self._safety_flags(fallback), 0.0

        messages = [
            {
                "role": "system",
                "content": (
                    "You write factual finance news posts for social media. "
                    "You must follow the user's style rules exactly and never add unsupported claims. "
                    "Always respond with valid JSON."
                ),
            },
            {
                "role": "user",
                "content": f"{POST_GENERATION_PROMPT}\n\nFacts:\n{facts}",
            },
        ]
        raw = self._call_openai_with_retry(messages)
        parsed = self._parse_json_response(raw)
        if parsed:
            text = self._normalize_text(parsed.get("post_text", "").strip() or fallback, facts)
            ai_confidence = float(parsed.get("confidence", 0.0))
            ai_needs_review = bool(parsed.get("needs_review", False))
            ai_review_reason = parsed.get("review_reason")
            flags = self._safety_flags(text)
            if ai_needs_review:
                flags["needs_review"] = True
            if ai_review_reason:
                flags["review_reason"] = ai_review_reason
            return text, flags, ai_confidence
        text = self._normalize_text((raw or fallback).strip(), facts)
        return text, self._safety_flags(text), 0.0

    def _call_openai_with_retry(self, messages: list[dict]) -> str | None:
        backoffs = [5.0, 10.0]
        for attempt, backoff in enumerate([0.0] + backoffs):
            if backoff:
                time.sleep(backoff)
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    response_format={"type": "json_object"},
                    messages=messages,
                )
                return response.choices[0].message.content if response.choices else None
            except RateLimitError:
                if attempt == len(backoffs):
                    logger.warning("OpenAI rate limit hit after %d attempts; using fallback", attempt + 1)
                    return None
                logger.warning("OpenAI rate limit (attempt %d); retrying in %.0fs", attempt + 1, backoffs[attempt] if attempt < len(backoffs) else 0)
            except APIStatusError as exc:
                if exc.status_code < 500 or attempt == len(backoffs):
                    logger.warning("OpenAI API error %s; using fallback", exc.status_code)
                    return None
                logger.warning("OpenAI server error %s (attempt %d); retrying", exc.status_code, attempt + 1)
            except Exception:
                logger.warning("OpenAI unexpected error; using fallback", exc_info=True)
                return None
        return None

    def _parse_json_response(self, raw: str | None) -> dict | None:
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return None

    def make_draft_post(self, event: Event) -> DraftPost:
        draft_text, safety_flags, ai_confidence = self.build_draft(event)
        if ai_confidence > 0:
            safety_flags["ai_confidence"] = round(ai_confidence, 3)
        return DraftPost(
            event_id=event.id,
            platform="x",
            status="approved" if not safety_flags["needs_review"] else "draft",
            draft_text=draft_text,
            safety_flags=safety_flags,
            needs_review=safety_flags["needs_review"],
            prompt_version=PROMPT_VERSION,
        )

    def _fallback_text(self, facts: dict) -> str:
        template_text = self._template_text(facts)
        if template_text:
            return template_text
        headline = str(facts.get("headline", "Market update")).strip().rstrip(".")
        source_name = self._display_source_name(facts)
        if headline:
            return f"{headline}. Source: {source_name}."
        return f"Market update. Source: {source_name}."

    def _safety_flags(self, text: str) -> dict:
        lowered = text.lower()
        matches = [phrase for phrase in SAFETY_BLOCKLIST if phrase in lowered]
        style_matches = [phrase for phrase in STYLE_BLOCKLIST if phrase in lowered]
        all_matches = matches + style_matches
        return {"blocked_phrases": matches, "needs_review": bool(matches)}

    def _normalize_text(self, text: str, facts: dict) -> str:
        cleaned = " ".join(text.split())
        cleaned = re.sub(r"\s+([.,;:!?])", r"\1", cleaned)
        cleaned = re.sub(r"(?i)\b(stay updated|watch this space|keep an eye|for more updates)\b[.! ]*", "", cleaned)
        cleaned = re.sub(r"@\w+", "", cleaned)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
        cleaned = re.sub(r"\s*#\w+\b", "", cleaned).strip()
        cleaned = re.sub(r"(?i)\bRBI will conduct\b", "RBI to conduct", cleaned)
        cleaned = re.sub(r"(?i)\bSEBI will issue\b", "SEBI to issue", cleaned)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
        cleaned = cleaned.rstrip("-–| ").strip()
        if len(cleaned) > 240:
            truncated = cleaned[:237]
            last_space = truncated.rfind(" ")
            cleaned = (truncated[:last_space] if last_space > 180 else truncated).rstrip() + "..."
        if "source:" not in cleaned.lower() and facts.get("attribution_required"):
            source_name = self._display_source_name(facts)
            separator = "" if cleaned.endswith(".") else "."
            cleaned = f"{cleaned}{separator} Source: {source_name}."
        return cleaned

    def _display_source_name(self, facts: dict) -> str:
        source_name = str(facts.get("source_name", "source"))
        mapping = {
            "rbi_press_releases": "RBI",
            "sebi_releases": "SEBI",
            "nse_corporate_filings": "an NSE filing",
            "bse_announcements": "a BSE filing",
            "pib_economy": "PIB",
            "mospi_releases": "MOSPI",
        }
        return mapping.get(source_name, source_name.replace("_", " ").upper())

    def _template_text(self, facts: dict) -> str | None:
        event_type = str(facts.get("event_class") or "")
        if event_type in {"rbi_policy", "macro_release"}:
            return self._macro_template(facts)
        if event_type == "rbi_penalty":
            return self._penalty_template(facts)
        if event_type in {"sebi_circular", "sebi_enforcement"}:
            return self._regulatory_template(facts)
        if event_type == "earnings":
            return self._earnings_template(facts)
        if event_type == "fund_notice":
            return self._fund_notice_template(facts)
        if event_type in {"dividend", "bonus_split"}:
            return self._corporate_action_template(facts)
        if event_type in {"fundraise", "order_win", "management_change", "acquisition", "default_fraud"}:
            return self._company_update_template(facts)
        return None

    def _macro_template(self, facts: dict) -> str | None:
        headline = self._clean_headline(facts)
        source_name = self._display_source_name(facts)
        if not headline:
            return None

        lowered = headline.lower()
        if source_name == "RBI":
            if "auction" in lowered and "result" in lowered:
                body = self._headline_rewrite(headline, [(r"(?i)^result of ", ""), (r"(?i)^RBI ", "RBI ")])
                body = re.sub(r"(?i)^the\s+", "", body)
                body = body[0].lower() + body[1:] if body else body
                return f"RBI releases the {body[0].lower() + body[1:] if body.startswith('Result') else body}. Source: RBI."
            if "auction" in lowered and ("conduct" in lowered or "calendar" in lowered):
                body = self._headline_rewrite(headline, [(r"(?i)^calendar for ", ""), (r"(?i)^RBI to ", "RBI to ")])
                if body.lower().startswith("auction"):
                    return f"RBI releases the {body.lower()}. Source: RBI."
                return f"{body}. Source: RBI."
            if "repo rate" in lowered or "monetary policy" in lowered:
                return f"{headline}. Source: RBI."
        return f"{headline}. Source: {source_name}."

    def _penalty_template(self, facts: dict) -> str | None:
        headline = self._clean_headline(facts)
        if not headline:
            return None
        if not headline.startswith("RBI"):
            return f"RBI {headline[0].lower() + headline[1:]}. Source: RBI."
        return f"{headline}. Source: RBI."

    def _regulatory_template(self, facts: dict) -> str | None:
        headline = self._clean_headline(facts)
        source_name = self._display_source_name(facts)
        if not headline:
            return None
        if source_name == "SEBI" and not headline.startswith("SEBI"):
            return f"SEBI {headline[0].lower() + headline[1:]}. Source: SEBI."
        return f"{headline}. Source: {source_name}."

    def _earnings_template(self, facts: dict) -> str | None:
        company = self._company_display(facts)
        period = facts.get("period")
        if company and period:
            return f"{company}: {period} results filed. Source: {self._display_source_name(facts)}."
        headline = self._clean_headline(facts)
        if headline:
            return f"{headline}. Source: {self._display_source_name(facts)}."
        return None

    def _fund_notice_template(self, facts: dict) -> str | None:
        headline = self._clean_headline(facts)
        source_name = self._display_source_name(facts)
        if not headline:
            return None
        cleaned = re.sub(r"(?i)\breinvestment of idcw\b", "IDCW reinvestment", headline)
        cleaned = re.sub(r"(?i)\bpayout of idcw\b", "IDCW payout", cleaned)
        cleaned = re.sub(r"(?i)\bof idcw\b", "IDCW", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return f"{cleaned}. Source: {source_name}."

    def _corporate_action_template(self, facts: dict) -> str | None:
        company = self._company_display(facts)
        event_type = facts.get("event_class")
        numbers = facts.get("numbers") or []
        event_date = facts.get("event_date") or facts.get("broadcast_date")
        source_name = self._display_source_name(facts)

        if event_type == "dividend" and company:
            per_share = next((item for item in numbers if item.get("type") == "per_share"), None)
            if per_share:
                amount = f"{per_share.get('currency')} {per_share.get('value')}"
                if event_date:
                    return f"{company}: dividend {amount}/share; ex-date {event_date}. Source: {source_name}."
                return f"{company}: dividend {amount}/share announced. Source: {source_name}."

        if event_type == "bonus_split" and company:
            ratio = next((item for item in numbers if item.get("type") == "ratio"), None)
            if ratio and event_date:
                return f"{company}: bonus issue ratio {ratio.get('value')}; ex-date {event_date}. Source: {source_name}."
            if ratio:
                return f"{company}: bonus issue ratio {ratio.get('value')}. Source: {source_name}."

        headline = self._clean_headline(facts)
        if headline:
            return f"{headline}. Source: {source_name}."
        return None

    def _company_update_template(self, facts: dict) -> str | None:
        headline = self._clean_headline(facts)
        source_name = self._display_source_name(facts)
        if headline:
            return f"{headline}. Source: {source_name}."
        return None

    def _clean_headline(self, facts: dict) -> str:
        return str(facts.get("headline", "")).strip().rstrip(".")

    def _company_display(self, facts: dict) -> str | None:
        company = facts.get("company") or facts.get("ticker")
        if not company:
            return None
        return str(company).strip()

    def _headline_rewrite(self, headline: str, replacements: list[tuple[str, str]]) -> str:
        text = headline.strip().rstrip(".")
        for pattern, replacement in replacements:
            text = re.sub(pattern, replacement, text)
        return text.strip()

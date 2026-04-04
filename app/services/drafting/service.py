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
        if headline:
            return self._with_optional_source(headline, facts)
        return self._with_optional_source("Market update", facts)

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
        max_len = 220
        if len(cleaned) > max_len:
            truncated = cleaned[: max_len - 3]
            last_space = truncated.rfind(" ")
            cleaned = (truncated[:last_space] if last_space > 180 else truncated).rstrip() + "..."
        return cleaned

    def _display_source_name(self, facts: dict) -> str:
        source_name = str(facts.get("source_name", "source"))
        mapping = {
            "rbi_press_releases": "RBI",
            "sebi_releases": "SEBI",
            "nse_corporate_filings": "an NSE filing",
            "bse_announcements": "a BSE filing",
            "tradient_market_news": "Tradient",
            "pib_economy": "PIB",
            "mospi_releases": "MOSPI",
        }
        return mapping.get(source_name, source_name.replace("_", " ").upper())

    def _template_text(self, facts: dict) -> str | None:
        wire_text = self._wire_template(facts)
        if wire_text:
            return wire_text
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
        context = self._wire_context_text(facts)
        source_name = self._display_source_name(facts)
        if not headline:
            return None

        lowered = headline.lower()
        bank_metrics = self._bank_metrics_wire_text(context, facts)
        if bank_metrics:
            return self._with_optional_source(bank_metrics, facts, source_override=source_name)

        market_metrics = self._market_metrics_wire_text(context, facts)
        if market_metrics:
            return self._with_optional_source(market_metrics, facts, source_override=source_name)

        if source_name == "RBI":
            if "auction" in lowered and "result" in lowered:
                body = self._headline_rewrite(headline, [(r"(?i)^result of ", ""), (r"(?i)^RBI ", "RBI ")])
                body = re.sub(r"(?i)^the\s+", "", body)
                body = body[0].lower() + body[1:] if body else body
                return self._with_optional_source(f"RBI releases the {body[0].lower() + body[1:] if body.startswith('Result') else body}", facts, source_override="RBI")
            if "auction" in lowered and ("conduct" in lowered or "calendar" in lowered):
                body = self._headline_rewrite(headline, [(r"(?i)^calendar for ", ""), (r"(?i)^RBI to ", "RBI to ")])
                if body.lower().startswith("auction"):
                    return self._with_optional_source(f"RBI releases the {body.lower()}", facts, source_override="RBI")
                return self._with_optional_source(body, facts, source_override="RBI")
            if "repo rate" in lowered or "monetary policy" in lowered:
                return self._with_optional_source(headline, facts, source_override="RBI")
        return self._with_optional_source(headline, facts, source_override=source_name)

    def _penalty_template(self, facts: dict) -> str | None:
        headline = self._clean_headline(facts)
        if not headline:
            return None
        if not headline.startswith("RBI"):
            return self._with_optional_source(f"RBI {headline[0].lower() + headline[1:]}", facts, source_override="RBI")
        return self._with_optional_source(headline, facts, source_override="RBI")

    def _regulatory_template(self, facts: dict) -> str | None:
        headline = self._clean_headline(facts)
        source_name = self._display_source_name(facts)
        if not headline:
            return None
        if source_name == "SEBI" and not headline.startswith("SEBI"):
            return self._with_optional_source(f"SEBI {headline[0].lower() + headline[1:]}", facts, source_override="SEBI")
        return self._with_optional_source(headline, facts, source_override=source_name)

    def _earnings_template(self, facts: dict) -> str | None:
        headline = self._clean_headline(facts)
        if self._should_preserve_company_wire_headline(headline):
            return self._with_optional_source(headline, facts)
        company = self._company_display(facts)
        period = facts.get("period")
        if company and period:
            return self._with_optional_source(f"{company}: {period} results filed", facts)
        if headline:
            return self._with_optional_source(headline, facts)
        return None

    def _fund_notice_template(self, facts: dict) -> str | None:
        headline = self._clean_headline(facts)
        if not headline:
            return None
        cleaned = re.sub(r"(?i)\breinvestment of idcw\b", "IDCW reinvestment", headline)
        cleaned = re.sub(r"(?i)\bpayout of idcw\b", "IDCW payout", cleaned)
        cleaned = re.sub(r"(?i)\bof idcw\b", "IDCW", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return self._with_optional_source(cleaned, facts)

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
                    return self._with_optional_source(f"{company}: dividend {amount}/share; ex-date {event_date}", facts, source_override=source_name)
                return self._with_optional_source(f"{company}: dividend {amount}/share announced", facts, source_override=source_name)

        if event_type == "bonus_split" and company:
            ratio = next((item for item in numbers if item.get("type") == "ratio"), None)
            if ratio and event_date:
                return self._with_optional_source(f"{company}: bonus issue ratio {ratio.get('value')}; ex-date {event_date}", facts, source_override=source_name)
            if ratio:
                return self._with_optional_source(f"{company}: bonus issue ratio {ratio.get('value')}", facts, source_override=source_name)

        headline = self._clean_headline(facts)
        if headline:
            return self._with_optional_source(headline, facts, source_override=source_name)
        return None

    def _company_update_template(self, facts: dict) -> str | None:
        headline = self._clean_headline(facts)
        if headline:
            return self._with_optional_source(headline, facts)
        return None

    def _wire_template(self, facts: dict) -> str | None:
        wire_from_facts = self._wire_from_facts(facts)
        if wire_from_facts:
            return wire_from_facts
        headline = self._clean_headline(facts)
        context = self._wire_context_text(facts)
        if not headline and not context:
            return None
        company = self._company_wire_label(facts)
        if not company:
            return None

        sales_text = self._sales_wire_text(headline, context, company)
        if sales_text:
            return sales_text

        turnover_text = self._turnover_wire_text(headline, context, company)
        if turnover_text:
            return turnover_text

        production_text = self._production_wire_text(headline, context, company)
        if production_text:
            return production_text

        penalty_text = self._penalty_wire_text(headline, context, company)
        if penalty_text:
            return penalty_text

        order_text = self._order_wire_text(headline, context, company)
        if order_text:
            return order_text

        approval_text = self._approval_wire_text(headline, context, company)
        if approval_text:
            return approval_text

        stake_text = self._stake_wire_text(headline, context, company)
        if stake_text:
            return stake_text

        fundraise_text = self._fundraise_wire_text(headline, context, company)
        if fundraise_text:
            return fundraise_text

        return None

    def _wire_from_facts(self, facts: dict) -> str | None:
        wire_facts = facts.get("wire_facts") or {}
        kind = str(wire_facts.get("kind") or "")
        subject = str(wire_facts.get("subject_label") or self._company_wire_label(facts) or "").strip()
        if not kind or not subject:
            return None

        if kind == "sales_update":
            period = str(wire_facts.get("period") or "").strip()
            metric = str(wire_facts.get("metric_label") or "SALES").strip()
            current = str(wire_facts.get("current_value") or "").strip()
            prior = str(wire_facts.get("prior_value") or "").strip()
            unit = str(wire_facts.get("unit") or "").strip()
            change_pct = str(wire_facts.get("change_pct") or "").strip()
            comparison = str(wire_facts.get("comparison_label") or "YOY").strip()
            estimate = str(wire_facts.get("estimate_value") or "").strip()
            if current and prior and unit:
                base = f"{subject}: {period + ' ' if period else ''}{metric} {current} {unit} VS {prior} {unit} ({comparison})"
                if estimate:
                    base += f"; EST {estimate}"
                secondary_value = str(wire_facts.get("secondary_metric_value") or "").strip()
                secondary_label = str(wire_facts.get("secondary_metric_label") or "").strip()
                secondary_unit = str(wire_facts.get("secondary_metric_unit") or "").strip()
                if secondary_value and secondary_label:
                    base += f"; {secondary_label} {secondary_value}{f' {secondary_unit}' if secondary_unit else ''}"
                return base
            if current and change_pct and unit:
                return f"{subject}: {period + ' ' if period else ''}{metric} UP {change_pct} TO {current} {unit}"
            if current and metric:
                return f"{subject}: {period + ' ' if period else ''}{metric} AT {current}"

        if kind == "production_update":
            period = str(wire_facts.get("period") or "").strip()
            metric = str(wire_facts.get("metric_label") or "PRODUCTION").strip()
            current = str(wire_facts.get("current_value") or "").strip()
            change_pct = str(wire_facts.get("change_pct") or "").strip()
            guidance = str(wire_facts.get("guidance_value") or "").strip()
            if current:
                base = f"{subject}: {period + ' ' if period else ''}{metric} AT {current}"
                if guidance:
                    base += f" VS GUIDANCE {guidance}"
                return base
            if change_pct:
                base = f"{subject}: {period + ' ' if period else ''}{metric} UP {change_pct} YOY"
                if guidance:
                    base += f"; VS GUIDANCE {guidance}"
                return base

        if kind == "offtake_update":
            period = str(wire_facts.get("period") or "").strip()
            current = str(wire_facts.get("current_value") or "").strip()
            change_pct = str(wire_facts.get("change_pct") or "").strip()
            if current and change_pct:
                return f"{subject}: {period + ' ' if period else ''}OFFTAKE UP {change_pct} TO {current}"

        if kind == "outlook_update":
            period = str(wire_facts.get("period") or "").strip()
            metric = str(wire_facts.get("metric_label") or "OUTLOOK").strip()
            current = str(wire_facts.get("current_value") or "").strip()
            unit = str(wire_facts.get("unit") or "").strip()
            if current:
                suffix = unit if unit and not current.endswith(unit) else ""
                return f"{subject}: {period + ' ' if period else ''}{metric} SEEN AT {current}{suffix}"

        if kind == "order_win":
            amount = str(wire_facts.get("amount_value") or "").strip()
            body = str(wire_facts.get("counterparty_or_body") or "").strip()
            metric = str(wire_facts.get("metric_label") or "ORDER").strip()
            if amount and body:
                extra = str(wire_facts.get("extra_clause") or "").strip()
                text = f"{subject}: WINS {body} {metric} WORTH {amount}"
                if extra:
                    text += f" || {extra}"
                return text
            if amount:
                return f"{subject}: {metric} WORTH {amount}"

        if kind == "tax_demand":
            amount = str(wire_facts.get("amount_value") or "").strip()
            metric = str(wire_facts.get("metric_label") or "GST DEMAND ORDER").strip()
            previous = str(wire_facts.get("previous_amount") or "").strip()
            extra = str(wire_facts.get("extra_clause") or "").strip()
            if amount:
                text = f"{subject}: {metric} OF {amount}"
                if previous:
                    text += f" VS PREV {previous}"
                if extra:
                    text += f" || {extra}"
                return text

        return None

    def _sales_wire_text(self, headline: str, context: str, company: str) -> str | None:
        detailed_match = re.search(
            r"(?P<period>MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER|Q\d)\s+total\s+sales\s+(?:at\s+)?(?P<current>[\d,]+)\s+units?\s+vs\s+(?P<prior>[\d,]+)\s+units?(?:\s*\((?P<comp>YOY)\))?(?:;\s*est\.?\s*(?P<est>[\d,]+))?",
            context,
            re.IGNORECASE,
        )
        if detailed_match:
            period = detailed_match.group("period").upper()
            current = detailed_match.group("current")
            prior = detailed_match.group("prior")
            comp = detailed_match.group("comp") or "YOY"
            est = detailed_match.group("est")
            base = f"{company}: {period} TOTAL SALES {current} UNITS VS {prior} UNITS ({comp.upper()})"
            if est:
                base += f"; EST {est}"
            extra = self._sales_extra_clause(context)
            if extra and extra not in base:
                base += f"; {extra}"
            return base

        rise_match = re.search(
            r"(?P<period>MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)?\s*sales\s+(?:rise|up)\s+(?P<pct>[\d.]+%)\s+to\s+(?P<current>[\d,]+)\s+units?",
            context,
            re.IGNORECASE,
        )
        if rise_match:
            period = (rise_match.group("period") or "").upper().strip()
            pct = rise_match.group("pct")
            current = rise_match.group("current")
            prefix = f"{period} " if period else ""
            return f"{company}: {prefix}SALES UP {pct} TO {current} UNITS"

        outlook_match = re.search(
            r"(?P<pct>[\d.]+(?:-[\d.]+)?)%\s+(?:bank\s+)?loan growth\s+for\s+(?P<period>FY\d+)",
            context,
            re.IGNORECASE,
        )
        if outlook_match:
            pct = outlook_match.group("pct")
            period = outlook_match.group("period").upper()
            return f"{company}: {period} LOAN GROWTH SEEN AT {pct}%"

        match = re.match(
            r"^(?P<name>.+?)\s+(?:achieves\s+record\s+)?(?P<period>Q\d|Q4|Q3|Q2|Q1|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)?\s*(?P<label>domestic sales|total sales)$",
            headline,
            re.IGNORECASE,
        )
        if match:
            period = (match.group("period") or "").upper().strip()
            label = match.group("label").upper()
            prefix = f"{period} " if period else ""
            record = "RECORD " if "record" in headline.lower() else ""
            return f"{company}: {record}{prefix}{label}"

        if "sales" in headline.lower() and ":" in headline:
            return self._headline_as_wire(headline)
        return None

    def _turnover_wire_text(self, headline: str, context: str, company: str) -> str | None:
        match = re.search(
            r"turnover\s+(?:in|for)\s+(?P<period>FY\d+)[,:\s]+(?:at\s+)?(?P<value>[₹Rsrs0-9,.\sA-Za-z]+?)(?:,|\s+)up\s+(?P<pct>[\d.]+%)",
            context,
            re.IGNORECASE,
        )
        if match:
            value = self._normalize_money(match.group("value"))
            period = match.group("period").upper()
            pct = match.group("pct")
            base = f"{company}: {period} TURNOVER AT {value}, UP {pct}"
            extra = self._ebitda_extra_clause(context)
            if extra:
                base += f"; {extra}"
            return base

        match = re.match(
            r"^(?P<name>.+?)\s+reports\s+(?P<value>[₹Rsrs0-9,.\sA-Za-z]+)\s+turnover\s+in\s+(?P<period>FY\d+),\s+up\s+(?P<pct>[\d.]+%)",
            headline,
            re.IGNORECASE,
        )
        if match:
            value = self._normalize_money(match.group("value"))
            period = match.group("period").upper()
            pct = match.group("pct")
            return f"{company}: {period} TURNOVER AT {value}, UP {pct}"
        return None

    def _production_wire_text(self, headline: str, context: str, company: str) -> str | None:
        match = re.search(
            r"(?P<product>iron ore pellets?|iron ore|dri|steel|pellets?)\s+production\s+at\s+(?P<current>[\d.,]+\s*(?:mt|mmt|ton|tons|units?))(?:\s+vs\s+guidance(?:\s+of)?\s+(?P<guidance>[\d.,]+\s*(?:mt|mmt|ton|tons|units?)))?",
            context,
            re.IGNORECASE,
        )
        if match:
            product = match.group("product").upper()
            current = match.group("current").upper()
            guidance = match.group("guidance")
            base = f"{company}: {product} PRODUCTION AT {current}"
            if guidance:
                base += f" VS GUIDANCE {guidance.upper()}"
            return base

        match = re.search(
            r"(?P<product>dri|iron ore pellets?|iron ore|steel|pellets?)\s+production\s+(?:surges|rises|up)\s+(?P<pct>[\d.]+%)\s*yoy",
            context,
            re.IGNORECASE,
        )
        if match:
            product = match.group("product").upper()
            pct = match.group("pct")
            base = f"{company}: {product} PRODUCTION UP {pct} YOY"
            extra = self._guidance_extra_clause(context)
            if extra:
                base += f"; {extra}"
            return base

        match = re.match(
            r"^(?P<name>.+?)\s+(?P<product>.+?)\s+production\s+surges\s+(?P<pct>[\d.]+%)\s+yoy$",
            headline,
            re.IGNORECASE,
        )
        if match:
            product = self._trim_company_words(match.group("product"), company)
            pct = match.group("pct")
            return f"{company}: {product} PRODUCTION UP {pct} YOY"

        match = re.match(
            r"^(?P<name>.+?)\s+reports\s+record\s+(?P<product>.+?)\s+production$",
            headline,
            re.IGNORECASE,
        )
        if match:
            product = self._trim_company_words(match.group("product"), company)
            base = f"{company}: RECORD {product} PRODUCTION"
            extra = self._guidance_extra_clause(context)
            if extra:
                base += f"; {extra}"
            return base

        if "production" in headline.lower() and ":" in headline:
            return self._headline_as_wire(headline)
        return None

    def _penalty_wire_text(self, headline: str, context: str, company: str) -> str | None:
        match = re.search(
            r"gst\s+demand(?:\s+order)?(?:\s+(?:worth|of))?\s+(?P<value>(?:₹|rs\.?\s*)?[\d.,]+\s*crore)",
            context,
            re.IGNORECASE,
        )
        if match:
            value = self._normalize_money(match.group("value"))
            return f"{company}: GST DEMAND ORDER OF {value}"

        match = re.match(
            r"^(?P<name>.+?)\s+(?:receives|faces)\s+(?P<body>GST\s+demand(?:\s+order)?(?:\s+worth)?\s+.+)$",
            headline,
            re.IGNORECASE,
        )
        if match:
            body = match.group("body").upper()
            body = re.sub(r"\bWORTH\b", "OF", body)
            body = body.replace("₹", "RS ")
            return f"{company}: {body}"
        match = re.match(
            r"^(?P<name>.+?)\s+faces\s+(?P<value>Rs\s*[\d.,]+\s*Crore)\s+GST\s+demand$",
            headline,
            re.IGNORECASE,
        )
        if match:
            value = self._normalize_money(match.group("value"))
            return f"{company}: GST DEMAND OF {value}"
        return None

    def _order_wire_text(self, headline: str, context: str, company: str) -> str | None:
        match = re.search(
            r"(?:wins?|secured?|receives?)\s+(?P<value>₹?[\d.,]+\s*cr)\s+(?P<body>.+?)\s+(?:order|contract)",
            context,
            re.IGNORECASE,
        )
        if match:
            value = self._normalize_money(match.group("value"))
            body = match.group("body").upper().strip(" -,.")
            return f"{company}: WINS {body} ORDER WORTH {value}"

        project_match = re.search(
            r"wins\s+(?P<value>₹?[\d.,]+\s*cr)\s+(?P<body>.+?)\s+project",
            context,
            re.IGNORECASE,
        )
        if project_match:
            value = self._normalize_money(project_match.group("value"))
            body = project_match.group("body").upper().strip(" -,.")
            return f"{company}: WINS {body} PROJECT WORTH {value}"

        match = re.match(
            r"^(?P<name>.+?)\s+wins\s+(?P<value>₹?[\d.,]+\s*Cr)\s+(?P<body>.+?)\s+order$",
            headline,
            re.IGNORECASE,
        )
        if match:
            value = self._normalize_money(match.group("value"))
            body = match.group("body").upper()
            return f"{company}: WINS {body} ORDER WORTH {value}"

        match = re.match(
            r"^(?P<name>.+?)\s+wins\s+(?P<body>.+?)\s+contract$",
            headline,
            re.IGNORECASE,
        )
        if match:
            body = match.group("body").upper()
            return f"{company}: WINS {body} CONTRACT"
        return None

    def _approval_wire_text(self, headline: str, context: str, company: str) -> str | None:
        match = re.search(
            r"consent to operate for\s+(?P<body>[\d.,]+\s*mw\s+.+?plant).*?trial operations starting\s+(?P<date>[A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?[,]?\s+\d{4})",
            context,
            re.IGNORECASE,
        )
        if match:
            body = match.group("body").upper().strip(" -,.")
            date = re.sub(r"(?i)(\d)(st|nd|rd|th)\b", r"\1", match.group("date").upper())
            return f"{company}: CONSENT TO OPERATE FOR {body} || TRIAL OPS START {date}"

        headline_match = re.match(
            r"^(?P<name>.+?)\s+gets\s+(?P<body>[\d.,]+\s*MW\s+.+?)\s+approval$",
            headline,
            re.IGNORECASE,
        )
        if headline_match:
            return f"{company}: APPROVAL FOR {headline_match.group('body').upper()}"
        return None

    def _stake_wire_text(self, headline: str, context: str, company: str) -> str | None:
        match = re.search(
            r"deposits\s+(?P<deposit>₹?[\d.,]+\s*(?:crore|cr)).+?for\s+.+?\s+in\s+(?P<target>.+?)\s+at\s+₹?[\d.,]+\s+per warrant,?\s+totaling\s+(?P<total>₹?[\d.,]+\s*(?:crore|cr))\s+investment",
            context,
            re.IGNORECASE,
        )
        if match:
            actor_match = re.match(r"^(?P<actor>.+?)\s+deposits\s+", headline, re.IGNORECASE)
            deposit = self._normalize_money(match.group("deposit"))
            total = self._normalize_money(match.group("total"))
            target = match.group("target").upper().strip(" -,.")
            actor = actor_match.group("actor").upper().strip() if actor_match else company
            return f"{actor}: DEPOSITS {deposit} FOR {target} STAKE || TOTAL INVESTMENT {total}"
        return None

    def _fundraise_wire_text(self, headline: str, context: str, company: str) -> str | None:
        match = re.match(
            r"^(?P<name>.+?)\s+rights issue opens (?P<date>.+)$",
            headline,
            re.IGNORECASE,
        )
        if match:
            return f"{company}: RIGHTS ISSUE OPENS {match.group('date').upper()}"
        match = re.match(
            r"^(?P<name>.+?)\s+sets record date for rights issue$",
            headline,
            re.IGNORECASE,
        )
        if match:
            return f"{company}: RECORD DATE SET FOR RIGHTS ISSUE"
        match = re.match(
            r"^(?P<name>.+?)\s+rights issue boosts (?P<body>.+)$",
            headline,
            re.IGNORECASE,
        )
        if match:
            return f"{company}: RIGHTS ISSUE BOOSTS {match.group('body').upper()}"
        return None

    def _sales_extra_clause(self, context: str) -> str | None:
        match = re.search(r"domestic sales(?:\s+(?:at|of))?\s*([\d,]+)\s+units?", context, re.IGNORECASE)
        if match and "total sales" in context.lower():
            return f"DOMESTIC SALES {match.group(1)} UNITS"
        store_match = re.search(r"adds?\s+(\d+)\s+stores?", context, re.IGNORECASE)
        if store_match:
            return f"ADDS {store_match.group(1)} STORES"
        return None

    def _guidance_extra_clause(self, context: str) -> str | None:
        match = re.search(r"guidance(?:\s+of)?\s*([\d.,]+\s*(?:mt|mmt|ton|tons|units?))", context, re.IGNORECASE)
        if match:
            return f"VS GUIDANCE {match.group(1).upper()}"
        return None

    def _ebitda_extra_clause(self, context: str) -> str | None:
        match = re.search(r"ebitda\s+(?:boost|up|rise|rises|surges)\s+(?:of\s+|at\s+)?(~?\s*₹?[\d.,]+\s*(?:crore|cr))", context, re.IGNORECASE)
        if match:
            return f"EBITDA {self._normalize_money(match.group(1))}"
        return None

    def _bank_metrics_wire_text(self, context: str, facts: dict) -> str | None:
        subject = self._company_wire_label(facts) or "BANKING"
        value_pattern = r"[\d.,]+\s*(?:(?:t|tn|trillion|b|bn|billion|crore|cr)(?:\s+rupees)?|rupees)"
        advances = re.search(
            rf"(?:bank\s+)?gross advances(?:\s+seen)?\s+at\s+(?P<current>{value_pattern})\s+vs\s+(?P<prior>{value_pattern})(?:\s*\((?P<comp>yoy)\))?",
            context,
            re.IGNORECASE,
        )
        deposits = re.search(
            rf"(?:bank\s+)?total deposits(?:\s+seen)?\s+at\s+(?P<current>{value_pattern})\s+vs\s+(?P<prior>{value_pattern})(?:\s*\((?P<comp>yoy)\))?",
            context,
            re.IGNORECASE,
        )
        business = re.search(
            r"(?P<pct>[\d.]+%)\s+growth in total business",
            context,
            re.IGNORECASE,
        )
        deposit_growth = re.search(
            r"(?P<pct>[\d.]+%)\s+growth in deposits",
            context,
            re.IGNORECASE,
        )
        deposit_level = re.search(
            r"total deposits reached\s+(?P<current>₹?[\d,]+(?:\.\d+)?\s*crore).*?(?P<pct>\d+(?:\.\d+)?)%\s*yoy\s+growth",
            context,
            re.IGNORECASE,
        )
        gold_advances = re.search(
            r"gold advances (?:surged|rose|up)\s+(?P<pct>\d+(?:\.\d+)?)%\s+to\s+(?P<current>₹?[\d,]+(?:\.\d+)?\s*crore)",
            context,
            re.IGNORECASE,
        )
        total_business = re.search(
            r"total business reached\s+(?P<current>₹?[\d,]+(?:\.\d+)?\s*crores?).*?(?P<pct>\d+(?:\.\d+)?)%\s*yoy\s+growth",
            context,
            re.IGNORECASE,
        )
        domestic_advances = re.search(
            r"domestic gross advances (?:growth )?to\s+(?P<current>₹?[\d.,]+\s*(?:trillion|t|crore|cr))\s+from\s+(?P<prior>₹?[\d.,]+\s*(?:trillion|t|crore|cr))",
            context,
            re.IGNORECASE,
        )
        global_advances = re.search(
            r"global advances (?:reach|reached)\s+(?P<current>₹?[\d.,]+\s*(?:trillion|t|crore|cr))\s+from\s+(?P<prior>₹?[\d.,]+\s*(?:trillion|t|crore|cr))",
            context,
            re.IGNORECASE,
        )
        domestic_deposits = re.search(
            r"domestic deposits (?:to reach|reach)\s+(?P<current>₹?[\d.,]+\s*(?:trillion|t|crore|cr)).*?from\s+(?P<prior>₹?[\d.,]+\s*(?:trillion|t|crore|cr))",
            context,
            re.IGNORECASE,
        )
        global_deposits = re.search(
            r"global deposits (?:are projected at|projected at|reach|reached)\s+(?P<current>₹?[\d.,]+\s*(?:trillion|t|crore|cr))",
            context,
            re.IGNORECASE,
        )
        advances_growth = re.search(
            r"gross advances (?:surged|grew|rose|up)\s+(?P<pct>\d+(?:\.\d+)?)%",
            context,
            re.IGNORECASE,
        )
        deposit_growth_secondary = re.search(
            r"deposits (?:grew|rose|up)\s+(?P<pct>\d+(?:\.\d+)?)%",
            context,
            re.IGNORECASE,
        )

        if advances and deposits:
            advances_comp = f" ({advances.group('comp').upper()})" if advances.group("comp") else ""
            deposits_comp = f" ({deposits.group('comp').upper()})" if deposits.group("comp") else ""
            left = f"GROSS ADVANCES AT {self._normalize_money(advances.group('current'))} VS {self._normalize_money(advances.group('prior'))}{advances_comp}"
            right = f"TOTAL DEPOSITS AT {self._normalize_money(deposits.group('current'))} VS {self._normalize_money(deposits.group('prior'))}{deposits_comp}"
            return f"{subject}: {left} || {right}"
        if deposit_level:
            left = f"DEPOSITS AT {self._normalize_money(deposit_level.group('current'))}, UP {deposit_level.group('pct')}% YOY"
            if gold_advances:
                right = f"GOLD ADVANCES UP {gold_advances.group('pct')}% TO {self._normalize_money(gold_advances.group('current'))}"
                return f"{subject}: {left} || {right}"
            return f"{subject}: {left}"
        if total_business:
            left = f"TOTAL BUSINESS AT {self._normalize_money(total_business.group('current'))}, UP {total_business.group('pct')}% YOY"
            right_parts: list[str] = []
            if advances_growth:
                right_parts.append(f"ADVANCES UP {advances_growth.group('pct')}%")
            if deposit_growth_secondary:
                right_parts.append(f"DEPOSITS UP {deposit_growth_secondary.group('pct')}%")
            if right_parts:
                return f"{subject}: {left} || {'; '.join(right_parts)}"
            return f"{subject}: {left}"
        if domestic_advances:
            left = f"DOMESTIC ADVANCES AT {self._normalize_money(domestic_advances.group('current'))} VS {self._normalize_money(domestic_advances.group('prior'))}"
            if global_advances:
                right = f"GLOBAL ADVANCES AT {self._normalize_money(global_advances.group('current'))} VS {self._normalize_money(global_advances.group('prior'))}"
                return f"{subject}: {left} || {right}"
            return f"{subject}: {left}"
        if domestic_deposits:
            left = f"DOMESTIC DEPOSITS AT {self._normalize_money(domestic_deposits.group('current'))} VS {self._normalize_money(domestic_deposits.group('prior'))}"
            if global_deposits:
                right = f"GLOBAL DEPOSITS AT {self._normalize_money(global_deposits.group('current'))}"
                return f"{subject}: {left} || {right}"
            return f"{subject}: {left}"
        if deposit_growth and business:
            return f"{subject}: DEPOSITS UP {deposit_growth.group('pct')} || TOTAL BUSINESS UP {business.group('pct')}"
        if deposit_growth:
            return f"{subject}: DEPOSITS UP {deposit_growth.group('pct')}"
        if business:
            return f"{subject}: TOTAL BUSINESS UP {business.group('pct')}"
        return None

    def _market_metrics_wire_text(self, context: str, facts: dict) -> str | None:
        loans_deposits = re.search(
            r"bank loans rise to\s+(?P<loans>₹?[\d.,]+\s*(?:trillion|t|crore|cr))[, ]+\s*deposits at\s+(?P<deposits>₹?[\d.,]+\s*(?:trillion|t|crore|cr))",
            context,
            re.IGNORECASE,
        )
        if loans_deposits:
            loans = self._normalize_money(loans_deposits.group("loans"))
            deposits = self._normalize_money(loans_deposits.group("deposits"))
            prior_match = re.search(
                r"loans increasing from\s+(?P<loan_prior>₹?[\d.,]+\s*(?:trillion|t|crore|cr))\s+to\s+₹?[\d.,]+\s*(?:trillion|t|crore|cr),\s+while deposits climb from\s+(?P<deposit_prior>₹?[\d.,]+\s*(?:trillion|t|crore|cr))\s+to\s+₹?[\d.,]+\s*(?:trillion|t|crore|cr)",
                context,
                re.IGNORECASE,
            )
            if prior_match:
                loan_prior = self._normalize_money(prior_match.group("loan_prior"))
                deposit_prior = self._normalize_money(prior_match.group("deposit_prior"))
                return f"BANKING: LOANS AT {loans} VS {loan_prior} || DEPOSITS AT {deposits} VS {deposit_prior}"
            return f"BANKING: LOANS AT {loans} || DEPOSITS AT {deposits}"

        oil_match = re.search(
            r"oil futures surge above\s+\$?(?P<level>\d+(?:\.\d+)?)\s+per barrel",
            context,
            re.IGNORECASE,
        )
        if oil_match:
            return f"US OIL FUTURES: ABOVE ${oil_match.group('level')}/BBL"

        if "strait of hormuz" in context.lower() and "tolls" in context.lower():
            return "IRAN: TO SET TOLLS FOR SHIPS THROUGH STRAIT OF HORMUZ"

        tariff_match = re.search(
            r"(?P<who>trump|u\.?s\.?|us)\s+plans?\s+(?P<pct>\d+%)\s+tariff\s+on\s+(?P<body>.+)",
            context,
            re.IGNORECASE,
        )
        if tariff_match:
            body = tariff_match.group("body").upper().strip(" .")
            return f"US: PLANS {tariff_match.group('pct')} TARIFF ON {body}"

        return None

    def _wire_context_text(self, facts: dict) -> str:
        parts = [self._clean_headline(facts), str(facts.get("article_text") or "").strip()]
        return " ".join(part for part in parts if part).strip()

    def _omit_source_attribution(self, facts: dict) -> bool:
        return True

    def _with_optional_source(self, text: str, facts: dict, source_override: str | None = None) -> str:
        cleaned = text.strip().rstrip(".")
        return cleaned

    def _headline_as_wire(self, headline: str) -> str:
        if ":" in headline:
            left, right = headline.split(":", 1)
            return f"{left.strip().upper()}: {right.strip().upper()}"
        return headline.upper()

    def _company_wire_label(self, facts: dict) -> str | None:
        company = self._company_display(facts)
        if not company:
            return None
        display_symbol = str(facts.get("display_symbol") or "").strip()
        if display_symbol:
            company = display_symbol
        cleaned = re.sub(r"\s*&\s*INDUSTRIES\b", "", company, flags=re.IGNORECASE)
        cleaned = re.sub(
            r"\b(LIMITED|LTD|LTD\.|INDUSTRIES|INDUSTRY|AND ENERGY|INFORMATION SECURITY L|INFORMATION SECURITY)\b",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\bAND\s+ISPAT\b", "& ISPAT", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" -,.")
        return cleaned.upper()

    def _trim_company_words(self, fragment: str, company: str) -> str:
        text = fragment.upper().strip()
        company_words = [word for word in company.upper().split() if len(word) > 2]
        while company_words and text.startswith(f"{company_words[-1]} "):
            word = company_words.pop()
            text = text[len(word) + 1 :].strip()
        return text

    def _normalize_money(self, value: str) -> str:
        text = value.strip()
        text = text.replace("₹", "RS ")
        text = re.sub(r"(?i)\brs\b\.?", "RS", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text.upper()

    def _should_preserve_company_wire_headline(self, headline: str) -> bool:
        lowered = headline.lower()
        return any(term in lowered for term in (
            "sales",
            "volume",
            "turnover",
            "production",
            "ebitda",
            "guidance",
            "gst demand",
            "tax demand",
            "demand order",
            "yoy",
            "domestic sales",
            "commercial production",
        ))

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

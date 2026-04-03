from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.core.config import get_settings
from app.wire_feed.pipeline import WirePipelineResult

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency runtime guard
    OpenAI = None

logger = logging.getLogger(__name__)

DISPLAY_TZ = ZoneInfo("Asia/Kolkata")
REPUTABLE_DOMAINS = [
    "reuters.com",
    "bloomberg.com",
    "cnbctv18.com",
    "moneycontrol.com",
    "livemint.com",
    "economictimes.indiatimes.com",
    "business-standard.com",
    "thehindubusinessline.com",
    "rbi.org.in",
    "sebi.gov.in",
    "pib.gov.in",
    "finmin.gov.in",
    "mca.gov.in",
]
RELIABLE_DOMAIN_KEYWORDS = tuple(domain.replace("www.", "") for domain in REPUTABLE_DOMAINS)


@dataclass(frozen=True)
class WebRunDef:
    key: str
    source_name: str
    run_window: str
    local_hour: int
    local_minute: int = 0


@dataclass(frozen=True)
class WebCandidate:
    title: str
    summary: str
    source_name: str
    source_url: str
    published_at: str
    category: str
    india_impact: str
    why_it_matters: str


@dataclass(frozen=True)
class ValidationResult:
    approved: bool
    reasons: list[str]
    published_at: datetime | None


WEB_RUNS: tuple[WebRunDef, ...] = (
    WebRunDef(
        key="preopen",
        source_name="openai_web_breaking_preopen",
        run_window="preopen",
        local_hour=7,
        local_minute=15,
    ),
    WebRunDef(
        key="midday",
        source_name="openai_web_breaking_midday",
        run_window="general",
        local_hour=13,
        local_minute=0,
    ),
    WebRunDef(
        key="night",
        source_name="openai_web_breaking_night",
        run_window="night",
        local_hour=21,
        local_minute=15,
    ),
)


def get_due_web_runs(now: datetime, has_run_since: callable) -> list[WebRunDef]:
    local_now = now.astimezone(DISPLAY_TZ)
    due: list[WebRunDef] = []
    for run in WEB_RUNS:
        local_start = local_now.replace(hour=run.local_hour, minute=run.local_minute, second=0, microsecond=0)
        if local_now < local_start:
            continue
        if has_run_since(run.source_name, local_start.astimezone(timezone.utc)):
            continue
        due.append(run)
    return due


def fetch_web_breaking_candidates(run: WebRunDef) -> list[WirePipelineResult]:
    settings = get_settings()
    if not settings.wire_web_breaking_enabled:
        return []
    if OpenAI is None or not settings.openai_api_key:
        logger.info("OpenAI web breaking pipeline skipped: client unavailable or key missing")
        return []

    client = OpenAI(api_key=settings.openai_api_key)
    try:
        payload = _response_json(
            client,
            model=settings.wire_web_breaking_model,
            prompt=_build_research_prompt(
                limit=settings.wire_web_breaking_limit,
                hours=settings.wire_web_breaking_freshness_hours,
                run_window=run.run_window,
            ),
            allow_domains=REPUTABLE_DOMAINS,
        )
    except Exception as exc:
        logger.warning("OpenAI web breaking research failed for %s: %s", run.key, exc)
        return [
            WirePipelineResult(
                external_id=f"{run.source_name}:fetch_error",
                source_name=run.source_name,
                source_family="web",
                title="",
                event_type="macro_release",
                dedupe_key=f"{run.source_name}:fetch_error",
                subject_key=None,
                ticker=None,
                importance_score=0,
                confidence_score=0,
                would_auto_post=False,
                review_reason="fetch_error",
                draft_text="",
                safety_flags={"fetch_error": True},
                raw_payload={"source_family": "web", "run_window": run.run_window},
                published_at=None,
                fetch_error=f"{type(exc).__name__}: {exc}",
            )
        ]

    raw_items = payload.get("items") or []
    seen_keys: set[str] = set()
    candidates: list[tuple[WebCandidate, ValidationResult]] = []
    for raw in raw_items:
        candidate = _parse_candidate(raw)
        if candidate is None:
            continue
        fingerprint = f"{candidate.title.strip().lower()}|{candidate.source_url.strip().lower()}"
        if fingerprint in seen_keys:
            continue
        seen_keys.add(fingerprint)

        validation = _validate_candidate(candidate, hours=settings.wire_web_breaking_freshness_hours)
        if not validation.approved:
            continue
        candidates.append((candidate, validation))

    results: list[WirePipelineResult] = []
    for candidate, validation in _dedupe_web_candidates(candidates):

        try:
            draft_text = _draft_tweet(client, model=settings.wire_web_breaking_model, candidate=candidate)
        except Exception as exc:
            logger.warning("OpenAI web breaking drafting failed for %s: %s", candidate.title, exc)
            continue

        event_type = _event_type_for_category(candidate.category, candidate.title, candidate.summary)
        importance = _importance_score(candidate)
        subject_key = _slug(candidate.title)[:120]
        published_at = validation.published_at
        results.append(
            WirePipelineResult(
                external_id=_external_id(run.source_name, candidate),
                source_name=run.source_name,
                source_family="web",
                title=candidate.title,
                event_type=event_type,
                dedupe_key=f"web|{event_type}|{subject_key}",
                subject_key=subject_key,
                ticker=None,
                importance_score=importance,
                confidence_score=0.9,
                would_auto_post=True,
                review_reason=None,
                draft_text=draft_text,
                safety_flags={"openai_web_breaking": True},
                raw_payload={
                    "source_family": "web",
                    "run_window": run.run_window,
                    "source_url": candidate.source_url,
                    "article_source_name": candidate.source_name,
                    "category": candidate.category,
                    "india_impact": candidate.india_impact,
                    "why_it_matters": candidate.why_it_matters,
                },
                published_at=published_at,
            )
        )
    if results:
        return results
    return [_noop_result(run, reason="no_approved_candidates")]


def _build_research_prompt(limit: int, hours: int, run_window: str) -> str:
    now_ist = datetime.now(timezone.utc).astimezone(DISPLAY_TZ)
    if run_window == "preopen":
        focus = (
            "Focus on overnight developments that matter for India market open: US markets, oil, dollar, rates, "
            "geopolitics, RBI/SEBI/government actions, banks, and major India company updates."
        )
    elif run_window == "night":
        focus = (
            "Focus on post-market India developments and global developments that could matter for the next India session: "
            "policy, macro, geopolitics, banks, commodities, and major company updates."
        )
    else:
        focus = (
            "Focus on India-relevant finance and market-moving developments: Indian finance news, geopolitics affecting India, "
            "and US market developments only when they matter for Indian markets."
        )

    return f"""
Find up to {limit} finance/market news items from the last {hours} hours.

Current IST time: {now_ist.strftime('%Y-%m-%d %H:%M IST')}
Current UTC time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}

{focus}

Rules:
- Prefer developments that a finance-market audience in India would care about.
- Prefer items published today when available; otherwise choose only the freshest items within the allowed window.
- If multiple articles describe the same event, return only the most recent one.
- Exclude backgrounders, explainers, or older follow-ups if a fresher event update exists.
- If freshness is unclear or the article appears older than the allowed window, do not include it.
- Include a mix of banking, macro, geopolitics with market impact, regulation/policy, and major company updates.
- Exclude low-signal items like routine compliance notices, minor management changes, tiny procedural updates, appeals filed by individuals, and clerical filings.
- Prefer reputable sources and official sources.
- Return only valid JSON with this shape:
{{
  "items": [
    {{
      "title": "short title",
      "summary": "1-2 sentence factual summary",
      "source_name": "Reuters / RBI / CNBC TV18 / ...",
      "source_url": "https://...",
      "published_at": "ISO-8601 timestamp if available, otherwise empty string",
      "category": "banking_metrics | macro_market | geopolitics | policy_regulation | company_update | commodity | rates_fx",
      "india_impact": "one short sentence on why it matters to India/Indian markets",
      "why_it_matters": "one short sentence on why the item is market-moving"
    }}
  ]
}}
""".strip()


def _response_json(client: OpenAI, *, model: str, prompt: str, allow_domains: list[str]) -> dict[str, Any]:
    response = client.responses.create(
        model=model,
        input=prompt,
        tools=[
            {
                "type": "web_search",
                "filters": {"allowed_domains": allow_domains},
                "search_context_size": "high",
                "user_location": {
                    "type": "approximate",
                    "country": "IN",
                    "region": "Maharashtra",
                    "city": "Mumbai",
                    "timezone": "Asia/Kolkata",
                },
            }
        ],
        include=["web_search_call.action.sources"],
        text={"format": {"type": "text"}, "verbosity": "low"},
        max_output_tokens=4000,
    )
    return _parse_json_text(response.output_text)


def _parse_json_text(value: str) -> dict[str, Any]:
    raw = value.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start : end + 1]
    return json.loads(raw)


def _draft_tweet(client: OpenAI, *, model: str, candidate: WebCandidate) -> str:
    prompt = f"""
Write one factual finance-market X post in a dense wire style.

Rules:
- No hashtags
- No emojis
- No source attribution in the tweet body
- Prefer 120-220 characters when supported by the facts
- Use company/entity first when appropriate
- Include a second fact, comparison, or market consequence whenever supported by the facts
- Prefer compressed wire syntax like:
  - `ENTITY: FACT 1; FACT 2`
  - `ENTITY: FACT 1 || FACT 2`
  - `MARKETS: MOVE; CONSEQUENCE`
- If there is a strong number, put it early
- If there is a strong market implication, include it in the second clause
- Do not sound like a generic news summary
- Do not invent facts

Facts:
Title: {candidate.title}
Summary: {candidate.summary}
Category: {candidate.category}
India impact: {candidate.india_impact}
Why it matters: {candidate.why_it_matters}

Return only the tweet text.
""".strip()
    response = client.responses.create(
        model=model,
        input=prompt,
        max_output_tokens=220,
        text={"format": {"type": "text"}, "verbosity": "low"},
    )
    return " ".join(response.output_text.split()).strip()


def _parse_candidate(item: dict[str, Any]) -> WebCandidate | None:
    title = str(item.get("title") or "").strip()
    source_url = str(item.get("source_url") or "").strip()
    if not title or not source_url:
        return None
    return WebCandidate(
        title=title,
        summary=str(item.get("summary") or "").strip(),
        source_name=str(item.get("source_name") or "").strip(),
        source_url=source_url,
        published_at=str(item.get("published_at") or "").strip(),
        category=str(item.get("category") or "").strip(),
        india_impact=str(item.get("india_impact") or "").strip(),
        why_it_matters=str(item.get("why_it_matters") or "").strip(),
    )


def _parse_published_at(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _validate_candidate(candidate: WebCandidate, *, hours: int) -> ValidationResult:
    reasons: list[str] = []
    parsed_time = _parse_published_at(candidate.published_at)
    if parsed_time is None:
        reasons.append("missing_or_invalid_time")
    else:
        age = datetime.now(timezone.utc) - parsed_time.astimezone(timezone.utc)
        if age > timedelta(hours=hours):
            reasons.append(f"stale_{int(age.total_seconds() // 3600)}h")

    source_url_lower = candidate.source_url.lower()
    if not any(domain in source_url_lower for domain in RELIABLE_DOMAIN_KEYWORDS):
        reasons.append("untrusted_domain")

    text = " ".join(
        [
            candidate.title.lower(),
            candidate.summary.lower(),
            candidate.india_impact.lower(),
            candidate.why_it_matters.lower(),
            candidate.category.lower(),
        ]
    )
    if not any(
        term in text
        for term in (
            "india",
            "indian",
            "bank",
            "market",
            "oil",
            "rupee",
            "rbi",
            "sebi",
            "tariff",
            "deposit",
            "advance",
            "rate",
            "policy",
            "equity",
            "stock",
            "borrower",
        )
    ):
        reasons.append("weak_india_relevance")

    return ValidationResult(approved=not reasons, reasons=reasons, published_at=parsed_time)


def _importance_score(candidate: WebCandidate) -> int:
    text = " ".join(
        [
            candidate.title.lower(),
            candidate.summary.lower(),
            candidate.india_impact.lower(),
            candidate.why_it_matters.lower(),
            candidate.category.lower(),
        ]
    )
    score = 84
    if candidate.category in {"macro_market", "geopolitics", "rates_fx", "policy_regulation"}:
        score += 5
    if candidate.category == "banking_metrics":
        score += 4
    if any(term in text for term in ("rbi", "sebi", "tariff", "oil", "rupee", "yields", "rates", "inflation")):
        score += 3
    if any(term in text for term in ("india market open", "next india session", "market-moving", "risk appetite")):
        score += 2
    return min(score, 96)


def _dedupe_web_candidates(
    candidates: list[tuple[WebCandidate, ValidationResult]],
    max_per_topic: int = 1,
) -> list[tuple[WebCandidate, ValidationResult]]:
    ordered = sorted(
        candidates,
        key=lambda item: (
            _importance_score(item[0]),
            item[1].published_at or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )
    kept: list[tuple[WebCandidate, ValidationResult]] = []
    topic_counts: dict[str, int] = {}
    seen_fingerprints: set[str] = set()
    for candidate, validation in ordered:
        fingerprint = _candidate_fingerprint(candidate)
        if fingerprint in seen_fingerprints:
            continue
        topic = _topic_bucket(candidate)
        if topic_counts.get(topic, 0) >= max_per_topic:
            continue
        kept.append((candidate, validation))
        seen_fingerprints.add(fingerprint)
        topic_counts[topic] = topic_counts.get(topic, 0) + 1
    return kept


def _event_type_for_category(category: str, title: str, summary: str) -> str:
    text = f"{category} {title} {summary}".lower()
    if any(term in text for term in ("rbi", "sebi", "approval", "regulator", "policy")):
        return "rbi_policy"
    if any(term in text for term in ("oil", "tariff", "rupee", "yield", "rate", "inflation", "geopolitic", "hormuz")):
        return "macro_release"
    if any(term in text for term in ("order", "contract", "project", "wins")):
        return "order_win"
    return "macro_release"


def _external_id(source_name: str, candidate: WebCandidate) -> str:
    return f"{source_name}:{_slug(candidate.source_url or candidate.title)}"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _candidate_fingerprint(candidate: WebCandidate) -> str:
    text = f"{candidate.title} {candidate.summary}".lower()
    tokens = [
        token
        for token in re.findall(r"[a-z0-9$%./-]+", text)
        if token not in {"the", "and", "for", "with", "after", "ahead", "from", "says", "say"}
    ]
    return "|".join(tokens[:8])


def _topic_bucket(candidate: WebCandidate) -> str:
    text = " ".join(
        [
            candidate.title.lower(),
            candidate.summary.lower(),
            candidate.category.lower(),
            candidate.india_impact.lower(),
            candidate.why_it_matters.lower(),
        ]
    )
    if any(term in text for term in ("rupee", "usd/inr", "fx curbs", "speculative bets", "ndf", "dollar glut")):
        return "fx_rupee"
    if any(term in text for term in ("repo", "rate hike", "rbi policy", "inflation target", "stance change")):
        return "rbi_policy_rates"
    if any(term in text for term in ("oil", "crude", "brent", "wti", "petrol", "diesel")):
        return "oil_energy"
    if any(term in text for term in ("wall street", "us stocks", "nasdaq", "s&p 500", "dow")):
        return "us_markets"
    if any(term in text for term in ("tariff", "trade", "shipping", "hormuz", "middle east", "iran")):
        return "global_geopolitics"
    if any(term in text for term in ("bond", "yield", "debt purchase")):
        return "bonds_yields"
    if any(term in text for term in ("bank", "deposits", "advances", "credit growth", "loan growth")):
        return "banking_metrics"
    return candidate.category or "other"


def _noop_result(run: WebRunDef, *, reason: str) -> WirePipelineResult:
    today = datetime.now(timezone.utc).astimezone(DISPLAY_TZ).strftime("%Y%m%d")
    return WirePipelineResult(
        external_id=f"{run.source_name}:{today}:{reason}",
        source_name=run.source_name,
        source_family="web",
        title="",
        event_type="macro_release",
        dedupe_key=f"{run.source_name}:{today}:{reason}",
        subject_key=None,
        ticker=None,
        importance_score=0,
        confidence_score=0,
        would_auto_post=False,
        review_reason=reason,
        draft_text="",
        safety_flags={reason: True},
        raw_payload={"source_family": "web", "run_window": run.run_window},
        published_at=None,
        fetch_error=reason,
    )

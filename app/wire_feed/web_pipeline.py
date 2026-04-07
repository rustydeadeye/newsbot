from __future__ import annotations

import json
import logging
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.core.config import get_settings
from app.wire_feed.pipeline import WirePipelineResult, ai_readiness_assessment
from app.wire_feed.products import normalize_wire_product

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency runtime guard
    OpenAI = None

logger = logging.getLogger(__name__)

DISPLAY_TZ = ZoneInfo("Asia/Kolkata")
FINANCE_REPUTABLE_DOMAINS = [
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
AI_PRODUCT_DOMAINS = (
    "openai.com",
    "anthropic.com",
    "blog.google",
    "huggingface.co",
    "reuters.com",
    "techcrunch.com",
    "theverge.com",
    "arstechnica.com",
    "venturebeat.com",
    "zdnet.com",
)
AI_INDUSTRY_DOMAINS = (
    "reuters.com",
    "ft.com",
    "bloomberg.com",
    "semafor.com",
    "techcrunch.com",
    "venturebeat.com",
)
AI_POLICY_DOMAINS = (
    "reuters.com",
    "ft.com",
    "bloomberg.com",
    "whitehouse.gov",
    "nist.gov",
    "ec.europa.eu",
)
AI_REPUTABLE_DOMAINS = list(dict.fromkeys(AI_PRODUCT_DOMAINS + AI_INDUSTRY_DOMAINS + AI_POLICY_DOMAINS))
AI_POLICY_ACTOR_TERMS = (
    "eu ai act",
    "european union",
    "european commission",
    "ftc",
    "federal trade commission",
    "white house",
    "nist",
    "uk ai safety institute",
    "copyright office",
    "court",
    "judge",
    "regulator",
    "regulation",
    "ministry",
    "government",
)
AI_COMPANY_TERMS = (
    "openai",
    "anthropic",
    "claude",
    "google",
    "gemini",
    "deepmind",
    "meta",
    "microsoft",
    "azure ai",
    "xai",
    "grok",
    "mistral",
    "cohere",
    "perplexity",
    "hugging face",
)
AI_PRODUCT_UPDATE_TERMS = (
    "model",
    "api",
    "pricing",
    "release",
    "launch",
    "tool",
    "agent",
    "developer",
    "context window",
    "subscription",
    "pay extra",
    "feature",
    "rollout",
    "billing",
    "bill separately",
    "pay-as-you-go",
    "limit",
    "limits",
    "availability",
)
AI_INDUSTRY_MOVE_TERMS = (
    "partnership",
    "acquisition",
    "funding",
    "enterprise",
    "chips",
    "cloud",
    "datacenter",
    "deal",
    "expansion",
    "leadership",
    "executive shuffle",
    "investment",
    "hiring",
)
AI_POLICY_TERMS = (
    "policy",
    "regulation",
    "copyright",
    "lawsuit",
    "ai act",
    "ftc",
    "white house",
    "export control",
    "training data",
    "licensing",
    "court ruling",
)
AI_EXPLICIT_POLICY_CONTEXT_TERMS = (
    "ai",
    "artificial intelligence",
    "foundation model",
    "generative ai",
    "training data",
    "model",
    "chatbot",
    "openai",
    "anthropic",
    "google",
    "meta",
    "microsoft",
    "claude",
    "gemini",
)
AI_WORLD_NOISE_TERMS = (
    "egypt says it held calls",
    "kuwait petroleum",
    "deportees",
    "military school",
    "drone attack",
    "regional counterparts",
    "cuba frees prisoners",
    "zelenskiy",
    "syria",
)
RELIABLE_DOMAIN_KEYWORDS = tuple(domain.replace("www.", "") for domain in (FINANCE_REPUTABLE_DOMAINS + AI_REPUTABLE_DOMAINS))


@dataclass(frozen=True)
class WebRunDef:
    product: str
    key: str
    source_name: str
    lane: str
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
        product="finance",
        key="india_preopen",
        source_name="tavily_web_india_preopen",
        lane="india_preopen",
        local_hour=7,
        local_minute=15,
    ),
    WebRunDef(
        product="finance",
        key="india_close",
        source_name="tavily_web_india_close",
        lane="india_close",
        local_hour=15,
        local_minute=45,
    ),
    WebRunDef(
        product="finance",
        key="global_impact",
        source_name="tavily_web_global_impact",
        lane="global_impact",
        local_hour=21,
        local_minute=15,
    ),
    WebRunDef(
        product="ai",
        key="ai_news",
        source_name="tavily_ai_news",
        lane="ai_news",
        local_hour=8,
        local_minute=0,
    ),
    WebRunDef(
        product="ai",
        key="ai_explained",
        source_name="tavily_ai_explained",
        lane="ai_explained",
        local_hour=13,
        local_minute=0,
    ),
    WebRunDef(
        product="ai",
        key="ai_for_business",
        source_name="tavily_ai_for_business",
        lane="ai_for_business",
        local_hour=20,
        local_minute=0,
    ),
)


def get_due_web_runs(now: datetime, has_run_since: callable, *, product: str = "finance") -> list[WebRunDef]:
    local_now = now.astimezone(DISPLAY_TZ)
    product = normalize_wire_product(product)
    due: list[WebRunDef] = []
    for run in WEB_RUNS:
        if run.product != product:
            continue
        local_start = local_now.replace(hour=run.local_hour, minute=run.local_minute, second=0, microsecond=0)
        if local_now < local_start:
            continue
        if has_run_since(run.source_name, local_start.astimezone(timezone.utc)):
            continue
        due.append(run)
    return due


def fetch_web_breaking_candidates(
    run: WebRunDef,
    *,
    openai_api_key: str | None = None,
    tavily_api_key: str | None = None,
) -> list[WirePipelineResult]:
    settings = get_settings()
    if not settings.wire_web_breaking_enabled:
        return []
    resolved_openai_key = openai_api_key or settings.openai_api_key
    resolved_tavily_key = tavily_api_key or settings.tavily_api_key
    if OpenAI is None or not resolved_openai_key or not resolved_tavily_key:
        logger.info("Tavily web breaking pipeline skipped: client or key missing")
        return []

    client = OpenAI(api_key=resolved_openai_key)
    try:
        raw_items = _tavily_lane_results(
            lane=run.lane,
            tavily_api_key=resolved_tavily_key,
            limit=settings.wire_web_breaking_limit,
            hours=settings.wire_web_breaking_freshness_hours,
            product=run.product,
        )
    except Exception as exc:
        logger.warning("Tavily web breaking research failed for %s: %s", run.key, exc)
        return [
            WirePipelineResult(
                product=run.product,
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
                raw_payload={"source_family": "web", "lane": run.lane, "product": run.product},
                published_at=None,
                fetch_error=f"{type(exc).__name__}: {exc}",
            )
        ]
    seen_keys: set[str] = set()
    raw_count = len(raw_items)
    filtered_count = 0
    drafted_count = 0
    band_counts = {"A": 0, "B": 0, "C": 0}
    skip_reasons: dict[str, int] = {}
    candidates: list[tuple[WebCandidate, ValidationResult]] = []
    for raw in raw_items:
        candidate = _parse_candidate(raw, product=run.product)
        if candidate is None:
            continue
        fingerprint = f"{candidate.title.strip().lower()}|{candidate.source_url.strip().lower()}"
        if fingerprint in seen_keys:
            continue
        seen_keys.add(fingerprint)

        validation = _validate_candidate(candidate, hours=settings.wire_web_breaking_freshness_hours, product=run.product)
        if not validation.approved:
            filtered_count += 1
            for reason in validation.reasons:
                skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
            continue
        if not _passes_lane_relevance_gate(candidate, lane=run.lane, product=run.product):
            filtered_count += 1
            skip_reasons["lane_mismatch"] = skip_reasons.get("lane_mismatch", 0) + 1
            continue
        candidates.append((candidate, validation))

    results: list[WirePipelineResult] = []
    selected = _select_web_candidates(candidates, lane=run.lane, product=run.product)
    for candidate, validation in selected:
        if not _passes_lane_relevance_gate(candidate, lane=run.lane, product=run.product):
            logger.info("Rejected Tavily candidate for lane mismatch: %s", candidate.title)
            skip_reasons["lane_mismatch"] = skip_reasons.get("lane_mismatch", 0) + 1
            continue
        try:
            draft_text = _draft_tweet(client, model=settings.wire_web_breaking_model, candidate=candidate, product=run.product, lane=run.lane)
        except Exception as exc:
            logger.warning("OpenAI web breaking drafting failed for %s: %s", candidate.title, exc)
            skip_reasons["draft_error"] = skip_reasons.get("draft_error", 0) + 1
            continue
        drafted_count += 1
        if not _passes_public_quality_gate(draft_text, candidate=candidate, product=run.product, lane=run.lane):
            logger.info("Rejected Tavily draft for public-facing quality: %s", candidate.title)
            skip_reasons["draft_quality"] = skip_reasons.get("draft_quality", 0) + 1
            continue

        event_type = _event_type_for_category(candidate.category, candidate.title, candidate.summary, product=run.product)
        importance = _importance_score(candidate, product=run.product)
        subject_key = _slug(candidate.title)[:120]
        published_at = validation.published_at
        if run.product == "ai":
            band, readiness_reason = ai_readiness_assessment(
                importance_score=importance,
                confidence_score=0.9,
                draft_text=draft_text,
                title=candidate.title,
                body_text=candidate.summary,
                event_type=event_type,
                review_reason=None,
                lane=run.lane,
            )
        else:
            band, readiness_reason = "A", "live_finance_candidate"
        band_counts[band] = band_counts.get(band, 0) + 1
        results.append(
            WirePipelineResult(
                product=run.product,
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
                would_auto_post=False,
                review_reason=None if band != "C" else "quality_band_c",
                draft_text=draft_text,
                safety_flags={
                    "openai_web_breaking": True,
                    "quality_band": band,
                    "shadow_mode": settings.ai_shadow_mode if run.product == "ai" else False,
                    "ai_lane": run.lane,
                },
                raw_payload={
                    "source_family": "web",
                    "product": run.product,
                    "shadow_mode": settings.ai_shadow_mode if run.product == "ai" else False,
                    "quality_band": band,
                    "readiness_reason": readiness_reason,
                    "lane": run.lane,
                    "topic_family": run.lane,
                    "seed_key": subject_key,
                    "seed_source_name": run.source_name,
                    "seed_source_family": "web",
                    "source_url": candidate.source_url,
                    "article_source_name": candidate.source_name,
                    "category": candidate.category,
                    "india_impact": candidate.india_impact,
                    "why_it_matters": candidate.why_it_matters,
                    "seed_facts": _instagram_seed_facts(candidate, published_at=published_at, lane=run.lane, product=run.product),
                },
                published_at=published_at,
            )
        )
    if run.product == "ai":
        logger.info(
            "AI web lane processed: lane=%s raw=%s post_filter=%s post_cluster=%s drafted=%s bands=%s skips=%s",
            run.lane,
            raw_count,
            len(candidates),
            len(selected),
            drafted_count,
            band_counts,
            skip_reasons,
        )
    if results:
        return results
    return [_noop_result(run, reason="no_approved_candidates")]


def _tavily_lane_results(*, lane: str, tavily_api_key: str, limit: int, hours: int, product: str = "finance") -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for query in _lane_queries(lane, product=product):
        payload = _tavily_search(
            query=query,
            tavily_api_key=tavily_api_key,
            max_results=max(6, limit),
            days=max(2, hours // 24 + 1),
            domains=_lane_domains(lane, product=product),
        )
        for item in payload.get("results") or []:
            url = str(item.get("url") or "").strip()
            if not url or url in seen_urls:
                continue
            if _is_obvious_junk(item):
                continue
            seen_urls.add(url)
            merged.append(item)
    ordered = sorted(merged, key=_tavily_sort_key, reverse=True)
    return ordered[: max(limit * 2, limit)]


def _tavily_search(*, query: str, tavily_api_key: str, max_results: int, days: int, domains: list[str]) -> dict[str, Any]:
    payload = {
        "query": query,
        "topic": "news",
        "search_depth": "advanced",
        "max_results": max_results,
        "include_raw_content": False,
        "include_answer": False,
        "include_images": False,
        "days": days,
        "include_domains": domains,
    }
    req = urllib.request.Request(
        "https://api.tavily.com/search",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {tavily_api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def _instagram_seed_facts(candidate: WebCandidate, *, published_at: datetime | None, lane: str, product: str) -> dict:
    combined_text = " ".join(part for part in (candidate.title, candidate.summary, candidate.why_it_matters) if part).strip()
    lowered = combined_text.lower()
    age_hours = None
    if published_at is not None:
        age_hours = max((datetime.now(timezone.utc) - published_at.astimezone(timezone.utc)).total_seconds() / 3600, 0)
    is_recent = age_hours is None or age_hours <= 24 * 7
    return {
        "headline": candidate.title,
        "article_text": candidate.summary,
        "snippet": candidate.summary,
        "company": _extract_company_hint(candidate.title, candidate.summary),
        "topic_tags": [tag for tag in ("pricing", "workflow", "policy", "launch", "agents", "enterprise") if tag in lowered],
        "source_name": candidate.source_name,
        "source_family": "web",
        "source_url": candidate.source_url,
        "published_at": published_at.isoformat() if published_at else None,
        "age_hours": age_hours,
        "seed_age_bucket": (
            "evergreen"
            if age_hours is None
            else "current"
            if age_hours <= 24
            else "recent"
            if age_hours <= 24 * 3
            else "recent_plus"
            if age_hours <= 24 * 7
            else "aged"
        ),
        "event_type": _event_type_for_category(candidate.category, candidate.title, candidate.summary, product=product),
        "is_official": any(domain in (candidate.source_url or "") for domain in ("openai.com", "anthropic.com", "google.com", "huggingface.co", "microsoft.com")),
        "is_recent": is_recent,
        "is_product_update": lane == "ai_news",
        "is_business_relevant": lane == "ai_for_business" or any(term in lowered for term in ("business", "enterprise", "workflow", "cost", "team")),
        "is_explainer_friendly": lane == "ai_explained" or any(term in lowered for term in ("means", "matters", "impact", "policy", "why")),
    }


def _extract_company_hint(title: str, summary: str) -> str | None:
    lowered = f"{title} {summary}".lower()
    for term, label in (
        ("openai", "OpenAI"),
        ("anthropic", "Anthropic"),
        ("claude", "Anthropic"),
        ("google", "Google"),
        ("gemini", "Google"),
        ("microsoft", "Microsoft"),
        ("copilot", "Microsoft"),
        ("meta", "Meta"),
        ("xai", "xAI"),
        ("hugging face", "Hugging Face"),
    ):
        if term in lowered:
            return label
    return None


def _lane_queries(lane: str, *, product: str = "finance") -> list[str]:
    if product == "ai":
        if lane == "ai_news":
            return [
                "OpenAI Anthropic Google Microsoft xAI Hugging Face AI release notes launch API pricing feature latest",
                "AI product launch API pricing access billing feature rollout official latest",
                "Claude Gemini ChatGPT Copilot API pricing subscription billing feature update latest",
            ]
        if lane == "ai_explained":
            return [
                "AI update what it means pricing model launch enterprise shift latest",
                "OpenAI Anthropic Google Microsoft AI product strategy implications latest",
                "AI policy pricing rollout why it matters latest Reuters Verge TechCrunch",
            ]
        return [
            "AI business workflow enterprise adoption pricing automation ROI latest",
            "OpenAI Anthropic Google Microsoft AI enterprise rollout cost productivity latest",
            "AI teams founders operators workflow automation adoption latest",
        ]
    if lane == "india_preopen":
        return [
            "India markets pre-open today GIFT Nifty rupee RBI latest news",
            "India pre-open crude oil yields dollar overnight Wall Street latest",
            "India market moving company news today pre-open",
            "RBI rupee latest India markets today",
        ]
    if lane == "india_close":
        return [
            "India market close today Sensex Nifty closing summary latest",
            "India top movers today rupee yields oil market close latest",
            "India closing sector performance today latest",
            "India market recap today biggest stories latest",
        ]
    return [
        "global news today affecting Indian markets oil dollar yields latest",
        "geopolitics oil shipping tariffs sanctions latest market impact India",
        "Fed Treasury yields dollar latest world market news India impact",
        "major world economic news today relevant for India markets",
    ]


def _lane_domains(lane: str, *, product: str = "finance") -> list[str]:
    if product == "ai":
        if lane == "ai_news":
            return list(AI_PRODUCT_DOMAINS)
        if lane == "ai_explained":
            return list(dict.fromkeys(AI_PRODUCT_DOMAINS + AI_POLICY_DOMAINS + ("wired.com", "technologyreview.com")))
        if lane == "ai_for_business":
            return list(dict.fromkeys(AI_INDUSTRY_DOMAINS + AI_PRODUCT_DOMAINS))
        return list(dict.fromkeys(AI_PRODUCT_DOMAINS + AI_INDUSTRY_DOMAINS + AI_POLICY_DOMAINS))
    if lane == "global_impact":
        return [
            "reuters.com",
            "apnews.com",
            "cnbc.com",
            "bloomberg.com",
            "wsj.com",
            "ft.com",
            "business-standard.com",
            "livemint.com",
        ]
    return [
        "business-standard.com",
        "economictimes.indiatimes.com",
        "moneycontrol.com",
        "livemint.com",
        "reuters.com",
        "nseindia.com",
        "bseindia.com",
        "rbi.org.in",
        "sebi.gov.in",
        "apnews.com",
    ]


def _tavily_sort_key(item: dict[str, Any]) -> tuple[datetime, float]:
    published_at = _parse_published_at(str(item.get("published_date") or item.get("published_at") or ""))
    return (published_at or datetime.min.replace(tzinfo=timezone.utc), float(item.get("score") or 0))


def _is_obvious_junk(item: dict[str, Any]) -> bool:
    text = " ".join(
        [
            str(item.get("title") or ""),
            str(item.get("content") or ""),
            str(item.get("url") or ""),
        ]
    ).lower()
    blocked_terms = (
        "horoscope",
        "astrology",
        "sports",
        "entertainment",
        "lifestyle",
        "celebrity",
        "weather",
        "recipe",
    )
    return any(term in text for term in blocked_terms)


def _draft_tweet(client: OpenAI, *, model: str, candidate: WebCandidate, product: str = "finance", lane: str | None = None) -> str:
    if product == "ai":
        if lane == "ai_explained":
            prompt = f"""
Write one public-facing AI explanation X post.

Rules:
- No hashtags
- No emojis
- No source attribution in the tweet body
- Prefer 120-230 characters when supported by the facts
- Explain what the update really means, not just what happened
- Keep one clear takeaway
- Avoid jargon, benchmark shorthand, and hype
- Sound calm, useful, and human
- Do not invent facts

Facts:
Title: {candidate.title}
Summary: {candidate.summary}
Category: {candidate.category}
Impact: {candidate.india_impact}
Why it matters: {candidate.why_it_matters}

Return only the tweet text.
""".strip()
        elif lane == "ai_for_business":
            prompt = f"""
Write one practical AI-for-business X post.

Rules:
- No hashtags
- No emojis
- No source attribution in the tweet body
- Prefer 120-230 characters when supported by the facts
- Translate the update into business or workflow value
- Keep it useful and grounded, not salesy
- Mention cost, time, workflow, adoption, or operator relevance when the facts support it
- Do not invent facts

Facts:
Title: {candidate.title}
Summary: {candidate.summary}
Category: {candidate.category}
Impact: {candidate.india_impact}
Why it matters: {candidate.why_it_matters}

Return only the tweet text.
""".strip()
        else:
            prompt = f"""
Write one factual AI news X post in plain public-facing language.

Rules:
- No hashtags
- No emojis
- No source attribution in the tweet body
- Prefer 110-220 characters when supported by the facts
- Explain what changed and why regular users, builders, or businesses should care
- Keep concrete numbers, pricing, names, or limits when the facts provide them
- Avoid unexplained jargon and benchmark shorthand
- Sound human, not like an AI roundup bot
- Do not invent facts

Facts:
Title: {candidate.title}
Summary: {candidate.summary}
Category: {candidate.category}
Impact: {candidate.india_impact}
Why it matters: {candidate.why_it_matters}

Return only the tweet text.
""".strip()
    else:
        prompt = f"""
Write one factual finance-market X post in a dense but human-written style.

Rules:
- No hashtags
- No emojis
- No source attribution in the tweet body
- Prefer 120-220 characters when supported by the facts
- Use simple, public-friendly finance language
- Explain why it matters in plain English
- Include a second fact, comparison, or market consequence whenever supported by the facts
- Sound like a sharp human market commentator, not a robotic wire bot
- If there is a strong number, put it early
- If there is a strong market implication, include it in the second clause
- Avoid unexplained jargon unless it is very common
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


def _parse_candidate(item: dict[str, Any], *, product: str = "finance") -> WebCandidate | None:
    title = str(item.get("title") or "").strip()
    source_url = str(item.get("source_url") or item.get("url") or "").strip()
    if not title or not source_url:
        return None
    summary = str(item.get("summary") or item.get("content") or "").strip()
    source_name = str(item.get("source_name") or _source_name_from_url(source_url)).strip()
    published_at = str(item.get("published_at") or item.get("published_date") or "").strip()
    inferred_category = _infer_category(title, summary, source_url, product=product)
    if product == "ai":
        category = inferred_category
    else:
        category = str(item.get("category") or inferred_category).strip()
    india_impact = str(item.get("india_impact") or _infer_india_impact(title, summary, category, product=product)).strip()
    why_it_matters = str(item.get("why_it_matters") or _infer_why_it_matters(title, summary, category, product=product)).strip()
    return WebCandidate(
        title=title,
        summary=summary,
        source_name=source_name,
        source_url=source_url,
        published_at=published_at,
        category=category,
        india_impact=india_impact,
        why_it_matters=why_it_matters,
    )


def _parse_published_at(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _validate_candidate(candidate: WebCandidate, *, hours: int, product: str = "finance") -> ValidationResult:
    reasons: list[str] = []
    parsed_time = _parse_published_at(candidate.published_at)
    if parsed_time is not None:
        age = datetime.now(timezone.utc) - parsed_time.astimezone(timezone.utc)
        if age > timedelta(hours=hours):
            reasons.append(f"stale_{int(age.total_seconds() // 3600)}h")

    source_url_lower = candidate.source_url.lower()
    domain_keywords = tuple(domain.replace("www.", "") for domain in (AI_REPUTABLE_DOMAINS if product == "ai" else FINANCE_REPUTABLE_DOMAINS))
    if not any(domain in source_url_lower for domain in domain_keywords):
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
    required_terms = (
        "model",
        "api",
        "pricing",
        "launch",
        "anthropic",
        "openai",
        "google",
        "meta",
        "microsoft",
        "xai",
        "mistral",
        "cohere",
        "perplexity",
        "hugging face",
        "policy",
        "regulation",
        "copyright",
        "billing",
        "feature",
        "subscription",
        "training data",
        "licensing",
        "enterprise",
        "ai",
    ) if product == "ai" else (
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
            "gift nifty",
            "sensex",
            "nifty",
            "yield",
            "fed",
        )
    if not any(term in text for term in required_terms):
        reasons.append("weak_relevance")
    if product == "ai" and any(
        term in text
        for term in (
            "horoscope",
            "astrology",
            "celebrity",
            "recipe",
            "sports",
            "cricket",
            "football",
            "opinion",
            "interview",
            "podcast",
            "recap",
            "weekly roundup",
            "how to use chatgpt",
            "best prompts",
            "vibe-coded",
            "for investors",
            "every day",
            "mega-theme",
            "turned my terminal",
        )
    ):
        reasons.append("junk_topic")
    if product == "ai" and any(term in text for term in ("middle east", "iran", "ukraine", "tariff", "shipping", "petroleum", "military school", "deportees")) and not any(
        term in text for term in ("ai", "model", "chip", "gpu", "export control", "copyright", "anthropic", "openai", "google", "meta", "microsoft", "claude", "gemini")
    ):
        reasons.append("off_brief_world_news")
    if any(term in text for term in ("horoscope", "astrology", "celebrity", "recipe", "cricket", "football")):
        reasons.append("junk_topic")

    return ValidationResult(approved=not reasons, reasons=reasons, published_at=parsed_time)


def _importance_score(candidate: WebCandidate, *, product: str = "finance") -> int:
    text = " ".join(
        [
            candidate.title.lower(),
            candidate.summary.lower(),
            candidate.india_impact.lower(),
            candidate.why_it_matters.lower(),
            candidate.category.lower(),
        ]
    )
    if product == "ai":
        score = 82
        if candidate.category in {"product_update", "policy_regulation"}:
            score += 7
        if candidate.category == "industry_move":
            score += 4
        if any(term in text for term in ("pricing", "api", "model", "launch", "copyright", "regulation", "partnership", "funding", "developer", "context window", "acquisition", "enterprise")):
            score += 3
        if any(term in text for term in ("opinion", "podcast", "interview", "research preview", "benchmark", "leaderboard")):
            score -= 8
        return min(score, 96)
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


def _select_web_candidates(
    candidates: list[tuple[WebCandidate, ValidationResult]],
    *,
    lane: str,
    product: str = "finance",
    max_per_topic: int = 1,
    max_selected: int = 5,
) -> list[tuple[WebCandidate, ValidationResult]]:
    ordered = sorted(
        candidates,
        key=lambda item: (
            _selection_score(item[0], lane=lane, product=product),
            item[1].published_at or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )
    kept: list[tuple[WebCandidate, ValidationResult]] = []
    topic_counts: dict[str, int] = {}
    company_counts: dict[str, int] = {}
    seen_fingerprints: set[str] = set()
    seen_clusters: set[str] = set()
    for candidate, validation in ordered:
        fingerprint = _candidate_fingerprint(candidate)
        if fingerprint in seen_fingerprints:
            continue
        topic = _topic_bucket(candidate, product=product)
        cluster = _cluster_bucket(candidate, product=product)
        if cluster in seen_clusters:
            continue
        if topic_counts.get(topic, 0) >= max_per_topic:
            continue
        company = _primary_company(candidate)
        if product == "ai" and company != "other" and company_counts.get(company, 0) >= 1:
            continue
        kept.append((candidate, validation))
        seen_fingerprints.add(fingerprint)
        seen_clusters.add(cluster)
        topic_counts[topic] = topic_counts.get(topic, 0) + 1
        company_counts[company] = company_counts.get(company, 0) + 1
        if len(kept) >= max_selected:
            break
    return kept


def _selection_score(candidate: WebCandidate, *, lane: str, product: str = "finance") -> int:
    return _importance_score(candidate, product=product) + _lane_fit_bonus(candidate, lane=lane, product=product)


def _lane_fit_bonus(candidate: WebCandidate, lane: str, product: str = "finance") -> int:
    text = " ".join(
        [
            candidate.title.lower(),
            candidate.summary.lower(),
            candidate.category.lower(),
            candidate.india_impact.lower(),
            candidate.why_it_matters.lower(),
        ]
    )
    bonus = 0
    if product == "ai":
        if lane == "ai_news":
            if any(term in text for term in AI_PRODUCT_UPDATE_TERMS):
                bonus += 6
            if any(term in text for term in ("opinion", "recap", "weekly roundup", "for investors", "vibe-coded", "interview")):
                bonus -= 6
        elif lane == "ai_explained":
            if any(term in text for term in ("means", "matters", "pricing", "adoption", "workflow", "enterprise", "policy", "regulation", "launch", "rollout", "billing")):
                bonus += 6
            if any(term in text for term in ("benchmark", "leaderboard", "paper", "opinion", "interview")):
                bonus -= 4
        elif lane == "ai_for_business":
            if any(term in text for term in ("business", "enterprise", "workflow", "cost", "teams", "operators", "founders", "adoption", "productivity", "automation", "subscription", "billing")):
                bonus += 6
            if any(term in text for term in ("book a call", "hire us", "our service", "our product", "investors")):
                bonus -= 6
        return bonus
    if lane == "india_preopen":
        if any(term in text for term in ("gift nifty", "market open", "overnight", "wall street", "rupee", "rbi", "brent", "wti", "yield", "dollar")):
            bonus += 6
        if any(term in text for term in ("market close", "uae equities", "spacex ipo")):
            bonus -= 5
    elif lane == "india_close":
        if any(term in text for term in ("sensex", "nifty", "top movers", "market close", "stocks fell", "stocks rose", "rupee", "bond yield", "oil")):
            bonus += 6
        if any(term in text for term in ("uae equities", "spacex ipo", "space etf", "echo star", "echostar")):
            bonus -= 8
    elif lane == "global_impact":
        if any(term in text for term in ("oil", "brent", "wti", "fed", "treasury", "yield", "dollar", "shipping", "tariff", "sanction", "hormuz", "rupee")):
            bonus += 6
        if any(term in text for term in ("sensex", "nifty close", "egm", "shareholder")):
            bonus -= 5
    return bonus


def _passes_lane_relevance_gate(candidate: WebCandidate, *, lane: str, product: str = "finance") -> bool:
    text = " ".join(
        [
            candidate.title.lower(),
            candidate.summary.lower(),
            candidate.category.lower(),
            candidate.india_impact.lower(),
            candidate.why_it_matters.lower(),
        ]
    )
    if product == "ai":
        ai_text = " ".join(
            [
                candidate.title.lower(),
                candidate.summary.lower(),
                candidate.category.lower(),
            ]
        )
        ai_story_text = " ".join([candidate.title.lower(), candidate.summary.lower()])
        ai_company_signal = any(term in ai_text for term in AI_COMPANY_TERMS)
        unrelated_world_news = any(term in ai_text for term in AI_WORLD_NOISE_TERMS) and not ai_company_signal
        policy_actor_signal = any(term in ai_text for term in AI_POLICY_ACTOR_TERMS)
        source_host = _source_host(candidate.source_url)
        if lane == "ai_news":
            concrete_update = any(term in ai_story_text for term in AI_PRODUCT_UPDATE_TERMS)
            weak_policy_crossover = any(term in ai_story_text for term in AI_POLICY_TERMS) and not concrete_update
            pure_industry_move = any(term in ai_story_text for term in ("expansion", "investment", "funding", "leadership", "executive shuffle")) and not concrete_update
            return (
                _host_in_domains(source_host, AI_PRODUCT_DOMAINS)
                and ai_company_signal
                and concrete_update
                and not weak_policy_crossover
                and not pure_industry_move
                and not unrelated_world_news
            )
        if lane == "ai_explained":
            has_explainable_signal = any(term in ai_story_text for term in AI_PRODUCT_UPDATE_TERMS + AI_POLICY_TERMS + AI_INDUSTRY_MOVE_TERMS)
            return (
                _host_in_domains(source_host, list(dict.fromkeys(AI_PRODUCT_DOMAINS + AI_POLICY_DOMAINS + ("wired.com", "technologyreview.com"))))
                and has_explainable_signal
                and (ai_company_signal or policy_actor_signal or "ai" in ai_story_text or "artificial intelligence" in ai_story_text)
                and not any(term in ai_text for term in ("podcast", "newsletter", "recap", "weekly roundup", "vibe-coded"))
                and not unrelated_world_news
            )
        if lane == "ai_for_business":
            has_business_signal = any(term in ai_story_text for term in ("enterprise", "workflow", "pricing", "billing", "subscription", "developer", "teams", "business", "productivity", "adoption", "automation", "cloud", "datacenter", "expansion", "investment", "deal", "partnership"))
            return (
                _host_in_domains(source_host, list(dict.fromkeys(AI_INDUSTRY_DOMAINS + AI_PRODUCT_DOMAINS)))
                and has_business_signal
                and (ai_company_signal or "ai" in ai_text)
                and not any(term in ai_text for term in ("book a call", "hire us", "newsletter", "podcast", "for investors", "mega-theme"))
                and not unrelated_world_news
            )
        return True
    if lane == "india_preopen":
        blocked = (
            "market close",
            "uae equities",
            "tribal casinos",
            "prediction markets",
            "spacex ipo",
            "space etf",
        )
        return not any(term in text for term in blocked)
    if lane == "india_close":
        if any(
            term in text
            for term in (
                "tribal casinos",
                "prediction markets",
                "spacex ipo",
                "space etf",
                "echo star",
                "echostar",
                "uae equities",
            )
        ):
            return False
        strong_close_signal = any(
            term in text
            for term in (
                "sensex",
                "nifty",
                "market close",
                "market recap",
                "top movers",
                "stocks fell",
                "stocks rose",
                "all sectors",
                "banks led the slide",
                "rupee",
                "bond yield",
                "oil",
                "manufacturing pmi",
                "exports",
                "factory",
            )
        )
        india_context = any(
            term in text
            for term in (
                "india",
                "indian",
                "sensex",
                "nifty",
                "rupee",
                "rbi",
                "bse",
                "nse",
            )
        )
        return strong_close_signal or india_context
    if lane == "global_impact":
        blocked = (
            "egm",
            "shareholder",
            "board meeting",
            "postal ballot",
        )
        return not any(term in text for term in blocked)
    return True


def _passes_public_quality_gate(
    draft_text: str,
    *,
    candidate: WebCandidate | None = None,
    product: str = "finance",
    lane: str | None = None,
) -> bool:
    draft = " ".join(draft_text.split()).strip()
    if len(draft) < 90 or len(draft) > 260:
        return False
    lowered = draft.lower()
    blocked_terms = (
        "risk assets",
        "positioning",
        "treasury books",
        "watchlist",
        "enters watchlist",
        "the bet is",
        "this could",
        "signals",
        "reprices",
    )
    if any(term in lowered for term in blocked_terms):
        return False
    if product == "ai":
        if any(term in lowered for term in ("signals momentum", "reflects momentum", "shows momentum", "ai roundup", "this signals", "this reflects interest")):
            return False
        if any(lowered.endswith(suffix) for suffix in ("...", "the real message is...", "what matters now is...", "watch this...")):
            return False
        if lane == "ai_explained":
            if not any(term in lowered for term in ("means", "matters", "the key shift", "the bigger point", "what changed", "why this matters", "real shift", "takeaway")):
                return False
            if any(term in lowered for term in ("book a call", "hire us", "our service", "our product")):
                return False
        elif lane == "ai_for_business":
            if not any(term in lowered for term in ("business", "operators", "teams", "workflow", "cost", "budget", "adopt", "productivity", "time")):
                return False
            if any(term in lowered for term in ("book a call", "hire us", "our service", "our product", "thought leadership")):
                return False
        else:
            if not any(
                term in lowered
                for term in (
                    "launched",
                    "released",
                    "added",
                    "adds",
                    "cut",
                    "raised",
                    "opened",
                    "approved",
                    "filed",
                    "sued",
                    "partnered",
                    "priced",
                    "expanded",
                    "banned",
                    "required",
                    "charging",
                    "charged",
                    "billing",
                    "bill separately",
                    "pay-as-you-go",
                    "pay extra",
                    "buying",
                    "bought",
                    "acquired",
                    "acquires",
                    "restricting",
                    "restricted",
                    "restricts",
                    "stopped",
                    "stops",
                    "will stop",
                )
            ):
                return False
            if candidate is not None and _requires_numeric_preservation(candidate) and not re.search(r"\d", draft):
                return False
    if lowered.count(";") > 1 or draft.count("||") > 1:
        return False
    return True


def _requires_numeric_preservation(candidate: WebCandidate) -> bool:
    source_text = f"{candidate.title} {candidate.summary}".lower()
    if not re.search(r"\d", source_text):
        return False
    if any(token in source_text for token in ("$", "%", "percent", "million", "billion", "pricing", "price", "cost", "rate limit", "context window", "token")):
        return True
    return False


def _event_type_for_category(category: str, title: str, summary: str, *, product: str = "finance") -> str:
    text = f"{category} {title} {summary}".lower()
    if product == "ai":
        if any(term in text for term in ("policy", "regulation", "copyright", "lawsuit", "antitrust", "ftc", "ai act")):
            return "policy_regulation"
        if any(term in text for term in ("security", "safety issue", "breach", "outage")):
            return "security_incident"
        if any(term in text for term in ("api", "sdk", "pricing", "context window", "developer")):
            return "api_update"
        if any(term in text for term in ("launch", "release", "introduces", "rollout", "tool", "agent", "model")):
            return "model_launch"
        if any(term in text for term in ("partnership", "acquisition", "funding", "enterprise", "datacenter", "chips")):
            return "industry_move"
        return "product_update"
    if any(term in text for term in ("rbi", "sebi", "approval", "regulator", "policy")):
        return "rbi_policy"
    if any(term in text for term in ("oil", "tariff", "rupee", "yield", "rate", "inflation", "geopolitic", "hormuz")):
        return "macro_release"
    if any(term in text for term in ("order", "contract", "project", "wins")):
        return "order_win"
    return "macro_release"


def _infer_category(title: str, summary: str, source_url: str, *, product: str = "finance") -> str:
    text = f"{title} {summary} {source_url}".lower()
    if product == "ai":
        source_host = _source_host(source_url)
        strong_policy_story = any(term in text for term in ("ai act", "copyright", "training data", "export control", "ftc", "white house", "nist", "licensing", "lawsuit", "regulation", "policy"))
        strong_industry_story = any(term in text for term in ("partnership", "acquisition", "funding", "enterprise", "datacenter", "chips", "cloud", "expansion", "investment", "leadership", "hiring"))
        strong_product_story = any(term in text for term in ("model", "api", "pricing", "tool", "agent", "release", "launch", "context window", "feature", "subscription", "billing", "pay-as-you-go"))
        if _host_in_domains(source_host, AI_PRODUCT_DOMAINS + AI_INDUSTRY_DOMAINS + AI_POLICY_DOMAINS):
            if strong_product_story:
                return "product_update"
            if strong_policy_story:
                return "policy_regulation"
            if strong_industry_story:
                return "industry_move"
        if any(term in text for term in ("policy", "regulation", "copyright", "lawsuit", "ai act", "ftc", "export control")):
            return "policy_regulation"
        if any(term in text for term in ("partnership", "acquisition", "funding", "enterprise", "datacenter", "chips", "cloud")):
            return "industry_move"
        if any(term in text for term in ("model", "api", "pricing", "tool", "agent", "release", "launch", "context window")):
            return "product_update"
        if any(term in text for term in ("paper", "benchmark", "eval", "leaderboard", "research")):
            return "research"
        return "industry_move"
    if any(term in text for term in ("rbi", "sebi", "regulator", "buyback", "policy", "approval", "nse", "bse")):
        return "policy_regulation"
    if any(term in text for term in ("rupee", "fx", "dollar", "yield", "bond", "repo", "rate")):
        return "rates_fx"
    if any(term in text for term in ("oil", "crude", "brent", "shipping", "iran", "hormuz", "tariff", "sanction")):
        return "geopolitics"
    if any(term in text for term in ("sensex", "nifty", "wall street", "stocks", "equities", "market close", "market open")):
        return "macro_market"
    if any(term in text for term in ("deposit", "advance", "loan growth", "credit growth", "bank")):
        return "banking_metrics"
    return "company_update"


def _infer_india_impact(title: str, summary: str, category: str, *, product: str = "finance") -> str:
    text = f"{title} {summary}".lower()
    if product == "ai":
        if category == "product_update":
            return "This matters if users, teams, or developers get new models, tools, prices, or limits to work with."
        if category == "industry_move":
            return "This matters because big AI deals and rollouts often signal where money, talent, and product demand are heading."
        if category == "policy_regulation":
            return "This matters because AI rules can shape what companies can ship, how they train models, and what users can access."
        return "This matters if it changes how fast AI products improve or reach more people."
    if category == "rates_fx":
        return "This can quickly affect the rupee, importer costs, bank treasury books and market sentiment in India."
    if category == "policy_regulation":
        return "This can change expectations for Indian markets, regulation-sensitive stocks and investor positioning."
    if category == "geopolitics":
        return "This matters for India through oil, inflation, the rupee, trade costs and overall market risk appetite."
    if category == "banking_metrics":
        return "This matters for Indian lenders, borrowers and investors tracking credit growth and deposit trends."
    if "sensex" in text or "nifty" in text or "wall street" in text:
        return "This can shape risk appetite, sector moves and expectations for Indian equities."
    return "This may matter to Indian markets if it changes sentiment, costs, regulation or company outlook."


def _infer_why_it_matters(title: str, summary: str, category: str, *, product: str = "finance") -> str:
    text = f"{title} {summary}".lower()
    if product == "ai":
        if category == "product_update":
            return "Product changes matter most when they alter capability, price, speed, or access."
        if category == "industry_move":
            return "Industry moves show which AI products and business models are gaining traction."
        if category == "policy_regulation":
            return "Policy moves can reshape AI competition, training data, deployment rules, and product roadmaps."
        return "This is useful if it changes what AI products can do or who can use them."
    if category == "rates_fx":
        return "Currency and rate moves often spill into banks, oil, IT, inflation expectations and foreign flows."
    if category == "policy_regulation":
        return "Policy and regulatory changes can quickly reprice market expectations and sector sentiment."
    if category == "geopolitics":
        return "Global shocks can feed into oil prices, inflation risks and market volatility for India."
    if category == "banking_metrics":
        return "Banking trends help explain how credit demand, liquidity and financial conditions are changing."
    if any(term in text for term in ("sensex", "nifty", "wall street")):
        return "Index moves help frame where risk appetite and sector leadership are heading."
    return "This is useful if it changes the market narrative or affects how investors read the next session."


def _source_name_from_url(url: str) -> str:
    hostname = urllib.parse.urlparse(url).hostname or ""
    hostname = hostname.removeprefix("www.")
    if not hostname:
        return ""
    parts = hostname.split(".")
    if len(parts) >= 2:
        return parts[-2].replace("-", " ").title()
    return hostname.title()


def _source_host(url: str) -> str:
    return (urllib.parse.urlparse(url).hostname or "").lower().removeprefix("www.")


def _host_in_domains(host: str, domains: tuple[str, ...] | list[str]) -> bool:
    return any(host == domain or host.endswith(f".{domain}") for domain in domains)


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


def _topic_family(candidate: WebCandidate, *, product: str) -> str:
    text = " ".join(
        [
            candidate.title.lower(),
            candidate.summary.lower(),
            candidate.category.lower(),
            candidate.india_impact.lower(),
            candidate.why_it_matters.lower(),
        ]
    )
    if product == "ai":
        if any(term in text for term in ("pricing", "api", "context window", "tool", "agent", "launch", "release", "subscription", "feature", "rollout")):
            return "ai_news"
        if any(term in text for term in ("policy", "copyright", "lawsuit", "ai act", "ftc", "white house", "export control", "what it means", "takeaway")):
            return "ai_explained"
        if any(term in text for term in ("funding", "partnership", "acquisition", "enterprise", "chips", "cloud", "datacenter", "deal", "leadership", "executive shuffle", "workflow", "business", "operators", "cost")):
            return "ai_for_business"
        return "ai_news"
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


def _topic_bucket(candidate: WebCandidate, *, product: str) -> str:
    family = _topic_family(candidate, product=product)
    if product == "ai":
        company = _primary_company(candidate)
        return f"{company}|{family}"
    return family


def _cluster_bucket(candidate: WebCandidate, *, product: str) -> str:
    company = _primary_company(candidate)
    if product == "ai":
        event_group = _event_group(candidate)
        return f"{company}|{event_group}|{_slug(candidate.title)[:80]}"
    return _topic_bucket(candidate, product=product)


def _primary_company(candidate: WebCandidate) -> str:
    text = f"{candidate.title} {candidate.summary}".lower()
    for company in ("openai", "anthropic", "google", "deepmind", "meta", "microsoft", "xai", "mistral", "cohere", "perplexity", "hugging face"):
        if company in text:
            return company.replace(" ", "_")
    return "other"


def _event_group(candidate: WebCandidate) -> str:
    text = f"{candidate.title} {candidate.summary} {candidate.category}".lower()
    if any(term in text for term in ("api", "pricing", "developer", "context window", "tool", "agent")):
        return "api_or_tooling"
    if any(term in text for term in ("launch", "release", "model", "rollout")):
        return "launch"
    if any(term in text for term in ("partnership", "acquisition", "funding", "enterprise", "deal", "datacenter", "chips", "cloud")):
        return "industry"
    if any(term in text for term in ("policy", "regulation", "copyright", "lawsuit", "ftc", "ai act", "export control")):
        return "policy"
    return candidate.category or "other"


def _noop_result(run: WebRunDef, *, reason: str) -> WirePipelineResult:
    today = datetime.now(timezone.utc).astimezone(DISPLAY_TZ).strftime("%Y%m%d")
    return WirePipelineResult(
        product=run.product,
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
        raw_payload={"source_family": "web", "lane": run.lane, "product": run.product},
        published_at=None,
        fetch_error=reason,
    )

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
        key="india_preopen",
        source_name="tavily_web_india_preopen",
        lane="india_preopen",
        local_hour=7,
        local_minute=15,
    ),
    WebRunDef(
        key="india_close",
        source_name="tavily_web_india_close",
        lane="india_close",
        local_hour=15,
        local_minute=45,
    ),
    WebRunDef(
        key="global_impact",
        source_name="tavily_web_global_impact",
        lane="global_impact",
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
    if OpenAI is None or not settings.openai_api_key or not settings.tavily_api_key:
        logger.info("Tavily web breaking pipeline skipped: client or key missing")
        return []

    client = OpenAI(api_key=settings.openai_api_key)
    try:
        raw_items = _tavily_lane_results(
            lane=run.lane,
            tavily_api_key=settings.tavily_api_key,
            limit=settings.wire_web_breaking_limit,
            hours=settings.wire_web_breaking_freshness_hours,
        )
    except Exception as exc:
        logger.warning("Tavily web breaking research failed for %s: %s", run.key, exc)
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
                raw_payload={"source_family": "web", "lane": run.lane},
                published_at=None,
                fetch_error=f"{type(exc).__name__}: {exc}",
            )
        ]
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
    for candidate, validation in _select_web_candidates(candidates, lane=run.lane):
        if not _passes_lane_relevance_gate(candidate, lane=run.lane):
            logger.info("Rejected Tavily candidate for lane mismatch: %s", candidate.title)
            continue
        try:
            draft_text = _draft_tweet(client, model=settings.wire_web_breaking_model, candidate=candidate)
        except Exception as exc:
            logger.warning("OpenAI web breaking drafting failed for %s: %s", candidate.title, exc)
            continue
        if not _passes_public_quality_gate(draft_text):
            logger.info("Rejected Tavily draft for public-facing quality: %s", candidate.title)
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
                    "lane": run.lane,
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


def _tavily_lane_results(*, lane: str, tavily_api_key: str, limit: int, hours: int) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for query in _lane_queries(lane):
        payload = _tavily_search(
            query=query,
            tavily_api_key=tavily_api_key,
            max_results=max(6, limit),
            days=max(2, hours // 24 + 1),
            domains=_lane_domains(lane),
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


def _lane_queries(lane: str) -> list[str]:
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


def _lane_domains(lane: str) -> list[str]:
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


def _draft_tweet(client: OpenAI, *, model: str, candidate: WebCandidate) -> str:
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


def _parse_candidate(item: dict[str, Any]) -> WebCandidate | None:
    title = str(item.get("title") or "").strip()
    source_url = str(item.get("source_url") or item.get("url") or "").strip()
    if not title or not source_url:
        return None
    summary = str(item.get("summary") or item.get("content") or "").strip()
    source_name = str(item.get("source_name") or _source_name_from_url(source_url)).strip()
    published_at = str(item.get("published_at") or item.get("published_date") or "").strip()
    category = str(item.get("category") or _infer_category(title, summary, source_url)).strip()
    india_impact = str(item.get("india_impact") or _infer_india_impact(title, summary, category)).strip()
    why_it_matters = str(item.get("why_it_matters") or _infer_why_it_matters(title, summary, category)).strip()
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


def _validate_candidate(candidate: WebCandidate, *, hours: int) -> ValidationResult:
    reasons: list[str] = []
    parsed_time = _parse_published_at(candidate.published_at)
    if parsed_time is not None:
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
            "gift nifty",
            "sensex",
            "nifty",
            "yield",
            "fed",
        )
    ):
        reasons.append("weak_india_relevance")
    if any(term in text for term in ("horoscope", "astrology", "celebrity", "recipe", "cricket", "football")):
        reasons.append("junk_topic")

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


def _select_web_candidates(
    candidates: list[tuple[WebCandidate, ValidationResult]],
    *,
    lane: str,
    max_per_topic: int = 1,
    max_selected: int = 5,
) -> list[tuple[WebCandidate, ValidationResult]]:
    ordered = sorted(
        candidates,
        key=lambda item: (
            _selection_score(item[0], lane=lane),
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
        if len(kept) >= max_selected:
            break
    return kept


def _selection_score(candidate: WebCandidate, *, lane: str) -> int:
    return _importance_score(candidate) + _lane_fit_bonus(candidate, lane=lane)


def _lane_fit_bonus(candidate: WebCandidate, lane: str) -> int:
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


def _passes_lane_relevance_gate(candidate: WebCandidate, *, lane: str) -> bool:
    text = " ".join(
        [
            candidate.title.lower(),
            candidate.summary.lower(),
            candidate.category.lower(),
            candidate.india_impact.lower(),
            candidate.why_it_matters.lower(),
        ]
    )
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


def _passes_public_quality_gate(draft_text: str) -> bool:
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
    if lowered.count(";") > 1 or draft.count("||") > 1:
        return False
    return True


def _event_type_for_category(category: str, title: str, summary: str) -> str:
    text = f"{category} {title} {summary}".lower()
    if any(term in text for term in ("rbi", "sebi", "approval", "regulator", "policy")):
        return "rbi_policy"
    if any(term in text for term in ("oil", "tariff", "rupee", "yield", "rate", "inflation", "geopolitic", "hormuz")):
        return "macro_release"
    if any(term in text for term in ("order", "contract", "project", "wins")):
        return "order_win"
    return "macro_release"


def _infer_category(title: str, summary: str, source_url: str) -> str:
    text = f"{title} {summary} {source_url}".lower()
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


def _infer_india_impact(title: str, summary: str, category: str) -> str:
    text = f"{title} {summary}".lower()
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


def _infer_why_it_matters(title: str, summary: str, category: str) -> str:
    text = f"{title} {summary}".lower()
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
        raw_payload={"source_family": "web", "lane": run.lane},
        published_at=None,
        fetch_error=reason,
    )

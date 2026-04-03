"""Local dry run for Tavily-based breaking finance news.

This script:
1. Uses Tavily with editorial lanes to find India-relevant finance/market news
2. Applies a lightweight freshness/reliability validation gate
3. Uses GPT-5.4 mini to draft tweet-style posts
4. Prints how many would be approved vs sent to review

Nothing is written to the database or posted to X.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://dryrun:dryrun@localhost/dryrun")

from openai import OpenAI

DISPLAY_TZ = ZoneInfo("Asia/Kolkata")
DEFAULT_MODEL = "gpt-5.4-mini"
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
    "apnews.com",
    "ft.com",
    "wsj.com",
    "cnbc.com",
]
RELIABLE_DOMAIN_KEYWORDS = tuple(domain.replace("www.", "") for domain in REPUTABLE_DOMAINS)


@dataclass
class WebCandidate:
    title: str
    summary: str
    source_name: str
    source_url: str
    published_at: str
    category: str
    india_impact: str
    why_it_matters: str


@dataclass
class ValidationResult:
    approved: bool
    reasons: list[str]
    published_at: datetime | None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--openai-key", help="OpenAI API key (overrides env)")
    parser.add_argument("--tavily-key", help="Tavily API key (overrides env)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model for drafting")
    parser.add_argument("--limit", type=int, default=8, help="Max candidates to keep after Tavily retrieval")
    parser.add_argument("--hours", type=int, default=18, help="Freshness window in hours")
    parser.add_argument(
        "--run-window",
        choices=("india_preopen", "india_close", "global_impact"),
        default="india_preopen",
        help="Editorial lane to test",
    )
    return parser.parse_args()


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
    return sorted(merged, key=_tavily_sort_key, reverse=True)[: max(limit * 2, limit)]


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
    blocked_terms = ("horoscope", "astrology", "sports", "entertainment", "lifestyle", "celebrity", "weather", "recipe")
    return any(term in text for term in blocked_terms)


def _draft_tweet(client: OpenAI, *, model: str, candidate: WebCandidate) -> str:
    prompt = f"""
Write one factual finance-market X post in a natural, human-written finance-commentator style.

Rules:
- No hashtags
- No emojis
- No source attribution in the tweet body
- Prefer 120-220 characters when supported by the facts
- Use simple, public-facing language that a general audience can understand
- Explain why it matters in plain English
- Include a second fact, comparison, or market consequence whenever supported by the facts
- Sound like a sharp human market commentator, not a robotic wire bot
- Use natural sentence rhythm, not article-summary language
- Prefer one clear takeaway and one clear reason to care
- It should feel like a person explaining the market, not a newsroom headline
- Keep important numbers, percentages, prices and comparisons whenever they are available
- If there is a strong number, put it early
- If there is a strong market implication, include it in the second clause
- Avoid unexplained jargon unless it is very common
- Prefer everyday words over insider terms like risk assets, treasury books, PMI, or positioning unless they are clearly explained
- Avoid stiff transitions like "That means", "This could", "The bet is", "signals", or "watchlist"
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
            "sensex",
            "nifty",
            "gift nifty",
            "fed",
            "yield",
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


def _print_candidate(index: int, candidate: WebCandidate, validation: ValidationResult, draft: str | None) -> None:
    status = "APPROVED" if validation.approved else f"REVIEW ({', '.join(validation.reasons)})"
    published = (
        validation.published_at.astimezone(DISPLAY_TZ).strftime("%Y-%m-%d %H:%M IST")
        if validation.published_at
        else "unknown time"
    )
    print("-" * 70)
    print(f"#{index}  {status}")
    print(f"Title:     {candidate.title}")
    print(f"Category:  {candidate.category or '-'}")
    print(f"Published: {published}")
    print(f"Source:    {candidate.source_name or '-'}")
    print(f"URL:       {candidate.source_url}")
    print(f"Impact:    {candidate.india_impact or '-'}")
    print(f"Why:       {candidate.why_it_matters or '-'}")
    if draft:
        print()
        print(f"Draft:     {draft}")


def main() -> None:
    args = _parse_args()
    if args.openai_key:
        os.environ["OPENAI_API_KEY"] = args.openai_key
    if args.tavily_key:
        os.environ["TAVILY_API_KEY"] = args.tavily_key

    openai_key = os.getenv("OPENAI_API_KEY")
    tavily_key = os.getenv("TAVILY_API_KEY")
    if not openai_key:
        raise SystemExit("OPENAI_API_KEY is required. Pass --openai-key or export it in the shell.")
    if not tavily_key:
        raise SystemExit("TAVILY_API_KEY is required. Pass --tavily-key or export it in the shell.")

    client = OpenAI(api_key=openai_key)

    now_local = datetime.now(timezone.utc).astimezone(DISPLAY_TZ)
    print(f"\nWeb Breaking Dry Run - {now_local.strftime('%Y-%m-%d %H:%M IST')}")
    print(f"Model: {args.model}")
    print(f"Window: {args.run_window}")
    print(f"Freshness gate: <= {args.hours}h")
    print()

    raw_items = _tavily_lane_results(
        lane=args.run_window,
        tavily_api_key=tavily_key,
        limit=args.limit,
        hours=args.hours,
    )
    candidates = [candidate for item in raw_items if (candidate := _parse_candidate(item))]

    validations: list[tuple[WebCandidate, ValidationResult]] = []
    for index, candidate in enumerate(candidates, 1):
        validation = _validate_candidate(candidate, hours=args.hours)
        validations.append((candidate, validation))
        if not validation.approved:
            _print_candidate(index, candidate, validation, None)
            print()

    approved_candidates = _dedupe_web_candidates(
        [(candidate, validation) for candidate, validation in validations if validation.approved]
    )
    approved = 0
    for offset, (candidate, validation) in enumerate(approved_candidates, 1):
        draft = _draft_tweet(client, model=args.model, candidate=candidate)
        approved += 1
        _print_candidate(offset, candidate, validation, draft)
        print()

    print("-" * 70)
    print(f"Total candidates: {len(candidates)}")
    print(f"Approved drafts:  {approved}")
    print(f"Review only:      {len(candidates) - approved}")
    print("Nothing was written to the database or posted to X.")


if __name__ == "__main__":
    main()

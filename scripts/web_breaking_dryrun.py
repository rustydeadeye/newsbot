"""Local dry run for OpenAI web-search based breaking finance news.

This script:
1. Uses OpenAI Responses + web search to find India-relevant finance/market news
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
]
RELIABLE_DOMAIN_KEYWORDS = tuple(
    domain.replace("www.", "")
    for domain in REPUTABLE_DOMAINS
)


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
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model for both research and drafting")
    parser.add_argument("--limit", type=int, default=8, help="Max candidates to request from research run")
    parser.add_argument("--hours", type=int, default=18, help="Freshness window in hours")
    parser.add_argument(
        "--run-window",
        choices=("preopen", "night", "general"),
        default="general",
        help="Prompt shape for the research run",
    )
    return parser.parse_args()


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

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is required. Pass --openai-key or export it in the shell.")

    client = OpenAI(api_key=api_key)

    now_local = datetime.now(timezone.utc).astimezone(DISPLAY_TZ)
    print(f"\nWeb Breaking Dry Run - {now_local.strftime('%Y-%m-%d %H:%M IST')}")
    print(f"Model: {args.model}")
    print(f"Window: {args.run_window}")
    print(f"Freshness gate: <= {args.hours}h")
    print()

    payload = _response_json(
        client,
        model=args.model,
        prompt=_build_research_prompt(args.limit, args.hours, args.run_window),
        allow_domains=REPUTABLE_DOMAINS,
    )
    raw_items = payload.get("items") or []
    candidates = [candidate for item in raw_items if (candidate := _parse_candidate(item))]

    validations: list[tuple[WebCandidate, ValidationResult]] = []
    for index, candidate in enumerate(candidates, 1):
        validation = _validate_candidate(candidate, hours=args.hours)
        validations.append((candidate, validation))
        draft = None
        if not validation.approved:
            _print_candidate(index, candidate, validation, draft)
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

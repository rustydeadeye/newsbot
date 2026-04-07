from __future__ import annotations

import html
import logging
import textwrap
from dataclasses import dataclass
from datetime import datetime, timezone
import re
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.models.source import Source, SourceItem
from app.services.drafting.service import DraftingService
from app.services.ingestion.base import FetchedItem
from app.services.normalization.dedupe import make_dedupe_key
from app.services.normalization.extractors import extract_facts
from app.services.scoring import SOURCE_PRIORITY, score_event
from app.wire_feed.sources import WireSourceDef, get_ai_source_cap

logger = logging.getLogger(__name__)
WIRE_AUTO_POST_THRESHOLD = 80
_DISPLAY_TZ = ZoneInfo("Asia/Kolkata")
AI_CONTENT_LANES = ("ai_news", "ai_explained", "ai_for_business")
AI_LANE_MAX_AGE_HOURS = {
    "ai_news": 48,
    "ai_explained": 24 * 7,
    "ai_for_business": 24 * 14,
}

_LOW_SIGNAL_WIRE_TERMS = (
    "shareholding disclosure",
    "shareholding details",
    "promoter acquires",
    "promoter increases stake",
    "promoter reduces stake",
    "promoter stake drops",
    "promoter pledged",
    "promoter pledges",
    "pledge disclosure",
    "pledged shares",
    "special window",
    "physical securities",
    "share transfer",
    "postal ballot",
    "e-voting",
    "investor meet",
    "investor meeting",
    "investor conference",
    "board meet",
    "board meeting",
    "company secretary",
    "independent director",
    "compliance certificate",
    "sebi compliance certificate",
    "non-large corporate",
    "non-lc status",
    "non-lce status",
    "price movement query",
    "price movement inquiry",
    "record date for share allotment",
)

_LOW_SIGNAL_MANAGEMENT_TERMS = (
    "appoints",
    "appointed",
    "resigns",
    "retires",
    "superannuates",
    "steps down",
    "completes tenure",
    "promotes",
    "new company secretary",
    "human resources",
    "chief commercial officer",
    "chief strategy officer",
)

_MARKET_IMPACT_BLOCK_TERMS = (
    "appeal no.",
    "appeal filed by",
    "order for compliance",
    "recovery officer",
    "release of attachment",
    "prohibitory order",
    "files annual disclosure",
    "annual disclosure under sebi regulations",
    "regulation 74(5)",
    "demat certificate",
    "demat report",
    "non-applicability of lc framework",
    "not a large corporate",
    "large corporate disclosure",
    "insider trading disclosure form",
    "share transfer notice",
    "iepf transfer notice",
    "price movement to bse",
    "clarifies price movement",
)

_MARKET_IMPACT_KEEP_TERMS = (
    "gross advances",
    "total deposits",
    "advances up",
    "deposits up",
    "business growth",
    "loan growth",
    "credit growth",
    "bank loans rise",
    "bank total deposits",
    "bank gross advances",
    "sales",
    "volume",
    "production",
    "offtake",
    "pre-sales",
    "deposits",
    "advances",
    "order",
    "contract",
    "project",
    "wins",
    "approval",
    "approved",
    "rbi approval",
    "stake purchase",
    "acquires",
    "acquisition",
    "milestone",
    "capacity",
    "commissioning",
    "commercial production",
    "expansion",
    "tax demand",
    "gst demand",
    "penalty",
    "default",
    "downgraded",
    "rating downgraded",
    "tariff",
    "crude",
    "oil futures",
    "oil",
    "fuel",
    "petrol",
    "diesel",
    "lpg",
    "rupee",
    "interest rate",
    "repo",
    "inflation",
    "tolls",
    "shipping",
    "strait of hormuz",
    "foreign minister",
    "deputy foreign minister",
)

_MARKET_FIRST_EVENT_TYPES = {
    "rbi_policy",
    "rbi_penalty",
    "macro_release",
    "order_win",
    "default_fraud",
}


@dataclass
class WirePipelineResult:
    external_id: str
    source_name: str
    source_family: str
    title: str
    event_type: str
    dedupe_key: str
    subject_key: str | None
    ticker: str | None
    importance_score: int
    confidence_score: float
    would_auto_post: bool
    review_reason: str | None
    draft_text: str
    safety_flags: dict
    raw_payload: dict
    published_at: datetime | None
    product: str = "finance"
    fetch_error: str | None = None


def fetch_and_process(source_def: WireSourceDef, drafting: DraftingService) -> list[WirePipelineResult]:
    if source_def.product == "ai":
        return _fetch_and_process_ai(source_def, drafting)
    source = Source(name=source_def.name, type=source_def.type, base_url=source_def.url)
    adapter = source_def.adapter_cls(source)
    try:
        items = adapter.fetch()
    except Exception as exc:
        return [
            WirePipelineResult(
                product=source_def.product,
                external_id="",
                source_name=source_def.name,
                source_family="base",
                title="",
                event_type="",
                dedupe_key="",
                subject_key=None,
                ticker=None,
                importance_score=0,
                confidence_score=0,
                would_auto_post=False,
                review_reason=None,
                draft_text="",
                safety_flags={},
                raw_payload={"source_family": "base"},
                published_at=None,
                fetch_error=f"{type(exc).__name__}: {exc}",
            )
        ]

    results: list[WirePipelineResult] = []
    for fetched in items:
        source_item = _fake_source_item(fetched)
        facts = extract_facts(source, source_item)
        if _should_drop_wire_candidate(facts):
            continue
        importance = score_event(
            source_def.name,
            facts["event_class"],
            facts.get("ticker"),
            headline=facts.get("headline"),
            body_text=facts.get("article_text"),
            category=facts.get("category"),
            sub_category=facts.get("sub_category"),
            wire_facts=facts.get("wire_facts"),
        )
        fallback_confidence = 0.95 if source_def.name in SOURCE_PRIORITY else 0.70
        event = _fake_event(facts, importance, fallback_confidence)
        draft = drafting.make_draft_post(event)
        confidence = draft.safety_flags.get("ai_confidence") or fallback_confidence
        reason = _review_reason(importance, confidence, draft.safety_flags)
        results.append(
            WirePipelineResult(
                product=source_def.product,
                external_id=fetched.external_id,
                source_name=source_def.name,
                source_family="base",
                title=fetched.title or "",
                event_type=facts["event_class"],
                dedupe_key=make_dedupe_key(
                    event_type=facts["event_class"],
                    ticker=facts.get("ticker"),
                    entity_name=facts.get("company"),
                    occurred_at=fetched.published_at,
                    key_number=facts.get("subject_key"),
                ),
                subject_key=facts.get("subject_key"),
                ticker=facts.get("ticker"),
                importance_score=importance,
                confidence_score=confidence,
                would_auto_post=reason is None,
                review_reason=reason,
                draft_text=draft.draft_text,
                safety_flags=draft.safety_flags,
                raw_payload={
                    "source_family": "base",
                    "product": source_def.product,
                    "subject_key": facts.get("subject_key"),
                    "safety_flags": draft.safety_flags,
                    "category": facts.get("category"),
                    "sub_category": facts.get("sub_category"),
                    "wire_facts": facts.get("wire_facts"),
                },
                published_at=fetched.published_at,
            )
        )
    return _apply_diversity_adjustment(_dedupe_results(results))


def generate_ai_evergreen_backlog_results(drafting: DraftingService, *, limit: int = 6) -> list[WirePipelineResult]:
    shadow_mode = True
    try:
        from app.core.config import get_settings

        shadow_mode = get_settings().ai_shadow_mode
    except Exception:
        shadow_mode = True
    provisional: list[WirePipelineResult] = []
    lane_texts_by_seed: dict[str, dict[str, str]] = {}
    for index, item in enumerate(_AI_EVERGREEN_BACKLOG[:limit], start=1):
        facts = _evergreen_ai_facts(item)
        seed_key = str(facts["subject_key"])
        story_cluster = _ai_story_cluster(facts)
        lane_texts = lane_texts_by_seed.setdefault(seed_key, {})
        for lane in _eligible_ai_lanes(facts):
            draft_text, safety_flags, confidence = drafting.build_ai_lane_post(facts, lane)
            reason = _review_reason(84, confidence, safety_flags)
            band, readiness_reason = ai_readiness_assessment(
                importance_score=84 + _ai_lane_importance_bonus(lane),
                confidence_score=confidence,
                draft_text=draft_text,
                title=str(facts.get("headline") or ""),
                body_text=str(facts.get("article_text") or ""),
                event_type=str(facts.get("event_class") or ""),
                review_reason=reason,
                lane=lane,
            )
            if band == "C":
                continue
            if _is_duplicate_ai_lane_text(lane_texts, draft_text):
                continue
            lane_texts[lane] = draft_text
            provisional.append(
                WirePipelineResult(
                    product="ai",
                    external_id=f"evergreen:{index}:{lane}",
                    source_name="ai_evergreen_backlog",
                    source_family="base",
                    title=str(facts["headline"]),
                    event_type=str(facts["event_class"]),
                    dedupe_key=f"ai|{lane}|evergreen|{seed_key}",
                    subject_key=seed_key,
                    ticker=None,
                    importance_score=84 + _ai_lane_importance_bonus(lane),
                    confidence_score=confidence,
                    would_auto_post=False,
                    review_reason=None,
                    draft_text=draft_text,
                    safety_flags={**safety_flags, "quality_band": band, "shadow_mode": shadow_mode, "ai_lane": lane},
                    raw_payload={
                        "source_family": "base",
                        "product": "ai",
                        "shadow_mode": shadow_mode,
                        "quality_band": band,
                        "readiness_reason": readiness_reason,
                        "subject_key": seed_key,
                        "seed_key": seed_key,
                        "parent_seed_key": seed_key,
                        "seed_source_name": "ai_evergreen_backlog",
                        "seed_source_family": "base",
                        "seed_family": "evergreen_backlog",
                        "seed_age_bucket": "evergreen",
                        "is_evergreen": True,
                        "framework_id": str(facts.get("framework_id") or ""),
                        "angle_hint": str(facts.get("angle_hint") or ""),
                        "company": facts["company"],
                        "event_group": _ai_event_group(str(facts["event_class"]), str(facts.get("headline") or ""), str(facts.get("article_text") or "")),
                        "story_cluster": story_cluster,
                        "topic_family": lane,
                        "lane": lane,
                        "article_text": facts["article_text"],
                        "category": facts["category"],
                        "source_label": facts["source_label"],
                        "source_url": facts["source_url"],
                        "published_at": facts["published_at"],
                        "topic_tags": facts["topic_tags"],
                        "is_official": facts["is_official"],
                        "is_recent": facts["is_recent"],
                        "is_product_update": facts["is_product_update"],
                        "is_business_relevant": facts["is_business_relevant"],
                        "is_explainer_friendly": facts["is_explainer_friendly"],
                        "seed_facts": _instagram_seed_facts(facts, source_name="ai_evergreen_backlog", source_family="base"),
                    },
                    published_at=None,
                )
            )
    return _apply_diversity_adjustment(_dedupe_results(provisional))


def summarize_results(results: list[WirePipelineResult], limit: int = 10) -> str:
    errors = [result for result in results if result.fetch_error]
    successful = [result for result in results if not result.fetch_error]
    if errors and not successful:
        return "\n".join(result.fetch_error or "Unknown fetch error" for result in errors)

    ordered = sorted(successful, key=lambda result: result.importance_score, reverse=True)
    total_auto = sum(1 for result in ordered if result.would_auto_post)
    lines = [
        f"Total: {len(ordered)} items — {total_auto} would auto-post, {len(ordered) - total_auto} would go to review",
        f"Showing top {min(limit, len(ordered))} by importance score:",
    ]
    for index, result in enumerate(ordered[:limit], 1):
        status = "AUTO-POST" if result.would_auto_post else f"REVIEW ({result.review_reason})"
        bar = "#" * (result.importance_score // 10) + "." * (10 - result.importance_score // 10)
        pub = result.published_at.astimezone(_DISPLAY_TZ).strftime("%Y-%m-%d %H:%M IST") if result.published_at else "no date"
        lines.extend(
            [
                "",
                "-" * 70,
                f"  #{index:<3}  [{result.source_name}]  {pub}",
                f"  Title:  {textwrap.shorten(result.title, 65)}",
                f"  Type:   {result.event_type:<20}  Ticker: {result.ticker or '-'}",
                f"  Score:  {bar} {result.importance_score}/100   Confidence: {result.confidence_score:.0%}",
                f"  Status: {status}",
                "",
            ]
        )
        for wrapped in textwrap.wrap(result.draft_text, width=68):
            lines.append(f"    {wrapped}")
    remaining = len(ordered) - min(limit, len(ordered))
    if remaining > 0:
        lines.extend(["", f"  ... {remaining} more items not shown"])
    return "\n".join(lines)


def _fake_event(facts: dict, importance: int, confidence: float) -> SimpleNamespace:
    return SimpleNamespace(
        id=None,
        summary_facts=facts,
        importance_score=importance,
        confidence_score=confidence,
        event_type=facts["event_class"],
    )


def _fake_source_item(fetched: FetchedItem, source_id: int = 1) -> SourceItem:
    return SourceItem(
        source_id=source_id,
        external_id=fetched.external_id,
        url=fetched.url,
        title=fetched.title,
        published_at=fetched.published_at,
        raw_payload=fetched.raw_payload,
        checksum="wire-dryrun",
    )


def _review_reason(importance: int, confidence: float, safety_flags: dict) -> str | None:
    if safety_flags.get("needs_review"):
        return "blocked_phrase"
    if importance < WIRE_AUTO_POST_THRESHOLD:
        return f"score={importance} below threshold={WIRE_AUTO_POST_THRESHOLD}"
    if confidence < 0.85:
        return f"low_confidence={confidence:.2f}"
    return None


def _dedupe_results(results: list[WirePipelineResult]) -> list[WirePipelineResult]:
    deduped: dict[str, WirePipelineResult] = {}
    for result in results:
        dedupe_key = result.dedupe_key
        current = deduped.get(dedupe_key)
        if current is None or _prefer_result(result, current):
            deduped[dedupe_key] = result
    return list(deduped.values())


def _prefer_result(candidate: WirePipelineResult, existing: WirePipelineResult) -> bool:
    candidate_date = candidate.published_at or datetime.min.replace(tzinfo=timezone.utc)
    existing_date = existing.published_at or datetime.min.replace(tzinfo=timezone.utc)
    if candidate_date != existing_date:
        return candidate_date > existing_date
    return candidate.importance_score > existing.importance_score


def _apply_diversity_adjustment(results: list[WirePipelineResult]) -> list[WirePipelineResult]:
    ordered = sorted(
        results,
        key=lambda result: (
            result.importance_score,
            result.published_at or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )
    family_counts: dict[str, int] = {}
    adjusted: list[WirePipelineResult] = []
    for result in ordered:
        family = _result_family(result)
        seen = family_counts.get(family, 0)
        penalty = min(seen * 6, 18)
        adjusted.append(
            WirePipelineResult(
                product=result.product,
                external_id=result.external_id,
                source_name=result.source_name,
                source_family=result.source_family,
                title=result.title,
                event_type=result.event_type,
                dedupe_key=result.dedupe_key,
                subject_key=result.subject_key,
                ticker=result.ticker,
                importance_score=max(result.importance_score - penalty, 0),
                confidence_score=result.confidence_score,
                would_auto_post=result.would_auto_post,
                review_reason=result.review_reason,
                draft_text=result.draft_text,
                safety_flags=result.safety_flags,
                raw_payload=result.raw_payload,
                published_at=result.published_at,
                fetch_error=result.fetch_error,
            )
        )
        family_counts[family] = seen + 1
    return adjusted


def _result_family(result: WirePipelineResult) -> str:
    if result.product == "ai":
        lane = str((result.raw_payload or {}).get("lane") or "")
        if lane in AI_CONTENT_LANES:
            return lane
        return "ai_other"
    combined = f"{result.title} {result.draft_text}".lower()

    if any(term in combined for term in ("gross advances", "total deposits", "total business", "loan growth", "deposits at", "advances up")):
        return "banking_metrics"
    if any(term in combined for term in ("oil futures", "tariff", "hormuz", "crude", "rupee", "fuel", "shipping", "tolls")):
        return "macro_market"
    if any(term in combined for term in ("tax demand", "gst demand", "default", "penalty")) or result.event_type == "default_fraud":
        return "tax_penalty_default"
    if any(term in combined for term in ("order worth", "contract worth", "wins", "secures", "project")) or result.event_type == "order_win":
        return "orders_contracts"
    if any(term in combined for term in ("sales", "production", "offtake", "pre-sales", "turnover", "total business")):
        return "company_business_metrics"
    if any(term in combined for term in ("approval", "consent to operate", "trial ops", "rbi approval")):
        return "regulatory_approvals"
    if any(term in combined for term in ("stake", "investment", "warrants", "acquires", "deposits rs")):
        return "deals_stakes"
    return result.event_type or "other"


def _should_drop_wire_candidate(facts: dict) -> bool:
    event_type = str(facts.get("event_class") or "")
    headline = str(facts.get("headline") or "")
    article_text = str(facts.get("article_text") or "")
    combined = f"{headline} {article_text}".lower()
    wire_facts = facts.get("wire_facts") or {}
    wire_kind = str(wire_facts.get("kind") or "")

    if any(term in combined for term in _LOW_SIGNAL_WIRE_TERMS):
        return True

    if event_type == "management_change" and any(term in combined for term in _LOW_SIGNAL_MANAGEMENT_TERMS):
        return True

    if any(term in combined for term in _MARKET_IMPACT_BLOCK_TERMS):
        return True

    if event_type == "general_update" and any(
        term in combined
        for term in (
            "opens special window",
            "publishes hindi notice",
            "publishes newspaper notice",
            "files regulatory disclosure",
            "submits regulatory certificate",
            "responds to bse price movement",
            "record date",
            "appoints rta",
            "grants stock options",
            "esop shares",
            "relocates registered office",
        )
    ):
        return True

    if event_type in _MARKET_FIRST_EVENT_TYPES:
        return False

    if wire_kind in {"sales_update", "production_update", "offtake_update", "order_win", "tax_demand", "outlook_update"}:
        return False

    if event_type == "sebi_enforcement":
        # Keep only clearly market-relevant enforcement items such as penalties/defaults,
        # and drop procedural appeal/compliance notices.
        return not any(term in combined for term in ("penalty", "tax demand", "gst demand", "default", "attachment", "auction"))

    if event_type == "fundraise":
        # Keep only material capital or ownership actions that look market-relevant.
        return not any(term in combined for term in ("open offer", "stake", "buy up to", "approval", "issue size", "fund raise", "fundraise"))

    if event_type in {"earnings", "acquisition", "general_update"}:
        if not any(term in combined for term in _MARKET_IMPACT_KEEP_TERMS):
            return True
        if "results filed" in combined or "q4/fy results filed" in combined or "q1 results filed" in combined:
            return True

    return False


_AI_LAUNCH_TERMS = (
    "launch",
    "launched",
    "releases",
    "released",
    "unveils",
    "unveiled",
    "introduces",
    "introduced",
    "rolls out",
    "rolled out",
    "debuts",
    "debut",
    "available now",
)
_AI_API_TERMS = (
    "api",
    "sdk",
    "pricing",
    "price cut",
    "rate limit",
    "context window",
    "developer",
    "endpoint",
    "fine-tuning",
    "fine tuning",
    "tool calling",
    "agent",
)
_AI_POLICY_TERMS = (
    "eu ai act",
    "policy",
    "regulation",
    "regulator",
    "white house",
    "copyright",
    "lawsuit",
    "ftc",
    "antitrust",
    "export control",
    "safety institute",
)
_AI_INDUSTRY_TERMS = (
    "partnership",
    "acquisition",
    "funding",
    "raised",
    "valuation",
    "enterprise",
    "datacenter",
    "chips",
    "cloud",
    "deal",
)
_AI_RESEARCH_TERMS = (
    "paper",
    "benchmark",
    "eval",
    "evaluation",
    "leaderboard",
    "arxiv",
    "research",
)
_AI_BLOCK_TERMS = (
    "podcast",
    "webinar",
    "opinion",
    "interview",
    "what is ai",
    "how to use chatgpt",
    "best prompts",
    "roundup",
    "weekly recap",
)
_AI_MARKETING_TERMS = (
    "behind the scenes",
    "for teens",
    "community",
    "researchers",
    "responsible ai",
    "our approach",
    "our mission",
    "culture",
    "fellows",
    "residency",
    "scholarship",
    "education",
    "podcast",
    "event",
)
_AI_CONCRETE_KEEP_TERMS = (
    "launch",
    "released",
    "release",
    "api",
    "pricing",
    "price",
    "available",
    "rollout",
    "tool",
    "model",
    "agent",
    "context window",
    "developer",
    "partnership",
    "acquisition",
    "funding",
    "enterprise",
    "lawsuit",
    "regulation",
    "copyright",
    "export control",
    "ban",
    "approved",
    "cut",
)
_AI_COMPANY_TERMS = (
    "openai",
    "anthropic",
    "google",
    "deepmind",
    "meta",
    "microsoft",
    "azure",
    "xai",
    "mistral",
    "cohere",
    "perplexity",
    "hugging face",
)

_AI_EVERGREEN_BACKLOG: tuple[dict[str, str | list[str]], ...] = (
    {
        "seed_key": "evergreen|workflow_before_tools",
        "title": "Most teams do not need more AI tools",
        "summary": "The real bottleneck is usually one broken workflow, not a lack of AI products. Fix the repeated handoff or reporting task first, then add AI where it removes friction.",
        "company": "AI",
        "event_class": "business_pattern",
        "topic_tags": ["workflow", "adoption", "operators"],
        "angle_hint": "common_mistake_to_better_way",
    },
    {
        "seed_key": "evergreen|copilot_sprawl",
        "title": "AI sprawl is becoming an operations problem",
        "summary": "Teams keep adding copilots, agents, and model subscriptions without deciding where each one fits. The result is tool sprawl, duplicated spend, and lower trust.",
        "company": "AI",
        "event_class": "business_pattern",
        "topic_tags": ["tool_sprawl", "cost", "workflow"],
        "angle_hint": "tool_hype_to_operator_reality",
    },
    {
        "seed_key": "evergreen|evaluation_guardrails",
        "title": "Most AI projects fail before model quality matters",
        "summary": "The first breakpoints are usually evaluation, approvals, and trust. Teams often learn too late that a stronger model does not solve weak review or guardrail design.",
        "company": "AI",
        "event_class": "adoption_pattern",
        "topic_tags": ["trust", "guardrails", "evaluation"],
        "angle_hint": "headline_to_deeper_meaning",
    },
    {
        "seed_key": "evergreen|model_choice_tradeoff",
        "title": "Model choice is usually a workflow tradeoff",
        "summary": "Most teams should choose models based on latency, cost, and reliability inside the workflow, not on benchmark bragging rights alone.",
        "company": "AI",
        "event_class": "adoption_pattern",
        "topic_tags": ["model_selection", "cost", "latency", "workflow"],
        "angle_hint": "what_people_think_vs_reality",
    },
)


def _fetch_and_process_ai(source_def: WireSourceDef, drafting: DraftingService) -> list[WirePipelineResult]:
    shadow_mode = True
    try:
        from app.core.config import get_settings

        shadow_mode = get_settings().ai_shadow_mode
    except Exception:
        shadow_mode = True
    source = Source(name=source_def.name, type=source_def.type, base_url=source_def.url)
    adapter = source_def.adapter_cls(source)
    try:
        items = adapter.fetch()
    except Exception as exc:
        return [
            WirePipelineResult(
                product="ai",
                external_id="",
                source_name=source_def.name,
                source_family="base",
                title="",
                event_type="product_update",
                dedupe_key="",
                subject_key=None,
                ticker=None,
                importance_score=0,
                confidence_score=0,
                would_auto_post=False,
                review_reason=None,
                draft_text="",
                safety_flags={},
                raw_payload={"source_family": "base", "product": "ai"},
                published_at=None,
                fetch_error=f"{type(exc).__name__}: {exc}",
            )
        ]

    source_cap = get_ai_source_cap(source_def.name)
    inspected = 0
    filtered = 0
    band_counts = {"A": 0, "B": 0, "C": 0}
    skip_reasons: dict[str, int] = {}
    provisional: list[WirePipelineResult] = []
    for fetched in items[: max(source_cap * 4, source_cap)]:
        inspected += 1
        facts = _extract_ai_facts(source_def.name, fetched)
        drop_reason = _should_drop_ai_candidate(facts)
        if drop_reason:
            filtered += 1
            skip_reasons[drop_reason] = skip_reasons.get(drop_reason, 0) + 1
            continue
        importance = _score_ai_facts(facts)
        seed_key = str(facts["subject_key"])
        seed_story_cluster = _ai_story_cluster(facts)
        eligible_lanes = _eligible_ai_lanes(facts)
        lane_texts: dict[str, str] = {}
        for lane in eligible_lanes:
            draft_text, safety_flags, confidence = drafting.build_ai_lane_post(facts, lane)
            reason = _review_reason(importance, confidence, safety_flags)
            band, readiness_reason = ai_readiness_assessment(
                importance_score=importance,
                confidence_score=confidence,
                draft_text=draft_text,
                title=str(facts.get("headline") or ""),
                body_text=str(facts.get("article_text") or ""),
                event_type=str(facts.get("event_class") or ""),
                review_reason=reason,
                lane=lane,
            )
            band_counts[band] = band_counts.get(band, 0) + 1
            if band == "C":
                skip_reasons[readiness_reason] = skip_reasons.get(readiness_reason, 0) + 1
                continue
            if _is_duplicate_ai_lane_text(lane_texts, draft_text):
                skip_reasons["duplicate_lane_angle"] = skip_reasons.get("duplicate_lane_angle", 0) + 1
                continue
            lane_texts[lane] = draft_text
            provisional.append(
                WirePipelineResult(
                    product="ai",
                    external_id=f"{fetched.external_id}:{lane}",
                    source_name=source_def.name,
                    source_family="base",
                    title=fetched.title or "",
                    event_type=str(facts["event_class"]),
                    dedupe_key=f"ai|{lane}|{facts['event_class']}|{seed_key}",
                    subject_key=seed_key,
                    ticker=None,
                    importance_score=importance + _ai_lane_importance_bonus(lane),
                    confidence_score=confidence,
                    would_auto_post=False,
                    review_reason=None,
                    draft_text=draft_text,
                    safety_flags={**safety_flags, "quality_band": band, "shadow_mode": shadow_mode, "ai_lane": lane},
                    raw_payload={
                        "source_family": "base",
                        "product": "ai",
                        "shadow_mode": shadow_mode,
                        "quality_band": band,
                        "readiness_reason": readiness_reason,
                        "subject_key": seed_key,
                        "seed_key": seed_key,
                        "parent_seed_key": seed_key,
                        "seed_source_name": source_def.name,
                        "seed_source_family": "base",
                        "seed_family": str(facts.get("seed_family") or "fresh_news"),
                        "seed_age_bucket": str(facts.get("seed_age_bucket") or "current"),
                        "is_evergreen": bool(facts.get("is_evergreen")),
                        "framework_id": _framework_for_lane(lane, str(facts.get("event_class") or ""), str(facts.get("combined_text") or "")),
                        "angle_hint": str(facts.get("angle_hint") or ""),
                        "company": facts["company"],
                        "event_group": _ai_event_group(str(facts["event_class"]), str(facts.get("headline") or ""), str(facts.get("article_text") or "")),
                        "story_cluster": seed_story_cluster,
                        "topic_family": lane,
                        "lane": lane,
                        "article_text": facts["article_text"],
                        "category": facts["category"],
                        "source_label": facts["source_label"],
                        "source_url": facts["source_url"],
                        "published_at": facts["published_at"],
                        "topic_tags": facts["topic_tags"],
                        "is_official": facts["is_official"],
                        "is_recent": facts["is_recent"],
                        "is_product_update": facts["is_product_update"],
                        "is_business_relevant": facts["is_business_relevant"],
                        "is_explainer_friendly": facts["is_explainer_friendly"],
                        "seed_facts": _instagram_seed_facts(facts, source_name=source_def.name, source_family="base"),
                    },
                    published_at=fetched.published_at,
                )
            )
    results = _apply_diversity_adjustment(_dedupe_results(provisional))
    results = sorted(results, key=lambda result: (_ai_band_rank(str((result.raw_payload or {}).get("quality_band") or "C")), result.importance_score), reverse=True)[:source_cap]
    logger.info(
        "AI base source processed: source=%s raw=%s filtered=%s kept=%s bands=%s skips=%s",
        source_def.name,
        inspected,
        filtered,
        len(results),
        band_counts,
        skip_reasons,
    )
    return results


def _extract_ai_facts(source_name: str, fetched: FetchedItem) -> dict:
    title = (fetched.title or "").strip()
    summary = " ".join(str(fetched.raw_payload.get(key) or "") for key in ("summary", "description", "content", "text")).strip()
    summary = _clean_ai_text(summary)
    article_text = " ".join(part for part in [title, summary] if part).strip()
    company = _ai_company_from_source(source_name, title)
    event_class = _classify_ai_event(title, summary)
    category = _ai_category(event_class)
    subject_key = re.sub(r"[^a-z0-9]+", "-", f"{company}-{title}".lower()).strip("-")[:140]
    combined_text = f"{title} {summary}".strip()
    topic_tags = _ai_topic_tags(event_class, combined_text)
    is_official = source_name in {"openai_news", "google_ai_blog", "huggingface_blog"}
    age_hours = _age_hours(fetched.published_at)
    news_fresh = _is_recent_ai_item(fetched.published_at, hours=AI_LANE_MAX_AGE_HOURS["ai_news"])
    explained_fresh = _is_recent_ai_item(fetched.published_at, hours=AI_LANE_MAX_AGE_HOURS["ai_explained"])
    business_fresh = _is_recent_ai_item(fetched.published_at, hours=AI_LANE_MAX_AGE_HOURS["ai_for_business"])
    is_recent = explained_fresh or business_fresh or news_fresh
    is_product_update = event_class in {"model_launch", "api_update", "product_update"}
    is_business_relevant = _ai_is_business_relevant(combined_text)
    is_explainer_friendly = _ai_is_explainer_friendly(event_class, combined_text)
    seed_age_bucket = _seed_age_bucket(fetched.published_at)
    return {
        "headline": title,
        "article_text": summary,
        "combined_text": combined_text,
        "source_name": source_name,
        "source_url": fetched.url,
        "company": company,
        "source_label": company,
        "event_class": event_class,
        "category": category,
        "subject_key": subject_key,
        "published_at": fetched.published_at.isoformat() if fetched.published_at else None,
        "topic_tags": topic_tags,
        "is_official": is_official,
        "is_recent": is_recent,
        "is_news_fresh": news_fresh,
        "is_explained_fresh": explained_fresh,
        "is_business_fresh": business_fresh,
        "age_hours": age_hours,
        "seed_age_bucket": seed_age_bucket,
        "seed_family": _seed_family_for_event(event_class),
        "is_product_update": is_product_update,
        "is_business_relevant": is_business_relevant,
        "is_explainer_friendly": is_explainer_friendly,
        "is_evergreen": False,
        "framework_id": _framework_for_lane("ai_explained", event_class, combined_text),
        "angle_hint": _angle_hint_for_event(event_class, combined_text),
    }


def _instagram_seed_facts(facts: dict, *, source_name: str, source_family: str) -> dict:
    return {
        "headline": str(facts.get("headline") or ""),
        "article_text": str(facts.get("article_text") or ""),
        "snippet": str(facts.get("article_text") or ""),
        "company": facts.get("company"),
        "topic_tags": list(facts.get("topic_tags") or []),
        "source_name": source_name,
        "source_family": source_family,
        "source_url": facts.get("source_url"),
        "published_at": facts.get("published_at"),
        "event_type": str(facts.get("event_class") or ""),
        "seed_family": str(facts.get("seed_family") or "fresh_news"),
        "seed_age_bucket": str(facts.get("seed_age_bucket") or "current"),
        "age_hours": facts.get("age_hours"),
        "framework_id": str(facts.get("framework_id") or ""),
        "angle_hint": str(facts.get("angle_hint") or ""),
        "is_evergreen": bool(facts.get("is_evergreen")),
        "is_official": bool(facts.get("is_official")),
        "is_recent": bool(facts.get("is_recent")),
        "is_news_fresh": bool(facts.get("is_news_fresh")),
        "is_explained_fresh": bool(facts.get("is_explained_fresh")),
        "is_business_fresh": bool(facts.get("is_business_fresh")),
        "is_product_update": bool(facts.get("is_product_update")),
        "is_business_relevant": bool(facts.get("is_business_relevant")),
        "is_explainer_friendly": bool(facts.get("is_explainer_friendly")),
    }


def _ai_company_from_source(source_name: str, title: str) -> str:
    mapping = {
        "openai_news": "OpenAI",
        "anthropic_news": "Anthropic",
        "google_ai_blog": "Google",
        "meta_ai_blog": "Meta",
        "azure_ai_blog": "Microsoft",
        "xai_news": "xAI",
        "mistral_news": "Mistral",
        "cohere_blog": "Cohere",
        "perplexity_blog": "Perplexity",
        "huggingface_blog": "Hugging Face",
    }
    if source_name in mapping:
        return mapping[source_name]
    if ":" in title:
        return title.split(":", 1)[0].strip()
    return source_name.replace("_", " ").title()


def _classify_ai_event(title: str, summary: str) -> str:
    text = f"{title} {summary}".lower()
    if any(term in text for term in _AI_POLICY_TERMS):
        return "policy_regulation"
    if any(term in text for term in ("security", "breach", "outage", "safety issue", "misuse")):
        return "security_incident"
    if any(term in text for term in _AI_API_TERMS):
        return "api_update"
    if any(term in text for term in _AI_LAUNCH_TERMS):
        return "model_launch"
    if any(term in text for term in _AI_INDUSTRY_TERMS):
        return "industry_move"
    if any(term in text for term in _AI_RESEARCH_TERMS):
        return "research_update"
    return "product_update"


def _ai_category(event_class: str) -> str:
    if event_class in {"model_launch", "api_update", "product_update"}:
        return "news_seed"
    if event_class in {"industry_move", "funding_deal"}:
        return "business_seed"
    if event_class in {"policy_regulation", "security_incident"}:
        return "explainer_seed"
    return "research"


def _should_drop_ai_candidate(facts: dict) -> str | None:
    text = f"{facts.get('headline', '')} {facts.get('article_text', '')}".lower()
    if any(term in text for term in _AI_BLOCK_TERMS):
        return "blocked_topic"
    if any(term in text for term in _AI_MARKETING_TERMS) and not any(term in text for term in _AI_CONCRETE_KEEP_TERMS):
        return "marketing_or_culture"
    if facts.get("event_class") == "research_update" and not any(
        term in text for term in ("launch", "available", "policy", "copyright", "enterprise", "adoption", "developer")
    ):
        return "research_without_broad_impact"
    if not any(term in text for term in _AI_COMPANY_TERMS) and not any(term in text for term in _AI_CONCRETE_KEEP_TERMS):
        return "weak_signal"
    return None


def _score_ai_facts(facts: dict) -> int:
    event_class = str(facts.get("event_class") or "")
    text = f"{facts.get('headline', '')} {facts.get('article_text', '')}".lower()
    score = 72
    if event_class in {"model_launch", "api_update"}:
        score += 10
    elif event_class in {"policy_regulation", "security_incident"}:
        score += 8
    elif event_class == "industry_move":
        score += 5
    if any(term in text for term in ("pricing", "free", "paid", "$", "million", "billion", "enterprise", "developer")):
        score += 4
    if any(term in text for term in ("openai", "anthropic", "google", "meta", "microsoft", "xai")):
        score += 3
    if any(term in text for term in ("map", "forest", "music", "teens", "creative")) and not any(term in text for term in ("api", "pricing", "model", "launch", "release", "tool", "agent")):
        score -= 6
    return min(score, 95)


def _clean_ai_text(value: str) -> str:
    cleaned = html.unescape(value or "")
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _ai_has_concrete_signal(*, title: str, body_text: str, draft_text: str, event_type: str) -> bool:
    combined = " ".join([title, body_text, draft_text, event_type]).lower()
    if re.search(r"\d", combined):
        return True
    return any(term in combined for term in _AI_CONCRETE_KEEP_TERMS)


def _ai_event_group(event_type: str, title: str, body_text: str) -> str:
    text = f"{title} {body_text} {event_type}".lower()
    if event_type == "api_update" or any(term in text for term in ("api", "sdk", "pricing", "rate limit", "context window", "developer", "tool calling")):
        return "api_or_tooling"
    if event_type == "model_launch" or any(term in text for term in ("launch", "released", "model", "rollout", "available now")):
        return "launch"
    if event_type == "industry_move" or any(term in text for term in ("partnership", "acquisition", "funding", "enterprise", "cloud", "chips", "datacenter", "deal")):
        return "industry"
    if event_type in {"policy_regulation", "security_incident"} or any(term in text for term in ("policy", "regulation", "copyright", "lawsuit", "export control", "ftc", "white house", "eu ai act")):
        return "policy"
    return event_type or "other"


def _ai_story_cluster(facts: dict) -> str:
    company = str(facts.get("company") or "other").lower().replace(" ", "_")
    event_group = _ai_event_group(
        str(facts.get("event_class") or ""),
        str(facts.get("headline") or ""),
        str(facts.get("article_text") or ""),
    )
    subject_key = str(facts.get("subject_key") or "other")
    return f"{company}|{event_group}|{subject_key}"


def _eligible_ai_lanes(facts: dict) -> list[str]:
    lanes: list[str] = []
    if bool(facts.get("is_news_fresh")) and _ai_has_news_value(facts):
        lanes.append("ai_news")
    if (bool(facts.get("is_explained_fresh")) or bool(facts.get("is_evergreen"))) and bool(facts.get("is_explainer_friendly")):
        lanes.append("ai_explained")
    if (bool(facts.get("is_business_fresh")) or bool(facts.get("is_evergreen"))) and bool(facts.get("is_business_relevant")):
        lanes.append("ai_for_business")
    return lanes


def _is_recent_ai_item(published_at: datetime | None, *, hours: int) -> bool:
    if published_at is None:
        return True
    return (datetime.now(timezone.utc) - published_at.astimezone(timezone.utc)).total_seconds() <= hours * 3600


def _ai_has_news_value(facts: dict) -> bool:
    combined = str(facts.get("combined_text") or "").lower()
    return bool(facts.get("is_product_update")) or any(
        term in combined
        for term in (
            "launch",
            "released",
            "rollout",
            "pricing",
            "subscription",
            "billing",
            "lawsuit",
            "copyright",
            "regulation",
            "partnership",
            "acquisition",
        )
    )


def _ai_is_business_relevant(text: str) -> bool:
    lowered = text.lower()
    return any(
        term in lowered
        for term in (
            "enterprise",
            "developer",
            "pricing",
            "billing",
            "subscription",
            "workflow",
            "team",
            "adoption",
            "business",
            "operators",
            "cloud",
            "datacenter",
            "automation",
            "productivity",
            "cost",
        )
    )


def _ai_is_explainer_friendly(event_class: str, text: str) -> bool:
    lowered = text.lower()
    if event_class in {"research_update"}:
        return False
    return any(
        term in lowered
        for term in (
            "pricing",
            "billing",
            "subscription",
            "model",
            "api",
            "feature",
            "tool",
            "policy",
            "regulation",
            "lawsuit",
            "copyright",
            "enterprise",
            "launch",
            "release",
        )
    )


def _age_hours(published_at: datetime | None) -> float | None:
    if published_at is None:
        return None
    return max((datetime.now(timezone.utc) - published_at.astimezone(timezone.utc)).total_seconds() / 3600, 0)


def _seed_age_bucket(published_at: datetime | None) -> str:
    age_hours = _age_hours(published_at)
    if age_hours is None:
        return "evergreen"
    if age_hours <= 24:
        return "current"
    if age_hours <= 24 * 3:
        return "recent"
    if age_hours <= 24 * 7:
        return "recent_plus"
    return "aged"


def _seed_family_for_event(event_class: str) -> str:
    if event_class in {"model_launch", "api_update", "product_update", "policy_regulation", "security_incident"}:
        return "fresh_news"
    if event_class in {"industry_move"}:
        return "recent_business"
    return "recent_explainable"


def _angle_hint_for_event(event_class: str, text: str) -> str:
    lowered = text.lower()
    if any(term in lowered for term in ("pricing", "billing", "subscription", "pay as you go", "pay-as-you-go")):
        return "pricing_shift"
    if any(term in lowered for term in ("workflow", "automation", "agent", "tool", "developer")):
        return "workflow_impact"
    if event_class == "policy_regulation":
        return "policy_shift"
    if event_class == "industry_move":
        return "operator_reality"
    return "what_changed_vs_what_matters"


def _framework_for_lane(lane: str, event_class: str, text: str) -> str:
    lowered = text.lower()
    if lane == "ai_news":
        return "change_then_why_it_matters"
    if lane == "ai_explained":
        if any(term in lowered for term in ("pricing", "billing", "subscription", "cost")):
            return "small_change_to_bigger_shift"
        return "what_people_think_vs_what_matters"
    if any(term in lowered for term in ("workflow", "automation", "agent", "developer")):
        return "update_to_workflow_implication"
    if event_class == "industry_move":
        return "common_mistake_to_better_way"
    return "tool_hype_to_operator_reality"


def _evergreen_ai_facts(item: dict[str, str | list[str]]) -> dict:
    headline = str(item.get("title") or "AI workflow lesson").strip()
    article_text = str(item.get("summary") or "").strip()
    topic_tags = [str(tag) for tag in list(item.get("topic_tags") or [])]
    event_class = str(item.get("event_class") or "business_pattern")
    return {
        "headline": headline,
        "article_text": article_text,
        "combined_text": f"{headline} {article_text}".strip(),
        "source_name": "ai_evergreen_backlog",
        "source_url": None,
        "company": str(item.get("company") or "AI"),
        "source_label": "AI",
        "event_class": event_class,
        "category": "evergreen_backlog",
        "subject_key": str(item.get("seed_key") or re.sub(r'[^a-z0-9]+', '-', headline.lower()).strip('-')),
        "published_at": None,
        "topic_tags": topic_tags,
        "is_official": False,
        "is_recent": True,
        "is_news_fresh": False,
        "is_explained_fresh": True,
        "is_business_fresh": True,
        "age_hours": None,
        "seed_age_bucket": "evergreen",
        "seed_family": "evergreen_backlog",
        "is_product_update": False,
        "is_business_relevant": True,
        "is_explainer_friendly": True,
        "is_evergreen": True,
        "framework_id": _framework_for_lane("ai_for_business", event_class, article_text),
        "angle_hint": str(item.get("angle_hint") or _angle_hint_for_event(event_class, article_text)),
    }


def _ai_topic_tags(event_class: str, text: str) -> list[str]:
    lowered = text.lower()
    tags: list[str] = [event_class]
    for term in (
        "pricing",
        "api",
        "model",
        "tool",
        "agent",
        "billing",
        "subscription",
        "enterprise",
        "copyright",
        "regulation",
        "lawsuit",
        "developer",
    ):
        if term in lowered:
            tags.append(term.replace(" ", "_"))
    return list(dict.fromkeys(tags))


def _is_duplicate_ai_lane_text(existing_texts: dict[str, str], candidate_text: str) -> bool:
    normalized_candidate = re.sub(r"[^a-z0-9]+", " ", candidate_text.lower()).strip()
    for existing in existing_texts.values():
        normalized_existing = re.sub(r"[^a-z0-9]+", " ", existing.lower()).strip()
        if normalized_existing == normalized_candidate:
            return True
    return False


def _ai_lane_importance_bonus(lane: str) -> int:
    if lane == "ai_explained":
        return 2
    if lane == "ai_for_business":
        return 1
    return 3


def ai_quality_band(
    *,
    importance_score: int,
    confidence_score: float,
    draft_text: str,
    title: str,
    body_text: str,
    event_type: str,
    review_reason: str | None,
) -> str:
    band, _reason = ai_readiness_assessment(
        importance_score=importance_score,
        confidence_score=confidence_score,
        draft_text=draft_text,
        title=title,
        body_text=body_text,
        event_type=event_type,
        review_reason=review_reason,
    )
    return band


def ai_readiness_assessment(
    *,
    importance_score: int,
    confidence_score: float,
    draft_text: str,
    title: str,
    body_text: str,
    event_type: str,
    review_reason: str | None,
    lane: str = "ai_news",
) -> tuple[str, str]:
    has_concrete_signal = _ai_has_concrete_signal(
        title=title,
        body_text=body_text,
        draft_text=draft_text,
        event_type=event_type,
    )
    if review_reason:
        return "C", "review_flagged"
    if not has_concrete_signal:
        return "C", "missing_concrete_signal"
    if lane == "ai_explained" and not any(term in draft_text.lower() for term in ("matters", "means", "bigger", "really", "takeaway")):
        return "C", "missing_explanatory_takeaway"
    if lane == "ai_for_business" and not any(term in draft_text.lower() for term in ("business", "team", "workflow", "cost", "time", "operator", "adopt")):
        return "C", "missing_business_angle"
    if event_type in {"model_launch", "api_update", "policy_regulation", "security_incident"} and importance_score >= 84 and confidence_score >= 0.82:
        return "A", "shadow_ready"
    if importance_score >= 76:
        return "B", "useful_but_hold"
    return "C", "low_importance"


def _ai_band_rank(band: str) -> int:
    return {"A": 3, "B": 2, "C": 1}.get(band.upper(), 0)

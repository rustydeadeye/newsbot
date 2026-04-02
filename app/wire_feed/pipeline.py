from __future__ import annotations

import textwrap
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.models.source import Source, SourceItem
from app.services.drafting.service import DraftingService
from app.services.ingestion.base import FetchedItem
from app.services.normalization.dedupe import make_dedupe_key
from app.services.normalization.extractors import extract_facts
from app.services.scoring import SOURCE_PRIORITY, score_event
from app.wire_feed.sources import WireSourceDef

WIRE_AUTO_POST_THRESHOLD = 80
_DISPLAY_TZ = ZoneInfo("Asia/Kolkata")

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


@dataclass
class WirePipelineResult:
    external_id: str
    source_name: str
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
    published_at: datetime | None
    fetch_error: str | None = None


def fetch_and_process(source_def: WireSourceDef, drafting: DraftingService) -> list[WirePipelineResult]:
    source = Source(name=source_def.name, type=source_def.type, base_url=source_def.url)
    adapter = source_def.adapter_cls(source)
    try:
        items = adapter.fetch()
    except Exception as exc:
        return [
            WirePipelineResult(
                external_id="",
                source_name=source_def.name,
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
                external_id=fetched.external_id,
                source_name=source_def.name,
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
                published_at=fetched.published_at,
            )
        )
    return _dedupe_results(results)


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


def _should_drop_wire_candidate(facts: dict) -> bool:
    event_type = str(facts.get("event_class") or "")
    headline = str(facts.get("headline") or "")
    article_text = str(facts.get("article_text") or "")
    combined = f"{headline} {article_text}".lower()

    if any(term in combined for term in _LOW_SIGNAL_WIRE_TERMS):
        return True

    if event_type == "management_change" and any(term in combined for term in _LOW_SIGNAL_MANAGEMENT_TERMS):
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

    return False

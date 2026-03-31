"""End-to-end pipeline dry run — no DB writes, no posting to X.

Shows exactly what would be fetched, how it would be classified/scored,
and what draft post text would be generated for each event.

Usage:
    python -m scripts.pipeline_dryrun              # all sources, top 10 by score
    python -m scripts.pipeline_dryrun --source rbi # one source only
    python -m scripts.pipeline_dryrun --limit 5    # show top N drafts
    python -m scripts.pipeline_dryrun --all        # show every item
"""

from __future__ import annotations

import argparse
import os
import textwrap
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import SimpleNamespace

# Provide a dummy DATABASE_URL so Settings() doesn't fail — we don't touch the DB.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://dryrun:dryrun@localhost/dryrun")

from app.models.source import Source, SourceItem
from app.services.drafting.service import DraftingService
from app.services.ingestion.adapters import (
    BSEMultiRSSAdapter,
    MOSPIPressReleaseAdapter,
    NSECorporateFilingsAdapter,
    RSSSourceAdapter,
    SEBIRSSAdapter,
)
from app.services.ingestion.base import FetchedItem
from app.services.normalization.dedupe import make_dedupe_key
from app.services.normalization.extractors import extract_facts
from app.services.scoring import SOURCE_PRIORITY, score_event

AUTO_POST_THRESHOLD = 80  # mirrors default settings

SOURCES = [
    {"key": "rbi",   "name": "rbi_press_releases",    "type": "rss",  "url": "https://rbi.org.in/pressreleases_rss.xml",          "cls": RSSSourceAdapter},
    {"key": "sebi",  "name": "sebi_releases",          "type": "rss",  "url": "https://www.sebi.gov.in/sebirss.xml",               "cls": SEBIRSSAdapter},
    {"key": "bse",   "name": "bse_announcements",      "type": "rss",  "url": "https://www.bseindia.com/data/xml/announcements.xml","cls": BSEMultiRSSAdapter},
    {"key": "nse",   "name": "nse_corporate_filings",  "type": "html", "url": "https://www.nseindia.com/companies-listing/corporate-filings-application", "cls": NSECorporateFilingsAdapter},
    {"key": "mospi", "name": "mospi_releases",          "type": "html", "url": "https://mospi.gov.in/press-release",                "cls": MOSPIPressReleaseAdapter},
]


@dataclass
class PipelineResult:
    source_name: str
    title: str
    event_type: str
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


def _fake_event(facts: dict, importance: int, confidence: float) -> SimpleNamespace:
    """Build a minimal event-like object that DraftingService.make_draft_post accepts."""
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
        checksum="dryrun",
    )


def _review_reason(importance: int, confidence: float, safety_flags: dict) -> str | None:
    if safety_flags.get("needs_review"):
        return "blocked_phrase"
    if importance < AUTO_POST_THRESHOLD:
        return f"score={importance} below threshold={AUTO_POST_THRESHOLD}"
    if confidence < 0.85:
        return f"low_confidence={confidence:.2f}"
    return None


def fetch_and_process(src: dict, drafting: DraftingService) -> list[PipelineResult]:
    source = Source(name=src["name"], type=src["type"], base_url=src["url"])
    adapter = src["cls"](source)
    results: list[PipelineResult] = []

    try:
        items = adapter.fetch()
    except Exception as exc:
        return [PipelineResult(
            source_name=src["name"], title="", event_type="", subject_key=None, ticker=None,
            importance_score=0, confidence_score=0, would_auto_post=False,
            review_reason=None, draft_text="", safety_flags={},
            published_at=None, fetch_error=f"{type(exc).__name__}: {exc}",
        )]

    for fetched in items:
        source_item = _fake_source_item(fetched)
        facts = extract_facts(source, source_item)
        fallback_confidence = 0.95 if src["name"] in SOURCE_PRIORITY else 0.70
        importance = score_event(src["name"], facts["event_class"], facts.get("ticker"))

        event = _fake_event(facts, importance, fallback_confidence)
        draft = drafting.make_draft_post(event)

        confidence = draft.safety_flags.get("ai_confidence") or fallback_confidence
        reason = _review_reason(importance, confidence, draft.safety_flags)
        results.append(PipelineResult(
            source_name=src["name"],
            title=fetched.title or "",
            event_type=facts["event_class"],
            subject_key=facts.get("subject_key"),
            ticker=facts.get("ticker"),
            importance_score=importance,
            confidence_score=confidence,
            would_auto_post=reason is None,
            review_reason=reason,
            draft_text=draft.draft_text,
            safety_flags=draft.safety_flags,
            published_at=fetched.published_at,
        ))

    return _dedupe_results(results)


def _dedupe_results(results: list[PipelineResult]) -> list[PipelineResult]:
    deduped: dict[str, PipelineResult] = {}
    for result in results:
        dedupe_key = make_dedupe_key(
            event_type=result.event_type,
            ticker=result.ticker,
            entity_name=None,
            occurred_at=result.published_at,
            key_number=result.subject_key,
        )
        current = deduped.get(dedupe_key)
        if current is None or _prefer_result(result, current):
            deduped[dedupe_key] = result
    return list(deduped.values())


def _prefer_result(candidate: PipelineResult, existing: PipelineResult) -> bool:
    candidate_date = candidate.published_at or datetime.min.replace(tzinfo=timezone.utc)
    existing_date = existing.published_at or datetime.min.replace(tzinfo=timezone.utc)
    if candidate_date != existing_date:
        return candidate_date > existing_date
    return candidate.importance_score > existing.importance_score


def print_result(r: PipelineResult, index: int) -> None:
    status = "AUTO-POST" if r.would_auto_post else f"REVIEW ({r.review_reason})"
    bar = "#" * (r.importance_score // 10) + "." * (10 - r.importance_score // 10)
    pub = r.published_at.strftime("%Y-%m-%d %H:%M") if r.published_at else "no date"

    print(f"\n{'-'*70}")
    print(f"  #{index:<3}  [{r.source_name}]  {pub}")
    print(f"  Title:  {textwrap.shorten(r.title, 65)}")
    print(f"  Type:   {r.event_type:<20}  Ticker: {r.ticker or '-'}")
    print(f"  Score:  {bar} {r.importance_score}/100   Confidence: {r.confidence_score:.0%}")
    print(f"  Status: {status}")
    if r.safety_flags.get("blocked_phrases"):
        print(f"  ! Blocked: {r.safety_flags['blocked_phrases']}")
    print()
    # Wrap draft text at 70 chars
    for line in textwrap.wrap(r.draft_text, width=68):
        print(f"    {line}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", help="Only run one source key (rbi/bse/nse/mospi)")
    parser.add_argument("--limit", type=int, default=10, help="Show top N results by score (default 10)")
    parser.add_argument("--all", action="store_true", help="Show all results, not just top N")
    parser.add_argument("--openai-key", help="OpenAI API key (overrides env)")
    args = parser.parse_args()

    if args.openai_key:
        os.environ["OPENAI_API_KEY"] = args.openai_key
        # Clear cached settings so the new key is picked up
        from app.core.config import get_settings
        get_settings.cache_clear()

    sources = [s for s in SOURCES if not args.source or s["key"] == args.source]
    if not sources:
        print(f"Unknown source. Valid keys: {[s['key'] for s in SOURCES]}")
        return

    print(f"\nNewsbot Pipeline Dry Run - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"Sources: {[s['key'] for s in sources]}")
    print("Initialising drafting service...")
    drafting = DraftingService()
    ai_mode = "OpenAI" if drafting.client else "fallback template (no OPENAI_API_KEY)"
    print(f"Drafting mode: {ai_mode}\n")

    all_results: list[PipelineResult] = []

    for src in sources:
        print(f"Fetching {src['key']}...", end=" ", flush=True)
        results = fetch_and_process(src, drafting)
        errors = [r for r in results if r.fetch_error]
        ok = [r for r in results if not r.fetch_error]
        if errors:
            print(f"FAILED — {errors[0].fetch_error}")
        else:
            print(f"{len(ok)} items")
        all_results.extend(ok)

    if not all_results:
        print("\nNo items fetched.")
        return

    # Sort by score descending
    all_results.sort(key=lambda r: r.importance_score, reverse=True)

    auto = sum(1 for r in all_results if r.would_auto_post)
    review = len(all_results) - auto
    print(f"\nTotal: {len(all_results)} items — {auto} would auto-post, {review} would go to review")

    display = all_results if args.all else all_results[:args.limit]
    limit_label = "all" if args.all else f"top {args.limit}"
    print(f"Showing {limit_label} by importance score:")

    for i, result in enumerate(display, 1):
        print_result(result, i)

    if not args.all and len(all_results) > args.limit:
        print(f"\n  ... {len(all_results) - args.limit} more items not shown (use --all or --limit N)")

    print(f"\n{'-'*70}")
    print("Dry run complete. Nothing was written to the database or posted to X.")


if __name__ == "__main__":
    main()

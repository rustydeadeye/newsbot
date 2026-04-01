"""Show only the draft post text — clean output for reviewing what would be tweeted.

Usage:
    python -m scripts.show_posts --openai-key <key>
    python -m scripts.show_posts --openai-key <key> --source rbi
    python -m scripts.show_posts --openai-key <key> --auto-only   # only posts that would auto-publish
    python -m scripts.show_posts --openai-key <key> --review-only # only posts going to review
"""
from __future__ import annotations

import argparse
import os
import sys
import textwrap
from datetime import datetime, timezone

# Force UTF-8 output on Windows so rupee signs and other chars don't crash
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://dryrun:dryrun@localhost/dryrun")

from app.models.source import Source, SourceItem
from app.services.drafting.service import DraftingService
from app.services.ingestion.adapters import (
    BSEMultiRSSAdapter,
    MOSPIPressReleaseAdapter,
    NSECorporateFilingsAdapter,
    RSSSourceAdapter,
)
from app.services.ingestion.base import FetchedItem
from app.services.normalization.extractors import extract_facts
from app.services.scoring import SOURCE_PRIORITY, score_event

AUTO_POST_THRESHOLD = 80

SOURCES = [
    {"key": "rbi",   "name": "rbi_press_releases",   "type": "rss",  "url": "https://rbi.org.in/pressreleases_rss.xml",           "cls": RSSSourceAdapter},
    {"key": "bse",   "name": "bse_announcements",     "type": "rss",  "url": "https://www.bseindia.com/data/xml/announcements.xml", "cls": BSEMultiRSSAdapter},
    {"key": "nse",   "name": "nse_corporate_filings", "type": "html", "url": "https://www.nseindia.com/companies-listing/corporate-filings-application", "cls": NSECorporateFilingsAdapter},
    {"key": "mospi", "name": "mospi_releases",         "type": "html", "url": "https://mospi.gov.in/press-release",                 "cls": MOSPIPressReleaseAdapter},
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--openai-key", required=True)
    parser.add_argument("--source", help="rbi/bse/nse/mospi")
    parser.add_argument("--auto-only", action="store_true", help="Only posts that would auto-publish")
    parser.add_argument("--review-only", action="store_true", help="Only posts going to review queue")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    os.environ["OPENAI_API_KEY"] = args.openai_key
    from app.core.config import get_settings
    get_settings.cache_clear()

    sources = [s for s in SOURCES if not args.source or s["key"] == args.source]
    drafting = DraftingService()

    print(f"\nGenerating posts — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC\n")

    posts = []
    for src in sources:
        source = Source(name=src["name"], type=src["type"], base_url=src["url"])
        try:
            items = src["cls"](source).fetch()
        except Exception as exc:
            print(f"[{src['key']}] FETCH FAILED: {exc}\n")
            continue

        print(f"[{src['key']}] Fetched {len(items)} items, drafting...", flush=True)
        for fetched in items:
            si = SourceItem(source_id=1, external_id=fetched.external_id, url=fetched.url,
                            title=fetched.title, published_at=fetched.published_at,
                            raw_payload=fetched.raw_payload, checksum="dryrun")
            facts = extract_facts(source, si)
            importance = score_event(src["name"], facts["event_class"], facts.get("ticker"), headline=facts.get("headline"))
            confidence = 0.95 if src["name"] in SOURCE_PRIORITY else 0.70

            from types import SimpleNamespace
            event = SimpleNamespace(id=None, summary_facts=facts, importance_score=importance,
                                    confidence_score=confidence, event_type=facts["event_class"])
            draft = drafting.make_draft_post(event)

            auto_post = (
                not draft.safety_flags.get("needs_review")
                and importance >= AUTO_POST_THRESHOLD
                and confidence >= 0.85
            )
            posts.append({
                "source": src["key"],
                "title": fetched.title or "",
                "event_type": facts["event_class"],
                "ticker": facts.get("ticker"),
                "score": importance,
                "auto_post": auto_post,
                "text": draft.draft_text,
                "flagged": draft.safety_flags.get("blocked_phrases", []),
                "date": fetched.published_at,
            })

    # Filter
    if args.auto_only:
        posts = [p for p in posts if p["auto_post"]]
    elif args.review_only:
        posts = [p for p in posts if not p["auto_post"]]

    # Sort by score
    posts.sort(key=lambda p: p["score"], reverse=True)
    posts = posts[:args.limit]

    print(f"\n{'='*72}")
    auto_count = sum(1 for p in posts if p["auto_post"])
    review_count = len(posts) - auto_count
    print(f"  {len(posts)} posts  |  {auto_count} AUTO-POST  |  {review_count} REVIEW")
    print(f"{'='*72}")

    for i, p in enumerate(posts, 1):
        date_str = p["date"].strftime("%d %b %Y %H:%M") if p["date"] else "no date"
        status = "AUTO-POST" if p["auto_post"] else "REVIEW"
        ticker_str = f"  ${p['ticker']}" if p["ticker"] else ""
        flag_str = f"  [FLAGGED: {p['flagged']}]" if p["flagged"] else ""

        print(f"\n  [{i:>2}]  {status}  |  score={p['score']}  |  {p['event_type']}{ticker_str}  |  {date_str}{flag_str}")
        print(f"        Source headline: {textwrap.shorten(p['title'], 65)}")
        print()
        # Indent the post text
        for line in p["text"].splitlines():
            for wrapped in textwrap.wrap(line, width=66) or [""]:
                print(f"        {wrapped}")
        print(f"  {'-'*68}")

    print(f"\n  Total shown: {len(posts)} posts. Nothing posted to X.")


if __name__ == "__main__":
    main()

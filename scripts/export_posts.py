"""Export draft posts to a plain text file for easy review.

Usage:
    python -m scripts.export_posts --openai-key <key>
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://dryrun:dryrun@localhost/dryrun")

from app.models.source import Source, SourceItem
from app.services.drafting.service import DraftingService
from app.services.ingestion.adapters import (
    BSEMultiRSSAdapter,
    MOSPIPressReleaseAdapter,
    NSECorporateFilingsAdapter,
    RSSSourceAdapter,
)
from app.services.normalization.extractors import extract_facts
from app.services.scoring import SOURCE_PRIORITY, score_event

AUTO_POST_THRESHOLD = 80

SOURCES = [
    {"key": "rbi",   "name": "rbi_press_releases",   "type": "rss",  "url": "https://rbi.org.in/pressreleases_rss.xml",           "cls": RSSSourceAdapter},
    {"key": "bse",   "name": "bse_announcements",     "type": "rss",  "url": "https://www.bseindia.com/data/xml/announcements.xml", "cls": BSEMultiRSSAdapter},
    {"key": "nse",   "name": "nse_corporate_filings", "type": "html", "url": "https://www.nseindia.com/companies-listing/corporate-filings-application", "cls": NSECorporateFilingsAdapter},
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--openai-key", required=True)
    parser.add_argument("--source", help="rbi/bse/nse")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    os.environ["OPENAI_API_KEY"] = args.openai_key
    from app.core.config import get_settings
    get_settings.cache_clear()

    sources = [s for s in SOURCES if not args.source or s["key"] == args.source]
    drafting = DraftingService()

    posts = []
    for src in sources:
        source = Source(name=src["name"], type=src["type"], base_url=src["url"])
        print(f"Fetching {src['key']}...", flush=True)
        try:
            items = src["cls"](source).fetch()
        except Exception as exc:
            print(f"  FAILED: {exc}")
            continue
        print(f"  {len(items)} items — drafting posts...", flush=True)
        for fetched in items:
            si = SourceItem(
                source_id=1, external_id=fetched.external_id, url=fetched.url,
                title=fetched.title, published_at=fetched.published_at,
                raw_payload=fetched.raw_payload, checksum="dryrun",
            )
            facts = extract_facts(source, si)
            importance = score_event(src["name"], facts["event_class"], facts.get("ticker"))
            confidence = 0.95 if src["name"] in SOURCE_PRIORITY else 0.70

            from types import SimpleNamespace
            event = SimpleNamespace(
                id=None, summary_facts=facts, importance_score=importance,
                confidence_score=confidence, event_type=facts["event_class"],
            )
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
                "date": fetched.published_at,
            })

    posts.sort(key=lambda p: p["score"], reverse=True)
    posts = posts[:args.limit]

    auto = [p for p in posts if p["auto_post"]]
    review = [p for p in posts if not p["auto_post"]]

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = []
    lines.append("=" * 72)
    lines.append("  NEWSBOT — DRAFT POSTS")
    lines.append(f"  Generated: {now}")
    lines.append(f"  Total: {len(posts)}  |  Auto-post: {len(auto)}  |  Needs review: {len(review)}")
    lines.append("=" * 72)

    def write_section(title: str, section_posts: list) -> None:
        lines.append("")
        lines.append(f"{'=' * 72}")
        lines.append(f"  {title} ({len(section_posts)} posts)")
        lines.append(f"{'=' * 72}")
        for i, p in enumerate(section_posts, 1):
            date_str = p["date"].strftime("%d %b %Y %H:%M") if p["date"] else "no date"
            ticker_str = f"  ${p['ticker']}" if p["ticker"] else ""
            lines.append("")
            lines.append(f"  [{i}]  {p['event_type'].upper()}{ticker_str}  |  score={p['score']}  |  {p['source']}  |  {date_str}")
            lines.append(f"  Headline: {p['title']}")
            lines.append("")
            lines.append("  DRAFT POST:")
            lines.append("  " + "-" * 60)
            for line in p["text"].splitlines():
                lines.append(f"  {line}")
            lines.append("  " + "-" * 60)

    write_section("WOULD AUTO-POST", auto)
    write_section("NEEDS REVIEW", review)

    lines.append("")
    lines.append("=" * 72)
    lines.append("  Nothing was posted to X. This is a dry run.")
    lines.append("=" * 72)

    output_path = Path(__file__).parent.parent / "draft_posts.txt"
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nDone. Posts written to: {output_path}")


if __name__ == "__main__":
    main()

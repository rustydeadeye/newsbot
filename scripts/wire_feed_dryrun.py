"""Experimental market-wire dry run.

This intentionally runs through app.wire_feed instead of the main product
pipeline so we can iterate on the high-frequency posting engine separately.
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://dryrun:dryrun@localhost/dryrun")

from app.services.drafting.service import DraftingService
from app.wire_feed.pipeline import fetch_and_process, summarize_results
from app.wire_feed.sources import get_wire_sources

DISPLAY_TZ = ZoneInfo("Asia/Kolkata")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", help="Only run one source key (tradient)")
    parser.add_argument("--limit", type=int, default=10, help="Show top N results by score")
    parser.add_argument("--openai-key", help="OpenAI API key (overrides env)")
    args = parser.parse_args()

    if args.openai_key:
        os.environ["OPENAI_API_KEY"] = args.openai_key
        from app.core.config import get_settings

        get_settings.cache_clear()

    sources = get_wire_sources(args.source)
    if not sources:
        print("Unknown wire source. Valid keys: ['tradient']")
        return

    now_local = datetime.now(timezone.utc).astimezone(DISPLAY_TZ)
    print(f"\nWire Feed Dry Run - {now_local.strftime('%Y-%m-%d %H:%M IST')}")
    print(f"Sources: {[source.key for source in sources]}")
    drafting = DraftingService()
    ai_mode = "OpenAI" if drafting.client else "fallback template (no OPENAI_API_KEY)"
    print(f"Drafting mode: {ai_mode}\n")

    for source in sources:
        print(f"Fetching {source.key}...", end=" ", flush=True)
        results = fetch_and_process(source, drafting)
        successful = [result for result in results if not result.fetch_error]
        if successful:
            print(f"{len(successful)} items")
        else:
            print("failed")
        print()
        print(summarize_results(results, limit=args.limit))
        print()

    print("-" * 70)
    print("Wire dry run complete. Nothing was written to the database or posted to X.")


if __name__ == "__main__":
    main()

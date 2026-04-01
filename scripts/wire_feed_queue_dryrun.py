"""Plan wire-feed posting cadence without writing to the database."""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://dryrun:dryrun@localhost/dryrun")

from app.services.drafting.service import DraftingService
from app.wire_feed.pipeline import fetch_and_process
from app.wire_feed.policy import WireFeedSettings, plan_wire_queue
from app.wire_feed.sources import get_wire_sources

DISPLAY_TZ = ZoneInfo("Asia/Kolkata")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", help="Only run one source key (tradient)")
    parser.add_argument("--limit", type=int, default=10, help="Show top N queue decisions")
    args = parser.parse_args()

    sources = get_wire_sources(args.source)
    if not sources:
        print("Unknown wire source. Valid keys: ['tradient']")
        return

    now = datetime.now(timezone.utc)
    now_local = now.astimezone(DISPLAY_TZ)
    print(f"\nWire Feed Queue Dry Run - {now_local.strftime('%Y-%m-%d %H:%M IST')}")
    drafting = DraftingService()
    for source in sources:
        results = fetch_and_process(source, drafting)
        decisions = plan_wire_queue(results, now=now, settings=WireFeedSettings())
        print(f"\nSource: {source.key}")
        for decision in decisions[: args.limit]:
            scheduled = decision.scheduled_for.astimezone(DISPLAY_TZ).strftime("%H:%M IST") if decision.scheduled_for else "-"
            print(f"- {decision.action:8} {scheduled:>9} [{decision.priority}] {decision.result.draft_text}")
            if decision.reason:
                print(f"  reason={decision.reason}")


if __name__ == "__main__":
    main()

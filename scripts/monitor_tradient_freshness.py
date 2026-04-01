"""Measure how often the Tradient feed actually changes.

Example:
    python -m scripts.monitor_tradient_freshness --iterations 6 --interval-sec 180
"""

from __future__ import annotations

import argparse
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://dryrun:dryrun@localhost/dryrun")

from app.models.source import Source
from app.services.ingestion.adapters import TradientMarketNewsAdapter

DISPLAY_TZ = ZoneInfo("Asia/Kolkata")


@dataclass
class Snapshot:
    taken_at: datetime
    total_items: int
    newest_item_at: datetime | None
    top_ids: list[str]
    top_titles: list[str]


def _take_snapshot(limit: int = 10) -> Snapshot:
    source = Source(
        name="tradient_market_news",
        type="json",
        base_url="https://api.tradient.org/v1/api/market/news",
    )
    items = TradientMarketNewsAdapter(source).fetch()
    top_items = items[:limit]
    newest_item_at = max((item.published_at for item in items if item.published_at), default=None)
    return Snapshot(
        taken_at=datetime.now(timezone.utc),
        total_items=len(items),
        newest_item_at=newest_item_at,
        top_ids=[item.external_id for item in top_items],
        top_titles=[item.title for item in top_items],
    )


def _diff_count(previous: Snapshot | None, current: Snapshot) -> int:
    if previous is None:
        return len(current.top_ids)
    previous_ids = set(previous.top_ids)
    return sum(1 for item_id in current.top_ids if item_id not in previous_ids)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=3, help="How many snapshots to collect")
    parser.add_argument("--interval-sec", type=int, default=180, help="Seconds between snapshots")
    parser.add_argument("--top-limit", type=int, default=10, help="How many top items to compare")
    args = parser.parse_args()

    snapshots: list[Snapshot] = []

    for index in range(args.iterations):
        snapshot = _take_snapshot(limit=args.top_limit)
        previous = snapshots[-1] if snapshots else None
        changed = _diff_count(previous, snapshot)
        snapshots.append(snapshot)

        taken_local = snapshot.taken_at.astimezone(DISPLAY_TZ).strftime("%Y-%m-%d %H:%M:%S IST")
        newest_local = snapshot.newest_item_at.astimezone(DISPLAY_TZ).strftime("%Y-%m-%d %H:%M:%S IST") if snapshot.newest_item_at else "no date"
        print(f"\nSnapshot {index + 1}/{args.iterations} at {taken_local}")
        print(f"- total items: {snapshot.total_items}")
        print(f"- newest item time: {newest_local}")
        print(f"- changed items in top {args.top_limit}: {changed}")
        for title in snapshot.top_titles[:5]:
            print(f"  - {title}")

        if index < args.iterations - 1:
            time.sleep(args.interval_sec)

    if len(snapshots) >= 2:
        deltas = [_diff_count(snapshots[i - 1], snapshots[i]) for i in range(1, len(snapshots))]
        avg_changed = sum(deltas) / len(deltas)
        print("\nSummary")
        print(f"- snapshots collected: {len(snapshots)}")
        print(f"- average changed items in top {args.top_limit}: {avg_changed:.2f}")
        print(f"- recommended fetch interval starting point: {_recommended_interval(avg_changed)}")


def _recommended_interval(avg_changed: float) -> str:
    if avg_changed >= 5:
        return "2-3 minutes"
    if avg_changed >= 2:
        return "3-5 minutes"
    if avg_changed >= 1:
        return "5-10 minutes"
    return "10-15 minutes"


if __name__ == "__main__":
    main()

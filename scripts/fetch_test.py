"""Live fetch test — hits real sources and prints results.

Usage:
    python scripts/fetch_test.py              # test all sources
    python scripts/fetch_test.py rbi bse      # test specific sources
"""

from __future__ import annotations

import sys
import textwrap
import traceback
from dataclasses import dataclass

from app.models.source import Source
from app.services.ingestion.adapters import (
    BSEMultiRSSAdapter,
    MOSPIPressReleaseAdapter,
    NSECorporateFilingsAdapter,
    RSSSourceAdapter,
)
from app.services.ingestion.base import FetchedItem

# ---------------------------------------------------------------------------
# Source definitions (mirrors what would be in the DB)
# ---------------------------------------------------------------------------

@dataclass
class SourceDef:
    key: str
    name: str
    type: str
    base_url: str
    adapter_cls: type


SOURCES: list[SourceDef] = [
    SourceDef(
        key="rbi",
        name="rbi_press_releases",
        type="rss",
        base_url="https://rbi.org.in/pressreleases_rss.xml",
        adapter_cls=RSSSourceAdapter,
    ),
    SourceDef(
        key="sebi",
        name="sebi_press_releases",
        type="rss",
        base_url="https://www.sebi.gov.in/sebirss.aspx",
        adapter_cls=RSSSourceAdapter,
    ),
    SourceDef(
        key="bse",
        name="bse_announcements",
        type="rss",
        base_url="https://www.bseindia.com/data/xml/announcements.xml",
        adapter_cls=BSEMultiRSSAdapter,
    ),
    SourceDef(
        key="nse",
        name="nse_corporate_filings",
        type="html",
        base_url="https://www.nseindia.com/companies-listing/corporate-filings-application",
        adapter_cls=NSECorporateFilingsAdapter,
    ),
    SourceDef(
        key="mospi",
        name="mospi_releases",
        type="html",
        base_url="https://mospi.gov.in/press-release",
        adapter_cls=MOSPIPressReleaseAdapter,
    ),
]


def _print_item(i: int, item: FetchedItem) -> None:
    section = item.raw_payload.get("section", "")
    exchange = item.raw_payload.get("exchange", "")
    tag = f"[{exchange}/{section}]" if exchange or section else ""
    title = textwrap.shorten(item.title or "(no title)", width=80)
    pub = item.published_at.strftime("%Y-%m-%d %H:%M") if item.published_at else "no date"
    print(f"  {i:>3}. {tag} {title}")
    print(f"       date={pub}  id={item.external_id[:60]}")


def fetch_source(defn: SourceDef) -> None:
    print(f"\n{'='*70}")
    print(f"  SOURCE: {defn.key.upper()} ({defn.name})")
    print(f"  URL:    {defn.base_url}")
    print(f"{'='*70}")

    source = Source(name=defn.name, type=defn.type, base_url=defn.base_url)
    adapter = defn.adapter_cls(source)

    try:
        items = adapter.fetch()
    except Exception:
        print("  [FAILED]")
        traceback.print_exc()
        return

    if not items:
        print("  (no items returned)")
        return

    print(f"  Fetched {len(items)} items")
    for i, item in enumerate(items[:10], 1):
        _print_item(i, item)

    if len(items) > 10:
        print(f"  ... and {len(items) - 10} more")


def main() -> None:
    requested = {a.lower() for a in sys.argv[1:]}
    targets = [s for s in SOURCES if not requested or s.key in requested]

    if not targets:
        print(f"Unknown source key(s): {requested}")
        print(f"Valid keys: {[s.key for s in SOURCES]}")
        sys.exit(1)

    print(f"Testing {len(targets)} source(s)...")
    for defn in targets:
        fetch_source(defn)

    print(f"\n{'='*70}")
    print("Done.")


if __name__ == "__main__":
    main()

from __future__ import annotations

from dataclasses import dataclass

from app.services.ingestion.adapters import TradientMarketNewsAdapter


@dataclass(frozen=True)
class WireSourceDef:
    key: str
    name: str
    type: str
    url: str
    adapter_cls: type


WIRE_SOURCES: tuple[WireSourceDef, ...] = (
    WireSourceDef(
        key="tradient",
        name="tradient_market_news",
        type="json",
        url="https://api.tradient.org/v1/api/market/news",
        adapter_cls=TradientMarketNewsAdapter,
    ),
)


def get_wire_sources(source_key: str | None = None) -> list[WireSourceDef]:
    return [source for source in WIRE_SOURCES if not source_key or source.key == source_key]


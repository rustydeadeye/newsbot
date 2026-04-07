from __future__ import annotations

from dataclasses import dataclass

from app.services.ingestion.adapters import RSSSourceAdapter, TradientMarketNewsAdapter


@dataclass(frozen=True)
class WireSourceDef:
    key: str
    name: str
    type: str
    url: str
    adapter_cls: type
    product: str = "finance"
    enabled: bool = True
    status: str = "keep"
    fetch_mode: str = "base"
    max_items: int = 3


SOURCE_REGISTRY: tuple[WireSourceDef, ...] = (
    WireSourceDef(
        product="finance",
        key="tradient",
        name="tradient_market_news",
        type="json",
        url="https://api.tradient.org/v1/api/market/news",
        adapter_cls=TradientMarketNewsAdapter,
        max_items=24,
    ),
    WireSourceDef(
        product="ai",
        key="openai_news",
        name="openai_news",
        type="rss",
        url="https://openai.com/news/rss.xml",
        adapter_cls=RSSSourceAdapter,
        max_items=4,
    ),
    WireSourceDef(
        product="ai",
        key="anthropic_news",
        name="anthropic_news",
        type="rss",
        url="",
        adapter_cls=RSSSourceAdapter,
        enabled=False,
        status="fallback_to_web_only",
        fetch_mode="web_only",
        max_items=0,
    ),
    WireSourceDef(
        product="ai",
        key="google_ai_blog",
        name="google_ai_blog",
        type="rss",
        url="https://blog.google/technology/ai/rss/",
        adapter_cls=RSSSourceAdapter,
        max_items=3,
    ),
    WireSourceDef(
        product="ai",
        key="meta_ai_blog",
        name="meta_ai_blog",
        type="rss",
        url="",
        adapter_cls=RSSSourceAdapter,
        enabled=False,
        status="fallback_to_web_only",
        fetch_mode="web_only",
        max_items=0,
    ),
    WireSourceDef(
        product="ai",
        key="azure_ai_blog",
        name="azure_ai_blog",
        type="rss",
        url="",
        adapter_cls=RSSSourceAdapter,
        enabled=False,
        status="fallback_to_web_only",
        fetch_mode="web_only",
        max_items=0,
    ),
    WireSourceDef(
        product="ai",
        key="xai_news",
        name="xai_news",
        type="rss",
        url="",
        adapter_cls=RSSSourceAdapter,
        enabled=False,
        status="fallback_to_web_only",
        fetch_mode="web_only",
        max_items=0,
    ),
    WireSourceDef(
        product="ai",
        key="mistral_news",
        name="mistral_news",
        type="rss",
        url="",
        adapter_cls=RSSSourceAdapter,
        enabled=False,
        status="fallback_to_web_only",
        fetch_mode="web_only",
        max_items=0,
    ),
    WireSourceDef(
        product="ai",
        key="cohere_blog",
        name="cohere_blog",
        type="rss",
        url="",
        adapter_cls=RSSSourceAdapter,
        enabled=False,
        status="fallback_to_web_only",
        fetch_mode="web_only",
        max_items=0,
    ),
    WireSourceDef(
        product="ai",
        key="perplexity_blog",
        name="perplexity_blog",
        type="rss",
        url="",
        adapter_cls=RSSSourceAdapter,
        enabled=False,
        status="fallback_to_web_only",
        fetch_mode="web_only",
        max_items=0,
    ),
    WireSourceDef(
        product="ai",
        key="huggingface_blog",
        name="huggingface_blog",
        type="rss",
        url="https://huggingface.co/blog/feed.xml",
        adapter_cls=RSSSourceAdapter,
        max_items=3,
    ),
)


def get_wire_sources(product: str, source_key: str | None = None) -> list[WireSourceDef]:
    return [
        source
        for source in SOURCE_REGISTRY
        if source.product == product
        and source.fetch_mode == "base"
        and source.enabled
        and (not source_key or source.key == source_key)
    ]


def get_ai_source_audit() -> dict[str, dict[str, str | int | None]]:
    return {
        source.name: {
            "status": source.status,
            "url": source.url or None,
            "max_items": source.max_items,
            "fetch_mode": source.fetch_mode,
            "enabled": source.enabled,
        }
        for source in SOURCE_REGISTRY
        if source.product == "ai"
    }


def get_ai_source_cap(source_name: str) -> int:
    for source in SOURCE_REGISTRY:
        if source.product == "ai" and source.name == source_name:
            return source.max_items
    return 3

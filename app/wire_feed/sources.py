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


AI_SOURCE_AUDIT: dict[str, dict[str, str | int | None]] = {
    "openai_news": {"status": "keep", "url": "https://openai.com/news/rss.xml", "max_items": 4},
    "anthropic_news": {"status": "fallback_to_web_only", "url": None, "max_items": 0},
    "google_ai_blog": {"status": "keep", "url": "https://blog.google/technology/ai/rss/", "max_items": 3},
    "meta_ai_blog": {"status": "fallback_to_web_only", "url": None, "max_items": 0},
    "azure_ai_blog": {"status": "fallback_to_web_only", "url": None, "max_items": 0},
    "xai_news": {"status": "fallback_to_web_only", "url": None, "max_items": 0},
    "mistral_news": {"status": "fallback_to_web_only", "url": None, "max_items": 0},
    "cohere_blog": {"status": "fallback_to_web_only", "url": None, "max_items": 0},
    "perplexity_blog": {"status": "keep", "url": "https://www.perplexity.ai/hub/blog/rss.xml", "max_items": 3},
    "huggingface_blog": {"status": "keep", "url": "https://huggingface.co/blog/feed.xml", "max_items": 3},
}


WIRE_SOURCES: tuple[WireSourceDef, ...] = (
    WireSourceDef(
        product="finance",
        key="tradient",
        name="tradient_market_news",
        type="json",
        url="https://api.tradient.org/v1/api/market/news",
        adapter_cls=TradientMarketNewsAdapter,
    ),
    WireSourceDef(
        product="ai",
        key="openai_news",
        name="openai_news",
        type="rss",
        url="https://openai.com/news/rss.xml",
        adapter_cls=RSSSourceAdapter,
    ),
    WireSourceDef(
        product="ai",
        key="google_ai_blog",
        name="google_ai_blog",
        type="rss",
        url="https://blog.google/technology/ai/rss/",
        adapter_cls=RSSSourceAdapter,
    ),
    WireSourceDef(
        product="ai",
        key="huggingface_blog",
        name="huggingface_blog",
        type="rss",
        url="https://huggingface.co/blog/feed.xml",
        adapter_cls=RSSSourceAdapter,
    ),
)


def get_wire_sources(product: str, source_key: str | None = None) -> list[WireSourceDef]:
    return [source for source in WIRE_SOURCES if source.product == product and (not source_key or source.key == source_key)]


def get_ai_source_audit() -> dict[str, dict[str, str | int | None]]:
    return AI_SOURCE_AUDIT.copy()

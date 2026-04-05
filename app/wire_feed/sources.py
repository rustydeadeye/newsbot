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
        key="anthropic_news",
        name="anthropic_news",
        type="rss",
        url="https://www.anthropic.com/news/rss.xml",
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
        key="meta_ai_blog",
        name="meta_ai_blog",
        type="rss",
        url="https://ai.meta.com/blog/rss/",
        adapter_cls=RSSSourceAdapter,
    ),
    WireSourceDef(
        product="ai",
        key="azure_ai_blog",
        name="azure_ai_blog",
        type="rss",
        url="https://azure.microsoft.com/en-us/blog/topics/ai-machine-learning/feed/",
        adapter_cls=RSSSourceAdapter,
    ),
    WireSourceDef(
        product="ai",
        key="xai_news",
        name="xai_news",
        type="rss",
        url="https://x.ai/news/rss.xml",
        adapter_cls=RSSSourceAdapter,
    ),
    WireSourceDef(
        product="ai",
        key="mistral_news",
        name="mistral_news",
        type="rss",
        url="https://mistral.ai/news/rss.xml",
        adapter_cls=RSSSourceAdapter,
    ),
    WireSourceDef(
        product="ai",
        key="cohere_blog",
        name="cohere_blog",
        type="rss",
        url="https://cohere.com/blog/rss.xml",
        adapter_cls=RSSSourceAdapter,
    ),
    WireSourceDef(
        product="ai",
        key="perplexity_blog",
        name="perplexity_blog",
        type="rss",
        url="https://www.perplexity.ai/hub/blog/rss.xml",
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

from datetime import datetime, timezone

from app.wire_feed.pipeline import WirePipelineResult, fetch_and_process
from app.wire_feed.products import normalize_wire_product, policy_for_product
from app.wire_feed.sources import WireSourceDef, get_wire_sources
from app.wire_feed.web_pipeline import get_due_web_runs


def test_normalize_wire_product_defaults_to_finance() -> None:
    assert normalize_wire_product(None) == "finance"
    assert normalize_wire_product("unknown") == "finance"
    assert normalize_wire_product("ai") == "ai"


def test_policy_for_ai_product_uses_ai_caps() -> None:
    policy = policy_for_product("ai")

    assert policy.product == "ai"
    assert policy.max_posts_per_day == 10
    assert policy.base_max_posts_per_day == 4
    assert policy.web_max_posts_per_day == 6


def test_get_wire_sources_returns_ai_roster() -> None:
    sources = get_wire_sources("ai")
    names = {source.name for source in sources}

    assert "openai_news" in names
    assert "anthropic_news" in names
    assert "huggingface_blog" in names
    assert all(source.product == "ai" for source in sources)


def test_get_due_web_runs_supports_ai_lanes() -> None:
    now = datetime(2026, 4, 4, 8, 5, tzinfo=timezone.utc)  # 13:35 IST

    due = get_due_web_runs(now, lambda source_name, since: False, product="ai")

    assert [run.key for run in due] == ["product_updates", "industry_moves"]


def test_fetch_and_process_ai_source_uses_ai_strategy() -> None:
    class StubAdapter:
        def __init__(self, source):
            self.source = source

        def fetch(self):
            return [
                type(
                    "Fetched",
                    (),
                    {
                        "external_id": "launch-1",
                        "title": "OpenAI launches a lighter GPT model for developers",
                        "url": "https://example.com/openai-launch",
                        "published_at": datetime.now(timezone.utc),
                        "raw_payload": {"summary": "The release adds lower pricing and faster responses for API users."},
                    },
                )()
            ]

    class StubDrafting:
        def build_ai_wire_post(self, facts):
            return (
                "OpenAI launched a lighter GPT model with lower pricing and faster responses. That matters for teams trying to ship AI features more cheaply.",
                {},
                0.94,
            )

    source_def = WireSourceDef(
        key="openai_news",
        name="openai_news",
        type="rss",
        url="https://example.com/rss",
        adapter_cls=StubAdapter,
        product="ai",
    )

    results = fetch_and_process(source_def, StubDrafting())

    assert len(results) == 1
    result = results[0]
    assert isinstance(result, WirePipelineResult)
    assert result.product == "ai"
    assert result.source_family == "base"
    assert result.event_type in {"model_launch", "api_update", "product_update"}
    assert result.raw_payload["product"] == "ai"

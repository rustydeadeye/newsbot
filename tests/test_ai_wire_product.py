from datetime import datetime, timedelta, timezone

from app.wire_feed.pipeline import (
    WirePipelineResult,
    ai_quality_band,
    ai_readiness_assessment,
    fetch_and_process,
    generate_ai_evergreen_backlog_results,
)
from app.wire_feed.policy import WireFeedSettings, plan_wire_queue
from app.wire_feed.products import normalize_wire_product, policy_for_product
from app.wire_feed.sources import WireSourceDef, get_ai_source_audit, get_wire_sources
from app.wire_feed.web_pipeline import WebCandidate, _passes_lane_relevance_gate, get_due_web_runs


def test_normalize_wire_product_defaults_to_finance() -> None:
    assert normalize_wire_product(None) == "finance"
    assert normalize_wire_product("unknown") == "finance"
    assert normalize_wire_product("ai") == "ai"


def test_policy_for_ai_product_uses_ai_caps() -> None:
    import os
    from app.core.config import get_settings
    os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://dryrun:dryrun@localhost/dryrun")
    get_settings.cache_clear()
    policy = policy_for_product("ai")

    assert policy.product == "ai"
    assert policy.shadow_mode is True
    assert policy.max_posts_per_day == 10
    assert policy.base_max_posts_per_day == 4
    assert policy.web_max_posts_per_day == 6
    assert policy.future_queue_horizon_hours == 24


def test_ai_planning_recent_records_ignores_far_future_queue() -> None:
    from app.wire_feed.policy import WirePostRecord
    from app.wire_feed.runner import _planning_recent_records

    now = datetime(2026, 4, 16, 12, 0, tzinfo=timezone.utc)
    policy = policy_for_product("ai")
    records = [
        WirePostRecord(dedupe_key="posted|recent", posted_at=now - timedelta(hours=2), status="posted"),
        WirePostRecord(dedupe_key="queued|near", posted_at=now + timedelta(hours=6), status="queued"),
        WirePostRecord(dedupe_key="queued|far", posted_at=now + timedelta(days=7), status="queued"),
    ]

    filtered = _planning_recent_records(records, now, policy)

    dedupe_keys = {record.dedupe_key for record in filtered}
    assert dedupe_keys == {"posted|recent", "queued|near"}


def test_policy_for_ai_product_can_disable_shadow_mode(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://dryrun:dryrun@localhost/dryrun")
    monkeypatch.setenv("AI_SHADOW_MODE", "false")
    from app.core.config import get_settings
    get_settings.cache_clear()

    policy = policy_for_product("ai")

    assert policy.shadow_mode is False
    get_settings.cache_clear()


def test_policy_for_finance_product_raises_base_source_daily_cap() -> None:
    policy = policy_for_product("finance")

    assert policy.product == "finance"
    assert policy.max_posts_per_hour == 8
    assert policy.max_posts_per_day == 15
    assert policy.base_max_posts_per_day == 12


def test_db_engine_kwargs_use_explicit_pooling_for_postgres() -> None:
    from app.db.session import _engine_kwargs

    kwargs = _engine_kwargs("postgresql+psycopg://dryrun:dryrun@localhost/dryrun")

    assert kwargs["pool_pre_ping"] is True
    assert kwargs["pool_size"] == 10
    assert kwargs["max_overflow"] == 20
    assert kwargs["pool_timeout"] == 30
    assert kwargs["pool_recycle"] == 1800
    assert kwargs["pool_use_lifo"] is True


def test_db_engine_kwargs_leave_sqlite_untuned() -> None:
    from app.db.session import _engine_kwargs

    kwargs = _engine_kwargs("sqlite+pysqlite:///:memory:")

    assert kwargs == {"future": True, "pool_pre_ping": True}


def test_get_wire_sources_returns_ai_roster() -> None:
    sources = get_wire_sources("ai")
    names = {source.name for source in sources}
    audit = get_ai_source_audit()

    assert "openai_news" in names
    assert "huggingface_blog" in names
    assert "google_ai_blog" in names
    assert "anthropic_news" not in names
    assert "cohere_blog" not in names
    assert "meta_ai_blog" not in names
    assert audit["meta_ai_blog"]["status"] == "fallback_to_web_only"
    assert audit["anthropic_news"]["status"] == "fallback_to_web_only"
    assert audit["cohere_blog"]["status"] == "fallback_to_web_only"
    assert audit["perplexity_blog"]["status"] == "fallback_to_web_only"
    assert all(source.product == "ai" for source in sources)


def test_get_due_web_runs_supports_ai_lanes() -> None:
    now = datetime(2026, 4, 4, 8, 5, tzinfo=timezone.utc)  # 13:35 IST

    due = get_due_web_runs(now, lambda source_name, since: False, product="ai")

    assert [run.key for run in due] == ["ai_news", "ai_explained"]


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
        def build_ai_lane_post(self, facts, lane):
            if lane == "ai_explained":
                return (
                    "The bigger point is that lower pricing and faster responses make this update easier for teams to adopt in real products.",
                    {},
                    0.93,
                )
            if lane == "ai_for_business":
                return (
                    "For businesses, lower pricing and faster responses make it easier to ship AI features without raising operating costs.",
                    {},
                    0.92,
                )
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

    assert len(results) == 3
    lanes = {result.raw_payload["lane"] for result in results}
    assert lanes == {"ai_news", "ai_explained", "ai_for_business"}
    for result in results:
        assert isinstance(result, WirePipelineResult)
        assert result.product == "ai"
        assert result.source_family == "base"
        assert result.event_type in {"model_launch", "api_update", "product_update"}
        assert result.raw_payload["product"] == "ai"
        assert result.raw_payload["shadow_mode"] is True
        assert result.raw_payload["quality_band"] in {"A", "B"}
        assert result.raw_payload["topic_family"] == result.raw_payload["lane"]
        assert result.raw_payload["story_cluster"].startswith("openai|")
        assert result.raw_payload["seed_source_family"] == "base"
        assert result.raw_payload["seed_family"] in {"fresh_news", "recent_explainable", "recent_business"}
        assert result.raw_payload["seed_age_bucket"] in {"current", "recent", "recent_plus", "aged"}
        assert result.raw_payload["framework_id"]
        assert result.raw_payload["angle_hint"]
        assert result.raw_payload["is_recent"] is True


def test_fetch_and_process_ai_source_drops_c_band_items() -> None:
    class StubAdapter:
        def __init__(self, source):
            self.source = source

        def fetch(self):
            return [
                type(
                    "Fetched",
                    (),
                    {
                        "external_id": "weak-1",
                        "title": "AI industry update",
                        "url": "https://example.com/weak",
                        "published_at": datetime.now(timezone.utc),
                        "raw_payload": {"summary": "Momentum is building across the sector."},
                    },
                )()
            ]

    class StubDrafting:
        def build_ai_lane_post(self, facts, lane):
            return (
                "AI companies are seeing more momentum lately.",
                {},
                0.9,
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

    assert results == []


def test_fetch_and_process_ai_source_allows_recent_explained_and_business_beyond_news_window() -> None:
    class StubAdapter:
        def __init__(self, source):
            self.source = source

        def fetch(self):
            return [
                type(
                    "Fetched",
                    (),
                    {
                        "external_id": "pricing-1",
                        "title": "OpenAI updates team pricing for Codex",
                        "url": "https://example.com/codex-pricing",
                        "published_at": datetime.now(timezone.utc) - timedelta(days=5),
                        "raw_payload": {"summary": "The change affects pricing, billing, and how teams adopt Codex in workflows."},
                    },
                )()
            ]

    class StubDrafting:
        def build_ai_lane_post(self, facts, lane):
            if lane == "ai_explained":
                return ("This matters because pricing changes often reshape adoption faster than model hype.", {}, 0.93)
            if lane == "ai_for_business":
                return ("For teams, this changes workflow cost and adoption decisions more than the headline does.", {}, 0.93)
            return ("OpenAI changed Codex pricing for teams.", {}, 0.93)

    source_def = WireSourceDef(
        key="openai_news",
        name="openai_news",
        type="rss",
        url="https://example.com/rss",
        adapter_cls=StubAdapter,
        product="ai",
    )

    results = fetch_and_process(source_def, StubDrafting())

    lanes = {result.raw_payload["lane"] for result in results}
    assert lanes == {"ai_explained", "ai_for_business"}
    assert all(result.raw_payload["seed_age_bucket"] in {"recent_plus", "aged"} for result in results)


def test_generate_ai_evergreen_backlog_results_emits_non_news_content() -> None:
    class StubDrafting:
        def build_ai_lane_post(self, facts, lane):
            if lane == "ai_explained":
                return ("What matters is that workflow design usually fails before model quality does.", {}, 0.92)
            if lane == "ai_for_business":
                return ("For businesses, the better move is fixing one repeated workflow before buying more AI tools.", {}, 0.92)
            return ("AI workflow lesson.", {}, 0.92)

    results = generate_ai_evergreen_backlog_results(StubDrafting())

    assert results
    assert {result.raw_payload["seed_family"] for result in results} == {"evergreen_backlog"}
    assert all(result.raw_payload["is_evergreen"] is True for result in results)
    assert "ai_news" not in {result.raw_payload["lane"] for result in results}


def test_ai_quality_band_requires_concrete_change() -> None:
    assert (
        ai_quality_band(
            importance_score=90,
            confidence_score=0.9,
            draft_text="OpenAI launched GPT-Next with a 1M-token context window for developers.",
            title="OpenAI launches GPT-Next",
            body_text="The new model adds a 1M-token context window and lower API pricing.",
            event_type="model_launch",
            review_reason=None,
        )
        == "A"
    )
    assert (
        ai_quality_band(
            importance_score=90,
            confidence_score=0.9,
            draft_text="AI companies are seeing more momentum lately.",
            title="AI industry update",
            body_text="Momentum is building across the sector.",
            event_type="industry_move",
            review_reason=None,
        )
        == "C"
    )


def test_ai_readiness_assessment_returns_reason() -> None:
    band, reason = ai_readiness_assessment(
        importance_score=86,
        confidence_score=0.9,
        draft_text="OpenAI launched GPT-Next with lower API pricing for developers.",
        title="OpenAI launches GPT-Next",
        body_text="The new model lowers API pricing for developers.",
        event_type="api_update",
        review_reason=None,
        lane="ai_news",
    )

    assert band == "A"
    assert reason == "shadow_ready"


def test_plan_wire_queue_holds_ai_candidates_in_shadow_mode() -> None:
    import os
    from app.core.config import get_settings
    os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://dryrun:dryrun@localhost/dryrun")
    get_settings.cache_clear()
    candidate = WirePipelineResult(
        product="ai",
        external_id="ai-1",
        source_name="openai_news",
        source_family="base",
        title="OpenAI launches a developer update",
        event_type="model_launch",
        dedupe_key="ai|model_launch|openai-update",
        subject_key="openai-update",
        ticker=None,
        importance_score=90,
        confidence_score=0.9,
        would_auto_post=True,
        review_reason=None,
        draft_text="OpenAI launched a new model with lower pricing for developers.",
        safety_flags={"quality_band": "A"},
        raw_payload={"quality_band": "A"},
        published_at=datetime.now(timezone.utc),
    )

    decisions = plan_wire_queue([candidate], recent_posts=[], now=datetime.now(timezone.utc), settings=policy_for_product("ai"))

    assert decisions[0].action == "skip"
    assert decisions[0].reason == "shadow_mode_a"


def test_plan_wire_queue_respects_lane_aware_ai_freshness() -> None:
    now = datetime.now(timezone.utc)
    explained = WirePipelineResult(
        product="ai",
        external_id="ai-explained-1",
        source_name="openai_news",
        source_family="base",
        title="OpenAI updates team pricing for Codex",
        event_type="api_update",
        dedupe_key="ai|ai_explained|api_update|codex-pricing",
        subject_key="codex-pricing",
        ticker=None,
        importance_score=88,
        confidence_score=0.9,
        would_auto_post=False,
        review_reason=None,
        draft_text="The bigger point is that pricing changes often reshape adoption faster than model hype.",
        safety_flags={"quality_band": "A"},
        raw_payload={"quality_band": "A", "lane": "ai_explained", "product": "ai"},
        published_at=now - timedelta(days=5),
    )
    news = WirePipelineResult(
        product="ai",
        external_id="ai-news-1",
        source_name="openai_news",
        source_family="base",
        title="OpenAI updates team pricing for Codex",
        event_type="api_update",
        dedupe_key="ai|ai_news|api_update|codex-pricing",
        subject_key="codex-pricing",
        ticker=None,
        importance_score=88,
        confidence_score=0.9,
        would_auto_post=False,
        review_reason=None,
        draft_text="OpenAI changed Codex pricing for teams.",
        safety_flags={"quality_band": "A"},
        raw_payload={"quality_band": "A", "lane": "ai_news", "product": "ai"},
        published_at=now - timedelta(days=5),
    )

    settings = WireFeedSettings(product="ai", shadow_mode=False, high_ttl_hours=18, normal_ttl_hours=12)
    decisions = plan_wire_queue([explained, news], recent_posts=[], now=now, settings=settings)

    reasons = {decision.result.external_id: decision.reason for decision in decisions}
    actions = {decision.result.external_id: decision.action for decision in decisions}
    assert reasons["ai-news-1"] == "stale_candidate"
    assert actions["ai-explained-1"] in {"post_now", "queue"}


def test_ai_explained_lane_rejects_unrelated_world_news() -> None:
    candidate = WebCandidate(
        title="Iran tensions hit global shipping routes",
        summary="Fresh conflict worries are pushing freight costs higher.",
        source_name="Reuters",
        source_url="https://www.reuters.com/world/middle-east/example",
        published_at="2026-04-06T08:00:00Z",
        category="policy_regulation",
        india_impact="This matters for trade costs.",
        why_it_matters="Global shocks can feed through to costs.",
    )

    assert _passes_lane_relevance_gate(candidate, lane="ai_explained", product="ai") is False


def test_ai_explained_lane_accepts_regulator_led_ai_story_without_company_name() -> None:
    candidate = WebCandidate(
        title="EU AI Act guidance clarifies new obligations for general-purpose AI models",
        summary="European Commission guidance outlines how providers should handle compliance and transparency.",
        source_name="Reuters",
        source_url="https://www.reuters.com/world/europe/eu-ai-act-guidance-example",
        published_at="2026-04-06T08:00:00Z",
        category="policy_regulation",
        india_impact="This matters because AI rules can shape what companies can ship, how they train models, and what users can access.",
        why_it_matters="Policy moves can reshape AI competition, training data, deployment rules, and product roadmaps.",
    )

    assert _passes_lane_relevance_gate(candidate, lane="ai_explained", product="ai") is True

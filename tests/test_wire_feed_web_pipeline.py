from datetime import datetime, timezone

from app.wire_feed.web_pipeline import (
    AI_INDUSTRY_DOMAINS,
    AI_POLICY_DOMAINS,
    AI_PRODUCT_DOMAINS,
    WebCandidate,
    ValidationResult,
    _infer_category,
    _lane_domains,
    _parse_candidate,
    _passes_lane_relevance_gate,
    _passes_public_quality_gate,
    _select_web_candidates,
    get_due_web_runs,
)


def test_get_due_web_runs_returns_windows_not_yet_executed() -> None:
    now = datetime(2026, 4, 2, 11, 0, tzinfo=timezone.utc)  # 16:30 IST
    seen_since: list[tuple[str, datetime]] = []

    def has_run_since(source_name: str, since: datetime) -> bool:
        seen_since.append((source_name, since))
        return source_name == "tavily_web_india_preopen"

    due = get_due_web_runs(now, has_run_since)

    assert [run.key for run in due] == ["india_close"]
    assert seen_since[0][0] == "tavily_web_india_preopen"


def test_get_due_web_runs_waits_until_configured_minute() -> None:
    now = datetime(2026, 4, 2, 1, 40, tzinfo=timezone.utc)  # 07:10 IST

    due = get_due_web_runs(now, lambda source_name, since: False)

    assert due == []


def test_select_web_candidates_keeps_one_item_per_topic_cluster() -> None:
    recent = datetime(2026, 4, 2, 10, 0, tzinfo=timezone.utc)
    older = datetime(2026, 4, 2, 8, 0, tzinfo=timezone.utc)
    items = [
        (
            WebCandidate(
                title="Rupee jumps after RBI FX curbs",
                summary="Traders see unwinds and fresh onshore dollar sales.",
                source_name="Reuters",
                source_url="https://example.com/rupee-jumps",
                published_at="2026-04-02T10:00:00+00:00",
                category="rates_fx",
                india_impact="Stronger rupee helps imported inflation.",
                why_it_matters="FX moves affect inflation and hedging.",
            ),
            ValidationResult(approved=True, reasons=[], published_at=recent),
        ),
        (
            WebCandidate(
                title="RBI tightens rupee-speculation curbs",
                summary="New curbs target NDF and corporate arbitrage.",
                source_name="Reuters",
                source_url="https://example.com/rbi-curbs",
                published_at="2026-04-02T08:00:00+00:00",
                category="rates_fx",
                india_impact="Supports rupee but can disrupt hedging.",
                why_it_matters="Direct FX intervention can move USD/INR.",
            ),
            ValidationResult(approved=True, reasons=[], published_at=older),
        ),
        (
            WebCandidate(
                title="Wall Street ends higher on Middle East de-escalation hopes",
                summary="Large-cap tech led gains overnight.",
                source_name="Reuters",
                source_url="https://example.com/wall-street",
                published_at="2026-04-02T09:00:00+00:00",
                category="macro_market",
                india_impact="US risk sentiment spills into India.",
                why_it_matters="Global risk appetite affects FII flows.",
            ),
            ValidationResult(approved=True, reasons=[], published_at=recent),
        ),
    ]

    kept = _select_web_candidates(items, lane="global_impact")

    assert len(kept) == 2
    assert kept[0][0].title == "Rupee jumps after RBI FX curbs"
    assert kept[1][0].title == "Wall Street ends higher on Middle East de-escalation hopes"


def test_select_web_candidates_penalizes_weak_india_close_fit() -> None:
    recent = datetime(2026, 4, 3, 10, 0, tzinfo=timezone.utc)
    items = [
        (
            WebCandidate(
                title="SpaceX IPO buzz lifts aerospace shares on spillover bets - Reuters",
                summary="EchoStar jumped 5.7% and space ETFs rose 4.9%.",
                source_name="Reuters",
                source_url="https://example.com/spacex",
                published_at="2026-04-03T10:00:00+00:00",
                category="policy_regulation",
                india_impact="Could affect sentiment.",
                why_it_matters="Investors are watching spillover bets.",
            ),
            ValidationResult(approved=True, reasons=[], published_at=recent),
        ),
        (
            WebCandidate(
                title="Indian shares open lower after Trump dashes hopes of Iran war de-escalation - Reuters",
                summary="Nifty fell 1.3%, Sensex dropped 1.2%, and Brent rose 5%.",
                source_name="Reuters",
                source_url="https://example.com/india-open",
                published_at="2026-04-03T10:01:00+00:00",
                category="macro_market",
                india_impact="Oil and war worries can hit Indian markets fast.",
                why_it_matters="It changes the market narrative for India.",
            ),
            ValidationResult(approved=True, reasons=[], published_at=recent),
        ),
    ]

    kept = _select_web_candidates(items, lane="india_close", max_selected=2)

    assert kept[0][0].title == "Indian shares open lower after Trump dashes hopes of Iran war de-escalation - Reuters"


def test_public_quality_gate_rejects_robotic_or_insider_drafts() -> None:
    assert _passes_public_quality_gate(
        "Brent fell $1.16 to $100 and WTI slipped $1.41 to $98.71, which can cool inflation pressure if the move holds."
    )
    assert not _passes_public_quality_gate(
        "Markets reprices risk assets as positioning shifts across treasury books and volatility spikes."
    )


def test_ai_public_quality_gate_accepts_restriction_and_billing_updates() -> None:
    candidate = WebCandidate(
        title="Anthropic essentially bans OpenClaw from Claude by making subscribers pay extra - The Verge",
        summary="Anthropic will require separate pay-as-you-go billing for OpenClaw support from Claude subscribers starting April 4 at 3PM ET.",
        source_name="The Verge",
        source_url="https://example.com/openclaw",
        published_at="2026-04-06T08:00:00+00:00",
        category="policy_regulation",
        india_impact="This matters if users, teams, or developers get new models, tools, prices, or limits to work with.",
        why_it_matters="Product changes matter most when they alter capability, price, speed, or access.",
    )

    assert _passes_public_quality_gate(
        "Anthropic will stop Claude subscribers from using their plan limits with OpenClaw on April 4 at 3PM ET. Users will need separate pay-as-you-go billing, making third-party agent use more expensive.",
        candidate=candidate,
        product="ai",
        lane="ai_news",
    )


def test_ai_explained_quality_gate_accepts_takeaway_driven_draft() -> None:
    candidate = WebCandidate(
        title="EU AI Act guidance clarifies new obligations for general-purpose AI models",
        summary="European Commission guidance outlines how providers should handle compliance, transparency, and downstream model responsibilities.",
        source_name="Reuters",
        source_url="https://www.reuters.com/world/europe/eu-ai-act-guidance-example",
        published_at="2026-04-06T08:00:00+00:00",
        category="policy_regulation",
        india_impact="This matters because AI rules can shape what companies can ship, how they train models, and what users can access.",
        why_it_matters="Policy moves can reshape AI competition, training data, deployment rules, and product roadmaps.",
    )

    assert _passes_public_quality_gate(
        "The bigger point is that AI policy is getting more specific about who is responsible after a model ships. That matters because compliance and transparency are becoming product requirements, not just legal cleanup.",
        candidate=candidate,
        product="ai",
        lane="ai_explained",
    )


def test_ai_for_business_quality_gate_accepts_practical_operator_draft() -> None:
    candidate = WebCandidate(
        title="Private equity buyouts slump as AI fears and war dent dealmaking - Financial Times",
        summary="Private equity activity is slowing as investors reassess software businesses and risk exposure.",
        source_name="Ft",
        source_url="https://www.ft.com/content/example",
        published_at="2026-04-06T08:00:00+00:00",
        category="industry_move",
        india_impact="This matters because big AI deals and rollouts often signal where money, talent, and product demand are heading.",
        why_it_matters="Industry moves show which AI products and business models are gaining traction.",
    )

    assert _passes_public_quality_gate(
        "Private equity is slowing, which means operators will face tighter budgets and harder ROI questions. Teams using AI will need to show they can cut cost, save time, or improve workflow before spending gets easier again.",
        candidate=candidate,
        product="ai",
        lane="ai_for_business",
    )


def test_india_close_lane_gate_blocks_prediction_market_story() -> None:
    candidate = WebCandidate(
        title="Prediction markets challenge tribal casinos’ hard-won place in US gambling - AP News",
        summary="A fight over sports-style bets could squeeze casino profits.",
        source_name="Apnews",
        source_url="https://example.com/prediction-markets",
        published_at="2026-04-03T10:00:00+00:00",
        category="company_update",
        india_impact="This may matter to Indian markets if it changes sentiment.",
        why_it_matters="This is useful if it changes the market narrative.",
    )

    assert not _passes_lane_relevance_gate(candidate, lane="india_close")


def test_ai_news_lane_blocks_unrelated_world_news() -> None:
    candidate = WebCandidate(
        title="Zelenskiy in Syria to meet President Sharaa, sources say - Reuters",
        summary="Regional diplomacy talks continue amid wider conflict concerns.",
        source_name="Reuters",
        source_url="https://example.com/syria",
        published_at="2026-04-06T08:00:00+00:00",
        category="policy_regulation",
        india_impact="This matters because AI rules can shape what companies can ship, how they train models, and what users can access.",
        why_it_matters="Policy moves can reshape AI competition, training data, deployment rules, and product roadmaps.",
    )

    assert _passes_lane_relevance_gate(candidate, lane="ai_news", product="ai") is False


def test_ai_web_selection_keeps_distinct_news_stories_from_different_companies() -> None:
    recent = datetime(2026, 4, 6, 8, 0, tzinfo=timezone.utc)
    items = [
        (
            WebCandidate(
                title="OpenAI launches GPT feature for developers",
                summary="The update adds new API tools and pricing changes.",
                source_name="Reuters",
                source_url="https://example.com/openai-product",
                published_at="2026-04-06T08:00:00+00:00",
                category="product_update",
                india_impact="This matters if users, teams, or developers get new models, tools, prices, or limits to work with.",
                why_it_matters="Product changes matter most when they alter capability, price, speed, or access.",
            ),
            ValidationResult(approved=True, reasons=[], published_at=recent),
        ),
        (
            WebCandidate(
                title="Anthropic adds separate pay-as-you-go billing for OpenClaw support",
                summary="Claude subscribers will need separate billing for a popular agent workflow.",
                source_name="The Verge",
                source_url="https://example.com/anthropic-product",
                published_at="2026-04-06T08:05:00+00:00",
                category="product_update",
                india_impact="This matters if users, teams, or developers get new models, tools, prices, or limits to work with.",
                why_it_matters="Product changes matter most when they alter capability, price, speed, or access.",
            ),
            ValidationResult(approved=True, reasons=[], published_at=recent),
        ),
    ]

    kept = _select_web_candidates(items, lane="ai_news", product="ai", max_selected=5)

    assert len(kept) == 2


def test_ai_for_business_lane_accepts_company_expansion_story() -> None:
    candidate = WebCandidate(
        title="Britain woos Anthropic expansion after US defence clash, FT says - Reuters",
        summary="The UK is trying to attract more Anthropic investment and expansion work after friction over defence access in the US.",
        source_name="Reuters",
        source_url="https://www.reuters.com/world/uk/britain-woos-expansion-effort-by-anthropic-after-us-defence-clash-ft-says-2026-04-05/",
        published_at="2026-04-06T08:00:00+00:00",
        category="industry_move",
        india_impact="This matters because big AI deals and rollouts often signal where money, talent, and product demand are heading.",
        why_it_matters="Industry moves show which AI products and business models are gaining traction.",
    )

    assert _passes_lane_relevance_gate(candidate, lane="ai_for_business", product="ai") is True
    assert _passes_lane_relevance_gate(candidate, lane="ai_news", product="ai") is False


def test_ai_explained_lane_blocks_unrelated_world_policy_story() -> None:
    candidate = WebCandidate(
        title="Cuba frees prisoners under scrutiny of rights groups and U.S. - Reuters",
        summary="The move comes amid broader diplomatic pressure and human-rights criticism.",
        source_name="Reuters",
        source_url="https://example.com/cuba-prisoners",
        published_at="2026-04-06T08:00:00+00:00",
        category="policy_regulation",
        india_impact="This matters because AI rules can shape what companies can ship, how they train models, and what users can access.",
        why_it_matters="Policy moves can reshape AI competition, training data, deployment rules, and product roadmaps.",
    )

    assert _passes_lane_relevance_gate(candidate, lane="ai_explained", product="ai") is False


def test_ai_infer_category_treats_reuters_expansion_story_as_industry_move() -> None:
    category = _infer_category(
        "Britain woos Anthropic expansion after US defence clash, FT says - Reuters",
        "The UK is trying to attract more Anthropic investment and expansion work after friction over defence access in the US.",
        "https://www.reuters.com/world/uk/britain-woos-expansion-effort-by-anthropic-after-us-defence-clash-ft-says-2026-04-05/",
        product="ai",
    )

    assert category == "industry_move"


def test_ai_infer_category_treats_reuters_product_billing_story_as_product_update() -> None:
    category = _infer_category(
        "Anthropic says Claude Code subscribers will need to pay extra for OpenClaw support - TechCrunch",
        "Anthropic will require separate pay-as-you-go billing for OpenClaw support from Claude subscribers starting April 4.",
        "https://techcrunch.com/2026/04/04/anthropic-says-claude-code-subscribers-will-need-to-pay-extra-for-openclaw-support/",
        product="ai",
    )

    assert category == "product_update"


def test_ai_parse_candidate_prefers_local_category_over_tavily_label() -> None:
    candidate = _parse_candidate(
        {
            "title": "Anthropic says Claude Code subscribers will need to pay extra for OpenClaw support - TechCrunch",
            "summary": "Anthropic will require separate pay-as-you-go billing for OpenClaw support from Claude subscribers starting April 4.",
            "url": "https://techcrunch.com/2026/04/04/anthropic-says-claude-code-subscribers-will-need-to-pay-extra-for-openclaw-support/",
            "category": "industry_move",
        },
        product="ai",
    )

    assert candidate is not None
    assert candidate.category == "product_update"


def test_ai_lane_domains_follow_curated_source_policy() -> None:
    assert _lane_domains("ai_news", product="ai") == list(AI_PRODUCT_DOMAINS)
    assert "wired.com" in _lane_domains("ai_explained", product="ai")
    assert "reuters.com" in _lane_domains("ai_for_business", product="ai")


def test_ai_explained_lane_accepts_curated_policy_domain() -> None:
    candidate = WebCandidate(
        title="How Trump became tech's regulator-in-chief",
        summary="The White House is taking a larger role in AI policy debates and tech enforcement.",
        source_name="Ft",
        source_url="https://www.ft.com/content/example",
        published_at="2026-04-06T08:00:00+00:00",
        category="policy_regulation",
        india_impact="This matters because AI rules can shape what companies can ship, how they train models, and what users can access.",
        why_it_matters="Policy moves can reshape AI competition, training data, deployment rules, and product roadmaps.",
    )

    assert _passes_lane_relevance_gate(candidate, lane="ai_explained", product="ai") is True


def test_ai_explained_lane_allows_high_signal_trusted_reporting() -> None:
    candidate = WebCandidate(
        title="AI copyright fight grows as publishers push back on training data use",
        summary="OpenAI and Anthropic face fresh criticism over how model training uses copyrighted material.",
        source_name="Techcrunch",
        source_url="https://techcrunch.com/example/ai-copyright-fight",
        published_at="2026-04-06T08:00:00+00:00",
        category="policy_regulation",
        india_impact="This matters because AI rules can shape what companies can ship, how they train models, and what users can access.",
        why_it_matters="Policy moves can reshape AI competition, training data, deployment rules, and product roadmaps.",
    )

    assert _passes_lane_relevance_gate(candidate, lane="ai_explained", product="ai") is True

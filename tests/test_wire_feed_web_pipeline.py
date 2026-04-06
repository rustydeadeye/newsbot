from datetime import datetime, timezone

from app.wire_feed.web_pipeline import (
    WebCandidate,
    ValidationResult,
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


def test_ai_product_updates_lane_blocks_unrelated_world_news() -> None:
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

    assert _passes_lane_relevance_gate(candidate, lane="product_updates", product="ai") is False

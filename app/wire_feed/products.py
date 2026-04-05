from __future__ import annotations

from dataclasses import dataclass

from app.wire_feed.policy import WireFeedSettings

WIRE_PRODUCTS = {"finance", "ai"}


def normalize_wire_product(value: str | None) -> str:
    candidate = (value or "finance").strip().lower()
    if candidate not in WIRE_PRODUCTS:
        return "finance"
    return candidate


def display_wire_product(value: str | None) -> str:
    product = normalize_wire_product(value)
    return "AI" if product == "ai" else "Finance"


@dataclass(frozen=True)
class WireProductPolicy:
    product: str
    settings: WireFeedSettings


def policy_for_product(product: str) -> WireFeedSettings:
    normalized = normalize_wire_product(product)
    if normalized == "ai":
        return WireFeedSettings(
            product="ai",
            max_posts_per_hour=2,
            max_posts_per_day=10,
            base_max_posts_per_day=4,
            web_max_posts_per_day=6,
            breaking_gap_minutes=15,
            high_gap_minutes=60,
            normal_gap_minutes=90,
            duplicate_cooldown_minutes=360,
            high_ttl_hours=18,
            normal_ttl_hours=12,
        )
    return WireFeedSettings(product="finance")

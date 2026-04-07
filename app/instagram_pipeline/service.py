from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.instagram_pipeline.contracts import (
    INSTAGRAM_DEFAULT_SLIDE_COUNT,
    INSTAGRAM_LANE_DEFAULT_SLIDE_COUNTS,
    INSTAGRAM_LANE_REQUIRED_ROLES,
    INSTAGRAM_LANE_ROLE_SEQUENCES,
    INSTAGRAM_LANES,
    INSTAGRAM_MAX_SLIDES,
    INSTAGRAM_MIN_SLIDES,
    INSTAGRAM_SCHEMA_VERSION,
    INSTAGRAM_TEMPLATE_MAP,
    INSTAGRAM_TEMPLATE_VERSION,
    SOURCE_TRUTH_PRIORITY,
    TEXT_BUDGETS,
)
from app.models.customer import CustomerProfile
from app.models.instagram import InstagramCarouselDraft
from app.repositories.customers import CustomerProfileRepository
from app.repositories.instagram import InstagramCarouselDraftRepository
from app.services.drafting.service import DraftingService
from app.wire_feed.pipeline import WirePipelineResult, fetch_and_process
from app.wire_feed.sources import get_wire_sources
from app.wire_feed.web_pipeline import WEB_RUNS, fetch_web_breaking_candidates


@dataclass(frozen=True)
class InstagramTopicSeed:
    seed_key: str
    story_cluster: str
    title: str
    source_name: str
    source_family: str
    published_at: datetime | None
    lane_hint: str
    topic_tags: list[str]
    snippet: str
    company: str | None
    is_official: bool
    is_recent: bool
    is_product_update: bool
    is_business_relevant: bool
    is_explainer_friendly: bool
    event_type: str
    quality_band: str
    readiness_reason: str | None
    source_truth_tier: str
    seed_facts: dict


def generate_instagram_drafts_for_profile(
    db: Session,
    profile: CustomerProfile,
    *,
    limit_per_lane: int = 2,
    drafting: DraftingService | None = None,
) -> list[InstagramCarouselDraft]:
    draft_repo = InstagramCarouselDraftRepository(db)
    service = drafting or DraftingService(api_key=(profile.token_store or {}).get("openai_api_key"))
    seeds = collect_ai_topic_pool(profile, drafting=service)
    recent_clusters = draft_repo.list_recent_story_clusters(profile.id, within_days=7)
    drafts: list[InstagramCarouselDraft] = []
    for lane in INSTAGRAM_LANES:
        selected = select_instagram_topics(seeds, lane=lane, max_selected=limit_per_lane, recent_clusters=recent_clusters)
        for seed in selected:
            blueprint = build_instagram_blueprint(seed, lane=lane, drafting=service)
            validation = validate_instagram_blueprint(blueprint, lane=lane)
            if not validation["approved"]:
                continue
            draft = draft_repo.add(
                InstagramCarouselDraft(
                    customer_profile_id=profile.id,
                    lane=lane,
                    seed_key=seed.seed_key,
                    story_cluster=seed.story_cluster,
                    seed_source_name=seed.source_name,
                    seed_source_family=seed.source_family,
                    title=blueprint["title"],
                    angle=blueprint["angle"],
                    hook=blueprint["hook"],
                    carousel_type=blueprint["carousel_type"],
                    slide_count=blueprint["slide_count"],
                    slides=blueprint["slides"],
                    caption=blueprint["caption"],
                    review_status="pending_review",
                    quality_band=seed.quality_band,
                    generation_notes={
                        "selection_score": validation.get("selection_score"),
                        "validation_reasons": validation["reasons"],
                        "density_warnings": validation.get("density_warnings") or [],
                        "word_count": validation.get("word_count") or 0,
                        "safe_zone_ok": validation.get("safe_zone_ok", True),
                        "lane": lane,
                    },
                    template_bundle_version="instagram_template_bundle_v1",
                    template_version=INSTAGRAM_TEMPLATE_VERSION,
                    schema_version=INSTAGRAM_SCHEMA_VERSION,
                    render_status="render_pending",
                    asset_manifest={},
                    publish_status="draft",
                    raw_payload={
                        "seed_facts": seed.seed_facts,
                        "topic_tags": seed.topic_tags,
                        "readiness_reason": seed.readiness_reason,
                        "source_truth_tier": seed.source_truth_tier,
                    },
                )
            )
            recent_clusters.add(seed.story_cluster)
            drafts.append(draft)
    return drafts


def regenerate_instagram_draft(
    db: Session,
    draft: InstagramCarouselDraft,
    *,
    actor: str,
    drafting: DraftingService | None = None,
) -> InstagramCarouselDraft | None:
    profile = db.get(CustomerProfile, draft.customer_profile_id)
    if profile is None:
        return None
    seed_facts = dict((draft.raw_payload or {}).get("seed_facts") or {})
    if not seed_facts:
        return None
    service = drafting or DraftingService(api_key=(profile.token_store or {}).get("openai_api_key"))
    seed = InstagramTopicSeed(
        seed_key=draft.seed_key,
        story_cluster=draft.story_cluster,
        title=draft.title,
        source_name=draft.seed_source_name,
        source_family=draft.seed_source_family,
        published_at=None,
        lane_hint=draft.lane,
        topic_tags=list((draft.raw_payload or {}).get("topic_tags") or []),
        snippet=str(seed_facts.get("snippet") or seed_facts.get("article_text") or ""),
        company=seed_facts.get("company"),
        is_official=bool(seed_facts.get("is_official")),
        is_recent=bool(seed_facts.get("is_recent", True)),
        is_product_update=bool(seed_facts.get("is_product_update")),
        is_business_relevant=bool(seed_facts.get("is_business_relevant")),
        is_explainer_friendly=bool(seed_facts.get("is_explainer_friendly")),
        event_type=str(seed_facts.get("event_type") or draft.lane),
        quality_band=draft.quality_band or "B",
        readiness_reason=(draft.raw_payload or {}).get("readiness_reason"),
        source_truth_tier=str((draft.raw_payload or {}).get("source_truth_tier") or "secondary"),
        seed_facts=seed_facts,
    )
    blueprint = build_instagram_blueprint(seed, lane=draft.lane, drafting=service)
    validation = validate_instagram_blueprint(blueprint, lane=draft.lane)
    if not validation["approved"]:
        return None
    repo = InstagramCarouselDraftRepository(db)
    repo.supersede(draft, actor=actor)
    return repo.add(
        InstagramCarouselDraft(
            customer_profile_id=draft.customer_profile_id,
            lane=draft.lane,
            seed_key=draft.seed_key,
            story_cluster=draft.story_cluster,
            seed_source_name=draft.seed_source_name,
            seed_source_family=draft.seed_source_family,
            title=blueprint["title"],
            angle=blueprint["angle"],
            hook=blueprint["hook"],
            carousel_type=blueprint["carousel_type"],
            slide_count=blueprint["slide_count"],
            slides=blueprint["slides"],
            caption=blueprint["caption"],
            review_status="pending_review",
            quality_band=draft.quality_band,
            generation_notes={
                "selection_score": validation.get("selection_score"),
                "validation_reasons": validation["reasons"],
                "density_warnings": validation.get("density_warnings") or [],
                "word_count": validation.get("word_count") or 0,
                "safe_zone_ok": validation.get("safe_zone_ok", True),
                "regenerated_from_id": draft.id,
            },
            template_bundle_version=draft.template_bundle_version,
            template_version=INSTAGRAM_TEMPLATE_VERSION,
            schema_version=INSTAGRAM_SCHEMA_VERSION,
            render_status="render_pending",
            asset_manifest={},
            publish_status="draft",
            raw_payload=draft.raw_payload or {},
        )
    )


def collect_ai_topic_pool(profile: CustomerProfile, *, drafting: DraftingService) -> list[InstagramTopicSeed]:
    results: list[WirePipelineResult] = []
    for source_def in get_wire_sources("ai"):
        results.extend(fetch_and_process(source_def, drafting))
    token_store = profile.token_store or {}
    for run in WEB_RUNS:
        if run.product != "ai":
            continue
        results.extend(
            fetch_web_breaking_candidates(
                run,
                openai_api_key=token_store.get("openai_api_key"),
                tavily_api_key=token_store.get("tavily_api_key"),
            )
        )
    return _dedupe_and_normalize_seeds(results)


def select_instagram_topics(
    seeds: list[InstagramTopicSeed],
    *,
    lane: str,
    max_selected: int = 2,
    recent_clusters: set[str] | None = None,
) -> list[InstagramTopicSeed]:
    recent_clusters = recent_clusters or set()
    eligible = [seed for seed in seeds if seed.story_cluster not in recent_clusters and _lane_fit(seed, lane=lane)]
    ranked = sorted(eligible, key=lambda seed: (_instagram_topic_score(seed, lane=lane), seed.is_recent, seed.is_official), reverse=True)
    selected: list[InstagramTopicSeed] = []
    seen_clusters: set[str] = set()
    for seed in ranked:
        if seed.story_cluster in seen_clusters:
            continue
        selected.append(seed)
        seen_clusters.add(seed.story_cluster)
        if len(selected) >= max_selected:
            break
    return selected


def build_instagram_blueprint(seed: InstagramTopicSeed, *, lane: str, drafting: DraftingService) -> dict:
    facts = {**seed.seed_facts, "headline": seed.title, "lane": lane}
    prompt_version = INSTAGRAM_SCHEMA_VERSION
    builder = getattr(drafting, "build_instagram_carousel_blueprint", None)
    if callable(builder):
        blueprint = builder(facts, lane=lane)
    else:
        blueprint = _fallback_blueprint(seed, lane=lane)
    blueprint.setdefault("schema_version", prompt_version)
    blueprint.setdefault("template_version", INSTAGRAM_TEMPLATE_VERSION)
    blueprint.setdefault("title", seed.title)
    blueprint.setdefault("lane", lane)
    target_count = _resolve_slide_count(blueprint, lane=lane)
    selected_roles = _select_roles_for_lane(lane=lane, target_count=target_count, seed=seed)
    slides = []
    raw_slides = {str(slide.get("role") or ""): slide for slide in list(blueprint.get("slides") or []) if str(slide.get("role") or "")}
    for index, role in enumerate(selected_roles, start=1):
        slide = raw_slides.get(role, {})
        template_meta = INSTAGRAM_TEMPLATE_MAP.get(lane, {}).get(role, {})
        fallback_slide = _fallback_slide(seed, lane=lane, role=role)
        headline = str(slide.get("headline") or fallback_slide["headline"] or "").strip()
        support = str(slide.get("support") or fallback_slide["support"] or "").strip()
        slides.append(
            {
                "slide_number": index,
                "role": role,
                "headline": headline,
                "support": support,
                "template_id": slide.get("template_id") or template_meta.get("template_id"),
                "template_version": slide.get("template_version") or template_meta.get("template_version") or INSTAGRAM_TEMPLATE_VERSION,
                "schema_version": slide.get("schema_version") or INSTAGRAM_SCHEMA_VERSION,
                "layout_family": slide.get("layout_family") or template_meta.get("layout_family") or "interior_statement",
                "fields": dict(slide.get("fields") or {"headline": headline, "support": support}),
            }
        )
    blueprint["slides"] = slides
    blueprint["slide_count"] = len(slides)
    return blueprint


def validate_instagram_blueprint(blueprint: dict, *, lane: str) -> dict:
    reasons: list[str] = []
    warnings: list[str] = []
    hook = str(blueprint.get("hook") or "").strip()
    angle = str(blueprint.get("angle") or "").strip()
    slides = list(blueprint.get("slides") or [])
    if not hook:
        reasons.append("missing_hook")
    if not angle:
        reasons.append("missing_angle")
    if len(slides) < INSTAGRAM_MIN_SLIDES or len(slides) > INSTAGRAM_MAX_SLIDES:
        reasons.append("invalid_slide_count")
    expected_roles = list(INSTAGRAM_LANE_ROLE_SEQUENCES[lane])
    required_roles = set(INSTAGRAM_LANE_REQUIRED_ROLES[lane])
    actual_roles = [str(slide.get("role") or "") for slide in slides]
    if not _is_role_subsequence(actual_roles, expected_roles):
        reasons.append("slide_sequence_mismatch")
    if len(set(actual_roles)) != len(actual_roles):
        reasons.append("duplicate_slide_roles")
    if not required_roles.issubset(set(actual_roles)):
        reasons.append("missing_required_roles")
    slide_metrics: list[dict] = []
    for slide in slides:
        role = str(slide.get("role") or "")
        headline = str(slide.get("headline") or "").strip()
        support = str(slide.get("support") or "").strip()
        role_budget = TEXT_BUDGETS.get(role, TEXT_BUDGETS["default"])
        word_count = _word_count(headline) + _word_count(support)
        slide_metrics.append({"slide_number": int(slide.get("slide_number") or 0), "role": role, "word_count": word_count})
        if not headline or len(headline) > role_budget["headline"]:
            reasons.append(f"headline_budget:{role}")
        if role == "hook":
            if support:
                reasons.append("hook_has_body_copy")
        elif not support or len(support) > role_budget["support"]:
            reasons.append(f"support_budget:{role}")
        if word_count > int(role_budget.get("words", TEXT_BUDGETS["default"]["words"])):
            reasons.append(f"word_budget:{role}")
        elif word_count > max(15, int(role_budget.get("words", TEXT_BUDGETS["default"]["words"])) - 4):
            warnings.append(f"dense_copy:{role}")
        if role == "closing_cta":
            closing_text = f"{headline} {support}".lower()
            if "@" not in closing_text:
                reasons.append("closing_missing_handle")
            if not any(term in closing_text for term in ("save", "follow", "share", "send", "keep")):
                reasons.append("closing_missing_cta")
    caption = dict(blueprint.get("caption") or {})
    if len(str(caption.get("hook") or "")) > TEXT_BUDGETS["caption"]["hook"]:
        reasons.append("caption_hook_budget")
    if len(str(caption.get("body") or "")) > TEXT_BUDGETS["caption"]["body"]:
        reasons.append("caption_body_budget")
    if len(str(caption.get("cta") or "")) > TEXT_BUDGETS["caption"]["cta"]:
        reasons.append("caption_cta_budget")
    takeaway_terms = {
        "ai_news": ("matters", "affects", "changes"),
        "ai_explained": ("means", "matters", "really", "takeaway"),
        "ai_for_business": ("workflow", "time", "cost", "team", "business"),
    }
    support_text = " ".join(str(slide.get("support") or "") for slide in slides).lower()
    if not any(term in support_text for term in takeaway_terms[lane]):
        reasons.append("missing_distinct_takeaway")
    return {
        "approved": not reasons,
        "reasons": reasons,
        "warnings": warnings,
        "word_count": sum(metric["word_count"] for metric in slide_metrics),
        "slide_metrics": slide_metrics,
        "density_warnings": warnings,
        "safe_zone_ok": True,
        "selection_score": max(0, 100 - (len(reasons) * 12)),
    }


def serialize_instagram_draft(draft: InstagramCarouselDraft) -> dict:
    return {
        "id": draft.id,
        "customer_profile_id": draft.customer_profile_id,
        "lane": draft.lane,
        "seed_key": draft.seed_key,
        "story_cluster": draft.story_cluster,
        "seed_source_name": draft.seed_source_name,
        "seed_source_family": draft.seed_source_family,
        "title": draft.title,
        "angle": draft.angle,
        "hook": draft.hook,
        "carousel_type": draft.carousel_type,
        "slide_count": draft.slide_count,
        "slides": draft.slides,
        "caption": draft.caption,
        "review_status": draft.review_status,
        "review_notes": draft.review_notes,
        "reviewed_by": draft.reviewed_by,
        "reviewed_at": draft.reviewed_at.isoformat() if draft.reviewed_at else None,
        "quality_band": draft.quality_band,
        "generation_notes": draft.generation_notes,
        "word_count": int((draft.generation_notes or {}).get("word_count") or 0),
        "density_warnings": list((draft.generation_notes or {}).get("density_warnings") or []),
        "safe_zone_ok": bool((draft.generation_notes or {}).get("safe_zone_ok", True)),
        "template_bundle_version": draft.template_bundle_version,
        "template_version": draft.template_version,
        "schema_version": draft.schema_version,
        "render_status": draft.render_status,
        "asset_manifest": draft.asset_manifest,
        "preview_slides": list((draft.asset_manifest or {}).get("slides") or []),
        "publish_status": draft.publish_status,
        "scheduled_for": draft.scheduled_for.isoformat() if draft.scheduled_for else None,
        "published_at": draft.published_at.isoformat() if draft.published_at else None,
        "instagram_media_container_id": draft.instagram_media_container_id,
        "instagram_publish_id": draft.instagram_publish_id,
        "last_error": draft.last_error,
        "render_attempt_count": draft.render_attempt_count,
        "publish_attempt_count": draft.publish_attempt_count,
        "created_at": draft.created_at.isoformat() if draft.created_at else None,
        "updated_at": draft.updated_at.isoformat() if draft.updated_at else None,
    }


def list_instagram_generation_profiles(db: Session) -> list[CustomerProfile]:
    repo = CustomerProfileRepository(db)
    candidates = repo.list_eligible_for_background_generation()
    return [
        profile
        for profile in candidates
        if profile.wire_product == "ai" and bool((profile.token_store or {}).get("openai_api_key"))
    ]


def _dedupe_and_normalize_seeds(results: list[WirePipelineResult]) -> list[InstagramTopicSeed]:
    grouped: dict[str, list[WirePipelineResult]] = {}
    for result in results:
        if result.fetch_error or result.product != "ai" or not (result.title or "").strip():
            continue
        raw_payload = result.raw_payload or {}
        if result.review_reason == "quality_band_c" or raw_payload.get("review_reason") == "no_approved_candidates":
            continue
        seed_facts = dict(raw_payload.get("seed_facts") or {})
        cluster = str(raw_payload.get("story_cluster") or raw_payload.get("seed_key") or result.dedupe_key or result.external_id)
        grouped.setdefault(cluster, []).append(result)
        if seed_facts:
            continue
    seeds: list[InstagramTopicSeed] = []
    for cluster, group in grouped.items():
        canonical = sorted(group, key=_canonical_result_rank, reverse=True)[0]
        payload = canonical.raw_payload or {}
        seed_facts = dict(payload.get("seed_facts") or {})
        title = canonical.title or str(seed_facts.get("headline") or "AI update")
        source_name = canonical.source_name
        source_family = canonical.source_family
        published_at = canonical.published_at
        topic_tags = list(payload.get("topic_tags") or seed_facts.get("topic_tags") or [])
        seeds.append(
            InstagramTopicSeed(
                seed_key=str(payload.get("seed_key") or canonical.subject_key or canonical.external_id),
                story_cluster=cluster,
                title=title,
                source_name=source_name,
                source_family=source_family,
                published_at=published_at,
                lane_hint=str(payload.get("lane") or "ai_news"),
                topic_tags=topic_tags,
                snippet=str(seed_facts.get("snippet") or seed_facts.get("article_text") or canonical.draft_text or ""),
                company=seed_facts.get("company"),
                is_official=bool(seed_facts.get("is_official")),
                is_recent=bool(seed_facts.get("is_recent", _is_recent(published_at, hours=120))),
                is_product_update=bool(seed_facts.get("is_product_update")),
                is_business_relevant=bool(seed_facts.get("is_business_relevant")),
                is_explainer_friendly=bool(seed_facts.get("is_explainer_friendly")),
                event_type=canonical.event_type,
                quality_band=str(payload.get("quality_band") or "B"),
                readiness_reason=payload.get("readiness_reason"),
                source_truth_tier=_source_truth_tier(seed_facts, source_name=source_name, source_family=source_family),
                seed_facts={
                    **seed_facts,
                    "headline": title,
                    "event_type": canonical.event_type,
                    "topic_tags": topic_tags,
                    "source_name": source_name,
                    "source_family": source_family,
                },
            )
        )
    return seeds


def _canonical_result_rank(result: WirePipelineResult) -> tuple[int, int, int, int]:
    payload = result.raw_payload or {}
    seed_facts = dict(payload.get("seed_facts") or {})
    tier = _source_truth_tier(seed_facts, source_name=result.source_name, source_family=result.source_family)
    published_score = int(result.published_at.timestamp()) if result.published_at else 0
    band_rank = {"A": 3, "B": 2, "C": 1}.get(str(payload.get("quality_band") or "C"), 0)
    return (
        SOURCE_TRUTH_PRIORITY.get(tier, 0),
        band_rank,
        int(result.importance_score),
        published_score,
    )


def _source_truth_tier(seed_facts: dict, *, source_name: str, source_family: str) -> str:
    if seed_facts.get("is_official"):
        return "official"
    lowered_source = source_name.lower()
    if any(domain in lowered_source for domain in ("reuters", "bloomberg", "ft", "verge", "techcrunch", "wired")):
        return "trusted_press"
    if source_family == "web":
        return "business_press"
    return "secondary"


def _lane_fit(seed: InstagramTopicSeed, *, lane: str) -> bool:
    seed_facts = dict(seed.seed_facts or {})
    news_fresh = bool(seed_facts.get("is_news_fresh", seed.is_recent))
    explained_fresh = bool(seed_facts.get("is_explained_fresh", seed.is_recent))
    business_fresh = bool(seed_facts.get("is_business_fresh", seed.is_recent))
    is_evergreen = bool(seed_facts.get("is_evergreen"))
    if lane == "ai_news":
        return news_fresh and (seed.is_product_update or seed.event_type in {"policy_regulation", "model_launch", "api_update", "product_update"})
    if lane == "ai_explained":
        return seed.is_explainer_friendly and (explained_fresh or is_evergreen)
    if lane == "ai_for_business":
        return seed.is_business_relevant and (business_fresh or is_evergreen)
    return False


def _instagram_topic_score(seed: InstagramTopicSeed, *, lane: str) -> int:
    score = 0
    if seed.is_official:
        score += 25
    if seed.is_recent:
        score += 20
    if lane == "ai_news" and seed.is_product_update:
        score += 25
    if lane == "ai_explained" and seed.is_explainer_friendly:
        score += 25
    if lane == "ai_for_business" and seed.is_business_relevant:
        score += 25
    if seed.quality_band == "A":
        score += 15
    elif seed.quality_band == "B":
        score += 8
    if "pricing" in seed.topic_tags or "workflow" in seed.topic_tags:
        score += 8
    if len(seed.snippet) > 80:
        score += 6
    return score


def _is_recent(published_at: datetime | None, *, hours: int) -> bool:
    if published_at is None:
        return False
    return published_at >= datetime.now(timezone.utc) - timedelta(hours=hours)


def _fallback_blueprint(seed: InstagramTopicSeed, lane: str) -> dict:
    title = seed.title.strip()
    company = (seed.company or "AI").strip()
    snippet = re.sub(r"\s+", " ", seed.snippet).strip()
    lanes = {
        "ai_news": {
            "angle": "What changed and why it matters right now",
            "hook": f"What changed with {company}?",
            "carousel_type": "news_breakdown",
            "slides": {
                "hook": (title, ""),
                "what_changed": ("WHAT CHANGED", snippet or "A concrete AI update just changed how the product works."),
                "why_now": ("WHY NOW", "This matters because AI adoption moves when friction drops or access expands."),
                "evidence": ("THE STRONGEST SIGNAL", "Watch the pricing, rollout, limit, or access change. That is the real signal."),
                "who_it_affects": ("WHO FEELS IT FIRST", "Builders, product teams, and power users usually feel the shift before everyone else."),
                "implication": ("WHAT HAPPENS NEXT", "A small product change can reshape usage faster than a flashy launch."),
                "key_takeaway": ("KEY TAKEAWAY", "The win is not the announcement. The win is what changes in actual use."),
                "closing_cta": ("@newsbot", "Save this and follow @newsbot for sharper AI breakdowns."),
            },
        },
        "ai_explained": {
            "angle": "Explain the bigger meaning behind the update",
            "hook": f"What most people miss about {company}",
            "carousel_type": "explainer_breakdown",
            "slides": {
                "hook": (title, ""),
                "myth": ("THE DEFAULT READ", "Most people stop at the announcement and miss the shift underneath."),
                "reality": ("WHAT IS ACTUALLY CHANGING", snippet or "The real change is in how the product gets used."),
                "evidence": ("THE EVIDENCE", "Look at pricing, access, workflow fit, or new constraints users now face."),
                "counter_argument": ("WHAT PEOPLE WILL SAY", "It can look like a small update. It rarely stays small once behavior changes."),
                "deeper_meaning": ("WHAT THIS REALLY MEANS", "The bigger story is about adoption, trust, distribution, or cost."),
                "key_takeaway": ("KEY TAKEAWAY", "The headline matters less than the behavior this unlocks or restricts."),
                "closing_cta": ("@newsbot", "Save this for the next time an AI launch sounds bigger than it is."),
            },
        },
        "ai_for_business": {
            "angle": "Turn the update into a practical business lesson",
            "hook": f"What businesses should learn from {company}",
            "carousel_type": "business_playbook",
            "slides": {
                "hook": (title, ""),
                "pain_point": ("THE OPERATOR PROBLEM", "Most teams still lose time to repetitive work, review loops, and manual handoffs."),
                "mistake": ("THE COMMON MISTAKE", "Buying more AI tools without fixing the workflow usually creates more noise."),
                "evidence": ("THE PRACTICAL SIGNAL", snippet or "The strongest signal is whether teams can use the change inside real work."),
                "better_way": ("THE BETTER QUESTION", "Ask if it changes speed, cost, quality, or adoption for a real team."),
                "workflow": ("WHERE THIS FITS", "The best use cases show up in repeated workflows, not one-off demos."),
                "outcome": ("WHAT GOOD LOOKS LIKE", "Saved time, lower cost, and fewer broken handoffs are the real outcome."),
                "closing_cta": ("@newsbot", "Save this if you want AI ideas that actually help operators."),
            },
        },
    }[lane]
    target_count = INSTAGRAM_LANE_DEFAULT_SLIDE_COUNTS.get(lane, INSTAGRAM_DEFAULT_SLIDE_COUNT)
    selected_roles = _select_roles_for_lane(lane=lane, target_count=target_count, seed=seed)
    slides = []
    for idx, role in enumerate(selected_roles, start=1):
        headline_seed, support_seed = lanes["slides"][role]
        budget = TEXT_BUDGETS.get(role, TEXT_BUDGETS["default"])
        headline = _trim_text(headline_seed, budget["headline"])
        support = _trim_text(support_seed, budget["support"])
        template_meta = INSTAGRAM_TEMPLATE_MAP[lane][role]
        slides.append(
            {
                "slide_number": idx,
                "role": role,
                "headline": headline,
                "support": support,
                "template_id": template_meta["template_id"],
                "template_version": template_meta["template_version"],
                "schema_version": INSTAGRAM_SCHEMA_VERSION,
                "layout_family": template_meta["layout_family"],
                "fields": {"headline": headline, "support": support},
            }
        )
    return {
        "title": title,
        "lane": lane,
        "angle": lanes["angle"],
        "hook": _trim_text(lanes["hook"], TEXT_BUDGETS["caption"]["hook"]),
        "carousel_type": lanes["carousel_type"],
        "slide_count": len(slides),
        "slides": slides,
        "caption": {
            "hook": _trim_text(lanes["hook"], TEXT_BUDGETS["caption"]["hook"]),
            "body": _trim_text(f"{title}. {snippet or lanes['angle']}", TEXT_BUDGETS["caption"]["body"]),
            "cta": "Save this and follow @newsbot for sharper AI breakdowns.",
        },
    }


def _resolve_slide_count(blueprint: dict, *, lane: str) -> int:
    requested = blueprint.get("slide_count")
    try:
        requested_count = int(requested) if requested is not None else INSTAGRAM_LANE_DEFAULT_SLIDE_COUNTS.get(lane, INSTAGRAM_DEFAULT_SLIDE_COUNT)
    except (TypeError, ValueError):
        requested_count = INSTAGRAM_LANE_DEFAULT_SLIDE_COUNTS.get(lane, INSTAGRAM_DEFAULT_SLIDE_COUNT)
    requested_count = max(INSTAGRAM_MIN_SLIDES, min(INSTAGRAM_MAX_SLIDES, requested_count))
    required_count = len(INSTAGRAM_LANE_REQUIRED_ROLES[lane])
    return max(requested_count, required_count)


def _select_roles_for_lane(*, lane: str, target_count: int, seed: InstagramTopicSeed) -> list[str]:
    sequence = list(INSTAGRAM_LANE_ROLE_SEQUENCES[lane])
    required_roles = list(INSTAGRAM_LANE_REQUIRED_ROLES[lane])
    optional_roles = [role for role in sequence if role not in required_roles]

    prioritized_optional = list(optional_roles)
    if lane == "ai_news":
        if not seed.is_official and "evidence" in prioritized_optional:
            prioritized_optional = ["evidence"] + [role for role in prioritized_optional if role != "evidence"]
    elif lane == "ai_explained":
        if seed.snippet and "evidence" in prioritized_optional:
            prioritized_optional = ["myth", "evidence", "counter_argument", "key_takeaway"]
    elif lane == "ai_for_business":
        prioritized_optional = ["mistake", "evidence", "workflow", "outcome"]

    selected = {"hook", "closing_cta", *required_roles}
    for role in prioritized_optional:
        if len(selected) >= target_count:
            break
        selected.add(role)

    return [role for role in sequence if role in selected][:target_count]


def _fallback_slide(seed: InstagramTopicSeed, *, lane: str, role: str) -> dict[str, str]:
    blueprint = _fallback_blueprint(seed, lane)
    for slide in blueprint["slides"]:
        if slide["role"] == role:
            return {"headline": str(slide["headline"] or ""), "support": str(slide["support"] or "")}
    return {"headline": "", "support": ""}


def _is_role_subsequence(actual_roles: list[str], expected_roles: list[str]) -> bool:
    iterator = iter(expected_roles)
    for role in actual_roles:
        for expected in iterator:
            if expected == role:
                break
        else:
            return False
    return True


def _trim_text(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if len(text) <= limit:
        return text
    truncated = text[: limit - 1].rstrip()
    if " " in truncated:
        truncated = truncated.rsplit(" ", 1)[0]
    return truncated.rstrip(" ,;:-") + "…"


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w@'-]+\b", text or ""))

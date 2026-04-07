from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.instagram_pipeline.runtime import publish_instagram_job, render_instagram_draft, schedule_instagram_draft
from app.instagram_pipeline.service import (
    InstagramTopicSeed,
    generate_instagram_drafts_for_profile,
    regenerate_instagram_draft,
    select_instagram_topics,
    validate_instagram_blueprint,
)
from app.models.access import WorkspaceUser
from app.models.customer import CustomerProfile
from app.models.instagram import InstagramCarouselDraft
from app.repositories.instagram import InstagramCarouselDraftRepository


class StubDrafting:
    def build_instagram_carousel_blueprint(self, facts: dict, lane: str) -> dict:
        title = str(facts.get("headline") or "AI update")
        if lane == "ai_explained":
            roles = [
                ("hook", title, ""),
                ("myth", "THE DEFAULT READ", "Most readers overfocus on the announcement."),
                ("reality", "WHAT IS ACTUALLY CHANGING", "The real shift is in how the change gets used."),
                ("evidence", "THE EVIDENCE", "The strongest signal is pricing, access, or workflow fit."),
                ("counter_argument", "WHAT PEOPLE WILL SAY", "It can look small, but behavior changes compound."),
                ("deeper_meaning", "WHAT THIS REALLY MEANS", "It changes adoption, trust, or distribution."),
                ("key_takeaway", "KEY TAKEAWAY", "The meaning behind the update matters more than the headline."),
                ("closing_cta", "@newsbot", "Save this and follow @newsbot for cleaner AI breakdowns."),
            ]
        elif lane == "ai_for_business":
            roles = [
                ("hook", title, ""),
                ("pain_point", "THE PAIN POINT", "Teams still waste time on repeated work."),
                ("mistake", "THE MISTAKE", "Most companies chase tools before workflows."),
                ("evidence", "THE EVIDENCE", "The useful signal is where teams can apply the change."),
                ("better_way", "THE BETTER WAY", "Start with the business bottleneck."),
                ("workflow", "THE WORKFLOW", "Use the change where it saves time or effort."),
                ("outcome", "THE OUTCOME", "Look for time saved, lower cost, or better reliability."),
                ("closing_cta", "@newsbot", "Save this if you want AI ideas that help operators."),
            ]
        else:
            roles = [
                ("hook", title, ""),
                ("what_changed", "WHAT CHANGED", str(facts.get("article_text") or "The product changed in a concrete way.")),
                ("why_now", "WHY NOW", "This matters because AI adoption moves when friction drops."),
                ("evidence", "THE SIGNAL", "Focus on the new pricing, rollout, or limit."),
                ("who_it_affects", "WHO IT AFFECTS", "The first impact lands on builders, teams, or users."),
                ("implication", "WHAT HAPPENS NEXT", "A small product change can shift real usage."),
                ("key_takeaway", "KEY TAKEAWAY", "The update matters because it changes real usage."),
                ("closing_cta", "@newsbot", "Save this and follow @newsbot for sharper AI updates."),
            ]
        slides = [
            {"slide_number": idx, "role": role, "headline": headline, "support": support}
            for idx, (role, headline, support) in enumerate(roles, start=1)
        ]
        return {
            "title": title,
            "hook": roles[0][1],
            "angle": f"{lane} angle",
            "carousel_type": f"{lane}_carousel",
            "slide_count": len(slides),
            "slides": slides,
            "caption": {
                "hook": roles[0][1],
                "body": str(facts.get("article_text") or title),
                "cta": "Save this if you want the useful version.",
            },
        }


def _make_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def _seed(
    *,
    lane_hint: str = "ai_news",
    story_cluster: str = "openai|pricing",
    title: str = "OpenAI updates API pricing",
    snippet: str = "The update lowers price and changes access for teams.",
    is_product_update: bool = True,
    is_business_relevant: bool = True,
    is_explainer_friendly: bool = True,
) -> InstagramTopicSeed:
    now = datetime.now(timezone.utc)
    return InstagramTopicSeed(
        seed_key=story_cluster,
        story_cluster=story_cluster,
        title=title,
        source_name="openai_news",
        source_family="base",
        published_at=now,
        lane_hint=lane_hint,
        topic_tags=["pricing", "workflow"],
        snippet=snippet,
        company="OpenAI",
        is_official=True,
        is_recent=True,
        is_product_update=is_product_update,
        is_business_relevant=is_business_relevant,
        is_explainer_friendly=is_explainer_friendly,
        event_type="api_update",
        quality_band="A",
        readiness_reason="shadow_ready",
        source_truth_tier="official",
        seed_facts={
            "headline": title,
            "article_text": snippet,
            "snippet": snippet,
            "company": "OpenAI",
            "topic_tags": ["pricing", "workflow"],
            "is_official": True,
            "is_recent": True,
            "is_product_update": is_product_update,
            "is_business_relevant": is_business_relevant,
            "is_explainer_friendly": is_explainer_friendly,
        },
    )


def test_select_instagram_topics_dedupes_story_clusters_and_prefers_explainer_fit() -> None:
    seeds = [
        _seed(story_cluster="openai|pricing", lane_hint="ai_news"),
        _seed(story_cluster="openai|pricing", title="Duplicate pricing story"),
        _seed(
            story_cluster="policy|infrastructure",
            lane_hint="ai_explained",
            title="AI infrastructure is becoming the real bottleneck",
            snippet="The bigger issue is power, water, and deployment friction.",
            is_product_update=False,
            is_business_relevant=False,
            is_explainer_friendly=True,
        ),
    ]

    selected = select_instagram_topics(seeds, lane="ai_explained", max_selected=3)

    assert len(selected) == 2
    assert len({seed.story_cluster for seed in selected}) == 2
    assert selected[0].story_cluster == "openai|pricing"


def test_validate_instagram_blueprint_rejects_duplicate_roles_and_budget_overflow() -> None:
    blueprint = {
        "hook": "Useful hook",
        "angle": "Clear angle",
        "slides": [
            {"slide_number": 1, "role": "hook", "headline": "Headline", "support": "Support"},
            {"slide_number": 2, "role": "hook", "headline": "Headline", "support": "x" * 200},
            {"slide_number": 3, "role": "reality", "headline": "Headline", "support": "Support"},
            {"slide_number": 4, "role": "evidence", "headline": "Headline", "support": "Support"},
            {"slide_number": 5, "role": "counter_argument", "headline": "Headline", "support": "Support"},
            {"slide_number": 6, "role": "deeper_meaning", "headline": "Headline", "support": "Support"},
            {"slide_number": 7, "role": "key_takeaway", "headline": "Headline", "support": "Support"},
            {"slide_number": 8, "role": "closing_cta", "headline": "Headline", "support": "Support"},
        ],
        "caption": {"hook": "h", "body": "b", "cta": "c"},
    }

    validation = validate_instagram_blueprint(blueprint, lane="ai_news")

    assert validation["approved"] is False
    assert "duplicate_slide_roles" in validation["reasons"]
    assert "hook_has_body_copy" in validation["reasons"]


def test_generate_instagram_drafts_for_profile_persists_pending_review_items(monkeypatch) -> None:
    db = _make_session()
    db.add(WorkspaceUser(id=1, auth_user_id="user-1", email="user-1@example.com", role="customer"))
    profile = CustomerProfile(
        workspace_user_id=1,
        display_name="AI Test",
        wire_product="ai",
        automation_mode="auto_generate_manual_review",
        onboarding_completed_at=datetime.now(timezone.utc),
        token_store={"openai_api_key": "test-key"},
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)

    monkeypatch.setattr(
        "app.instagram_pipeline.service.collect_ai_topic_pool",
        lambda profile, drafting: [
            _seed(story_cluster="openai|pricing", lane_hint="ai_news"),
            _seed(
                story_cluster="ai|infra",
                lane_hint="ai_explained",
                title="AI infrastructure is the real bottleneck",
                snippet="Infrastructure, power, and local pushback matter more now.",
                is_product_update=False,
                is_business_relevant=False,
                is_explainer_friendly=True,
            ),
            _seed(
                story_cluster="openai|workflow",
                lane_hint="ai_for_business",
                title="Teams can now automate reporting with lower friction",
                snippet="The update lowers adoption friction for internal workflows.",
                is_product_update=False,
                is_business_relevant=True,
                is_explainer_friendly=True,
            ),
        ],
    )

    drafts = generate_instagram_drafts_for_profile(db, profile, limit_per_lane=1, drafting=StubDrafting())

    assert len(drafts) == 3
    assert {draft.lane for draft in drafts} == {"ai_news", "ai_explained", "ai_for_business"}
    assert all(draft.review_status == "pending_review" for draft in drafts)
    assert all(4 <= draft.slide_count <= 8 for draft in drafts)
    assert all(draft.raw_payload.get("seed_facts") for draft in drafts)


def test_regenerate_instagram_draft_supersedes_original(monkeypatch) -> None:
    db = _make_session()
    db.add(WorkspaceUser(id=2, auth_user_id="user-2", email="user-2@example.com", role="customer"))
    profile = CustomerProfile(
        workspace_user_id=2,
        display_name="AI Test",
        wire_product="ai",
        automation_mode="auto_generate_manual_review",
        onboarding_completed_at=datetime.now(timezone.utc),
        token_store={"openai_api_key": "test-key"},
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)

    repo = InstagramCarouselDraftRepository(db)
    original = repo.add(
        InstagramCarouselDraft(
            customer_profile_id=profile.id,
            lane="ai_news",
            seed_key="openai|pricing",
            story_cluster="openai|pricing",
            seed_source_name="openai_news",
            seed_source_family="base",
            title="OpenAI updates API pricing",
            angle="What changed and why it matters right now",
            hook="What changed with OpenAI?",
            carousel_type="news_breakdown",
            slide_count=8,
            slides=[{"slide_number": idx, "role": role, "headline": "Old", "support": "" if role == "hook" else "Old"} for idx, role in enumerate(("hook", "what_changed", "why_now", "evidence", "who_it_affects", "implication", "key_takeaway", "closing_cta"), start=1)],
            caption={"hook": "Old", "body": "Old", "cta": "Old"},
            review_status="pending_review",
            quality_band="A",
            raw_payload={
                "seed_facts": _seed().seed_facts,
                "topic_tags": ["pricing"],
                "readiness_reason": "shadow_ready",
                "source_truth_tier": "official",
            },
        )
    )
    db.commit()

    regenerated = regenerate_instagram_draft(db, original, actor="Admin", drafting=StubDrafting())

    assert regenerated is not None
    assert regenerated.id != original.id
    assert regenerated.review_status == "pending_review"
    assert repo.get(original.id).review_status == "superseded"


def test_validate_instagram_blueprint_allows_context_aware_shorter_deck() -> None:
    blueprint = {
        "hook": "Useful hook",
        "angle": "Clear angle",
        "slides": [
            {"slide_number": 1, "role": "hook", "headline": "PRICING JUST CHANGED", "support": ""},
            {"slide_number": 2, "role": "what_changed", "headline": "WHAT CHANGED", "support": "Teams now pay as they go instead of using plan limits."},
            {"slide_number": 3, "role": "why_now", "headline": "WHY NOW", "support": "This matters because it lowers friction for teams testing Codex in real workflows."},
            {"slide_number": 4, "role": "closing_cta", "headline": "@newsbot", "support": "Save this and follow @newsbot for sharper AI updates."},
        ],
        "caption": {"hook": "h", "body": "b", "cta": "c"},
    }

    validation = validate_instagram_blueprint(blueprint, lane="ai_news")

    assert validation["approved"] is True
    assert "invalid_slide_count" not in validation["reasons"]
    assert "slide_sequence_mismatch" not in validation["reasons"]


class StubRenderer:
    def render(self, draft: InstagramCarouselDraft):
        return [
            type(
                "RenderedSlideAsset",
                (),
                {
                    "slide_number": index,
                    "template_id": slide.get("template_id"),
                    "template_version": slide.get("template_version"),
                    "schema_version": slide.get("schema_version"),
                    "width": 1080,
                    "height": 1350,
                    "content_hash": f"hash-{index}",
                    "filename": f"slide-{index:02d}.png",
                    "content": f"png-{index}".encode("utf-8"),
                },
            )()
            for index, slide in enumerate(draft.slides, start=1)
        ]


class StubStorage:
    bucket = "instagram-carousel-assets"

    def upload_png(self, *, path: str, content: bytes) -> str:
        assert path.endswith(".png")
        assert content
        return f"https://storage.example/{path}"


class StubPublisher:
    def publish_carousel(self, profile: CustomerProfile, draft: InstagramCarouselDraft) -> dict:
        assert profile.token_store["instagram_access_token"] == "ig-token"
        assert draft.asset_manifest["slides"]
        return {
            "child_ids": ["child-1", "child-2"],
            "container_id": "container-1",
            "publish_id": "publish-1",
            "publish_payload": {"id": "publish-1"},
        }


def test_render_schedule_and_publish_instagram_draft_lifecycle() -> None:
    db = _make_session()
    db.add(WorkspaceUser(id=3, auth_user_id="user-3", email="user-3@example.com", role="customer"))
    profile = CustomerProfile(
        workspace_user_id=3,
        display_name="IG Test",
        wire_product="ai",
        automation_mode="auto_generate_manual_review",
        onboarding_completed_at=datetime.now(timezone.utc),
        token_store={
            "openai_api_key": "test-key",
            "instagram_access_token": "ig-token",
            "instagram_business_account_id": "ig-account",
        },
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)

    repo = InstagramCarouselDraftRepository(db)
    draft = repo.add(
        InstagramCarouselDraft(
            customer_profile_id=profile.id,
            lane="ai_news",
            seed_key="openai|pricing",
            story_cluster="openai|pricing",
            seed_source_name="openai_news",
            seed_source_family="base",
            title="OpenAI updates API pricing",
            angle="What changed and why it matters right now",
            hook="What changed with OpenAI?",
            carousel_type="news_breakdown",
            slide_count=5,
            slides=StubDrafting().build_instagram_carousel_blueprint(_seed().seed_facts, "ai_news")["slides"],
            caption={"hook": "Hook", "body": "Body", "cta": "CTA"},
            review_status="approved",
            quality_band="A",
            render_status="render_pending",
            publish_status="draft",
            raw_payload={
                "seed_facts": _seed().seed_facts,
            },
        )
    )
    db.commit()

    rendered = render_instagram_draft(db, draft, renderer=StubRenderer(), storage=StubStorage())
    assert rendered.render_status == "rendered"
    assert len(rendered.asset_manifest["slides"]) == 8

    job = schedule_instagram_draft(db, rendered)
    assert job.status == "queued"
    assert rendered.publish_status == "scheduled"

    publish_instagram_job(db, job, publisher=StubPublisher())
    db.commit()

    assert job.status == "posted"
    assert rendered.publish_status == "published"
    assert rendered.instagram_publish_id == "publish-1"
    assert len(repo.list_publish_logs(limit=10)) == 1

from __future__ import annotations

INSTAGRAM_SCHEMA_VERSION = "instagram_carousel_schema_v1"
INSTAGRAM_TEMPLATE_VERSION = "instagram_templates_v1"
INSTAGRAM_DEFAULT_SLIDE_COUNT = 6
INSTAGRAM_MIN_SLIDES = 4
INSTAGRAM_MAX_SLIDES = 8
INSTAGRAM_BOTTOM_SAFE_ZONE_PX = 170

INSTAGRAM_LANES = ("ai_news", "ai_explained", "ai_for_business")

SLIDE_ROLE_FIELDS: dict[str, tuple[str, ...]] = {
    "hook": ("headline", "support"),
    "what_changed": ("headline", "support"),
    "why_now": ("headline", "support"),
    "evidence": ("headline", "support"),
    "who_it_affects": ("headline", "support"),
    "key_takeaway": ("headline", "support"),
    "closing_cta": ("headline", "support"),
    "myth": ("headline", "support"),
    "reality": ("headline", "support"),
    "counter_argument": ("headline", "support"),
    "deeper_meaning": ("headline", "support"),
    "implication": ("headline", "support"),
    "pain_point": ("headline", "support"),
    "mistake": ("headline", "support"),
    "better_way": ("headline", "support"),
    "workflow": ("headline", "support"),
    "outcome": ("headline", "support"),
}

INSTAGRAM_TEMPLATE_MAP: dict[str, dict[str, dict[str, str]]] = {
    "ai_news": {
        "hook": {"template_id": "ig_news_hook_v2", "template_version": INSTAGRAM_TEMPLATE_VERSION, "layout_family": "hook"},
        "what_changed": {"template_id": "ig_news_change_v2", "template_version": INSTAGRAM_TEMPLATE_VERSION, "layout_family": "interior_statement"},
        "why_now": {"template_id": "ig_news_why_now_v2", "template_version": INSTAGRAM_TEMPLATE_VERSION, "layout_family": "interior_statement"},
        "evidence": {"template_id": "ig_news_evidence_v2", "template_version": INSTAGRAM_TEMPLATE_VERSION, "layout_family": "interior_proof"},
        "who_it_affects": {"template_id": "ig_news_audience_v2", "template_version": INSTAGRAM_TEMPLATE_VERSION, "layout_family": "interior_statement"},
        "implication": {"template_id": "ig_news_implication_v2", "template_version": INSTAGRAM_TEMPLATE_VERSION, "layout_family": "interior_statement"},
        "key_takeaway": {"template_id": "ig_news_takeaway_v2", "template_version": INSTAGRAM_TEMPLATE_VERSION, "layout_family": "interior_proof"},
        "closing_cta": {"template_id": "ig_news_closing_v2", "template_version": INSTAGRAM_TEMPLATE_VERSION, "layout_family": "closing"},
    },
    "ai_explained": {
        "hook": {"template_id": "ig_explained_hook_v2", "template_version": INSTAGRAM_TEMPLATE_VERSION, "layout_family": "hook"},
        "myth": {"template_id": "ig_explained_myth_v2", "template_version": INSTAGRAM_TEMPLATE_VERSION, "layout_family": "interior_statement"},
        "reality": {"template_id": "ig_explained_reality_v2", "template_version": INSTAGRAM_TEMPLATE_VERSION, "layout_family": "interior_statement"},
        "evidence": {"template_id": "ig_explained_evidence_v2", "template_version": INSTAGRAM_TEMPLATE_VERSION, "layout_family": "interior_proof"},
        "counter_argument": {"template_id": "ig_explained_counter_v2", "template_version": INSTAGRAM_TEMPLATE_VERSION, "layout_family": "interior_statement"},
        "deeper_meaning": {"template_id": "ig_explained_depth_v2", "template_version": INSTAGRAM_TEMPLATE_VERSION, "layout_family": "interior_proof"},
        "key_takeaway": {"template_id": "ig_explained_takeaway_v2", "template_version": INSTAGRAM_TEMPLATE_VERSION, "layout_family": "interior_statement"},
        "closing_cta": {"template_id": "ig_explained_closing_v2", "template_version": INSTAGRAM_TEMPLATE_VERSION, "layout_family": "closing"},
    },
    "ai_for_business": {
        "hook": {"template_id": "ig_business_hook_v2", "template_version": INSTAGRAM_TEMPLATE_VERSION, "layout_family": "hook"},
        "pain_point": {"template_id": "ig_business_pain_v2", "template_version": INSTAGRAM_TEMPLATE_VERSION, "layout_family": "interior_statement"},
        "mistake": {"template_id": "ig_business_mistake_v2", "template_version": INSTAGRAM_TEMPLATE_VERSION, "layout_family": "interior_statement"},
        "evidence": {"template_id": "ig_business_evidence_v2", "template_version": INSTAGRAM_TEMPLATE_VERSION, "layout_family": "interior_proof"},
        "better_way": {"template_id": "ig_business_solution_v2", "template_version": INSTAGRAM_TEMPLATE_VERSION, "layout_family": "interior_statement"},
        "workflow": {"template_id": "ig_business_workflow_v2", "template_version": INSTAGRAM_TEMPLATE_VERSION, "layout_family": "interior_proof"},
        "outcome": {"template_id": "ig_business_outcome_v2", "template_version": INSTAGRAM_TEMPLATE_VERSION, "layout_family": "interior_statement"},
        "closing_cta": {"template_id": "ig_business_closing_v2", "template_version": INSTAGRAM_TEMPLATE_VERSION, "layout_family": "closing"},
    },
}

INSTAGRAM_LANE_ROLE_SEQUENCES: dict[str, tuple[str, ...]] = {
    "ai_news": ("hook", "what_changed", "why_now", "evidence", "who_it_affects", "implication", "key_takeaway", "closing_cta"),
    "ai_explained": ("hook", "myth", "reality", "evidence", "counter_argument", "deeper_meaning", "key_takeaway", "closing_cta"),
    "ai_for_business": ("hook", "pain_point", "mistake", "evidence", "better_way", "workflow", "outcome", "closing_cta"),
}

INSTAGRAM_LANE_REQUIRED_ROLES: dict[str, tuple[str, ...]] = {
    "ai_news": ("hook", "what_changed", "why_now", "closing_cta"),
    "ai_explained": ("hook", "reality", "deeper_meaning", "closing_cta"),
    "ai_for_business": ("hook", "pain_point", "better_way", "closing_cta"),
}

INSTAGRAM_LANE_DEFAULT_SLIDE_COUNTS: dict[str, int] = {
    "ai_news": 5,
    "ai_explained": 6,
    "ai_for_business": 6,
}

TEXT_BUDGETS: dict[str, dict[str, int]] = {
    "default": {"headline": 64, "support": 90, "words": 30},
    "hook": {"headline": 72, "support": 0, "words": 16},
    "evidence": {"headline": 58, "support": 88, "words": 28},
    "workflow": {"headline": 58, "support": 88, "words": 28},
    "closing_cta": {"headline": 56, "support": 80, "words": 22},
    "caption": {"hook": 110, "body": 420, "cta": 100},
}

SOURCE_TRUTH_PRIORITY: dict[str, int] = {
    "official": 4,
    "trusted_press": 3,
    "business_press": 2,
    "secondary": 1,
}

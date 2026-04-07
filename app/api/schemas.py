from datetime import datetime

from pydantic import BaseModel, Field


class ProfileSettingsUpdate(BaseModel):
    display_name: str | None = None
    auto_post_enabled: bool | None = None
    wire_product: str | None = Field(default=None, pattern="^(finance|ai)$")
    openai_api_key: str | None = None
    tavily_api_key: str | None = None
    source_families: list[str] | None = None


class PublishJobRetryAction(BaseModel):
    scheduled_for: datetime | None = None


class InstagramDraftGenerateRequest(BaseModel):
    customer_profile_id: int | None = None
    limit_per_lane: int = Field(default=2, ge=1, le=5)


class InstagramDraftReviewAction(BaseModel):
    notes: str | None = None


class InstagramDraftScheduleAction(BaseModel):
    scheduled_for: datetime | None = None

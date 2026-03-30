from pydantic import BaseModel, Field


class DraftReviewAction(BaseModel):
    reviewer: str | None = None
    edited_text: str | None = None
    auto_queue: bool = True


class DraftRejectAction(BaseModel):
    reviewer: str | None = None
    reason: str = Field(min_length=3)


class ReviewResolveAction(BaseModel):
    reviewer: str | None = None
    status: str = Field(default="resolved")


class CreatorSettingsUpdate(BaseModel):
    display_name: str | None = None
    primary_platform: str | None = None
    tone: str | None = None
    language: str | None = None
    max_posts_per_hour: int | None = Field(default=None, ge=1, le=60)
    watchlist: list[str] | None = None
    blocked_phrases: list[str] | None = None


class PublishJobRetryAction(BaseModel):
    scheduled_for: str | None = None

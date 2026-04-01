from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class DraftReviewAction(BaseModel):
    reviewer: str | None = None
    edited_text: str | None = None
    auto_queue: bool = True
    scheduled_for: datetime | None = None


class DraftRejectAction(BaseModel):
    reviewer: str | None = None
    reason: str = Field(min_length=3)


class ReviewStatus(str, Enum):
    open = "open"
    resolved = "resolved"
    rejected = "rejected"


class ReviewResolveAction(BaseModel):
    reviewer: str | None = None
    status: ReviewStatus = ReviewStatus.resolved


class CreatorSettingsUpdate(BaseModel):
    display_name: str | None = None
    primary_platform: str | None = None
    tone: str | None = None
    language: str | None = None
    max_posts_per_hour: int | None = Field(default=None, ge=1, le=60)
    watchlist: list[str] | None = None
    blocked_phrases: list[str] | None = None
    timezone: str | None = None
    posting_window_start: int | None = Field(default=None, ge=0, le=23)
    posting_window_end: int | None = Field(default=None, ge=0, le=23)
    automation_mode: str | None = None
    freshness_window_hours: int | None = Field(default=None, ge=1, le=72)
    auto_post_enabled: bool | None = None
    auto_post_threshold: int | None = Field(default=None, ge=50, le=100)
    openai_api_key: str | None = None


class CustomerProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1)
    tone: str | None = None
    language: str | None = None
    watchlist: list[str] | None = None
    blocked_phrases: list[str] | None = None


class CustomerOpenAIUpdate(BaseModel):
    openai_api_key: str = Field(min_length=10)


class PublishJobRetryAction(BaseModel):
    scheduled_for: datetime | None = None


class PublishJobScheduleAction(BaseModel):
    scheduled_for: datetime = Field()


class SourceUpdate(BaseModel):
    enabled: bool

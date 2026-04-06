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

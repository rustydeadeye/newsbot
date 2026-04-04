from datetime import datetime

from pydantic import BaseModel, Field


class ProfileSettingsUpdate(BaseModel):
    display_name: str | None = None
    auto_post_enabled: bool | None = None


class PublishJobRetryAction(BaseModel):
    scheduled_for: datetime | None = None

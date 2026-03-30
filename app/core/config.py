from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "Newsbot"
    database_url: str = Field(alias="DATABASE_URL")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_MODEL")
    x_api_base_url: str = Field(default="https://api.x.com/2", alias="X_API_BASE_URL")
    x_bearer_token: str | None = Field(default=None, alias="X_BEARER_TOKEN")
    auto_post_threshold: int = Field(default=80, alias="AUTO_POST_THRESHOLD")
    app_env: str = Field(default="development", alias="APP_ENV")
    cors_origins: list[str] = Field(default=["*"], alias="CORS_ORIGINS")


@lru_cache
def get_settings() -> Settings:
    return Settings()

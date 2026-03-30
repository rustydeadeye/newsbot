from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "Newsbot"
    database_url: str = Field(alias="DATABASE_URL")
    supabase_url: str | None = Field(default=None, alias="SUPABASE_URL")
    supabase_publishable_key: str | None = Field(default=None, alias="SUPABASE_PUBLISHABLE_KEY")
    supabase_jwt_secret: str | None = Field(default=None, alias="SUPABASE_JWT_SECRET")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_MODEL")
    x_api_base_url: str = Field(default="https://api.x.com/2", alias="X_API_BASE_URL")
    x_client_id: str | None = Field(default=None, alias="X_CLIENT_ID")
    x_client_secret: str | None = Field(default=None, alias="X_CLIENT_SECRET")
    x_access_token: str | None = Field(default=None, alias="X_ACCESS_TOKEN")
    x_refresh_token: str | None = Field(default=None, alias="X_REFRESH_TOKEN")
    x_token_url: str = Field(default="https://api.x.com/2/oauth2/token", alias="X_TOKEN_URL")
    auto_post_threshold: int = Field(default=80, alias="AUTO_POST_THRESHOLD")
    auth_admin_emails: str = Field(default="", alias="AUTH_ADMIN_EMAILS")
    auth_auto_provision_users: bool = Field(default=True, alias="AUTH_AUTO_PROVISION_USERS")
    app_env: str = Field(default="development", alias="APP_ENV")
    cors_origins: list[str] = Field(default=["*"], alias="CORS_ORIGINS")

    @property
    def auth_admin_email_set(self) -> set[str]:
        return {item.strip().lower() for item in self.auth_admin_emails.split(",") if item.strip()}

    @property
    def supabase_jwks_url(self) -> str | None:
        if not self.supabase_url:
            return None
        return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()

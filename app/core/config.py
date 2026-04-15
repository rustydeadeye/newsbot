from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "Newsbot"
    database_url: str = Field(alias="DATABASE_URL")
    supabase_url: str | None = Field(default=None, alias="SUPABASE_URL")
    supabase_publishable_key: str | None = Field(default=None, alias="SUPABASE_PUBLISHABLE_KEY")
    supabase_service_role_key: str | None = Field(default=None, alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_jwt_secret: str | None = Field(default=None, alias="SUPABASE_JWT_SECRET")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    tavily_api_key: str | None = Field(default=None, alias="TAVILY_API_KEY")
    openai_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_MODEL")
    x_api_base_url: str = Field(default="https://api.x.com/2", alias="X_API_BASE_URL")
    x_client_id: str | None = Field(default=None, alias="X_CLIENT_ID")
    x_client_secret: str | None = Field(default=None, alias="X_CLIENT_SECRET")
    x_access_token: str | None = Field(default=None, alias="X_ACCESS_TOKEN")
    x_refresh_token: str | None = Field(default=None, alias="X_REFRESH_TOKEN")
    x_token_url: str = Field(default="https://api.x.com/2/oauth2/token", alias="X_TOKEN_URL")
    x_redirect_uri: str = Field(default="http://localhost:8000/settings/x/callback", alias="X_REDIRECT_URI")
    frontend_url: str = Field(default="http://localhost:3000", alias="FRONTEND_URL")
    auto_post_threshold: int = Field(default=80, alias="AUTO_POST_THRESHOLD")
    pipeline_enabled: bool = Field(default=True, alias="PIPELINE_ENABLED")
    pipeline_interval_sec: int = Field(default=900, alias="PIPELINE_INTERVAL_SEC")
    engagement_fetch_enabled: bool = Field(default=True, alias="ENGAGEMENT_FETCH_ENABLED")
    wire_feed_enabled: bool = Field(default=False, alias="WIRE_FEED_ENABLED")
    ai_shadow_mode: bool = Field(default=True, alias="AI_SHADOW_MODE")
    wire_feed_interval_sec: int = Field(default=900, alias="WIRE_FEED_INTERVAL_SEC")
    wire_feed_timeout_sec: int = Field(default=720, alias="WIRE_FEED_TIMEOUT_SEC")
    instagram_pipeline_enabled: bool = Field(default=False, alias="INSTAGRAM_PIPELINE_ENABLED")
    instagram_pipeline_interval_sec: int = Field(default=300, alias="INSTAGRAM_PIPELINE_INTERVAL_SEC")
    instagram_asset_bucket: str = Field(default="instagram-carousel-assets", alias="INSTAGRAM_ASSET_BUCKET")
    instagram_graph_api_base: str = Field(default="https://graph.facebook.com/v23.0", alias="INSTAGRAM_GRAPH_API_BASE")
    wire_web_breaking_enabled: bool = Field(default=False, alias="WIRE_WEB_BREAKING_ENABLED")
    wire_web_breaking_model: str = Field(default="gpt-5.4-mini", alias="WIRE_WEB_BREAKING_MODEL")
    wire_web_breaking_limit: int = Field(default=12, alias="WIRE_WEB_BREAKING_LIMIT")
    wire_web_breaking_freshness_hours: int = Field(default=18, alias="WIRE_WEB_BREAKING_FRESHNESS_HOURS")
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

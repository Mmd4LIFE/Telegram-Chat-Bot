"""Application configuration loaded from environment variables."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # OpenAI
    openai_api_key: str

    # Telegram
    telegram_bot_token: str
    admin_telegram_id: int

    # Database
    postgres_user: str = "chatbot"
    postgres_password: str = "chatbot"
    postgres_db: str = "chatbot"
    postgres_host: str = "db"
    postgres_port: int = 5432

    # Web search (@web). If a Google Programmable Search key + engine id are set,
    # Google is used (reliable); otherwise it falls back to DuckDuckGo (no key,
    # but can be rate-limited from server IPs).
    google_api_key: str = ""
    google_cx: str = ""

    # Vector store (Qdrant) for per-user personalization memory
    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333
    embed_model: str = "text-embedding-3-small"
    embed_dim: int = 1536
    personalization_topk: int = 4

    # Proactive re-engagement: close a conversation that has been idle this long
    # and open a new one with a persona-aware follow-up question.
    reengage_enabled: bool = True
    reengage_inactivity_hours: int = 24
    reengage_check_minutes: int = 30
    reengage_max_per_run: int = 50

    # App
    app_port: int = 8009
    default_model: str = "gpt-4o-mini"
    context_messages: int = 12

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

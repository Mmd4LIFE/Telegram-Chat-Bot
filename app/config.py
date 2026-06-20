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

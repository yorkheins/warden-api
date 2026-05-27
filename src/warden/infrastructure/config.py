from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    OPENAI_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_TIMEOUT_SECONDS: float = 15.0
    USE_MOCK_LLM: bool = False

    PRODUCTION_ENVIRONMENTS: list[str] = ["prod"]
    WORKLOAD_HISTORY_LIMIT: int = 5

    DATABASE_URL: str = "sqlite+aiosqlite:///./warden.db"

    ORCHESTRATOR_MOCK_URL: str = "http://mock-orchestrator:8001"
    NOTIFIER_MOCK_URL: str = "http://mock-notifier:8002"
    MOCK_ERROR_RATE: float = 0.1
    MOCK_LATENCY_MS_MIN: int = 100
    MOCK_LATENCY_MS_MAX: int = 500

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

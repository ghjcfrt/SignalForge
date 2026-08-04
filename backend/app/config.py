import json
from functools import lru_cache
from pathlib import Path
from threading import RLock

from dotenv import load_dotenv
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.app.schemas import TimeoutSettings


ROOT_DIR = Path(__file__).resolve().parents[2]
WORKSPACE_DIR = ROOT_DIR / "workspaces"
RUNTIME_SETTINGS_PATH = WORKSPACE_DIR / "runtime-settings.json"
_RUNTIME_SETTINGS_LOCK = RLock()

load_dotenv(ROOT_DIR / ".env")


class Settings(BaseSettings):
    """Runtime configuration for the workshop."""

    ai_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AI_API_KEY", "OPENAI_API_KEY_YW_SF", "MPT_LLM_API_KEY"),
    )
    ai_base_url: str = Field(
        default="https://api.openlux.ai/v1",
        validation_alias=AliasChoices("AI_BASE_URL", "OPENAI_BASE_URL_YW_SF", "MPT_LLM_BASE_URL"),
    )
    ai_model: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AI_MODEL", "OPENAI_MODEL_YW_SF", "MPT_LLM_MODEL_NAME"),
    )
    mpt_pexels_api_key: str | None = Field(default=None, alias="MPT_PEXELS_API_KEY")
    backend_port: int = Field(default=8017, alias="BACKEND_PORT")
    tushare_token: str | None = Field(default=None, alias="TUSHARE_TOKEN")
    tavily_api_key: str | None = Field(default=None, alias="TAVILY_API_KEY")
    serpapi_key: str | None = Field(default=None, alias="SERPAPI_KEY")
    news_fetch_timeout_seconds: int = Field(
        default=90,
        ge=0,
        validation_alias=AliasChoices("NEWS_FETCH_TIMEOUT_SECONDS"),
    )
    model_timeout_seconds: int = Field(
        default=30,
        ge=0,
        validation_alias=AliasChoices("MODEL_TIMEOUT_SECONDS"),
    )

    @field_validator("ai_model", mode="before")
    @classmethod
    def empty_model_means_auto(cls, value: str | None) -> str | None:
        return value.strip() or None if isinstance(value, str) else value

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @property
    def ai_enabled(self) -> bool:
        return bool(self.ai_api_key)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    with _RUNTIME_SETTINGS_LOCK:
        try:
            saved = TimeoutSettings.model_validate_json(RUNTIME_SETTINGS_PATH.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError):
            saved = None
    if saved:
        settings.news_fetch_timeout_seconds = saved.news_fetch_timeout_seconds
        settings.model_timeout_seconds = saved.model_timeout_seconds
    return settings


def get_timeout_settings() -> TimeoutSettings:
    settings = get_settings()
    return TimeoutSettings(
        news_fetch_timeout_seconds=settings.news_fetch_timeout_seconds,
        model_timeout_seconds=settings.model_timeout_seconds,
    )


def update_timeout_settings(value: TimeoutSettings) -> TimeoutSettings:
    settings = get_settings()
    settings.news_fetch_timeout_seconds = value.news_fetch_timeout_seconds
    settings.model_timeout_seconds = value.model_timeout_seconds
    with _RUNTIME_SETTINGS_LOCK:
        RUNTIME_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        RUNTIME_SETTINGS_PATH.write_text(
            json.dumps(value.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return get_timeout_settings()

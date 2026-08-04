from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[2]
WORKSPACE_DIR = ROOT_DIR / "workspaces"

load_dotenv(ROOT_DIR / ".env")


class Settings(BaseSettings):
    """Runtime configuration for the workshop."""

    ai_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AI_API_KEY", "OPENAI_API_KEY_YW_SF", "MPT_LLM_API_KEY"),
    )
    ai_base_url: str = Field(
        default="https://api.wlai.vip/v1",
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
    return Settings()

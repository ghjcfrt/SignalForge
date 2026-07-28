from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[2]
WORKSPACE_DIR = ROOT_DIR / "workspaces"

load_dotenv(ROOT_DIR / ".env")


class Settings(BaseSettings):
    """Runtime configuration for the workshop."""

    openai_api_key_yw_sf: str | None = Field(default=None, alias="OPENAI_API_KEY_YW_SF")
    openai_base_url_yw_sf: str = Field(
        default="https://api.wlai.vip/v1",
        alias="OPENAI_BASE_URL_YW_SF",
    )
    openai_model_yw_sf: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL_YW_SF")
    mpt_llm_provider: str | None = Field(default=None, alias="MPT_LLM_PROVIDER")
    mpt_llm_api_key: str | None = Field(default=None, alias="MPT_LLM_API_KEY")
    mpt_llm_base_url: str | None = Field(default=None, alias="MPT_LLM_BASE_URL")
    mpt_llm_model_name: str | None = Field(default=None, alias="MPT_LLM_MODEL_NAME")
    mpt_pexels_api_key: str | None = Field(default=None, alias="MPT_PEXELS_API_KEY")
    backend_port: int = Field(default=8017, alias="BACKEND_PORT")

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @property
    def ai_enabled(self) -> bool:
        return bool(self.openai_api_key_yw_sf)


@lru_cache
def get_settings() -> Settings:
    return Settings()

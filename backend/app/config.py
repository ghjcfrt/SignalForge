import json
from functools import lru_cache
from pathlib import Path
from threading import RLock

from dotenv import load_dotenv, set_key
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.app.schemas import EnvSettings, EnvSettingsUpdate, OutputDirectorySettings, SecretSetting, TimeoutSettings


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
    socialdatax_api_key: str | None = Field(default=None, alias="SOCIALDATAX_API_KEY")
    socialdatax_base_url: str = Field(
        default="https://mcp.socialdatax.com",
        alias="SOCIALDATAX_BASE_URL",
    )
    socialdatax_timeout_seconds: int = Field(
        default=60,
        ge=0,
        alias="SOCIALDATAX_TIMEOUT_SECONDS",
    )
    workflow_timeout_seconds: int = Field(
        default=300,
        ge=0,
        validation_alias=AliasChoices("WORKFLOW_TIMEOUT_SECONDS"),
    )
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
    news_source_mode: str = Field(default="live_then_fixture", alias="NEWS_SOURCE_MODE")
    news_rss_feeds: str = Field(default="", alias="NEWS_RSS_FEEDS")
    news_fixture_path: str | None = Field(default=None, alias="NEWS_FIXTURE_PATH")
    stock_fetch_retries: int = Field(default=2, ge=0, le=5, alias="STOCK_FETCH_RETRIES")
    stock_cache_ttl_seconds: int = Field(default=60, ge=0, le=3600, alias="STOCK_CACHE_TTL_SECONDS")

    # 函数「empty_model_means_auto」负责完成该步骤的输入处理、核心逻辑和结果返回。
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

    # 函数「ai_enabled」负责完成该步骤的输入处理、核心逻辑和结果返回。
    @property
    def ai_enabled(self) -> bool:
        return bool(self.ai_api_key)


# 函数「get_settings」负责完成该步骤的输入处理、核心逻辑和结果返回。
@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    with _RUNTIME_SETTINGS_LOCK:
        try:
            payload = json.loads(RUNTIME_SETTINGS_PATH.read_text(encoding="utf-8"))
            saved = TimeoutSettings.model_validate(payload)
        except (FileNotFoundError, OSError, ValueError, TypeError):
            saved = None
    if saved:
        settings.news_fetch_timeout_seconds = saved.news_fetch_timeout_seconds
        settings.model_timeout_seconds = saved.model_timeout_seconds
        settings.workflow_timeout_seconds = saved.workflow_timeout_seconds
    return settings


# 函数「get_timeout_settings」负责完成该步骤的输入处理、核心逻辑和结果返回。
def get_timeout_settings() -> TimeoutSettings:
    settings = get_settings()
    return TimeoutSettings(
        news_fetch_timeout_seconds=settings.news_fetch_timeout_seconds,
        model_timeout_seconds=settings.model_timeout_seconds,
        workflow_timeout_seconds=settings.workflow_timeout_seconds,
    )


# 函数「get_output_directory_settings」负责完成该步骤的输入处理、核心逻辑和结果返回。
def get_output_directory_settings() -> OutputDirectorySettings:
    with _RUNTIME_SETTINGS_LOCK:
        try:
            payload = json.loads(RUNTIME_SETTINGS_PATH.read_text(encoding="utf-8"))
            return OutputDirectorySettings.model_validate(payload.get("output_directories", payload))
        except (FileNotFoundError, OSError, ValueError, TypeError):
            return OutputDirectorySettings()


# 函数「update_output_directory_settings」负责完成该步骤的输入处理、核心逻辑和结果返回。
def update_output_directory_settings(value: OutputDirectorySettings) -> OutputDirectorySettings:
    # Preserve timeout settings in the shared runtime-settings file.
    with _RUNTIME_SETTINGS_LOCK:
        RUNTIME_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            payload = json.loads(RUNTIME_SETTINGS_PATH.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError):
            payload = {}
        payload["output_directories"] = value.model_dump()
        RUNTIME_SETTINGS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return value


# 函数「update_timeout_settings」负责完成该步骤的输入处理、核心逻辑和结果返回。
def update_timeout_settings(value: TimeoutSettings) -> TimeoutSettings:
    settings = get_settings()
    settings.news_fetch_timeout_seconds = value.news_fetch_timeout_seconds
    settings.model_timeout_seconds = value.model_timeout_seconds
    settings.workflow_timeout_seconds = value.workflow_timeout_seconds
    with _RUNTIME_SETTINGS_LOCK:
        RUNTIME_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            payload = json.loads(RUNTIME_SETTINGS_PATH.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError):
            payload = {}
        payload.update(value.model_dump())
        RUNTIME_SETTINGS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return get_timeout_settings()


_ENV_FIELDS = {
    "ai_api_key": "AI_API_KEY",
    "ai_base_url": "AI_BASE_URL",
    "ai_model": "AI_MODEL",
    "mpt_pexels_api_key": "MPT_PEXELS_API_KEY",
    "backend_port": "BACKEND_PORT",
    "socialdatax_api_key": "SOCIALDATAX_API_KEY",
    "socialdatax_base_url": "SOCIALDATAX_BASE_URL",
    "socialdatax_timeout_seconds": "SOCIALDATAX_TIMEOUT_SECONDS",
    "tushare_token": "TUSHARE_TOKEN",
    "tavily_api_key": "TAVILY_API_KEY",
    "serpapi_key": "SERPAPI_KEY",
}
_SECRET_FIELDS = {"ai_api_key", "mpt_pexels_api_key", "socialdatax_api_key", "tushare_token", "tavily_api_key", "serpapi_key"}


# 函数「_secret_setting」负责完成该步骤的输入处理、核心逻辑和结果返回。
def _secret_setting(value: str | None) -> SecretSetting:
    if not value:
        return SecretSetting()
    if len(value) > 8:
        preview = f"{value[:4]}{'*' * max(4, len(value) - 8)}{value[-4:]}"
    elif len(value) >= 4:
        preview = f"{value[:2]}{'*' * max(2, len(value) - 4)}{value[-2:]}"
    else:
        preview = "*" * len(value)
    return SecretSetting(configured=True, preview=preview)


# 函数「get_env_settings」负责完成该步骤的输入处理、核心逻辑和结果返回。
def get_env_settings() -> EnvSettings:
    settings = get_settings()
    return EnvSettings(
        ai_api_key=_secret_setting(settings.ai_api_key),
        ai_base_url=settings.ai_base_url,
        ai_model=settings.ai_model or "",
        mpt_pexels_api_key=_secret_setting(settings.mpt_pexels_api_key),
        backend_port=settings.backend_port,
        socialdatax_api_key=_secret_setting(settings.socialdatax_api_key),
        socialdatax_base_url=settings.socialdatax_base_url,
        socialdatax_timeout_seconds=settings.socialdatax_timeout_seconds,
        tushare_token=_secret_setting(settings.tushare_token),
        tavily_api_key=_secret_setting(settings.tavily_api_key),
        serpapi_key=_secret_setting(settings.serpapi_key),
    )


# 函数「update_env_settings」负责完成该步骤的输入处理、核心逻辑和结果返回。
def update_env_settings(value: EnvSettingsUpdate) -> EnvSettings:
    """Persist editable values to .env and reload settings for this process."""
    ROOT_DIR.joinpath(".env").touch(exist_ok=True)
    data = value.model_dump(exclude_unset=True)
    for field, env_name in _ENV_FIELDS.items():
        if field not in data or data[field] is None:
            continue
        # Empty secret values intentionally leave the existing secret intact;
        # this lets the UI submit a blank field without erasing credentials.
        if field in _SECRET_FIELDS and not str(data[field]).strip():
            continue
        set_key(str(ROOT_DIR / ".env"), env_name, str(data[field]))
    load_dotenv(ROOT_DIR / ".env", override=True)
    get_settings.cache_clear()
    return get_env_settings()

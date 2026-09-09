"""运行时配置读取、脱敏展示和持久化更新。"""

import json
from functools import lru_cache
from pathlib import Path
from threading import RLock

from dotenv import load_dotenv, set_key
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.app.schemas import EnvSettings, EnvSettingsUpdate, OutputDirectorySettings, SecretSetting, TimeoutSettings


# 项目根目录、工作区目录和运行时设置文件位置。
ROOT_DIR = Path(__file__).resolve().parents[2]
WORKSPACE_DIR = ROOT_DIR / "workspaces"
# JSON 形式保存用户在界面修改的运行时设置。
RUNTIME_SETTINGS_PATH = WORKSPACE_DIR / "runtime-settings.json"
# 保护运行时设置文件读写的进程内锁。
_RUNTIME_SETTINGS_LOCK = RLock()

load_dotenv(ROOT_DIR / ".env")

class Settings(BaseSettings):
    """应用运行时配置，统一管理环境变量和可持久化设置。"""

    # AI 供应商连接参数；密钥支持多个兼容变量名。
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
    # MoneyPrinterTurbo 所需的素材服务密钥。
    mpt_pexels_api_key: str | None = Field(default=None, alias="MPT_PEXELS_API_KEY")
    # 本地 FastAPI 服务监听端口。
    backend_port: int = Field(default=8017, alias="BACKEND_PORT")
    # 股票、搜索和社交样本服务的可选凭据。
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
    # 新闻抓取、模型调用和整条工作流的超时；0 表示不限时。
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
    # 新闻来源策略、RSS 列表及本地 fixture 路径。
    news_source_mode: str = Field(default="live_then_fixture", alias="NEWS_SOURCE_MODE")
    news_rss_feeds: str = Field(default="", alias="NEWS_RSS_FEEDS")
    news_fixture_path: str | None = Field(default=None, alias="NEWS_FIXTURE_PATH")
    # 股票数据请求的重试次数和缓存时长。
    stock_fetch_retries: int = Field(default=2, ge=0, le=5, alias="STOCK_FETCH_RETRIES")
    stock_cache_ttl_seconds: int = Field(default=60, ge=0, le=3600, alias="STOCK_CACHE_TTL_SECONDS")

    @field_validator("ai_model", mode="before")
    @classmethod
    def empty_model_means_auto(cls, value: str | None) -> str | None:
        """函数“empty_model_means_auto”：将空模型名标准化为 None，使调用方可以自动选择模型。
参数：
    value: str | None
返回：str | None。"""
        return value.strip() or None if isinstance(value, str) else value

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @property
    def ai_enabled(self) -> bool:
        """函数“ai_enabled”：根据是否配置 AI 密钥判断实时模型能力是否启用。
返回：bool。"""
        return bool(self.ai_api_key)


@lru_cache
def get_settings() -> Settings:
    """函数“get_settings”：读取并缓存环境变量及运行时配置文件中的完整设置。
返回：Settings。"""
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


def get_timeout_settings() -> TimeoutSettings:
    """函数“get_timeout_settings”：返回当前生效的新闻、模型和工作流超时设置。
返回：TimeoutSettings。"""
    settings = get_settings()
    return TimeoutSettings(
        news_fetch_timeout_seconds=settings.news_fetch_timeout_seconds,
        model_timeout_seconds=settings.model_timeout_seconds,
        workflow_timeout_seconds=settings.workflow_timeout_seconds,
    )


def get_output_directory_settings() -> OutputDirectorySettings:
    """函数“get_output_directory_settings”：读取用户配置的成片与运营产物输出目录。
返回：OutputDirectorySettings。"""
    with _RUNTIME_SETTINGS_LOCK:
        try:
            payload = json.loads(RUNTIME_SETTINGS_PATH.read_text(encoding="utf-8"))
            return OutputDirectorySettings.model_validate(payload.get("output_directories", payload))
        except (FileNotFoundError, OSError, ValueError, TypeError):
            return OutputDirectorySettings()


def update_output_directory_settings(value: OutputDirectorySettings) -> OutputDirectorySettings:
    # 保留共享运行时配置文件中的超时设置。
    """函数“update_output_directory_settings”：持久化输出目录，同时保留同一文件中的其他运行时设置。
参数：
    value: OutputDirectorySettings
返回：OutputDirectorySettings。"""
    with _RUNTIME_SETTINGS_LOCK:
        RUNTIME_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            payload = json.loads(RUNTIME_SETTINGS_PATH.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError):
            payload = {}
        payload["output_directories"] = value.model_dump()
        RUNTIME_SETTINGS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return value


def update_timeout_settings(value: TimeoutSettings) -> TimeoutSettings:
    """函数“update_timeout_settings”：更新内存与运行时配置文件中的三个超时值。
参数：
    value: TimeoutSettings
返回：TimeoutSettings。"""
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


# 前端可编辑字段到 .env 变量名的映射。
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
# 必须脱敏展示且不允许空值覆盖的密钥字段。
_SECRET_FIELDS = {"ai_api_key", "mpt_pexels_api_key", "socialdatax_api_key", "tushare_token", "tavily_api_key", "serpapi_key"}


def _secret_setting(value: str | None) -> SecretSetting:
    """内部辅助函数“_secret_setting”：将密钥转换为仅含配置状态和脱敏预览的安全模型。
参数：
    value: str | None
返回：SecretSetting。"""
    if not value:
        return SecretSetting()
    if len(value) > 8:
        preview = f"{value[:4]}{'*' * max(4, len(value) - 8)}{value[-4:]}"
    elif len(value) >= 4:
        preview = f"{value[:2]}{'*' * max(2, len(value) - 4)}{value[-2:]}"
    else:
        preview = "*" * len(value)
    return SecretSetting(configured=True, preview=preview)


def get_env_settings() -> EnvSettings:
    """函数“get_env_settings”：返回可安全展示给前端的环境变量配置。
返回：EnvSettings。"""
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


def update_env_settings(value: EnvSettingsUpdate) -> EnvSettings:
    """将可编辑配置写入 .env，并重新加载当前进程的设置。"""
    ROOT_DIR.joinpath(".env").touch(exist_ok=True)
    data = value.model_dump(exclude_unset=True)
    for field, env_name in _ENV_FIELDS.items():
        if field not in data or data[field] is None:
            continue
        # 空的密钥字段表示“不修改”，保留现有凭据；
        # 这样前端可以提交空输入而不会误删密钥。
        if field in _SECRET_FIELDS and not str(data[field]).strip():
            continue
        set_key(str(ROOT_DIR / ".env"), env_name, str(data[field]))
    load_dotenv(ROOT_DIR / ".env", override=True)
    get_settings.cache_clear()
    return get_env_settings()

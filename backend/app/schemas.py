from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


AgentStatus = Literal["online", "idle", "busy", "offline"]
WorkflowStatus = Literal["queued", "running", "paused", "completed", "failed"]
WorkflowStageStatus = Literal["pending", "running", "completed", "failed"]
ViralAnalysisSource = Literal["socialdatax", "manual"]


class Skill(BaseModel):
    name: str
    source: str
    description: str


class Agent(BaseModel):
    id: str
    name: str
    title: str
    role: str
    status: AgentStatus = "idle"
    focus: str
    workspace: str
    skills: list[Skill] = Field(default_factory=list)


class ApiStatus(BaseModel):
    key_variable: str
    has_key: bool
    base_url: str
    model: str
    mode: Literal["live", "local-template"]
    model_available: bool = False
    diagnostic: str | None = None
    key_preview: str | None = None


class TimeoutSettings(BaseModel):
    news_fetch_timeout_seconds: int = Field(default=90, ge=0)
    model_timeout_seconds: int = Field(default=30, ge=0)
    workflow_timeout_seconds: int = Field(default=300, ge=0, le=86400)


class ViralAnalysisConfig(BaseModel):
    """How the viral analyst should obtain its analysis brief."""

    source: ViralAnalysisSource = "socialdatax"
    enabled: bool = True
    manual_content: str = Field(default="", max_length=30000)


class RunAgentRequest(BaseModel):
    agent_id: str
    prompt: str = ""
    settings: dict[str, object] = Field(default_factory=dict)


class TopicSeed(BaseModel):
    domain: str = Field(default="AI 圈")
    brief: str = Field(
        default="近期 AI 产品、模型、创业工具或内容生产热点",
        description="老板给热点监控员的方向。",
    )
    audience: str = Field(default="关注 AI 工具的一线创作者和创业者")
    duration_seconds: int = Field(default=110, ge=30, le=240)


class SourceEvidence(BaseModel):
    name: str
    url: str
    published_at: datetime
    claim: str


class Topic(BaseModel):
    title: str
    heat: int = Field(ge=0, le=100)
    source_hint: str
    source_url: str | None = None
    source_published_at: datetime | None = None
    sources: list[SourceEvidence] = Field(default_factory=list)
    cross_check_note: str = "未完成多方交叉验证。"
    checked_at: datetime | None = None
    verification_status: Literal["verified", "unverified"] = "unverified"
    verification_note: str = "未完成来源核验，不得作为新闻事实发布。"
    angle: str
    risk: str


class AgentOutput(BaseModel):
    agent_id: str
    agent_name: str
    title: str
    content: str
    artifact_path: str
    created_at: datetime


class WorkflowLog(BaseModel):
    timestamp: datetime
    level: Literal["info", "warning", "error"] = "info"
    stage: str | None = None
    message: str
    detail: str | None = None


class WorkflowRun(BaseModel):
    id: str
    status: WorkflowStatus
    seed: TopicSeed
    topics: list[Topic]
    outputs: list[AgentOutput]
    run_dir: str
    created_at: datetime
    completed_at: datetime | None = None
    error: str | None = None
    current_stage: str | None = None
    resumable: bool = False
    source_status: dict[str, str] = Field(default_factory=dict)
    stage_status: dict[str, WorkflowStageStatus] = Field(default_factory=dict)
    logs: list[WorkflowLog] = Field(default_factory=list)
    log_file: str | None = None
    viral_analysis: ViralAnalysisConfig = Field(default_factory=ViralAnalysisConfig)


class RunWorkflowRequest(BaseModel):
    seed: TopicSeed = Field(default_factory=TopicSeed)
    # ``manual`` creates a checkpoint without starting background work.  This
    # is used by the UI's "新任务" action; execution only begins after the
    # user explicitly clicks "运行工作流" or "执行下一步".
    execution_mode: Literal["auto", "step", "manual"] = "auto"
    viral_analysis: ViralAnalysisConfig = Field(default_factory=ViralAnalysisConfig)


class GenerateScriptRequest(BaseModel):
    topic: str
    angle: str = ""
    duration_seconds: int = Field(default=110, ge=30, le=240)
    audience: str = Field(default="关注 AI 工具的一线创作者和创业者")


class StockAnalysisRequest(BaseModel):
    stocks: str = Field(
        min_length=1,
        description="股票代码或名称，多个代码用逗号分隔，例如 600519,TSLA,HK00700。",
    )
    days: int = Field(default=120, ge=30, le=365)
    include_news: bool = True


class StockAnalysisResult(BaseModel):
    agent_id: str = "stock_assistant"
    skill: str = "stock-analysis"
    skill_source: str
    stocks: str
    report: str
    raw_data: dict
    data_script: str
    news_enabled: bool
    disclaimer: str

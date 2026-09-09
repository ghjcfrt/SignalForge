"""API 请求、响应以及工作流领域数据模型。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# 对外 API 使用的有限状态集合，避免前后端出现拼写不一致。
AgentStatus = Literal["online", "idle", "busy", "offline"]
WorkflowStatus = Literal["queued", "running", "paused", "completed", "failed"]
WorkflowStageStatus = Literal["pending", "running", "completed", "failed"]
ViralAnalysisSource = Literal["socialdatax", "manual"]


class Skill(BaseModel):
    """员工技能定义。
字段：
- `name`：str
- `source`：str
- `description`：str"""
    name: str
    source: str
    description: str


class Agent(BaseModel):
    """员工身份与工作状态。
字段：
- `id`：str
- `name`：str
- `title`：str
- `role`：str
- `status`：AgentStatus
- `focus`：str
- `workspace`：str
- `skills`：list[Skill]"""
    id: str
    name: str
    title: str
    role: str
    status: AgentStatus = "idle"
    focus: str
    workspace: str
    skills: list[Skill] = Field(default_factory=list)


class ApiStatus(BaseModel):
    """模型 API 连接状态。
字段：
- `key_variable`：str
- `has_key`：bool
- `base_url`：str
- `model`：str
- `mode`：Literal['live', 'local-template']
- `model_available`：bool
- `diagnostic`：str | None
- `key_preview`：str | None"""
    key_variable: str
    has_key: bool
    base_url: str
    model: str
    mode: Literal["live", "local-template"]
    model_available: bool = False
    diagnostic: str | None = None
    key_preview: str | None = None


class TimeoutSettings(BaseModel):
    """各阶段超时配置。
字段：
- `news_fetch_timeout_seconds`：int
- `model_timeout_seconds`：int
- `workflow_timeout_seconds`：int"""
    news_fetch_timeout_seconds: int = Field(default=90, ge=0)
    model_timeout_seconds: int = Field(default=30, ge=0)
    workflow_timeout_seconds: int = Field(default=300, ge=0, le=86400)


class OutputDirectorySettings(BaseModel):
    """生成产物输出目录。
字段：
- `video_output_dir`：str
- `operator_output_dir`：str"""

    video_output_dir: str = ""
    operator_output_dir: str = ""


class SecretSetting(BaseModel):
    """密钥脱敏状态。
字段：
- `configured`：bool
- `preview`：str | None"""

    configured: bool = False
    preview: str | None = None


class EnvSettings(BaseModel):
    """可展示的环境变量配置。
字段：
- `ai_api_key`：SecretSetting
- `ai_base_url`：str
- `ai_model`：str
- `mpt_pexels_api_key`：SecretSetting
- `backend_port`：int
- `socialdatax_api_key`：SecretSetting
- `socialdatax_base_url`：str
- `socialdatax_timeout_seconds`：int
- `tushare_token`：SecretSetting
- `tavily_api_key`：SecretSetting
- `serpapi_key`：SecretSetting"""

    ai_api_key: SecretSetting = Field(default_factory=SecretSetting)
    ai_base_url: str = ""
    ai_model: str = ""
    mpt_pexels_api_key: SecretSetting = Field(default_factory=SecretSetting)
    backend_port: int = Field(default=8017, ge=1, le=65535)
    socialdatax_api_key: SecretSetting = Field(default_factory=SecretSetting)
    socialdatax_base_url: str = ""
    socialdatax_timeout_seconds: int = Field(default=60, ge=0)
    tushare_token: SecretSetting = Field(default_factory=SecretSetting)
    tavily_api_key: SecretSetting = Field(default_factory=SecretSetting)
    serpapi_key: SecretSetting = Field(default_factory=SecretSetting)


class EnvSettingsUpdate(BaseModel):
    """环境变量更新请求。
字段：
- `ai_api_key`：str | None
- `ai_base_url`：str | None
- `ai_model`：str | None
- `mpt_pexels_api_key`：str | None
- `backend_port`：int | None
- `socialdatax_api_key`：str | None
- `socialdatax_base_url`：str | None
- `socialdatax_timeout_seconds`：int | None
- `tushare_token`：str | None
- `tavily_api_key`：str | None
- `serpapi_key`：str | None"""

    ai_api_key: str | None = None
    ai_base_url: str | None = None
    ai_model: str | None = None
    mpt_pexels_api_key: str | None = None
    backend_port: int | None = Field(default=None, ge=1, le=65535)
    socialdatax_api_key: str | None = None
    socialdatax_base_url: str | None = None
    socialdatax_timeout_seconds: int | None = Field(default=None, ge=0)
    tushare_token: str | None = None
    tavily_api_key: str | None = None
    serpapi_key: str | None = None


class ViralAnalysisConfig(BaseModel):
    """爆款分析配置。
字段：
- `source`：ViralAnalysisSource
- `enabled`：bool
- `manual_content`：str"""

    source: ViralAnalysisSource = "socialdatax"
    enabled: bool = True
    manual_content: str = Field(default="", max_length=30000)


class RunAgentRequest(BaseModel):
    """独立员工任务请求。
字段：
- `agent_id`：str
- `prompt`：str
- `settings`：dict[str, object]
- `project_run_id`：str | None
- `timeout_seconds`：int"""
    agent_id: str
    prompt: str = ""
    settings: dict[str, object] = Field(default_factory=dict)
    # 员工从已打开项目运行时，把独立工作台结果保存到项目中，确保导入导出不会丢失。
    project_run_id: str | None = None
    # 独立工作台拥有自己的执行预算，与控制台持久化的工作流超时分开。
    timeout_seconds: int = Field(default=300, ge=0, le=86400)


class TopicSeed(BaseModel):
    """热点任务种子。
字段：
- `domain`：str
- `brief`：str
- `audience`：str
- `duration_seconds`：int
- `video_aspect`：Literal['vertical', 'horizontal']"""
    domain: str = Field(default="AI 圈")
    brief: str = Field(
        default="近期 AI 产品、模型、创业工具或内容生产热点",
        description="老板给热点监控员的方向。",
    )
    audience: str = Field(default="关注 AI 工具的一线创作者和创业者")
    duration_seconds: int = Field(default=110, ge=30, le=240)
    video_aspect: Literal["vertical", "horizontal"] = "vertical"


class SourceEvidence(BaseModel):
    """选题来源证据。
字段：
- `name`：str
- `url`：str
- `published_at`：datetime
- `claim`：str"""
    name: str
    url: str
    published_at: datetime
    claim: str


class Topic(BaseModel):
    """热点候选选题。
字段：
- `title`：str
- `heat`：int
- `source_hint`：str
- `source_url`：str | None
- `source_published_at`：datetime | None
- `sources`：list[SourceEvidence]
- `cross_check_note`：str
- `checked_at`：datetime | None
- `verification_status`：Literal['verified', 'unverified']
- `verification_note`：str
- `angle`：str
- `risk`：str"""
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
    """员工产物记录。
字段：
- `agent_id`：str
- `agent_name`：str
- `title`：str
- `content`：str
- `artifact_path`：str
- `created_at`：datetime"""
    agent_id: str
    agent_name: str
    title: str
    content: str
    artifact_path: str
    created_at: datetime


class AgentTaskLog(BaseModel):
    """员工任务日志。
字段：
- `timestamp`：datetime
- `level`：Literal['info', 'success', 'error']
- `message`：str
- `artifact_path`：str | None"""
    timestamp: datetime
    level: Literal["info", "success", "error"] = "info"
    message: str
    artifact_path: str | None = None


class WorkflowLog(BaseModel):
    """工作流日志。
字段：
- `timestamp`：datetime
- `level`：Literal['info', 'warning', 'error']
- `stage`：str | None
- `message`：str
- `detail`：str | None"""
    timestamp: datetime
    level: Literal["info", "warning", "error"] = "info"
    stage: str | None = None
    message: str
    detail: str | None = None


class WorkflowRun(BaseModel):
    """工作流持久化状态。
字段：
- `id`：str
- `status`：WorkflowStatus
- `seed`：TopicSeed
- `topics`：list[Topic]
- `outputs`：list[AgentOutput]
- `standalone_outputs`：list[AgentOutput]
- `run_dir`：str
- `created_at`：datetime
- `completed_at`：datetime | None
- `error`：str | None
- `current_stage`：str | None
- `resumable`：bool
- `source_status`：dict[str, str]
- `stage_status`：dict[str, WorkflowStageStatus]
- `logs`：list[WorkflowLog]
- `log_file`：str | None
- `viral_analysis`：ViralAnalysisConfig
- `selected_topic_title`：str | None"""
    id: str
    status: WorkflowStatus
    seed: TopicSeed
    topics: list[Topic]
    outputs: list[AgentOutput]
    # 独立工作台生成的结果与流水线阶段产物分开保存，但仍属于项目导入导出边界。
    standalone_outputs: list[AgentOutput] = Field(default_factory=list)
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
    selected_topic_title: str | None = None


class RunWorkflowRequest(BaseModel):
    """创建工作流请求。
字段：
- `seed`：TopicSeed
- `execution_mode`：Literal['auto', 'step', 'manual']
- `viral_analysis`：ViralAnalysisConfig
- `selected_topic_title`：str | None"""
    seed: TopicSeed = Field(default_factory=TopicSeed)
    # manual 模式只创建检查点，不启动后台任务；用户点击“运行工作流”或“执行下一步”后才执行。
    execution_mode: Literal["auto", "step", "manual"] = "auto"
    viral_analysis: ViralAnalysisConfig = Field(default_factory=ViralAnalysisConfig)
    selected_topic_title: str | None = None


class StepWorkflowRequest(BaseModel):
    """单步或阶段重跑请求。
字段：
- `selected_topic_title`：str | None
- `stage`：str | None"""
    selected_topic_title: str | None = None
    # 指定后，从该阶段开始重跑并执行下游阶段，同时保留上游检查点。
    stage: str | None = None


class GenerateScriptRequest(BaseModel):
    """口播脚本生成请求。
字段：
- `topic`：str
- `angle`：str
- `duration_seconds`：int
- `audience`：str"""
    topic: str
    angle: str = ""
    duration_seconds: int = Field(default=110, ge=30, le=240)
    audience: str = Field(default="关注 AI 工具的一线创作者和创业者")


class StockAnalysisRequest(BaseModel):
    """股票分析请求。
字段：
- `stocks`：str
- `days`：int
- `include_news`：bool"""
    stocks: str = Field(
        min_length=1,
        description="股票代码或名称，多个代码用逗号分隔，例如 600519,TSLA,HK00700。",
    )
    days: int = Field(default=120, ge=30, le=365)
    include_news: bool = True


class StockAnalysisResult(BaseModel):
    """股票分析结果。
字段：
- `agent_id`：str
- `skill`：str
- `skill_source`：str
- `stocks`：str
- `report`：str
- `raw_data`：dict
- `data_script`：str
- `news_enabled`：bool
- `disclaimer`：str
- `data_status`：Literal['ok', 'partial', 'unavailable']
- `source_status`：dict[str, str]"""
    agent_id: str = "stock_assistant"
    skill: str = "stock-analysis"
    skill_source: str
    stocks: str
    report: str
    raw_data: dict
    data_script: str
    news_enabled: bool
    disclaimer: str
    data_status: Literal["ok", "partial", "unavailable"] = "ok"
    source_status: dict[str, str] = Field(default_factory=dict)

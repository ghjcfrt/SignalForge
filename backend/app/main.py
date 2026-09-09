"""FastAPI 应用入口及全部 HTTP 接口。"""

import json
import asyncio
import contextlib
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.app.agents import AGENTS, ensure_agent_workspaces
from backend.app.config import WORKSPACE_DIR, get_env_settings, get_output_directory_settings, get_settings, get_timeout_settings, update_env_settings, update_output_directory_settings, update_timeout_settings
from backend.app.directory_picker import directory_picker
from backend.app.llm import LlmGateway
from backend.app.schemas import (
    ApiStatus,
    Agent,
    AgentOutput,
    RunWorkflowRequest,
    RunAgentRequest,
    Topic,
    TopicSeed,
    WorkflowRun,
    StockAnalysisRequest,
    StockAnalysisResult,
    TimeoutSettings,
    OutputDirectorySettings,
    EnvSettings,
    EnvSettingsUpdate,
    StepWorkflowRequest,
)
from backend.app.workflows import (
    get_run,
    list_runs,
    run_hot_video_workflow,
    scout_topics,
    analyze_stocks,
    stock_sources_health,
    _load_persisted_runs,
    _ensure_workflow_state,
    create_workflow,
    next_workflow_stage,
    reset_workflow_from_stage,
    WORKFLOW_STAGES,
    run_agent,
    RUNS,
    _checkpoint,
    _log,
)
from backend.app.video_tools import (
    MoneyPrinterTurboRequest,
    MoneyPrinterTurboRunResult,
    MoneyPrinterTurboStatus,
    mpt_status,
    run_moneyprinterturbo,
)


# FastAPI 应用实例和后台任务索引。
app = FastAPI(title="热讯工坊 API", version="0.1.0")
WORKFLOW_TASKS: dict[str, asyncio.Task] = {}
# 员工日志文件名；读取时兼容旧版 JSONL 文件。
AGENT_LOG_FILENAME = "agent.log"
LEGACY_AGENT_LOG_FILENAME = "agent.log.jsonl"

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    """函数“startup”：应用启动时加载持久化工作流并准备员工工作目录。
返回：None。"""
    ensure_agent_workspaces()
    _load_persisted_runs()


@app.get("/api/health")
async def health() -> dict[str, str]:
    """函数“health”：返回服务存活状态。
返回：dict[str, str]。"""
    return {"status": "ok", "service": "热讯工坊"}


@app.get("/api/status", response_model=ApiStatus)
async def api_status() -> ApiStatus:
    """函数“api_status”：返回模型配置、密钥状态和可用性诊断。
返回：ApiStatus。"""
    settings = get_settings()
    model_available, diagnostic = await LlmGateway(settings).check_model()
    key = settings.ai_api_key or ""
    if len(key) > 8:
        key_preview = f"{key[:4]}{'*' * max(4, len(key) - 8)}{key[-4:]}"
    elif len(key) >= 4:
        key_preview = f"{key[:2]}{'*' * max(2, len(key) - 4)}{key[-2:]}"
    else:
        key_preview = "*" * len(key) if key else None
    return ApiStatus(
        key_variable="AI_API_KEY",
        has_key=settings.ai_enabled,
        base_url=settings.ai_base_url,
        model=settings.ai_model or "未配置（在线模式不可用）",
        mode="live" if settings.ai_enabled and model_available else "local-template",
        model_available=model_available,
        diagnostic=diagnostic,
        key_preview=key_preview,
    )


@app.get("/api/settings/timeouts", response_model=TimeoutSettings)
async def timeout_settings() -> TimeoutSettings:
    """函数“timeout_settings”，负责timeout settings。
返回：TimeoutSettings。"""
    return get_timeout_settings()


@app.put("/api/settings/timeouts", response_model=TimeoutSettings)
async def timeout_settings_update(payload: TimeoutSettings) -> TimeoutSettings:
    """函数“timeout_settings_update”，负责timeout settings update。
参数：
    payload: TimeoutSettings
返回：TimeoutSettings。"""
    return update_timeout_settings(payload)


@app.get("/api/settings/output-directories", response_model=OutputDirectorySettings)
async def output_directories() -> OutputDirectorySettings:
    """函数“output_directories”，负责output directories。
返回：OutputDirectorySettings。"""
    return get_output_directory_settings()


@app.put("/api/settings/output-directories", response_model=OutputDirectorySettings)
async def output_directories_update(payload: OutputDirectorySettings) -> OutputDirectorySettings:
    """函数“output_directories_update”，负责output directories update。
参数：
    payload: OutputDirectorySettings
返回：OutputDirectorySettings。"""
    return update_output_directory_settings(payload)


@app.get("/api/local/select-directory")
async def select_directory() -> dict[str, str | None]:
    """在运行 API 的机器上打开原生目录选择器。"""
    path = await asyncio.to_thread(directory_picker.pick)
    return {"path": path}


@app.get("/api/local/open-artifacts")
async def open_artifacts_folder() -> dict[str, str]:
    """打开包含所有工作流产物的父目录。"""
    target = (WORKSPACE_DIR / "runs").resolve()
    target.mkdir(parents=True, exist_ok=True)

    def launch() -> None:
        """函数“launch”：在操作系统中打开指定文件或目录。
返回：None。"""
        if os.name == "nt":
            os.startfile(str(target))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])

    try:
        await asyncio.to_thread(launch)
    except OSError as exc:
        raise HTTPException(status_code=502, detail=f"无法打开产物文件夹：{exc}") from exc
    return {"path": str(target)}


@app.get("/api/settings/env", response_model=EnvSettings)
async def env_settings() -> EnvSettings:
    """函数“env_settings”，负责env settings。
返回：EnvSettings。"""
    return get_env_settings()


@app.put("/api/settings/env", response_model=EnvSettings)
async def env_settings_update(payload: EnvSettingsUpdate) -> EnvSettings:
    """函数“env_settings_update”，负责env settings update。
参数：
    payload: EnvSettingsUpdate
返回：EnvSettings。"""
    return update_env_settings(payload)


@app.get("/api/agents", response_model=list[Agent])
async def agents() -> list[Agent]:
    """函数“agents”，负责agents。
返回：list[Agent]。"""
    return AGENTS


@app.post("/api/topics/scout", response_model=list[Topic])
async def topics(seed: TopicSeed) -> list[Topic]:
    """函数“topics”，负责topics。
参数：
    seed: TopicSeed
返回：list[Topic]。"""
    try:
        settings = get_settings()
        scout = scout_topics(seed, settings)
        if settings.workflow_timeout_seconds > 0:
            topics_result, _ = await asyncio.wait_for(scout, timeout=settings.workflow_timeout_seconds)
        else:
            topics_result, _ = await scout
        return topics_result
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="热点扫描超过工作流总时限，已停止") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/agents/{agent_id}/run", response_model=AgentOutput)
async def run_single_agent(agent_id: str, request: RunAgentRequest) -> AgentOutput:
    """函数“run_single_agent”：独立执行一个员工工作台任务并保存结果。
参数：
    agent_id: str
    request: RunAgentRequest
返回：AgentOutput。"""
    _write_agent_log(agent_id, None, "info", "独立任务已开始")
    try:
        # 为本次请求复制全局配置，避免控制台修改超时后影响员工工作台。
        workbench_settings = get_settings().model_copy(update={
            "workflow_timeout_seconds": request.timeout_seconds,
            "news_fetch_timeout_seconds": request.timeout_seconds,
            "model_timeout_seconds": request.timeout_seconds,
        })
        task = run_agent(agent_id, request, workbench_settings)
        output = await task if request.timeout_seconds <= 0 else await asyncio.wait_for(task, timeout=request.timeout_seconds)
        # 独立工作台结果也属于项目资产；
        # 与流水线阶段输出分开保存，便于单独重跑阶段。
        if request.project_run_id:
            project = get_run(request.project_run_id)
            if project is not None:
                project.standalone_outputs = [
                    item for item in project.standalone_outputs
                    if item.agent_id != output.agent_id
                ]
                project.standalone_outputs.append(output)
                _checkpoint(project)
        _write_agent_log(agent_id, output.artifact_path, "success", "独立任务已完成")
        return output
    except asyncio.TimeoutError as exc:
        message = f"独立工作台超过设定超时 {request.timeout_seconds} 秒"
        _write_agent_log(agent_id, None, "error", message)
        raise HTTPException(status_code=504, detail=message) from exc
    except ValueError as exc:
        _write_agent_log(agent_id, None, "error", str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        _write_agent_log(agent_id, None, "error", str(exc))
        raise HTTPException(status_code=502, detail=f"{agent_id} 执行失败：{exc}") from exc


def _agent_log_path(agent_id: str) -> Path:
    """返回员工日志的标准路径，并在需要时迁移旧版 JSONL 文件名。"""
    log_dir = WORKSPACE_DIR / "agent-logs" / agent_id
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / AGENT_LOG_FILENAME
    legacy_path = log_dir / LEGACY_AGENT_LOG_FILENAME
    if legacy_path.exists():
        if path.exists():
            with legacy_path.open("rb") as source, path.open("ab") as destination:
                destination.write(source.read())
            legacy_path.unlink()
        else:
            legacy_path.replace(path)
    return path


def _write_agent_log(agent_id: str, artifact_path: str | None, level: str, message: str) -> None:
    """持久化单个员工日志，不与控制台工作流日志混在一起。"""
    path = _agent_log_path(agent_id)
    entry = {"timestamp": datetime.now().astimezone().isoformat(), "level": level, "message": message, "artifact_path": artifact_path}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


@app.get("/api/agents/{agent_id}/logs")
async def agent_logs(agent_id: str) -> list[dict[str, object]]:
    """函数“agent_logs”：读取指定员工的执行日志。
参数：
    agent_id: str
返回：list[dict[str, object]]。"""
    if agent_id not in {agent.id for agent in AGENTS}:
        raise HTTPException(status_code=404, detail="未知员工")
    path = _agent_log_path(agent_id)
    if not path.exists():
        return []
    entries: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines()[-100:]:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


@app.post("/api/stocks/analyze", response_model=StockAnalysisResult)
async def stocks(request: StockAnalysisRequest) -> StockAnalysisResult:
    """函数“stocks”，负责stocks。
参数：
    request: StockAnalysisRequest
返回：StockAnalysisResult。"""
    return await analyze_stocks(request, get_settings())


@app.get("/api/stocks/health")
async def stocks_health() -> dict[str, object]:
    """函数“stocks_health”，负责stocks health。
返回：dict[str, object]。"""
    return stock_sources_health(get_settings())


@app.post("/api/workflows/hot-video", response_model=WorkflowRun)
async def workflow(request: RunWorkflowRequest) -> WorkflowRun:
    """函数“workflow”：创建工作流任务并按执行模式启动或暂停。
参数：
    request: RunWorkflowRequest
返回：WorkflowRun。"""
    run = create_workflow(request.seed, request.viral_analysis)
    run.selected_topic_title = request.selected_topic_title
    if request.execution_mode == "manual":
        return run
    stop_after = next_workflow_stage(run) if request.execution_mode == "step" else None
    task = asyncio.create_task(_execute_workflow(run, stop_after_stage=stop_after))
    WORKFLOW_TASKS[run.id] = task
    return run


async def _execute_workflow(run: WorkflowRun, *, stop_after_stage: str | None = None) -> None:
    """内部辅助函数“_execute_workflow”：在后台执行工作流并持久化每个阶段的状态。
参数：
    run: WorkflowRun
    stop_after_stage: str | None
返回：None。"""
    runner: asyncio.Task | None = None
    try:
        timeout = get_settings().workflow_timeout_seconds
        runner = asyncio.create_task(run_hot_video_workflow(
            run.seed,
            get_settings(),
            existing=run,
            stop_after_stage=stop_after_stage,
            selected_topic_title=run.selected_topic_title,
        ))
        if timeout > 0:
            # 工作流超时只约束规划阶段，不限制视频编辑器；
            # MoneyPrinterTurbo 可能花费较长时间安装依赖、下载素材、合成语音和编码。
            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    if run.current_stage == "video_editor":
                        await runner
                        break
                    runner.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await runner
                    raise asyncio.TimeoutError
                try:
                    await asyncio.wait_for(asyncio.shield(runner), timeout=remaining)
                    break
                except asyncio.TimeoutError:
                    # 如果编辑器启动时规划阶段已到截止时间，则给予它独立的执行窗口；
                    # 否则继续执行工作流超时限制，保留可恢复检查点。
                    if run.current_stage == "video_editor":
                        await runner
                        break
                    runner.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await runner
                    raise
        else:
            await runner
    except asyncio.TimeoutError:
        run.status = "failed"
        run.resumable = True
        run.completed_at = None
        stage = run.current_stage or "unknown"
        if stage in run.stage_status:
            run.stage_status[stage] = "failed"
        run.error = f"{stage}: 超过工作流总时限 {get_settings().workflow_timeout_seconds} 秒"
        _log(run, "工作流超过总时限，已停止并保留检查点", stage=stage, level="error", detail=run.error)
        _checkpoint(run)
    except asyncio.CancelledError:
        if runner is not None and not runner.done():
            runner.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await runner
        run.status = "paused"
        run.resumable = True
        run.completed_at = None
        stage = run.current_stage or "unknown"
        run.error = f"{stage}: 用户手动停止了任务"
        _log(run, "任务已手动停止，可从检查点继续", stage=stage, level="warning")
        _checkpoint(run)
    finally:
        WORKFLOW_TASKS.pop(run.id, None)


@app.get("/api/workflows", response_model=list[WorkflowRun])
async def workflows() -> list[WorkflowRun]:
    """函数“workflows”：列出所有可恢复或已完成的工作流。
返回：list[WorkflowRun]。"""
    return list_runs()


@app.get("/api/workflows/{run_id}", response_model=WorkflowRun)
async def workflow_detail(run_id: str) -> WorkflowRun:
    """函数“workflow_detail”：读取指定工作流的完整状态和日志。
参数：
    run_id: str
返回：WorkflowRun。"""
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    return run


@app.post("/api/workflows/{run_id}/resume", response_model=WorkflowRun)
async def workflow_resume(run_id: str) -> WorkflowRun:
    """函数“workflow_resume”：从当前检查点继续执行工作流。
参数：
    run_id: str
返回：WorkflowRun。"""
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    if not run.resumable:
        raise HTTPException(status_code=409, detail="该任务没有可继续的未完成阶段")
    if run_id in WORKFLOW_TASKS and not WORKFLOW_TASKS[run_id].done():
        raise HTTPException(status_code=409, detail="该任务正在执行中")
    run.status = "queued"
    run.error = None
    task = asyncio.create_task(_execute_workflow(run))
    WORKFLOW_TASKS[run_id] = task
    return run


@app.get("/api/artifacts/preview")
async def artifact_preview(path: str) -> FileResponse:
    """为应用内产物预览提供本地生成的图像文件。"""
    target = Path(path).expanduser().resolve()
    workspace_root = Path(__file__).resolve().parents[2] / "workspaces"
    try:
        target.relative_to(workspace_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="产物路径不在工作区内") from exc
    if target.suffix.lower() not in {".svg", ".png", ".jpg", ".jpeg", ".webp"} or not target.is_file():
        raise HTTPException(status_code=404, detail="图片产物不存在")
    return FileResponse(target)


@app.post("/api/workflows/{run_id}/step", response_model=WorkflowRun)
async def workflow_step(run_id: str, request: StepWorkflowRequest | None = None) -> WorkflowRun:
    """函数“workflow_step”：只执行工作流的下一阶段。
参数：
    run_id: str
    request: StepWorkflowRequest | None
返回：WorkflowRun。"""
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    if run_id in WORKFLOW_TASKS and not WORKFLOW_TASKS[run_id].done():
        raise HTTPException(status_code=409, detail="该任务正在执行中")
    requested_stage = request.stage.strip() if request and request.stage else None
    if requested_stage and requested_stage not in WORKFLOW_STAGES:
        raise HTTPException(status_code=400, detail=f"未知流水线阶段：{requested_stage}")
    if requested_stage:
        if requested_stage != "hotspot_monitor" and not run.topics:
            raise HTTPException(status_code=409, detail="该阶段依赖热点监控产物，请先完成热点监控")
        reset_workflow_from_stage(run, requested_stage)
        stage = requested_stage
    else:
        if run.status == "completed":
            raise HTTPException(status_code=409, detail="该任务已经完成")
        stage = next_workflow_stage(run)
    if not stage:
        raise HTTPException(status_code=409, detail="没有可执行的阶段")
    run.status = "queued"
    run.error = None
    if request and request.selected_topic_title is not None:
        run.selected_topic_title = request.selected_topic_title.strip() or None
    task = asyncio.create_task(_execute_workflow(run, stop_after_stage=stage))
    WORKFLOW_TASKS[run_id] = task
    return run


@app.post("/api/workflows/{run_id}/cancel", response_model=WorkflowRun)
async def workflow_cancel(run_id: str) -> WorkflowRun:
    """函数“workflow_cancel”：取消正在运行的工作流并保存取消状态。
参数：
    run_id: str
返回：WorkflowRun。"""
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    task = WORKFLOW_TASKS.get(run_id)
    if task is None or task.done():
        raise HTTPException(status_code=409, detail="该任务当前没有正在执行的后台任务")
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    return run


@app.get("/api/workflows/{run_id}/export")
async def workflow_export(run_id: str) -> dict:
    """函数“workflow_export”：导出工作流项目及其产物。
参数：
    run_id: str
返回：dict。"""
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    return {"format": "signalforge-project", "version": 1, "project": run.model_dump(mode="json")}


@app.post("/api/workflows/import", response_model=WorkflowRun)
async def workflow_import(file: UploadFile = File(...)) -> WorkflowRun:
    """函数“workflow_import”：导入项目压缩包并恢复工作流状态。
参数：
    file: UploadFile
返回：WorkflowRun。"""
    try:
        payload = json.loads((await file.read()).decode("utf-8"))
        project = payload.get("project", payload)
        run = WorkflowRun.model_validate(project)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"项目文件无效：{exc}") from exc
    run.id = f"imported-{uuid4().hex[:10]}"
    # 导入项目要成为面板中的当前项目；
    # 保留原始时间戳可使旧任务按时间排序并恢复为待处理状态。
    run.created_at = datetime.now().astimezone()
    _ensure_workflow_state(run)
    RUNS[run.id] = run
    Path(run.run_dir).mkdir(parents=True, exist_ok=True)
    Path(run.run_dir, "run-state.json").write_text(run.model_dump_json(indent=2), encoding="utf-8")
    return run


@app.get("/api/video/moneyprinterturbo/status", response_model=MoneyPrinterTurboStatus)
async def moneyprinterturbo_status() -> MoneyPrinterTurboStatus:
    """函数“moneyprinterturbo_status”：返回视频生成工具的安装和可用性状态。
返回：MoneyPrinterTurboStatus。"""
    return mpt_status(get_settings())


@app.post("/api/video/moneyprinterturbo/run", response_model=MoneyPrinterTurboRunResult)
async def moneyprinterturbo_run(request: MoneyPrinterTurboRequest) -> MoneyPrinterTurboRunResult:
    """函数“moneyprinterturbo_run”：启动一次独立的视频生成任务。
参数：
    request: MoneyPrinterTurboRequest
返回：MoneyPrinterTurboRunResult。"""
    if not request.output_dir:
        request.output_dir = get_output_directory_settings().video_output_dir.strip() or None
    return await run_moneyprinterturbo(request, get_settings())

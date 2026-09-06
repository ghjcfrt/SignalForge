import json
import asyncio
import contextlib
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.app.agents import AGENTS, ensure_agent_workspaces
from backend.app.config import get_env_settings, get_output_directory_settings, get_settings, get_timeout_settings, update_env_settings, update_output_directory_settings, update_timeout_settings
from backend.app.directory_picker import directory_picker
from backend.app.llm import LlmGateway
from backend.app.schemas import (
    ApiStatus,
    Agent,
    AgentOutput,
    GenerateScriptRequest,
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
    generate_script,
    get_run,
    list_runs,
    run_hot_video_workflow,
    scout_topics,
    analyze_stocks,
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


app = FastAPI(title="热讯工坊 API", version="0.1.0")
WORKFLOW_TASKS: dict[str, asyncio.Task] = {}

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
    ensure_agent_workspaces()
    _load_persisted_runs()


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "热讯工坊"}


@app.get("/api/status", response_model=ApiStatus)
async def api_status() -> ApiStatus:
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
    return get_timeout_settings()


@app.put("/api/settings/timeouts", response_model=TimeoutSettings)
async def timeout_settings_update(payload: TimeoutSettings) -> TimeoutSettings:
    return update_timeout_settings(payload)


@app.get("/api/settings/output-directories", response_model=OutputDirectorySettings)
async def output_directories() -> OutputDirectorySettings:
    return get_output_directory_settings()


@app.put("/api/settings/output-directories", response_model=OutputDirectorySettings)
async def output_directories_update(payload: OutputDirectorySettings) -> OutputDirectorySettings:
    return update_output_directory_settings(payload)


@app.get("/api/local/select-directory")
async def select_directory() -> dict[str, str | None]:
    """Open the native directory chooser on the machine running the API."""
    path = await asyncio.to_thread(directory_picker.pick)
    return {"path": path}


@app.get("/api/settings/env", response_model=EnvSettings)
async def env_settings() -> EnvSettings:
    return get_env_settings()


@app.put("/api/settings/env", response_model=EnvSettings)
async def env_settings_update(payload: EnvSettingsUpdate) -> EnvSettings:
    return update_env_settings(payload)


@app.get("/api/agents", response_model=list[Agent])
async def agents() -> list[Agent]:
    return AGENTS


@app.post("/api/topics/scout", response_model=list[Topic])
async def topics(seed: TopicSeed) -> list[Topic]:
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


@app.post("/api/scripts/generate", response_model=AgentOutput)
async def scripts(request: GenerateScriptRequest) -> AgentOutput:
    return await generate_script(request, get_settings())


@app.post("/api/agents/{agent_id}/run", response_model=AgentOutput)
async def run_single_agent(agent_id: str, request: RunAgentRequest) -> AgentOutput:
    try:
        return await run_agent(agent_id, request, get_settings())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"{agent_id} 执行失败：{exc}") from exc


@app.post("/api/stocks/analyze", response_model=StockAnalysisResult)
async def stocks(request: StockAnalysisRequest) -> StockAnalysisResult:
    return await analyze_stocks(request, get_settings())


@app.post("/api/workflows/hot-video", response_model=WorkflowRun)
async def workflow(request: RunWorkflowRequest) -> WorkflowRun:
    run = create_workflow(request.seed, request.viral_analysis)
    run.selected_topic_title = request.selected_topic_title
    if request.execution_mode == "manual":
        return run
    stop_after = next_workflow_stage(run) if request.execution_mode == "step" else None
    task = asyncio.create_task(_execute_workflow(run, stop_after_stage=stop_after))
    WORKFLOW_TASKS[run.id] = task
    return run


async def _execute_workflow(run: WorkflowRun, *, stop_after_stage: str | None = None) -> None:
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
            # The workflow limit applies to the planning stages, but must not
            # terminate the video editor. MoneyPrinterTurbo can spend an
            # unbounded amount of time installing dependencies, downloading
            # footage, synthesising audio and encoding the final video.
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
                    # If the editor started as the deadline elapsed, hand it
                    # an unlimited window; otherwise enforce the workflow
                    # timeout and retain the normal resumable checkpoint.
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
    return list_runs()


@app.get("/api/workflows/{run_id}", response_model=WorkflowRun)
async def workflow_detail(run_id: str) -> WorkflowRun:
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    return run


@app.post("/api/workflows/{run_id}/resume", response_model=WorkflowRun)
async def workflow_resume(run_id: str) -> WorkflowRun:
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
    """Serve a generated local image for the in-app artifact preview."""
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
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    return {"format": "signalforge-project", "version": 1, "project": run.model_dump(mode="json")}


@app.post("/api/workflows/import", response_model=WorkflowRun)
async def workflow_import(file: UploadFile = File(...)) -> WorkflowRun:
    try:
        payload = json.loads((await file.read()).decode("utf-8"))
        project = payload.get("project", payload)
        run = WorkflowRun.model_validate(project)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"项目文件无效：{exc}") from exc
    run.id = f"imported-{uuid4().hex[:10]}"
    # Imported projects must become the current/latest project in the
    # dashboard; retaining the source timestamp lets an older run win the
    # recency sort and makes the overview appear to reset to pending.
    run.created_at = datetime.now().astimezone()
    _ensure_workflow_state(run)
    RUNS[run.id] = run
    Path(run.run_dir).mkdir(parents=True, exist_ok=True)
    Path(run.run_dir, "run-state.json").write_text(run.model_dump_json(indent=2), encoding="utf-8")
    return run


@app.get("/api/video/moneyprinterturbo/status", response_model=MoneyPrinterTurboStatus)
async def moneyprinterturbo_status() -> MoneyPrinterTurboStatus:
    return mpt_status(get_settings())


@app.post("/api/video/moneyprinterturbo/run", response_model=MoneyPrinterTurboRunResult)
async def moneyprinterturbo_run(request: MoneyPrinterTurboRequest) -> MoneyPrinterTurboRunResult:
    if not request.output_dir:
        request.output_dir = get_output_directory_settings().video_output_dir.strip() or None
    return await run_moneyprinterturbo(request, get_settings())

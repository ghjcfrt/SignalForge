import json
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

from backend.app.agents import AGENTS, ensure_agent_workspaces
from backend.app.config import get_settings, get_timeout_settings, update_timeout_settings
from backend.app.llm import LlmGateway
from backend.app.schemas import (
    ApiStatus,
    Agent,
    AgentOutput,
    GenerateScriptRequest,
    RunWorkflowRequest,
    Topic,
    TopicSeed,
    WorkflowRun,
    StockAnalysisRequest,
    StockAnalysisResult,
    TimeoutSettings,
)
from backend.app.workflows import (
    generate_script,
    get_run,
    list_runs,
    run_hot_video_workflow,
    scout_topics,
    analyze_stocks,
    _load_persisted_runs,
)
from backend.app.video_tools import (
    MoneyPrinterTurboRequest,
    MoneyPrinterTurboRunResult,
    MoneyPrinterTurboStatus,
    mpt_status,
    run_moneyprinterturbo,
)


app = FastAPI(title="热讯工坊 API", version="0.1.0")

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
    return ApiStatus(
        key_variable="AI_API_KEY",
        has_key=settings.ai_enabled,
        base_url=settings.ai_base_url,
        model=settings.ai_model or "未配置（在线模式不可用）",
        mode="live" if settings.ai_enabled and model_available else "local-template",
        model_available=model_available,
        diagnostic=diagnostic,
    )


@app.get("/api/settings/timeouts", response_model=TimeoutSettings)
async def timeout_settings() -> TimeoutSettings:
    return get_timeout_settings()


@app.put("/api/settings/timeouts", response_model=TimeoutSettings)
async def timeout_settings_update(payload: TimeoutSettings) -> TimeoutSettings:
    return update_timeout_settings(payload)


@app.get("/api/agents", response_model=list[Agent])
async def agents() -> list[Agent]:
    return AGENTS


@app.post("/api/topics/scout", response_model=list[Topic])
async def topics(seed: TopicSeed) -> list[Topic]:
    try:
        topics_result, _ = await scout_topics(seed, get_settings())
        return topics_result
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/scripts/generate", response_model=AgentOutput)
async def scripts(request: GenerateScriptRequest) -> AgentOutput:
    return await generate_script(request, get_settings())


@app.post("/api/stocks/analyze", response_model=StockAnalysisResult)
async def stocks(request: StockAnalysisRequest) -> StockAnalysisResult:
    return await analyze_stocks(request, get_settings())


@app.post("/api/workflows/hot-video", response_model=WorkflowRun)
async def workflow(request: RunWorkflowRequest) -> WorkflowRun:
    return await run_hot_video_workflow(request.seed, get_settings())


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
    # Re-enter the persisted task through the same workflow contract. The
    # checkpoint remains available if a later stage fails again.
    return await run_hot_video_workflow(run.seed, get_settings(), existing=run)


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
    RUNS[run.id] = run
    Path(run.run_dir).mkdir(parents=True, exist_ok=True)
    Path(run.run_dir, "run-state.json").write_text(run.model_dump_json(indent=2), encoding="utf-8")
    return run


@app.get("/api/video/moneyprinterturbo/status", response_model=MoneyPrinterTurboStatus)
async def moneyprinterturbo_status() -> MoneyPrinterTurboStatus:
    return mpt_status(get_settings())


@app.post("/api/video/moneyprinterturbo/run", response_model=MoneyPrinterTurboRunResult)
async def moneyprinterturbo_run(request: MoneyPrinterTurboRequest) -> MoneyPrinterTurboRunResult:
    return await run_moneyprinterturbo(request, get_settings())

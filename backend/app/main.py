from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.app.agents import AGENTS, ensure_agent_workspaces
from backend.app.config import get_settings
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
)
from backend.app.workflows import (
    generate_script,
    get_run,
    list_runs,
    run_hot_video_workflow,
    scout_topics,
    analyze_stocks,
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


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "热讯工坊"}


@app.get("/api/status", response_model=ApiStatus)
async def api_status() -> ApiStatus:
    settings = get_settings()
    return ApiStatus(
        key_variable="AI_API_KEY",
        has_key=settings.ai_enabled,
        base_url=settings.ai_base_url,
        model=settings.ai_model or "中转站自动选择",
        mode="live" if settings.ai_enabled else "local-template",
    )


@app.get("/api/agents", response_model=list[Agent])
async def agents() -> list[Agent]:
    return AGENTS


@app.post("/api/topics/scout", response_model=list[Topic])
async def topics(seed: TopicSeed) -> list[Topic]:
    topics_result, _ = await scout_topics(seed, get_settings())
    return topics_result


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


@app.get("/api/video/moneyprinterturbo/status", response_model=MoneyPrinterTurboStatus)
async def moneyprinterturbo_status() -> MoneyPrinterTurboStatus:
    return mpt_status(get_settings())


@app.post("/api/video/moneyprinterturbo/run", response_model=MoneyPrinterTurboRunResult)
async def moneyprinterturbo_run(request: MoneyPrinterTurboRequest) -> MoneyPrinterTurboRunResult:
    return await run_moneyprinterturbo(request, get_settings())

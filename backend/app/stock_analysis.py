"""股票数据采集和分析报告生成。"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import subprocess
import sys
import time
from backend.app.config import WORKSPACE_DIR, Settings
from backend.app.llm import LlmGateway
from backend.app.schemas import StockAnalysisRequest, StockAnalysisResult

# 股票 Skill 目录、数据脚本、提示词模板和报告模板。
STOCK_SKILL_DIR = WORKSPACE_DIR / "agents" / "stock_assistant" / "skills" / "stock-analysis"
STOCK_DATA_SCRIPT = STOCK_SKILL_DIR / "references" / "stock_data_fetcher.py"
STOCK_ANALYSIS_PROMPT = STOCK_SKILL_DIR / "references" / "analysis-prompt-template.md"
# 股票分析结果的中文输出格式模板。
STOCK_OUTPUT_TEMPLATE = STOCK_SKILL_DIR / "references" / "output-format-template.md"
# 按股票、天数和是否包含新闻缓存近期分析结果。
STOCK_ANALYSIS_CACHE: dict[tuple[str, int, bool], tuple[float, StockAnalysisResult]] = {}

async def analyze_stocks(request: StockAnalysisRequest, settings: Settings) -> StockAnalysisResult:
    """执行已安装的股票分析 Skill，返回行情、指标和风险说明。"""
    cache_key = (request.stocks.strip().upper(), request.days, request.include_news)
    cached = STOCK_ANALYSIS_CACHE.get(cache_key)
    if cached and settings.stock_cache_ttl_seconds > 0 and time.monotonic() - cached[0] < settings.stock_cache_ttl_seconds:
        result = cached[1].model_copy(deep=True)
        result.source_status = {**result.source_status, "cache": "hit"}
        return result
    if not STOCK_DATA_SCRIPT.exists():
        raise FileNotFoundError(f"Stock Analysis Skill data script not found: {STOCK_DATA_SCRIPT}")

    env = os.environ.copy()
    for name, value in {
        "TUSHARE_TOKEN": settings.tushare_token,
        "TAVILY_API_KEY": settings.tavily_api_key,
        "SERPAPI_KEY": settings.serpapi_key,
    }.items():
        if value:
            env[name] = value

    command = [sys.executable, str(STOCK_DATA_SCRIPT), "--stocks", request.stocks, "--days", str(request.days)]
    if request.include_news:
        command.append("--news")
    process_error: str | None = None
    stdout = b""
    stderr = b""
    completed = None
    for attempt in range(settings.stock_fetch_retries + 1):
        try:
            completed = await asyncio.wait_for(
                asyncio.to_thread(subprocess.run, command, cwd=STOCK_SKILL_DIR, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False),
                timeout=120,
            )
            stdout, stderr = completed.stdout or b"", completed.stderr or b""
            if completed.returncode == 0:
                process_error = None
                break
            process_error = stderr.decode("utf-8", errors="replace").strip() or "Stock Analysis Skill returned a non-zero exit code"
        except asyncio.TimeoutError:
            process_error = "Stock Analysis Skill data fetch exceeded 120 seconds"
        if attempt < settings.stock_fetch_retries:
            await asyncio.sleep(min(2 ** attempt, 4))

    raw_text = stdout.decode("utf-8", errors="replace")
    if process_error is None and completed is not None and completed.returncode != 0:
        process_error = stderr.decode("utf-8", errors="replace").strip() or raw_text.strip()
    try:
        raw_data = json.loads(raw_text)
    except json.JSONDecodeError:
        raw_data = {}
        process_error = process_error or f"Stock Analysis Skill returned invalid JSON: {raw_text[-500:]}"

    if process_error:
        raw_data = {**(raw_data if isinstance(raw_data, dict) else {}), "errors": [*((raw_data.get("errors") or []) if isinstance(raw_data, dict) else []), {"type": "data_fetch", "error": process_error}], "total_success": 0}

    fallback = json.dumps(raw_data, ensure_ascii=False, indent=2)
    prompt = STOCK_ANALYSIS_PROMPT.read_text(encoding="utf-8") if STOCK_ANALYSIS_PROMPT.exists() else ""
    template = STOCK_OUTPUT_TEMPLATE.read_text(encoding="utf-8") if STOCK_OUTPUT_TEMPLATE.exists() else ""
    result = await LlmGateway(settings).complete(
        system=("你是 SignalForge 的股票助手。严格依据输入的真实数据和新闻输出中文股票决策看板。"
                "不得编造价格或新闻；缺失数据必须明确标注。必须包含数据来源、分析时间、风险和免责声明。"
                "这不是投资建议。\n\n分析框架：\n" + prompt + "\n\n输出模板：\n" + template),
        user="请分析以下 Stock Analysis Skill 数据：\n" + fallback,
        fallback=((f"# 股票数据暂不可用\n\n{process_error}\n\n请稍后重试。\n\n" if process_error else "") + fallback + "\n\n> 免责声明：以上分析仅供参考，不构成投资建议。投资有风险，入市需谨慎。"),
    )
    source_status = {str(name): str(status) for name, status in (raw_data.get("data_sources") or {}).items()} if isinstance(raw_data, dict) else {}
    source_status["cache"] = "miss"
    if process_error:
        data_status = "unavailable"
    elif isinstance(raw_data, dict) and raw_data.get("total_success", 0) < raw_data.get("total_requested", 0):
        data_status = "partial"
    else:
        data_status = "ok"
    final = StockAnalysisResult(skill_source="https://github.com/liusai0820/Stock-Analysis-Skill", stocks=request.stocks, report=result.content, raw_data=raw_data, data_script=str(STOCK_DATA_SCRIPT), news_enabled=request.include_news, disclaimer="以上分析仅供参考，不构成投资建议。投资有风险，入市需谨慎。", data_status=data_status, source_status=source_status)
    if data_status != "unavailable":
        STOCK_ANALYSIS_CACHE[cache_key] = (time.monotonic(), final.model_copy(deep=True))
    return final

def stock_sources_health(settings: Settings) -> dict[str, object]:
    """函数“stock_sources_health”：检查股票数据源及其依赖脚本是否可用。
参数：
    settings: Settings
返回：dict[str, object]。"""
    libraries = {name: bool(importlib.util.find_spec(name)) for name in ("tushare", "efinance", "akshare", "yfinance")}
    return {
        "status": "ok" if any(libraries.values()) else "unavailable",
        "libraries": {name: "available" if available else "not_installed" for name, available in libraries.items()},
        "credentials": {"tushare": "configured" if settings.tushare_token else "not_configured", "tavily": "configured" if settings.tavily_api_key else "not_configured", "serpapi": "configured" if settings.serpapi_key else "not_configured"},
        "retry_limit": settings.stock_fetch_retries,
        "cache_ttl_seconds": settings.stock_cache_ttl_seconds,
    }

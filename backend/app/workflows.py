from __future__ import annotations

import json
from urllib.parse import urlparse
import asyncio
import os
import subprocess
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Awaitable, TypeVar
from uuid import uuid4

from backend.app.agents import AGENT_BY_ID
from backend.app.config import WORKSPACE_DIR, Settings, get_settings
from backend.app.llm import LlmGateway
from backend.app.schemas import (
    AgentOutput,
    GenerateScriptRequest,
    Topic,
    TopicSeed,
    WorkflowRun,
    StockAnalysisRequest,
    StockAnalysisResult,
    SourceEvidence,
)


RUNS: dict[str, WorkflowRun] = {}
STOCK_SKILL_DIR = WORKSPACE_DIR / "agents" / "stock_assistant" / "skills" / "stock-analysis"
STOCK_DATA_SCRIPT = STOCK_SKILL_DIR / "references" / "stock_data_fetcher.py"
STOCK_ANALYSIS_PROMPT = STOCK_SKILL_DIR / "references" / "analysis-prompt-template.md"
STOCK_OUTPUT_TEMPLATE = STOCK_SKILL_DIR / "references" / "output-format-template.md"
NEWS_SKILL_DIR = WORKSPACE_DIR / "agents" / "hotspot_monitor" / "skills" / "news-aggregator-skill"
NEWS_FETCH = NEWS_SKILL_DIR / "scripts" / "fetch_news.py"
_T = TypeVar("_T")


def _require_skill(agent_id: str, skill_name: str) -> Path:
    skill_dir = WORKSPACE_DIR / "agents" / agent_id / "skills" / skill_name
    if not skill_dir.exists():
        raise RuntimeError(f"{agent_id} 的 Skill 不存在：{skill_dir}")
    return skill_dir


def _exception_detail(exc: Exception) -> str:
    return str(exc) or type(exc).__name__


async def _await_with_optional_timeout(awaitable: Awaitable[_T], timeout_seconds: int) -> _T:
    if timeout_seconds <= 0:
        return await awaitable
    return await asyncio.wait_for(awaitable, timeout=timeout_seconds)


def _parse_public_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (TypeError, ValueError, OverflowError):
            return None
    else:
        text = str(value or "").strip()
        if not text:
            return None
        if text.casefold() in {"real-time", "realtime", "today", "hot", "updated recently"}:
            return datetime.now().astimezone()
        try:
            parsed = parsedate_to_datetime(text)
        except (TypeError, ValueError, OverflowError):
            try:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                parsed = None
                for format_string in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                    try:
                        parsed = datetime.strptime(text, format_string)
                        break
                    except ValueError:
                        continue
                if parsed is None:
                    return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.now().astimezone().tzinfo or timezone.utc)
    return parsed


def _extract_json_payload(content: str) -> object:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for index, character in enumerate(text):
            if character not in "[{":
                continue
            try:
                payload, _ = decoder.raw_decode(text[index:])
                return payload
            except json.JSONDecodeError:
                continue
    raise ValueError("model response does not contain a JSON object or array")


def _coerce_heat(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return max(0, min(100, int(value)))
    text = str(value or "").strip().casefold()
    qualitative = {
        "极高": 95,
        "very high": 95,
        "高": 85,
        "high": 85,
        "中": 65,
        "medium": 65,
        "低": 40,
        "low": 40,
    }
    if text in qualitative:
        return qualitative[text]
    try:
        return max(0, min(100, int(float(text))))
    except (TypeError, ValueError):
        return 50


def _normalize_source_evidence(
    source: object,
    evidence_by_url: dict[str, dict],
) -> SourceEvidence | None:
    if not isinstance(source, dict):
        return None
    url = str(source.get("url") or "").strip()
    evidence = evidence_by_url.get(url)
    if not evidence:
        return None
    published_at = _parse_public_datetime(
        source.get("published_at")
        or source.get("time")
        or evidence.get("pubdate")
        or evidence.get("time")
    )
    name = str(source.get("name") or source.get("source") or evidence.get("source") or "").strip()
    claim = str(
        source.get("claim")
        or source.get("summary")
        or evidence.get("summary")
        or evidence.get("title")
        or ""
    ).strip()
    if not published_at or not name or not claim:
        return None
    return SourceEvidence(name=name, url=url, published_at=published_at, claim=claim)


def _normalize_model_topics(content: str, raw_items: list[dict]) -> list[Topic]:
    payload = _extract_json_payload(content)
    if isinstance(payload, dict):
        payload = payload.get("topics", [])
    if not isinstance(payload, list):
        return []

    evidence_by_url = {
        str(item.get("url")).strip(): item
        for item in raw_items
        if str(item.get("url") or "").strip().startswith(("http://", "https://"))
    }
    topics: list[Topic] = []
    for item in payload[:5]:
        if not isinstance(item, dict):
            continue
        raw_sources = item.get("sources")
        if not isinstance(raw_sources, list):
            continue
        sources = [
            normalized
            for raw_source in raw_sources
            if (normalized := _normalize_source_evidence(raw_source, evidence_by_url))
        ]
        title = str(item.get("title") or "").strip()
        if not title or not sources:
            continue
        domains = {(urlparse(source.url).netloc or "").lower() for source in sources}
        status_text = str(item.get("verification_status") or "").strip().casefold()
        is_verified = status_text in {"verified", "已验证", "已核验"} and len(sources) >= 2 and len(domains) >= 2
        status = "verified" if is_verified else "unverified"
        checked_at = _parse_public_datetime(item.get("checked_at")) or datetime.now().astimezone()
        source_names = "、".join(dict.fromkeys(source.name for source in sources))
        try:
            topics.append(
                Topic.model_validate(
                    {
                        "title": title,
                        "heat": _coerce_heat(item.get("heat")),
                        "source_hint": str(item.get("source_hint") or source_names).strip(),
                        "source_url": sources[0].url,
                        "source_published_at": sources[0].published_at,
                        "sources": [source.model_dump() for source in sources],
                        "cross_check_note": str(
                            item.get("cross_check_note") or f"已引用 {len(sources)} 个公开来源。"
                        ).strip(),
                        "checked_at": checked_at,
                        "verification_status": status,
                        "verification_note": str(
                            item.get("verification_note")
                            or ("已通过不同域名来源交叉验证。" if is_verified else "尚未完成独立来源交叉验证。")
                        ).strip(),
                        "angle": str(
                            item.get("angle") or f"围绕“{title}”解释事件本身及其影响，避免超出来源内容。"
                        ).strip(),
                        "risk": str(
                            item.get("risk") or "发布前仍需复核原文，不要把未核验信息当作事实。"
                        ).strip(),
                    }
                )
            )
        except Exception:
            continue
    return topics


def _evidence_only_topics(raw_items: list[dict]) -> list[Topic]:
    topics: list[Topic] = []
    seen_urls: set[str] = set()
    for item in raw_items:
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        source_name = str(item.get("source") or "公开来源").strip()
        published_at = _parse_public_datetime(item.get("pubdate") or item.get("time"))
        if not title or not url or not published_at or url in seen_urls:
            continue
        seen_urls.add(url)
        evidence = SourceEvidence(
            name=source_name,
            url=url,
            published_at=published_at,
            claim=str(item.get("summary") or title).strip(),
        )
        topics.append(
            Topic(
                title=title,
                heat=_coerce_heat(item.get("heat")),
                source_hint=f"{source_name}：{title}",
                source_url=url,
                source_published_at=published_at,
                sources=[evidence],
                cross_check_note="仅引用一条公开来源，尚未完成独立来源交叉验证。",
                checked_at=datetime.now().astimezone(),
                verification_status="unverified",
                verification_note="模型未返回可用结构；此候选仅来自公开来源原始条目。",
                angle=f"围绕“{title}”梳理公开信息，避免超出来源内容。",
                risk="单一来源，发布前必须复核原文，不要把未核验信息当作事实。",
            )
        )
        if len(topics) >= 5:
            break
    return topics


async def _run_news_aggregator(timeout_seconds: int | None = None) -> list[dict]:
    _require_skill("hotspot_monitor", "news-aggregator-skill")
    if not NEWS_FETCH.exists():
        raise RuntimeError(f"news-aggregator-skill 入口不存在：{NEWS_FETCH}")
    if timeout_seconds is None:
        timeout_seconds = get_settings().news_fetch_timeout_seconds
    command = [
        sys.executable,
        str(NEWS_FETCH),
        "--source",
        "weibo,wallstreetcn,bbc_top,bbc_chinese,reuters",
        "--limit",
        "8",
        "--no-save",
    ]
    run_options = {
        "cwd": NEWS_SKILL_DIR,
        "env": os.environ.copy(),
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "check": False,
    }
    if timeout_seconds > 0:
        run_options["timeout"] = timeout_seconds
    try:
        # Windows selector event loops do not implement asyncio subprocesses.
        # Run the blocking process in a worker so both loop policies work.
        completed = await asyncio.to_thread(subprocess.run, command, **run_options)
    except subprocess.TimeoutExpired as exc:
        timeout_label = f"{timeout_seconds} seconds" if timeout_seconds > 0 else "the configured limit"
        raise RuntimeError(f"news-aggregator-skill fetch timed out after {timeout_label}") from exc

    stdout = completed.stdout or b""
    stderr = completed.stderr or b""
    if completed.returncode != 0:
        detail = stderr.decode("utf-8", errors="replace")[-1200:]
        raise RuntimeError(f"news-aggregator-skill 执行失败：{detail or stdout.decode('utf-8', errors='replace')[-500:]}")
    try:
        data = json.loads(stdout.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("news-aggregator-skill 返回了无效 JSON") from exc
    if not isinstance(data, list):
        raise RuntimeError("news-aggregator-skill 返回格式不是新闻列表")
    normalized: list[dict] = []
    for item in data:
        normalized_item = dict(item)
        if not normalized_item.get("pubdate"):
            published = normalized_item.get("time") or normalized_item.get("published_at")
            if published:
                try:
                    if isinstance(published, (int, float)):
                        normalized_item["pubdate"] = int(published)
                    else:
                        parsed = _parse_public_datetime(published)
                        if parsed:
                            normalized_item["pubdate"] = int(parsed.timestamp())
                except (TypeError, ValueError, OverflowError):
                    pass
        normalized.append(normalized_item)
    return normalized


async def analyze_stocks(request: StockAnalysisRequest, settings: Settings) -> StockAnalysisResult:
    """Run the installed Stock Analysis Skill for finance/stock requests."""
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
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=STOCK_SKILL_DIR,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        raise RuntimeError("Stock Analysis Skill data fetch exceeded 120 seconds")

    raw_text = stdout.decode("utf-8", errors="replace")
    if process.returncode != 0:
        raise RuntimeError(stderr.decode("utf-8", errors="replace") or raw_text)
    try:
        raw_data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Stock Analysis Skill returned invalid JSON: {raw_text[-500:]}") from exc

    fallback = json.dumps(raw_data, ensure_ascii=False, indent=2)
    prompt = STOCK_ANALYSIS_PROMPT.read_text(encoding="utf-8") if STOCK_ANALYSIS_PROMPT.exists() else ""
    template = STOCK_OUTPUT_TEMPLATE.read_text(encoding="utf-8") if STOCK_OUTPUT_TEMPLATE.exists() else ""
    gateway = LlmGateway(settings)
    result = await gateway.complete(
        system=(
            "你是 SignalForge 的股票助手林量。严格依据输入的真实数据和新闻输出中文股票决策看板。"
            "不得编造价格或新闻；缺失数据必须明确标注。必须包含数据来源、分析时间、风险和免责声明。"
            "这不是投资建议。\n\n分析框架：\n" + prompt + "\n\n输出模板：\n" + template
        ),
        user="请分析以下 Stock Analysis Skill 数据：\n" + fallback,
        fallback=fallback + "\n\n> 免责声明：以上分析仅供参考，不构成投资建议。投资有风险，入市需谨慎。",
    )
    return StockAnalysisResult(
        skill_source="https://github.com/liusai0820/Stock-Analysis-Skill",
        stocks=request.stocks,
        report=result.content,
        raw_data=raw_data,
        data_script=str(STOCK_DATA_SCRIPT),
        news_enabled=request.include_news,
        disclaimer="以上分析仅供参考，不构成投资建议。投资有风险，入市需谨慎。",
    )


def _now() -> datetime:
    return datetime.now().astimezone()


def _write_artifact(run_dir: Path, agent_id: str, filename: str, content: str) -> str:
    agent_dir = run_dir / agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    path = agent_dir / filename
    path.write_text(content, encoding="utf-8")
    return str(path)


def _output(run_dir: Path, agent_id: str, title: str, content: str) -> AgentOutput:
    agent = AGENT_BY_ID[agent_id]
    path = _write_artifact(run_dir, agent_id, f"{agent_id}.md", content)
    return AgentOutput(
        agent_id=agent_id,
        agent_name=agent.name,
        title=title,
        content=content,
        artifact_path=path,
        created_at=_now(),
    )


def _checkpoint(workflow: WorkflowRun) -> None:
    path = Path(workflow.run_dir) / "run-state.json"
    path.write_text(json.dumps(workflow.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")


def _load_persisted_runs() -> None:
    runs_dir = WORKSPACE_DIR / "runs"
    if not runs_dir.exists():
        return
    for state_path in runs_dir.glob("*/run-state.json"):
        try:
            workflow = WorkflowRun.model_validate_json(state_path.read_text(encoding="utf-8"))
            RUNS[workflow.id] = workflow
        except Exception:
            continue


def _fallback_topics(seed: TopicSeed) -> list[Topic]:
    return [
        Topic(
            title="AI 编程 Agent 从演示走向日常生产",
            heat=92,
            source_hint="公开新闻/RSS：AI Agent 编程 / 一人公司 / 自动化工作流",
            verification_note="仅为本地模板线索，未连接实时来源核验。",
            angle="强调普通创作者也能把 Agent 当员工调度，而不是只看模型发布会。",
            risk="避免夸大自动化能力，明确仍需要老板决策和事实核查。",
        ),
        Topic(
            title="短视频自动成片工具正在重塑内容团队",
            heat=86,
            source_hint="GitHub/社区：MoneyPrinterTurbo、自动字幕、TTS、素材抓取",
            verification_note="仅为本地模板线索，未连接实时来源核验。",
            angle="从脚本、配音、字幕到剪辑方案，解释自动成片链路的真实边界。",
            risk="版权素材、声音授权、平台重复内容审核需要重点提醒。",
        ),
        Topic(
            title="个人知识库 + Skill 让 AI 员工更像专员",
            heat=81,
            source_hint="博客/开源技能库：mattpocock/skills、Qclaw 教程思路",
            verification_note="仅为本地模板线索，未连接实时来源核验。",
            angle="Skill 不是魔法，而是把固定流程和工具说明封装给 Agent。",
            risk="避免把第三方教程说成唯一方案，保留开源项目致谢。",
        ),
    ]


def _fallback_hotspot_report(seed: TopicSeed, topics: list[Topic]) -> str:
    lines = [
        f"# 热点监控报告：{seed.domain}",
        "",
        f"老板方向：{seed.brief}",
        f"目标观众：{seed.audience}",
        "",
    ]
    for index, topic in enumerate(topics, start=1):
        lines.extend(
            [
                f"## {index}. {topic.title}",
                f"- 热度：{topic.heat}/100",
                f"- 线索：{topic.source_hint}",
                f"- 多方来源：{len(topic.sources)} 个",
                f"- 交叉验证：{topic.cross_check_note}",
                f"- 核验状态：{topic.verification_status}（{topic.verification_note}）",
                f"- 推荐角度：{topic.angle}",
                f"- 风险提示：{topic.risk}",
                "",
            ]
        )
    return "\n".join(lines)


def _parse_topics(raw: str, seed: TopicSeed) -> list[Topic]:
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            payload = payload.get("topics", [])
        topics = [Topic.model_validate(item) for item in payload]
    except Exception:
        topics = []
    return topics[:5]


def _verified_topics(topics: list[Topic]) -> list[Topic]:
    def independent_sources(topic: Topic) -> bool:
        domains = {
            (urlparse(source.url).netloc or "").lower()
            for source in topic.sources
            if source.url
        }
        return len(topic.sources) >= 2 and len(domains) >= 2

    return [
        topic
        for topic in topics
        if topic.verification_status == "verified"
        and topic.checked_at
        and topic.cross_check_note.strip()
        and independent_sources(topic)
    ]


async def scout_topics(seed: TopicSeed, settings: Settings) -> tuple[list[Topic], AgentOutput]:
    run_dir = WORKSPACE_DIR / "runs" / f"radar-{uuid4().hex[:12]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    raw_items: list[dict] = []
    source_status: dict[str, str] = {}
    try:
        news_items = await _run_news_aggregator(settings.news_fetch_timeout_seconds)
        raw_items.extend({**item, "channel": "news-aggregator-skill"} for item in news_items)
        source_status["news-aggregator"] = f"ok:{len(news_items)}"
    except Exception as exc:
        source_status["news-aggregator"] = f"error:{_exception_detail(exc)}"
    if not raw_items:
        detail = "; ".join(f"{name}={status}" for name, status in source_status.items())
        raise RuntimeError(
            "所有热点来源均未返回公开结果，已停止，不使用模型记忆补齐热点。"
            f"来源状态：{detail}"
        )
    cutoff = datetime.now().timestamp() - 14 * 24 * 60 * 60
    recent_items: list[dict] = []
    for item in raw_items:
        try:
            if float(item.get("pubdate") or 0) >= cutoff:
                recent_items.append(item)
        except (TypeError, ValueError):
            continue
    raw_items = recent_items
    if not raw_items:
        raise RuntimeError("热点来源返回结果全部早于最近14天，已停止展示旧热点")
    evidence = json.dumps(raw_items[:80], ensure_ascii=False)
    prompt_contract = (
        "Return one JSON object only. heat must be an integer from 0 to 100; "
        "verification_status must be verified or unverified; each sources item must contain "
        "name, url, published_at in ISO-8601 format, and claim. Do not wrap the response in Markdown."
    )
    gateway = LlmGateway(settings)

    try:
        result = await _await_with_optional_timeout(gateway.complete(
        system=(
            prompt_contract +
            "你是热讯工坊的热点监控员赵爽。你只输出 JSON，不输出解释。"
            "字段必须是 topics 数组，每个元素包含 title, heat, source_hint, sources, "
            "cross_check_note, checked_at, verification_status, verification_note, angle, risk。"
            "sources 必须引用输入中的真实来源；来源可以来自微博、BBC、Reuters fallback 或华尔街见闻。不得凭模型记忆补充旧新闻或编造来源。"
        ),
        user=(
            f"领域：{seed.domain}\n方向：{seed.brief}\n受众：{seed.audience}\n"
            "请只从下面最近14天的公开来源结果中给出 3-5 个热点候选：\n" + evidence
        ),
        fallback=json.dumps({"topics": []}, ensure_ascii=False),
        ), settings.model_timeout_seconds)
    except (asyncio.TimeoutError, RuntimeError):
        result = None
    topics: list[Topic] = []
    if result is not None:
        try:
            topics = _normalize_model_topics(result.content, raw_items)
        except (TypeError, ValueError, json.JSONDecodeError):
            topics = []
    if not topics:
        topics = _evidence_only_topics(raw_items)
    if not topics:
        raise RuntimeError("赵爽没有基于公开实时结果返回有效热点，已拒绝展示模型记忆内容")
    report = _fallback_hotspot_report(seed, topics)
    output = _output(run_dir, "hotspot_monitor", "热点监控报告", report)
    return topics, output


async def generate_script(request: GenerateScriptRequest, settings: Settings) -> AgentOutput:
    run_id = f"script-{uuid4().hex[:8]}"
    run_dir = WORKSPACE_DIR / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    gateway = LlmGateway(settings)
    fallback = f"""# 90-120 秒短视频脚本：{request.topic}

## 开场钩子（0-8 秒）
你有没有发现，最近大家聊 AI 已经不只是在聊模型，而是在聊“一个人能不能开一家公司”。

## 事件经过（8-65 秒）
这次的核心看点是：{request.topic}。它背后的变化不是某个工具突然变强，而是工作流开始被拆成多个 AI 员工：有人盯热点，有人拆爆款，有人写脚本，有人给出剪辑方案，还有人负责运营复盘。

## 关键分析（65-95 秒）
真正有价值的地方，是老板不用把所有事情都交给一个 AI。每个 Agent 只负责一个清晰岗位，拥有自己的工作区和技能，输出也能被追踪和复用。

## 收束观点（95-{request.duration_seconds} 秒）
所以这不是“AI 替你躺赚”，而是把过去团队里的重复劳动，拆成可管理、可检查、可迭代的流程。你仍然要做判断，但生产速度会完全不一样。
"""
    result = await gateway.complete(
        system=(
            "你是热讯工坊的文案助手洛一。请写中文短视频口播脚本，"
            "结构必须包含开场钩子、事件经过、关键分析、收束观点，语气克制但有传播性。"
        ),
        user=(
            f"选题：{request.topic}\n角度：{request.angle}\n"
            f"目标时长：{request.duration_seconds} 秒\n目标受众：{request.audience}"
        ),
        fallback=fallback,
    )
    return _output(run_dir, "copywriter", "短视频脚本", result.content)


async def run_hot_video_workflow(seed: TopicSeed, settings: Settings, existing: WorkflowRun | None = None) -> WorkflowRun:
    run_id = existing.id if existing else uuid4().hex[:12]
    run_dir = Path(existing.run_dir) if existing else WORKSPACE_DIR / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    created_at = existing.created_at if existing else _now()
    workflow = existing or WorkflowRun(
        id=run_id,
        status="running",
        seed=seed,
        topics=[],
        outputs=[],
        run_dir=str(run_dir),
        created_at=created_at,
        current_stage="queued",
        resumable=True,
    )
    workflow.status = "running"
    workflow.error = None
    workflow.completed_at = None
    RUNS[run_id] = workflow
    _checkpoint(workflow)
    gateway = LlmGateway(settings)

    try:
        workflow.current_stage = "hotspot_monitor"
        _checkpoint(workflow)
        # Hotspot candidates must come from the live evidence pipeline. The
        # old _fallback_topics() data is historical demo content, not news.
        topics = workflow.topics
        scout_fallback = json.dumps(
            {"topics": [topic.model_dump(mode="json") for topic in topics]},
            ensure_ascii=False,
        )
        scout_result = await gateway.complete(
            system=(
                "你是热点监控员赵爽。只输出 JSON。每个 topic 必须包含 title, heat, source_hint, sources, "
                "cross_check_note, checked_at, verification_status, verification_note, angle, risk。"
                "sources 至少包含两个相互独立的来源，每个来源必须有 name, url, published_at, claim。"
                "只有两方来源对同一事实交叉印证后才可标记 verified；单一来源或转载链只能是 unverified。"
            ),
            user=f"领域：{seed.domain}\n方向：{seed.brief}\n受众：{seed.audience}",
            fallback=scout_fallback,
        )
        if not workflow.topics:
            # Do not let a model-only response become a fabricated hotspot
            # list. scout_topics records source failures and only returns
            # candidates grounded in fetched public evidence.
            topics, _ = await scout_topics(seed, settings)
        workflow.topics = topics
        workflow.current_stage = "viral_analyst"
        _checkpoint(workflow)
        workflow.outputs.append(
            _output(run_dir, "hotspot_monitor", "热点监控报告", _fallback_hotspot_report(seed, topics))
        )

        verified_topics = _verified_topics(topics)
        if not verified_topics:
            fallback_reason = (
                "热点候选未通过双来源交叉核验，已停止后续生产。"
                "回退原因：模型没有返回可验证的实时热点，当前候选仅来自新闻抓取到的原始来源，"
                "因此系统拒绝把它们当成事实继续生成内容。"
            )
            raise RuntimeError(f"{fallback_reason} 当前候选数：{len(topics)}。")
            raise RuntimeError("没有通过至少两个独立来源交叉验证的新闻线索，已停止后续爆款分析、脚本和发布流程。")
        selected = verified_topics[0]
        analyst_fallback = f"""# 爆款分析：{selected.title}

- 核心冲突：普通人期待 AI 提效，但真实落地需要流程、边界和复盘。
- 情绪抓手：惊讶感来自“一人公司”这个强画面，可信度来自展示不同 Agent 的分工。
- 结构建议：先抛问题，再展示流水线，最后提醒别把自动化当成无需判断。
- 标题方向：一个人开内容公司，AI 员工到底怎么分工？
"""
        analyst_output = next((item for item in workflow.outputs if item.agent_id == "viral_analyst"), None)
        analyst = await gateway.complete(
            system="你是爆款分析师星辰。输出中文 Markdown，聚焦传播结构、钩子和风险。",
            user=f"请分析这个选题为什么可能爆：{selected.model_dump_json()}",
            fallback=analyst_fallback,
        )
        if not analyst_output:
            workflow.outputs.append(_output(run_dir, "viral_analyst", "爆款分析", analyst.content))
        else:
            analyst = type(analyst)(content=analyst_output.content, live=True)
        workflow.current_stage = "copywriter"
        _checkpoint(workflow)

        script_request = GenerateScriptRequest(
            topic=selected.title,
            angle=selected.angle,
            duration_seconds=seed.duration_seconds,
            audience=seed.audience,
        )
        script_fallback = f"""# 口播脚本：{selected.title}

## 开场钩子（0-8 秒）
如果你把 AI 当成一个聊天框，它只能帮你省一点时间；但如果你把它拆成一家公司，事情就变了。

## 事件经过（8-60 秒）
今天这个热点是：{selected.title}。它之所以值得关注，是因为内容生产已经开始被拆成岗位：赵爽负责找热点，星辰负责判断能不能爆，洛一写 90 到 120 秒脚本，小李给出镜头和字幕方案，尤道理负责发布和复盘。

## 关键分析（60-95 秒）
这里最重要的不是名字，而是边界。每个 AI 员工有自己的任务、产物和工作区，老板只负责决策和验收。这样做能减少串台，也方便把流程接到公开新闻、自动剪辑、数据复盘这些真实工具上。

## 总结（95-{seed.duration_seconds} 秒）
所以，一人公司不是让 AI 替你思考，而是让你的判断力有一条生产线。你决定方向，AI 员工负责把重复动作跑起来。
"""
        script_output = next((item for item in workflow.outputs if item.agent_id == "copywriter"), None)
        script = await gateway.complete(
            system="你是文案助手洛一。写中文短视频脚本，含时间段、口播、镜头提示。",
            user=f"请基于爆款分析写 {seed.duration_seconds} 秒脚本：\n{analyst.content}",
            fallback=script_fallback,
        )
        if not script_output:
            workflow.outputs.append(_output(run_dir, "copywriter", "短视频脚本", script.content))
        else:
            script = type(script)(content=script_output.content, live=True)
        workflow.current_stage = "video_editor"
        _checkpoint(workflow)

        edit_fallback = f"""# 自动剪辑方案：{selected.title}

## 工具
- 首选：MoneyPrinterTurbo 官方 Agent Skill
- Skill 路径：workspaces/agents/video_editor/skills/moneyprinterturbo-video
- 上游出处：https://github.com/harry0703/MoneyPrinterTurbo

## 画幅
- 竖版：1080x1920，适合 B站竖屏、抖音、视频号
- 横版：1920x1080，适合 B站普通视频

## 素材
- 屏幕录制：热讯工坊 Agent 看板、运行日志、产物目录
- B-roll：AI 工具界面、GitHub 项目页、脚本文档滚动
- 字幕：每 12-16 字断行，关键字高亮“AI员工”“工作区”“老板决策”

## 配音
- 语速：中快，约每分钟 260-300 字
- 情绪：冷静、清晰、带一点兴奋

## 导出
- 可执行命令：
  uv run --no-project --python 3.11 python mpt_agent.py --subject "{selected.title}"
- 如需真实成片，请配置 AI_API_KEY、AI_BASE_URL、AI_MODEL 和 MPT_PEXELS_API_KEY。
"""
        editor = await gateway.complete(
            system="你是视频剪辑员小李。优先使用 MoneyPrinterTurbo 官方 Agent Skill。输出可执行剪辑方案，包含工具出处、画幅、素材、字幕、配音、导出命令。",
            user=f"请根据脚本生成剪辑计划：\n{script.content}",
            fallback=edit_fallback,
        )
        workflow.outputs.append(_output(run_dir, "video_editor", "自动剪辑方案", editor.content))
        workflow.current_stage = "operator"
        _checkpoint(workflow)

        op_fallback = f"""# 运营发布方案：{selected.title}

- 标题 1：一个人开 AI 内容公司，员工怎么分工？
- 标题 2：我把 AI 拆成 5 个员工，短视频流程跑通了
- 封面文案：AI 一人公司 / 从热点到成片
- 发布时间：工作日 12:00 或 20:30，先测 B站和视频号
- 评论引导：你最想给 AI 员工安排哪个岗位？
- 复盘指标：完播率、3 秒留存、收藏率、评论问题密度
"""
        # Keep local fallback output tied to the verified topic. The generic
        # AI-company template previously caused unrelated posts after a
        # connection failure.
        op_fallback = f"""# 运营发布方案：{selected.title}

- 标题 1：{selected.title}
- 标题 2：从数据看，{selected.title}意味着什么？
- 封面文案：{selected.title}
- 发布时间：工作日 12:00 或 20:30，先测试 B 站和视频号
- 评论引导：你怎么看这条热点对行业和普通用户的影响？
- 复盘指标：完播率、3 秒留存、收藏率、评论问题密度
- 来源提示：{selected.source_hint}
- 发布前复核：{selected.risk}"""
        operator = await gateway.complete(
            system="你是运营大师尤道理。输出发布标题、封面文案、发布时间、评论引导和复盘指标。",
            user=f"请为这个脚本生成运营方案：\n{script.content}",
            fallback=op_fallback,
        )
        workflow.outputs.append(_output(run_dir, "operator", "运营发布方案", operator.content))

        summary = {
            "id": workflow.id,
            "seed": seed.model_dump(),
            "topics": [topic.model_dump(mode="json") for topic in workflow.topics],
            "outputs": [output.model_dump(mode="json") for output in workflow.outputs],
        }
        _write_artifact(run_dir, "boss", "run-summary.json", json.dumps(summary, ensure_ascii=False, indent=2))
        workflow.status = "completed"
        workflow.current_stage = None
        workflow.resumable = False
        workflow.completed_at = _now()
    except Exception as exc:
        workflow.status = "failed"
        detail = _exception_detail(exc)
        stage = workflow.current_stage or "unknown"
        workflow.error = f"{stage}: {detail}"
        workflow.resumable = True
        workflow.completed_at = _now()
        _checkpoint(workflow)

    RUNS[run_id] = workflow
    return workflow


def list_runs() -> list[WorkflowRun]:
    return sorted(RUNS.values(), key=lambda run: run.created_at, reverse=True)


def get_run(run_id: str) -> WorkflowRun | None:
    return RUNS.get(run_id)

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from backend.app.agents import AGENT_BY_ID
from backend.app.config import WORKSPACE_DIR, Settings
from backend.app.llm import LlmGateway
from backend.app.schemas import (
    AgentOutput,
    GenerateScriptRequest,
    Topic,
    TopicSeed,
    WorkflowRun,
)


RUNS: dict[str, WorkflowRun] = {}


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


def _fallback_topics(seed: TopicSeed) -> list[Topic]:
    return [
        Topic(
            title="AI 编程 Agent 从演示走向日常生产",
            heat=92,
            source_hint="B站搜索：AI Agent 编程 / 一人公司 / 自动化工作流",
            angle="强调普通创作者也能把 Agent 当员工调度，而不是只看模型发布会。",
            risk="避免夸大自动化能力，明确仍需要老板决策和事实核查。",
        ),
        Topic(
            title="短视频自动成片工具正在重塑内容团队",
            heat=86,
            source_hint="GitHub/社区：MoneyPrinterTurbo、自动字幕、TTS、素材抓取",
            angle="从脚本、配音、字幕到剪辑方案，解释自动成片链路的真实边界。",
            risk="版权素材、声音授权、平台重复内容审核需要重点提醒。",
        ),
        Topic(
            title="个人知识库 + Skill 让 AI 员工更像专员",
            heat=81,
            source_hint="博客/开源技能库：mattpocock/skills、Qclaw 教程思路",
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
    return topics[:5] or _fallback_topics(seed)


async def scout_topics(seed: TopicSeed, settings: Settings) -> tuple[list[Topic], AgentOutput]:
    run_dir = WORKSPACE_DIR / "scratch" / "topic-scout"
    run_dir.mkdir(parents=True, exist_ok=True)
    gateway = LlmGateway(settings)
    fallback_topics = _fallback_topics(seed)
    fallback_report = _fallback_hotspot_report(seed, fallback_topics)

    result = await gateway.complete(
        system=(
            "你是热讯工坊的热点监控员赵爽。你只输出 JSON，不输出解释。"
            "字段必须是 topics 数组，每个元素包含 title, heat, source_hint, angle, risk。"
        ),
        user=(
            f"领域：{seed.domain}\n方向：{seed.brief}\n受众：{seed.audience}\n"
            "请给出 3-5 个适合短视频选题的热点。"
        ),
        fallback=json.dumps(
            {"topics": [topic.model_dump() for topic in fallback_topics]},
            ensure_ascii=False,
        ),
    )
    topics = _parse_topics(result.content, seed)
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


async def run_hot_video_workflow(seed: TopicSeed, settings: Settings) -> WorkflowRun:
    run_id = uuid4().hex[:12]
    run_dir = WORKSPACE_DIR / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    created_at = _now()
    workflow = WorkflowRun(
        id=run_id,
        status="running",
        seed=seed,
        topics=[],
        outputs=[],
        run_dir=str(run_dir),
        created_at=created_at,
    )
    RUNS[run_id] = workflow
    gateway = LlmGateway(settings)

    try:
        topics = _fallback_topics(seed)
        scout_fallback = json.dumps(
            {"topics": [topic.model_dump() for topic in topics]},
            ensure_ascii=False,
        )
        scout_result = await gateway.complete(
            system=(
                "你是热点监控员赵爽。只输出 JSON："
                "{\"topics\":[{\"title\":\"\",\"heat\":0,\"source_hint\":\"\",\"angle\":\"\",\"risk\":\"\"}]}"
            ),
            user=f"领域：{seed.domain}\n方向：{seed.brief}\n受众：{seed.audience}",
            fallback=scout_fallback,
        )
        topics = _parse_topics(scout_result.content, seed)
        workflow.topics = topics
        workflow.outputs.append(
            _output(run_dir, "hotspot_monitor", "热点监控报告", _fallback_hotspot_report(seed, topics))
        )

        selected = topics[0]
        analyst_fallback = f"""# 爆款分析：{selected.title}

- 核心冲突：普通人期待 AI 提效，但真实落地需要流程、边界和复盘。
- 情绪抓手：惊讶感来自“一人公司”这个强画面，可信度来自展示不同 Agent 的分工。
- 结构建议：先抛问题，再展示流水线，最后提醒别把自动化当成无需判断。
- 标题方向：一个人开内容公司，AI 员工到底怎么分工？
"""
        analyst = await gateway.complete(
            system="你是爆款分析师星辰。输出中文 Markdown，聚焦传播结构、钩子和风险。",
            user=f"请分析这个选题为什么可能爆：{selected.model_dump_json()}",
            fallback=analyst_fallback,
        )
        workflow.outputs.append(_output(run_dir, "viral_analyst", "爆款分析", analyst.content))

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
这里最重要的不是名字，而是边界。每个 AI 员工有自己的任务、产物和工作区，老板只负责决策和验收。这样做能减少串台，也方便把流程接到 B站搜索、自动剪辑、数据复盘这些真实工具上。

## 总结（95-{seed.duration_seconds} 秒）
所以，一人公司不是让 AI 替你思考，而是让你的判断力有一条生产线。你决定方向，AI 员工负责把重复动作跑起来。
"""
        script = await gateway.complete(
            system="你是文案助手洛一。写中文短视频脚本，含时间段、口播、镜头提示。",
            user=f"请基于爆款分析写 {seed.duration_seconds} 秒脚本：\n{analyst.content}",
            fallback=script_fallback,
        )
        workflow.outputs.append(_output(run_dir, "copywriter", "短视频脚本", script.content))

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
- 如需真实成片，请配置 MPT_LLM_PROVIDER、MPT_LLM_API_KEY、MPT_LLM_BASE_URL、MPT_LLM_MODEL_NAME 和 MPT_PEXELS_API_KEY。
"""
        editor = await gateway.complete(
            system="你是视频剪辑员小李。优先使用 MoneyPrinterTurbo 官方 Agent Skill。输出可执行剪辑方案，包含工具出处、画幅、素材、字幕、配音、导出命令。",
            user=f"请根据脚本生成剪辑计划：\n{script.content}",
            fallback=edit_fallback,
        )
        workflow.outputs.append(_output(run_dir, "video_editor", "自动剪辑方案", editor.content))

        op_fallback = f"""# 运营发布方案：{selected.title}

- 标题 1：一个人开 AI 内容公司，员工怎么分工？
- 标题 2：我把 AI 拆成 5 个员工，短视频流程跑通了
- 封面文案：AI 一人公司 / 从热点到成片
- 发布时间：工作日 12:00 或 20:30，先测 B站和视频号
- 评论引导：你最想给 AI 员工安排哪个岗位？
- 复盘指标：完播率、3 秒留存、收藏率、评论问题密度
"""
        operator = await gateway.complete(
            system="你是运营大师尤道理。输出发布标题、封面文案、发布时间、评论引导和复盘指标。",
            user=f"请为这个脚本生成运营方案：\n{script.content}",
            fallback=op_fallback,
        )
        workflow.outputs.append(_output(run_dir, "operator", "运营发布方案", operator.content))

        summary = {
            "id": workflow.id,
            "seed": seed.model_dump(),
            "topics": [topic.model_dump() for topic in workflow.topics],
            "outputs": [output.model_dump(mode="json") for output in workflow.outputs],
        }
        _write_artifact(run_dir, "boss", "run-summary.json", json.dumps(summary, ensure_ascii=False, indent=2))
        workflow.status = "completed"
        workflow.completed_at = _now()
    except Exception as exc:
        workflow.status = "failed"
        workflow.error = str(exc)
        workflow.completed_at = _now()

    RUNS[run_id] = workflow
    return workflow


def list_runs() -> list[WorkflowRun]:
    return sorted(RUNS.values(), key=lambda run: run.created_at, reverse=True)


def get_run(run_id: str) -> WorkflowRun | None:
    return RUNS.get(run_id)

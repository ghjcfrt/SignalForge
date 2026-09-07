from pathlib import Path

from backend.app.config import WORKSPACE_DIR
from backend.app.schemas import Agent, Skill


def _workspace(agent_id: str) -> str:
    path = WORKSPACE_DIR / "agents" / agent_id
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


AGENTS: list[Agent] = [
    Agent(
        id="hotspot_monitor",
        name="热点监控员",
        title="热点监控员",
        role="抓取 AI 圈、技术社区和创作者生态热点，辅助选题。",
        focus="热点舆情、搜索线索、选题初筛",
        workspace=_workspace("hotspot_monitor"),
        skills=[
            Skill(
                name="news-aggregator-skill",
                source="https://github.com/cclank/news-aggregator-skill (MIT)",
                description="抓取微博、BBC、Reuters fallback、华尔街见闻及其他公开 RSS/新闻源，用于多源热点监控。",
            )
        ],
    ),
    Agent(
        id="viral_analyst",
        name="爆款分析师",
        title="爆款分析师",
        role="分析爆款内容规律，拆解传播钩子、情绪冲突和受众动机。",
        focus="爆款结构、封面标题、传播因子",
        workspace=_workspace("viral_analyst"),
        skills=[
            Skill(
                name="socialdatax-xhs",
                source="https://socialdatax.com/dashboard/api-docs",
                description="通过 SocialDataX 搜索小红书公开笔记，获取标题、摘要、点赞/收藏/评论/分享和发布时间，用于爆款样本分析。",
            )
        ],
    ),
    Agent(
        id="copywriter",
        name="文案助手",
        title="文案助手",
        role="根据热点资料撰写短视频脚本，适配 90-120 秒结构。",
        focus="开场钩子、事件经过、总结转折、口播节奏",
        workspace=_workspace("copywriter"),
    ),
    Agent(
        id="video_editor",
        name="视频剪辑员",
        title="视频剪辑员",
        role="根据脚本生成配音、镜头、字幕、素材和导出方案。",
        focus="自动剪辑、素材清单、1080P/4K 横竖版方案",
        workspace=_workspace("video_editor"),
        skills=[
            Skill(
                name="MoneyPrinterTurbo 官方 Agent Skill",
                source="https://github.com/harry0703/MoneyPrinterTurbo/tree/main/docs/skill",
                description="从主题或脚本自动生成文案、素材、字幕、配音、背景音乐并合成短视频。",
            )
        ],
    ),
    Agent(
        id="operator",
        name="运营大师",
        title="运营大师",
        role="负责发布节奏、标题、封面话术、互动引导和复盘。",
        focus="运营策略、平台适配、发布计划",
        workspace=_workspace("operator"),
        skills=[
            Skill(
                name="newmedia-operations",
                source="ClawHub/Volces: swcxy12315/newmedia-operations@1.0.0",
                description="覆盖行业分析、竞品分析、账号养号、爆款内容创作和互动钩子设计。",
            )
        ],
    ),
    Agent(
        id="product_manager",
        name="产品经理",
        title="产品经理",
        role="做产品调研、市场分析、需求总结和竞品分析。",
        focus="需求拆解、竞品研究、路线图",
        workspace=_workspace("product_manager"),
        skills=[
            Skill(
                name="Product-Manager-Skills",
                source="https://github.com/deanpeters/Product-Manager-Skills (CC BY-NC-SA 4.0)",
                description="产品发现、需求澄清、路线图、竞品分析和 PM 文档方法库。",
            )
        ],
    ),
    Agent(
        id="programmer",
        name="程序员",
        title="程序员",
        role="配合产品经理做项目开发和自动化工具落地。",
        focus="后端接口、脚本、自动化集成",
        workspace=_workspace("programmer"),
    ),
    Agent(
        id="stock_assistant",
        name="股票助手",
        title="股票助手",
        role="查看股票相关信息，辅助财经选题。",
        focus="行情摘要、财报线索、风险提示",
        workspace=_workspace("stock_assistant"),
        skills=[
            Skill(
                name="stock-analysis",
                source="https://github.com/liusai0820/Stock-Analysis-Skill",
                description="获取 A 股、港股、美股行情和历史数据，计算技术指标，并结合最新新闻输出中文决策看板；输出区分数据、推断和风险提示。",
            )
        ],
    ),
    Agent(
        id="healer",
        name="心理疗愈师",
        title="心理疗愈师",
        role="用于情感话题的沟通疏导和内容把关。",
        focus="情绪安抚、表达边界、心理话题安全",
        workspace=_workspace("healer"),
        skills=[
            Skill(
                name="mental-health-assistant",
                source="ClawHub/Volces: ttoooong/mental-health-assistant@2.1.0",
                description="提供情绪支持、危机识别、心理量表、CBT 技术和专业转介边界提示。",
            )
        ],
    ),
]


AGENT_BY_ID = {agent.id: agent for agent in AGENTS}


def ensure_agent_workspaces() -> None:
    for agent in AGENTS:
        Path(agent.workspace).mkdir(parents=True, exist_ok=True)

"""五阶段热点视频工作流的确定性端到端冒烟测试。"""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import backend.app.workflows as workflows
from backend.app.config import get_settings
from backend.app.schemas import TopicSeed, ViralAnalysisConfig


class _Completion:
    """数据模型或服务类“_Completion”，封装相关状态与行为。"""
    def __init__(self, content: str):
        """内部辅助函数“__init__”，负责init。
参数：
    content: str
返回：未标注。"""
        self.content = content


class _Gateway:
    """数据模型或服务类“_Gateway”，封装相关状态与行为。"""
    def __init__(self, _settings):
        """内部辅助函数“__init__”，负责init。
参数：
    _settings: 未标注
返回：未标注。"""
        pass

    async def complete(self, system: str, user: str, fallback: str):
        """函数“complete”，负责complete。
参数：
    system: str
    user: str
    fallback: str
返回：未标注。"""
        if "热点监控员" in system:
            return _Completion(
                json.dumps(
                    {
                        "topics": [
                            {
                                "title": "Smoke test: AI workflow",
                                "heat": 90,
                                "source_hint": "Smoke fixtures",
                                "sources": [
                                    {
                                        "name": "Fixture A",
                                        "url": "https://fixture-a.example/topic",
                                        "published_at": "2026-09-02T00:00:00Z",
                                        "claim": "Fixture fact A",
                                    },
                                    {
                                        "name": "Fixture B",
                                        "url": "https://fixture-b.example/topic",
                                        "published_at": "2026-09-02T00:00:00Z",
                                        "claim": "Fixture fact B",
                                    },
                                ],
                                "angle": "从创作者效率切入",
                                "risk": "仅用于自动化测试",
                            }
                        ]
                    },
                    ensure_ascii=False,
                )
            )
        return _Completion(fallback)


async def _fixture_news(_timeout=None):
    """内部辅助函数“_fixture_news”，负责fixture news。
参数：
    _timeout: 未标注
返回：未标注。"""
    now = int(time.time())
    return [
        {"title": "Smoke test: AI workflow", "url": "https://fixture-a.example/topic", "source": "Fixture A", "summary": "Fixture fact A", "pubdate": now},
        {"title": "Smoke test: AI workflow", "url": "https://fixture-b.example/topic", "source": "Fixture B", "summary": "Fixture fact B", "pubdate": now},
    ]


async def main() -> None:
    """函数“main”，负责main。
返回：None。"""
    original_gateway = workflows.LlmGateway
    original_news = workflows._run_news_aggregator
    workflows.LlmGateway = _Gateway
    workflows._run_news_aggregator = _fixture_news
    try:
        settings = get_settings()
        settings.socialdatax_api_key = ""
        seed = TopicSeed(domain="AI", brief="workflow smoke test", audience="创作者", duration_seconds=60)
        run = workflows.create_workflow(
            seed,
            ViralAnalysisConfig(source="manual", enabled=True, manual_content="先说影响，再讲事实。"),
        )
        result = await workflows.run_hot_video_workflow(seed, settings, existing=run)
        expected = set(workflows.WORKFLOW_STAGES)
        assert result.status == "completed", result.error
        assert set(result.stage_status) >= expected
        assert all(result.stage_status[stage] == "completed" for stage in expected)
        assert {output.agent_id for output in result.outputs} >= expected
        print(f"workflow smoke OK: {result.id}, outputs={len(result.outputs)}")
    finally:
        workflows.LlmGateway = original_gateway
        workflows._run_news_aggregator = original_news


if __name__ == "__main__":
    asyncio.run(main())

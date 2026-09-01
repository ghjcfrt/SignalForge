"""Deterministic end-to-end smoke test for the five-stage hot-video workflow."""

import asyncio
import json
import time

import backend.app.workflows as workflows
from backend.app.config import get_settings
from backend.app.schemas import TopicSeed, ViralAnalysisConfig


class _Completion:
    def __init__(self, content: str):
        self.content = content


class _Gateway:
    def __init__(self, _settings):
        pass

    async def complete(self, system: str, user: str, fallback: str):
        if "热点监控员赵爽" in system:
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
    now = int(time.time())
    return [
        {"title": "Smoke test: AI workflow", "url": "https://fixture-a.example/topic", "source": "Fixture A", "summary": "Fixture fact A", "pubdate": now},
        {"title": "Smoke test: AI workflow", "url": "https://fixture-b.example/topic", "source": "Fixture B", "summary": "Fixture fact B", "pubdate": now},
    ]


async def main() -> None:
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

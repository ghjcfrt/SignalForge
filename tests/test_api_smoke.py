"""SignalForge API 和工作流契约的异步冒烟测试。"""

from __future__ import annotations

import asyncio
import json
import unittest
from datetime import datetime, timezone

import httpx

from backend.app import main, workflows
from backend.app.schemas import AgentOutput, TopicSeed


class ApiSmokeTests(unittest.IsolatedAsyncioTestCase):
    """数据模型或服务类“ApiSmokeTests”，封装相关状态与行为。"""
    async def asyncSetUp(self) -> None:
        """函数“asyncSetUp”，负责asyncSetUp。
返回：None。"""
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test")

    async def asyncTearDown(self) -> None:
        """函数“asyncTearDown”，负责asyncTearDown。
返回：None。"""
        await self.client.aclose()

    async def test_health_agents_and_every_employee_workbench(self) -> None:
        """函数“test_health_agents_and_every_employee_workbench”，负责test health agents and every employee workbench。
返回：None。"""
        response = await self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        agents = (await self.client.get("/api/agents")).json()
        self.assertGreaterEqual(len(agents), 9)
        stock_health = await self.client.get("/api/stocks/health")
        self.assertEqual(stock_health.status_code, 200)
        self.assertIn("libraries", stock_health.json())
        original = main.run_agent

        async def fake_run(agent_id, request, settings):
            """函数“fake_run”，负责fake run。
参数：
    agent_id: 未标注
    request: 未标注
    settings: 未标注
返回：未标注。"""
            return AgentOutput(
                agent_id=agent_id,
                agent_name=agent_id,
                title="smoke",
                content="deterministic smoke output",
                artifact_path=f"tests/{agent_id}.md",
                created_at=datetime.now(timezone.utc),
            )

        main.run_agent = fake_run
        try:
            for agent in agents:
                result = await self.client.post(
                    f"/api/agents/{agent['id']}/run",
                    json={"agent_id": agent["id"], "prompt": "smoke", "timeout_seconds": 1},
                )
                self.assertEqual(result.status_code, 200, agent["id"])
                self.assertEqual(result.json()["agent_id"], agent["id"])
        finally:
            main.run_agent = original

    async def test_manual_step_resume_and_cancel_contract(self) -> None:
        """函数“test_manual_step_resume_and_cancel_contract”，负责test manual step resume and cancel contract。
返回：None。"""
        seed = TopicSeed(domain="AI", brief="smoke", audience="test", duration_seconds=60)
        created = await self.client.post(
            "/api/workflows/hot-video",
            json={"execution_mode": "manual", "seed": seed.model_dump(mode="json")},
        )
        self.assertEqual(created.status_code, 200)
        run_id = created.json()["id"]
        original_execute = main._execute_workflow

        async def fake_execute(run, *, stop_after_stage=None):
            """函数“fake_execute”，负责fake execute。
参数：
    run: 未标注
    stop_after_stage: 未标注
返回：未标注。"""
            await asyncio.sleep(30)

        main._execute_workflow = fake_execute
        try:
            stepped = await self.client.post(f"/api/workflows/{run_id}/step")
            self.assertEqual(stepped.status_code, 200)
            await asyncio.sleep(0)
            cancelled = await self.client.post(f"/api/workflows/{run_id}/cancel")
            self.assertEqual(cancelled.status_code, 200)
            self.assertEqual(cancelled.json()["status"], "queued")
        finally:
            main._execute_workflow = original_execute
            task = main.WORKFLOW_TASKS.pop(run_id, None)
            if task and not task.done():
                task.cancel()

    async def test_fixture_source_keeps_two_domain_gate(self) -> None:
        """函数“test_fixture_source_keeps_two_domain_gate”，负责test fixture source keeps two domain gate。
返回：None。"""
        original_settings = main.get_settings
        original_workflow_settings = workflows.get_settings
        original_gateway = workflows.LlmGateway
        settings = original_settings().model_copy(update={"news_source_mode": "fixture"})
        main.get_settings = lambda: settings
        workflows.get_settings = lambda: settings

        class FixtureGateway:
            """数据模型或服务类“FixtureGateway”，封装相关状态与行为。"""
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
                class Completion:
                    """数据模型或服务类“Completion”，封装相关状态与行为。"""
                    content = json.dumps({"topics": []}, ensure_ascii=False)
                return Completion()

        workflows.LlmGateway = FixtureGateway
        try:
            response = await self.client.post("/api/topics/scout", json={"domain": "AI", "brief": "AI 工作流", "audience": "创作者", "duration_seconds": 60, "video_aspect": "vertical"})
            self.assertEqual(response.status_code, 200, response.text)
            topics = response.json()
            self.assertTrue(topics)
            self.assertTrue(any(len({source["url"].split("/")[2] for source in topic["sources"]}) >= 2 for topic in topics))
        finally:
            main.get_settings = original_settings
            workflows.get_settings = original_workflow_settings
            workflows.LlmGateway = original_gateway


if __name__ == "__main__":
    unittest.main()

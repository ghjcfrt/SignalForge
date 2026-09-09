"""针对已运行 SignalForge 后端的 HTTP 冒烟测试。

Usage: ``python scripts/smoke_api.py [base_url]``
"""

from __future__ import annotations

import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# 冒烟测试目标地址，可通过第一个命令行参数覆盖。
BASE_URL = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8017").rstrip("/")


def request(path: str, method: str = "GET", payload: object | None = None) -> tuple[int, object]:
    """函数“request”，负责request。
参数：
    path: str
    method: str
    payload: object | None
返回：tuple[int, object]。"""
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"} if data else {}
    try:
        with urlopen(Request(BASE_URL + path, data=data, headers=headers, method=method), timeout=15) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else None
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AssertionError(f"{method} {path} returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise AssertionError(f"无法连接后端 {BASE_URL}: {exc.reason}") from exc


def main() -> None:
    """函数“main”，负责main。
返回：None。"""
    status, health = request("/api/health")
    assert status == 200 and health.get("status") == "ok", health

    status, api_status = request("/api/status")
    assert status == 200 and "mode" in api_status and "diagnostic" in api_status, api_status

    status, agents = request("/api/agents")
    assert status == 200 and len(agents) >= 9, agents
    agent_ids = {agent["id"] for agent in agents}
    assert {"hotspot_monitor", "viral_analyst", "copywriter", "video_editor", "operator"} <= agent_ids

    status, timeouts = request("/api/settings/timeouts")
    assert status == 200 and all(name in timeouts for name in (
        "news_fetch_timeout_seconds", "model_timeout_seconds", "workflow_timeout_seconds"
    )), timeouts

    status, run = request(
        "/api/workflows/hot-video",
        "POST",
        {
            "execution_mode": "manual",
            "seed": {"domain": "API smoke", "brief": "接口创建测试", "audience": "测试用户", "duration_seconds": 60, "video_aspect": "horizontal"},
            "viral_analysis": {"source": "manual", "enabled": True, "manual_content": "仅用于接口冒烟测试"},
        },
    )
    assert status == 200 and run.get("status") == "queued" and run.get("id"), run
    assert run["seed"]["video_aspect"] == "horizontal", run

    status, detail = request(f"/api/workflows/{run['id']}")
    assert status == 200 and detail.get("id") == run["id"], detail
    print(f"API smoke OK: agents={len(agents)}, workflow={run['id']}")


if __name__ == "__main__":
    main()

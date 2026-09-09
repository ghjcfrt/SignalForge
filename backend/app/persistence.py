"""工作流产物、检查点和日志的磁盘持久化工具。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from backend.app.agents import AGENT_BY_ID
from backend.app.config import WORKSPACE_DIR, get_output_directory_settings
from backend.app.schemas import AgentOutput, WorkflowLog, WorkflowRun


def write_artifact(run_dir: Path, agent_id: str, filename: str, content: str) -> str:
    """函数“write_artifact”：将文本内容写入工作流产物文件并返回路径。
参数：
    run_dir: Path
    agent_id: str
    filename: str
    content: str
返回：str。"""
    agent_dir = run_dir / agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    path = agent_dir / filename
    path.write_text(content, encoding="utf-8")
    return str(path)


def output(run_dir: Path, agent_id: str, title: str, content: str, output_dir: str | None = None, now: Callable[[], object] | None = None) -> AgentOutput:
    """函数“output”：创建一条员工产物记录。
参数：
    run_dir: Path
    agent_id: str
    title: str
    content: str
    output_dir: str | None
    now: Callable[[], object] | None
返回：AgentOutput。"""
    agent = AGENT_BY_ID[agent_id]
    if output_dir is None:
        configured = get_output_directory_settings()
        if agent_id == "operator": output_dir = configured.operator_output_dir.strip() or None
        elif agent_id == "video_editor":
            configured_video_dir = configured.video_output_dir.strip() or None
            output_dir = str(Path(configured_video_dir).expanduser().resolve() / "video_editor") if configured_video_dir else None
    path = write_artifact(Path(output_dir).expanduser().resolve(), agent_id, f"{agent_id}.md", content) if output_dir else write_artifact(run_dir, agent_id, f"{agent_id}.md", content)
    return AgentOutput(agent_id=agent_id, agent_name=agent.name, title=title, content=content, artifact_path=path, created_at=now() if now else __import__("datetime").datetime.now().astimezone())


def checkpoint(workflow: WorkflowRun) -> None:
    """函数“checkpoint”：保存工作流检查点。
参数：
    workflow: WorkflowRun
返回：None。"""
    run_dir = Path(workflow.run_dir); run_dir.mkdir(parents=True, exist_ok=True)
    temporary = run_dir / "run-state.json.tmp"
    temporary.write_text(json.dumps(workflow.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(run_dir / "run-state.json")


def workflow_log_path(workflow: WorkflowRun, log_filename: str, legacy_filename: str) -> Path:
    """返回标准日志路径，并在需要时迁移旧版 JSONL 文件名。"""
    run_dir = Path(workflow.run_dir); run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / log_filename; legacy_path = run_dir / legacy_filename
    if legacy_path.exists():
        if path.exists():
            with legacy_path.open("rb") as source, path.open("ab") as destination: destination.write(source.read())
            legacy_path.unlink()
        else: legacy_path.replace(path)
    workflow.log_file = str(path)
    return path


def log(workflow: WorkflowRun, message: str, *, stage: str | None = None, level: str = "info", detail: str | None = None, now: Callable[[], object] | None = None, log_filename: str = "run.log", legacy_filename: str = "run.log.jsonl") -> None:
    """立即持久化可读事件文本和结构化诊断信息。"""
    entry = WorkflowLog(timestamp=now() if now else __import__("datetime").datetime.now().astimezone(), level=level if level in {"info", "warning", "error"} else "info", stage=stage, message=message, detail=detail)
    workflow.logs.append(entry)
    with workflow_log_path(workflow, log_filename, legacy_filename).open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(entry.model_dump(mode="json"), ensure_ascii=False) + "\n")
    checkpoint(workflow)


def load_persisted_runs(runs: dict[str, WorkflowRun], ensure_state: Callable[[WorkflowRun], None], log_fn: Callable[..., None]) -> None:
    """函数“load_persisted_runs”：扫描磁盘并加载已有工作流。
参数：
    runs: dict[str, WorkflowRun]
    ensure_state: Callable[[WorkflowRun], None]
    log_fn: Callable[..., None]
返回：None。"""
    runs_dir = WORKSPACE_DIR / "runs"
    if not runs_dir.exists(): return
    for state_path in runs_dir.glob("*/run-state.json"):
        try:
            workflow = WorkflowRun.model_validate_json(state_path.read_text(encoding="utf-8")); ensure_state(workflow)
            if workflow.status == "running":
                if workflow.current_stage in workflow.stage_status: workflow.stage_status[workflow.current_stage] = "failed"
                workflow.status = "failed"; workflow.resumable = True
                workflow.error = f"{workflow.current_stage or 'unknown'}: 服务在该阶段中断，已恢复为可继续任务"
                log_fn(workflow, "检测到服务重启，任务已恢复为可继续状态", stage=workflow.current_stage, level="warning")
            runs[workflow.id] = workflow
        except Exception:
            continue

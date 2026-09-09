"""MoneyPrinterTurbo 视频生成工具适配。"""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from backend.app.config import WORKSPACE_DIR, Settings


# MoneyPrinterTurbo Skill 目录和执行脚本位置。
MPT_SKILL_DIR = WORKSPACE_DIR / "agents" / "video_editor" / "skills" / "moneyprinterturbo-video"
# Skill 说明、执行辅助脚本、许可证和上游 README 文件。
MPT_SKILL_FILE = MPT_SKILL_DIR / "SKILL.md"
MPT_HELPER_FILE = MPT_SKILL_DIR / "mpt_agent.py"
MPT_LICENSE_FILE = MPT_SKILL_DIR / "LICENSE.MoneyPrinterTurbo"
# 上游项目 README，用于在状态接口展示来源说明。
MPT_README_FILE = MPT_SKILL_DIR / "README.MoneyPrinterTurbo.md"


class MoneyPrinterTurboStatus(BaseModel):
    """视频生成工具的安装状态、版本和可执行性。"""
    installed: bool
    skill_dir: str
    skill_file: str
    helper_file: str
    license_file: str
    upstream: str
    license: str
    missing_env: list[str]
    default_command: str


class MoneyPrinterTurboRequest(BaseModel):
    """视频生成任务的输入参数和超时策略。"""
    subject: str
    extra_args: list[str] = []
    output_dir: str | None = None
    video_aspect: Literal["9:16", "16:9"] = "9:16"


class MoneyPrinterTurboRunResult(BaseModel):
    """视频生成任务的执行结果、产物路径和状态。"""
    exit_code: int
    status: str
    stdout: str
    stderr: str
    video_files: list[str]
    task_dir: str | None = None
    log_file: str | None = None
    result_file: str | None = None


def mpt_status(settings: Settings) -> MoneyPrinterTurboStatus:
    """函数“mpt_status”，负责mpt status。
参数：
    settings: Settings
返回：MoneyPrinterTurboStatus。"""
    missing_env: list[str] = []
    provider = "oneapi"
    llm_key = settings.ai_api_key
    base_url = settings.ai_base_url

    if not llm_key:
        missing_env.append("AI_API_KEY")
    if provider in {"oneapi", "openai_compatible"} and not base_url:
        missing_env.append("AI_BASE_URL")
    if not settings.mpt_pexels_api_key:
        missing_env.append("MPT_PEXELS_API_KEY")

    return MoneyPrinterTurboStatus(
        installed=MPT_SKILL_FILE.exists() and MPT_HELPER_FILE.exists(),
        skill_dir=str(MPT_SKILL_DIR),
        skill_file=str(MPT_SKILL_FILE),
        helper_file=str(MPT_HELPER_FILE),
        license_file=str(MPT_LICENSE_FILE),
        upstream="https://github.com/harry0703/MoneyPrinterTurbo",
        license="MIT",
        missing_env=missing_env,
        default_command='uv run --no-project --python 3.11.15 python mpt_agent.py --subject "<视频主题或脚本>" -- --video-aspect "9:16"',
    )


def _mpt_env(settings: Settings) -> dict[str, str]:
    """内部辅助函数“_mpt_env”，负责mpt env。
参数：
    settings: Settings
返回：dict[str, str]。"""
    env = os.environ.copy()
    env["MPT_LLM_PROVIDER"] = "oneapi"
    env["MPT_LLM_BASE_URL"] = settings.ai_base_url
    if settings.ai_model and settings.ai_model.strip():
        env["MPT_LLM_MODEL_NAME"] = settings.ai_model.strip()
    if settings.ai_api_key:
        env["MPT_LLM_API_KEY"] = settings.ai_api_key
    if settings.mpt_pexels_api_key:
        env["MPT_PEXELS_API_KEY"] = settings.mpt_pexels_api_key
    return env


def _parse_mpt_output(stdout: str) -> dict[str, str | list[str]]:
    """内部辅助函数“_parse_mpt_output”，负责parse mpt output。
参数：
    stdout: str
返回：dict[str, str | list[str]]。"""
    values: dict[str, str | list[str]] = {"video_files": []}
    for line in stdout.splitlines():
        if line.startswith("VIDEO_FILE="):
            values.setdefault("video_files", [])
            assert isinstance(values["video_files"], list)
            values["video_files"].append(line.removeprefix("VIDEO_FILE=").strip())
        elif line.startswith("TASK_DIR="):
            values["task_dir"] = line.removeprefix("TASK_DIR=").strip()
        elif line.startswith("LOG_FILE="):
            values["log_file"] = line.removeprefix("LOG_FILE=").strip()
        elif line.startswith("RESULT_FILE="):
            values["result_file"] = line.removeprefix("RESULT_FILE=").strip()
    return values


async def run_moneyprinterturbo(
    request: MoneyPrinterTurboRequest,
    settings: Settings,
    timeout_seconds: int | None = 0,
) -> MoneyPrinterTurboRunResult:
    """函数“run_moneyprinterturbo”，负责run moneyprinterturbo。
参数：
    request: MoneyPrinterTurboRequest
    settings: Settings
    timeout_seconds: int | None
返回：MoneyPrinterTurboRunResult。"""
    if not MPT_HELPER_FILE.exists():
        return MoneyPrinterTurboRunResult(
            exit_code=1,
            status="missing_skill",
            stdout="",
            stderr=f"MoneyPrinterTurbo Skill helper not found: {MPT_HELPER_FILE}",
            video_files=[],
        )

    command = [
        "python",
        "-m",
        "uv",
        "run",
        "--no-project",
        "--python",
        # 固定完整的 Python 补丁版本，避免本机 uv 的小版本入口失效。
        "3.11.15",
        "python",
        "mpt_agent.py",
        "--subject",
        request.subject,
        *( ["--output-dir", request.output_dir] if request.output_dir else [] ),
        *request.extra_args,
        "--",
        "--video-aspect",
        request.video_aspect,
    ]
    try:
        # 默认不限制视频渲染时长，因为依赖安装、下载、TTS 和编码都可能耗时较久；
        # 调用方仍可传入显式超时来设置硬上限。
        # 不使用 asyncio.create_subprocess_exec：Windows 下的 uvicorn 可能运行在不支持子进程传输的事件循环；
        # 将阻塞子进程放到线程池，可兼容不同事件循环策略。
        run_options = {
            "cwd": MPT_SKILL_DIR,
            "env": _mpt_env(settings),
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "check": False,
        }
        if timeout_seconds is not None and timeout_seconds > 0:
            run_options["timeout"] = timeout_seconds
        completed = await asyncio.to_thread(subprocess.run, command, **run_options)
    except subprocess.TimeoutExpired:
        return MoneyPrinterTurboRunResult(
            exit_code=124,
            status="timeout",
            stdout="",
            stderr=f"MoneyPrinterTurbo generation exceeded {timeout_seconds} seconds.",
            video_files=[],
        )

    stdout = (completed.stdout or b"").decode("utf-8", errors="replace")
    stderr = (completed.stderr or b"").decode("utf-8", errors="replace")
    parsed = _parse_mpt_output(stdout)
    status = "completed" if completed.returncode == 0 else "needs_input" if completed.returncode == 10 else "failed"
    return MoneyPrinterTurboRunResult(
        exit_code=completed.returncode or 0,
        status=status,
        stdout=stdout,
        stderr=stderr,
        video_files=list(parsed.get("video_files", [])),
        task_dir=parsed.get("task_dir") if isinstance(parsed.get("task_dir"), str) else None,
        log_file=parsed.get("log_file") if isinstance(parsed.get("log_file"), str) else None,
        result_file=parsed.get("result_file") if isinstance(parsed.get("result_file"), str) else None,
    )

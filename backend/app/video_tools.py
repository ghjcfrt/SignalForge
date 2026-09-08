from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from backend.app.config import WORKSPACE_DIR, Settings


MPT_SKILL_DIR = WORKSPACE_DIR / "agents" / "video_editor" / "skills" / "moneyprinterturbo-video"
MPT_SKILL_FILE = MPT_SKILL_DIR / "SKILL.md"
MPT_HELPER_FILE = MPT_SKILL_DIR / "mpt_agent.py"
MPT_LICENSE_FILE = MPT_SKILL_DIR / "LICENSE.MoneyPrinterTurbo"
MPT_README_FILE = MPT_SKILL_DIR / "README.MoneyPrinterTurbo.md"


class MoneyPrinterTurboStatus(BaseModel):
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
    subject: str
    extra_args: list[str] = []
    output_dir: str | None = None
    video_aspect: Literal["9:16", "16:9"] = "9:16"


class MoneyPrinterTurboRunResult(BaseModel):
    exit_code: int
    status: str
    stdout: str
    stderr: str
    video_files: list[str]
    task_dir: str | None = None
    log_file: str | None = None
    result_file: str | None = None


# 中文说明：函数「mpt_status」负责完成该步骤的输入处理、核心逻辑和结果返回。
def mpt_status(settings: Settings) -> MoneyPrinterTurboStatus:
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


# 中文说明：函数「_mpt_env」负责完成该步骤的输入处理、核心逻辑和结果返回。
def _mpt_env(settings: Settings) -> dict[str, str]:
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


# 中文说明：函数「_parse_mpt_output」负责完成该步骤的输入处理、核心逻辑和结果返回。
def _parse_mpt_output(stdout: str) -> dict[str, str | list[str]]:
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


# 中文说明：异步函数「run_moneyprinterturbo」负责完成该步骤的输入处理、核心逻辑和结果返回。
async def run_moneyprinterturbo(
    request: MoneyPrinterTurboRequest,
    settings: Settings,
    timeout_seconds: int | None = 0,
) -> MoneyPrinterTurboRunResult:
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
        # Pin the fully-qualified patch release.  On this machine uv's
        # `3.11` minor-version junction is stale, while the installed
        # 3.11.15 interpreter is valid.
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
        # Video rendering is intentionally unbounded by default.  It may
        # involve dependency installation, downloads, TTS and encoding, all
        # of which can legitimately exceed a fixed request timeout.  Keep an
    # 中文说明：上半段结果在这里汇总，下面继续执行后续校验、转换或持久化。
    # 中文说明：上半段结果在这里汇总，下面继续执行后续校验、转换或持久化。
        # explicit timeout available for callers that need a hard cap.
        # Do not use asyncio.create_subprocess_exec here: uvicorn may run
        # under Windows' SelectorEventLoop (notably with --reload), whose
        # subprocess transport raises NotImplementedError.  Running the
        # blocking subprocess in a worker works with either loop policy.
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

from __future__ import annotations

import asyncio
import os
from pathlib import Path

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


class MoneyPrinterTurboRunResult(BaseModel):
    exit_code: int
    status: str
    stdout: str
    stderr: str
    video_files: list[str]
    task_dir: str | None = None
    log_file: str | None = None
    result_file: str | None = None


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
        default_command='uv run --no-project --python 3.11 python mpt_agent.py --subject "<视频主题或脚本>"',
    )


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


async def run_moneyprinterturbo(
    request: MoneyPrinterTurboRequest,
    settings: Settings,
    timeout_seconds: int = 1200,
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
        "3.11",
        "python",
        "mpt_agent.py",
        "--subject",
        request.subject,
        *request.extra_args,
    ]
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=MPT_SKILL_DIR,
        env=_mpt_env(settings),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        return MoneyPrinterTurboRunResult(
            exit_code=124,
            status="timeout",
            stdout="",
            stderr=f"MoneyPrinterTurbo generation exceeded {timeout_seconds} seconds.",
            video_files=[],
        )

    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")
    parsed = _parse_mpt_output(stdout)
    status = "completed" if process.returncode == 0 else "needs_input" if process.returncode == 10 else "failed"
    return MoneyPrinterTurboRunResult(
        exit_code=process.returncode or 0,
        status=status,
        stdout=stdout,
        stderr=stderr,
        video_files=list(parsed.get("video_files", [])),
        task_dir=parsed.get("task_dir") if isinstance(parsed.get("task_dir"), str) else None,
        log_file=parsed.get("log_file") if isinstance(parsed.get("log_file"), str) else None,
        result_file=parsed.get("result_file") if isinstance(parsed.get("result_file"), str) else None,
    )

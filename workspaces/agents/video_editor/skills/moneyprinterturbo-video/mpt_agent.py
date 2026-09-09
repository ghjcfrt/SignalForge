#!/usr/bin/env python3
"""Cross-platform installation and video generation for the MoneyPrinterTurbo Skill."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ARCHIVE_URL = (
    "https://github.com/harry0703/MoneyPrinterTurbo/archive/refs/heads/main.zip"
)
# Keep the upstream checkout inside this SignalForge project so all runtime
# state and generated assets remain self-contained.  The helper lives five
# levels below the repository root:
#   SignalForge/workspaces/agents/video_editor/skills/moneyprinterturbo-video/
PROJECT_ROOT = Path(__file__).resolve().parents[5]
DEFAULT_ROOT = PROJECT_ROOT / "MoneyPrinterTurbo"
DEFAULT_VOICE_NAME = "zh-CN-XiaoxiaoNeural-Female"
NEEDS_INPUT_EXIT_CODE = 10
SUPPORTED_SOURCES = {"pexels", "pixabay", "coverr", "local"}
PEXELS_API_KEY_URL = "https://www.pexels.com/api/"
PEXELS_VALIDATION_URL = "https://api.pexels.com/v1/collections?per_page=1"
PEXELS_API_KEY_HELP_URL = (
    "https://help.pexels.com/hc/en-us/articles/"
    "900004904026-How-do-I-get-an-API-key"
)

# Keep the recommended list focused on commonly used providers. When an LLM
# key is missing, the helper emits all choices at once to avoid extra turns.
RECOMMENDED_LLM_PROVIDERS = {
    "moonshot": (
        "Kimi / Moonshot AI",
        "https://platform.kimi.com/console/api-keys?aff=MoneyPrinterTurbo",
    ),
    "openai": ("OpenAI", "https://platform.openai.com/api-keys"),
    "gemini": ("Google Gemini", "https://aistudio.google.com/app/apikey"),
    "deepseek": ("DeepSeek", "https://platform.deepseek.com/api_keys"),
    "volcengine": (
        "ByteDance VolcEngine Ark / Doubao",
        "https://www.volcengine.com/activity/ai618?utm_source=MoneyPrinterTurbo",
    ),
    "minimax": ("MiniMax", "https://platform.minimax.io/"),
    "mimo": (
        "Xiaomi MiMo",
        "https://platform.xiaomimimo.com/docs/zh-CN/quick-start/first-api-call",
    ),
}
KEYLESS_LLM_PROVIDERS = {"ollama", "litellm"}
CUSTOM_OPENAI_PROVIDER = "oneapi"


def _spoken_script(value: str) -> str:
    """Extract narration only; never send shot/subtitle directions to TTS."""
    lines: list[str] = []
    skip_markers = ("镜头", "画面", "素材", "字幕", "转场", "音效", "配乐", "剪辑", "导出")
    for raw in (value or "").splitlines():
        raw = raw.strip()
        # Markdown headings and bold metadata are layout instructions, not narration.
        if re.match(r"^#{1,6}\s*", raw) or re.match(r"^\*\*[^*]+\*\*\s*$", raw):
            continue
        line = re.sub(r"^\s*[【\[][^】\]]+[】\]]\s*", "", raw).strip()
        line = re.sub(
            r"^\s*(?:[-*]\s*)?(?:口播|旁白|配音)(?:\s*[（(][^）)]*[）)])?\s*[:：]\s*",
            "",
            line,
        )
        if not line or any(marker in line for marker in skip_markers):
            continue
        # Metadata lines are not narration even when written as bullets.
        if re.match(r"^\s*(?:时间|时长|目标时长|画幅|规格|工具)\s*[:：]", line):
            continue
        lines.append(line)
    return "\n".join(lines).strip()

# Hidden providers such as Qwen, Azure, and Grok remain usable when already
# selected, but are not automatic fallback candidates. A fully configured
# generic OpenAI-compatible endpoint can be reused safely.
ADDITIONAL_REUSABLE_PROVIDERS = (CUSTOM_OPENAI_PROVIDER,)


class SkillError(RuntimeError):
    """An actionable Skill error that can be reported without a traceback."""


# 函数「log」负责完成该步骤的输入处理、核心逻辑和结果返回。
def log(message: str) -> None:
    """Flush concise progress so the agent knows the long-running job started."""
    print(f"[MoneyPrinterTurbo] {message}", flush=True)


# 函数「parse_args」负责完成该步骤的输入处理、核心逻辑和结果返回。
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install MoneyPrinterTurbo and generate a final video from a topic."
    )
    parser.add_argument("--subject", required=True, help="video topic")
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help=f"MoneyPrinterTurbo installation directory (default: {DEFAULT_ROOT})",
    )
    parser.add_argument("--output-dir", type=Path, default=None, help="copy final videos to this directory")
    parser.add_argument("--video-script", default="", help="complete script forwarded to MoneyPrinterTurbo")
    parser.add_argument("--target-duration", type=float, default=None, help="pad/trim final videos to this duration in seconds")
    parser.add_argument(
        "cli_args",
        nargs=argparse.REMAINDER,
        help="additional MoneyPrinterTurbo CLI arguments placed after --",
    )
    args = parser.parse_args(argv)
    args.subject = args.subject.strip()
    if not args.subject:
        parser.error("--subject cannot be empty")
    if args.cli_args and args.cli_args[0] == "--":
        args.cli_args = args.cli_args[1:]
    if args.video_script.strip():
        args.video_script = _spoken_script(args.video_script)
        args.cli_args = ["--video-script", args.video_script, *args.cli_args]
        # A complete script must finish speaking before the requested canvas
        # duration.  The upstream default (1.0) produced a 169s soundtrack for
        # this 110s script, after which post-processing cut the final sentence.
        # Estimate the required rate from Chinese/non-whitespace character
        # count; the final normalizer pads short output and never cuts speech.
        if args.target_duration and args.target_duration > 0 and not has_cli_option(args.cli_args, "--voice-rate"):
            spoken_chars = len(re.sub(r"\s+", "", args.video_script))
            estimated_rate = spoken_chars / (5.0 * args.target_duration)
            args.cli_args.extend(["--voice-rate", f"{max(1.0, min(2.5, estimated_rate)):.3f}"])
    return args


# 函数「_safe_extract」负责完成该步骤的输入处理、核心逻辑和结果返回。
def _safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    """Reject ZIP entries that would escape the temporary extraction directory."""
    destination = destination.resolve()
    for member in archive.infolist():
        target = (destination / member.filename).resolve()
        if target != destination and destination not in target.parents:
            raise SkillError(f"project archive contains an unsafe path: {member.filename}")
    archive.extractall(destination)


# 函数「ensure_project」负责完成该步骤的输入处理、核心逻辑和结果返回。
def ensure_project(root: Path) -> None:
    """Reuse an existing project or install it from the official GitHub archive."""
    root = root.expanduser().resolve()
    if (root / "cli.py").is_file() and (root / "config.example.toml").is_file():
        log(f"using existing project: {root}")
        return
    if root.exists() and any(root.iterdir()):
        raise SkillError(f"installation directory exists but is not a valid project: {root}")

    root.parent.mkdir(parents=True, exist_ok=True)
    log(f"first-time installation: downloading the official project to {root}")
    with tempfile.TemporaryDirectory(prefix="mpt-install-") as temp_dir_value:
        temp_dir = Path(temp_dir_value)
        archive_path = temp_dir / "MoneyPrinterTurbo.zip"
        request = urllib.request.Request(
            PROJECT_ARCHIVE_URL,
            headers={"User-Agent": "MoneyPrinterTurbo-Agent-Skill"},
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                # Stream the archive to avoid holding a second full copy in memory.
                with archive_path.open("wb") as archive_file:
                    shutil.copyfileobj(response, archive_file)
        except (urllib.error.URLError, TimeoutError) as exc:
            # Some Windows Python builds cannot complete GitHub's TLS
            # handshake even though the system curl client can.  Retry via
            # curl before reporting an installation failure.
    # 这里汇总前半段结果，继续执行后续校验、转换或输出。
            curl = shutil.which("curl.exe") or shutil.which("curl")
            if not curl:
                raise SkillError(f"GitHub download failed: {exc}") from exc
            completed = subprocess.run(
                [curl, "-L", "--fail", "--silent", "--show-error", "--max-time", "120",
                 "-A", "MoneyPrinterTurbo-Agent-Skill", "-o", str(archive_path), PROJECT_ARCHIVE_URL],
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                detail = (completed.stderr or str(exc)).strip()[-1000:]
                raise SkillError(f"GitHub download failed via urllib and curl: {detail}") from exc
        with zipfile.ZipFile(archive_path) as archive:
            _safe_extract(archive, temp_dir)

        candidates = [
            path
            for path in temp_dir.iterdir()
            if path.is_dir() and (path / "cli.py").is_file()
        ]
        if len(candidates) != 1:
            raise SkillError("download completed but no valid MoneyPrinterTurbo project was found")
        if root.exists():
            root.rmdir()
        shutil.move(str(candidates[0]), str(root))
    log("project download completed")


def ensure_llm_timeout(root: Path) -> None:
    """Keep upstream OpenAI-compatible requests from using the SDK's short default timeout.

    MoneyPrinterTurbo is downloaded at runtime and is intentionally not vendored
    into SignalForge.  Apply this small, idempotent runtime patch after both a
    fresh download and reuse of an existing checkout so long prompts can finish
    through slower OpenAI-compatible gateways.
    """
    llm_file = root / "app" / "services" / "llm.py"
    if not llm_file.is_file():
        return
    text = llm_file.read_text(encoding="utf-8")
    if "_OPENAI_REQUEST_TIMEOUT_SECONDS" in text:
        # Already patched.  Returning here is important: a broad constructor
        # regex can mistake the nested ``base_url=(...)`` close parenthesis for
        # the end of OpenAI(...), corrupting valid Python on every retry.
        return
    if "_OPENAI_REQUEST_TIMEOUT_SECONDS" not in text:
        marker = "_max_retries = 5"
        if marker not in text:
            return
        text = text.replace(
            marker,
            marker
            + "\n# Allow long prompts to complete through OpenAI-compatible gateways.\n"
            + "_OPENAI_REQUEST_TIMEOUT_SECONDS = 120.0",
            1,
        )
    # Insert after the first api_key argument.  This avoids matching nested
    # parentheses in Cloudflare's multiline base_url expression.
    patched = re.sub(
        r"(?m)^(\s*client = (?:AzureOpenAI|OpenAI)\(\r?\n\s*api_key=api_key,\r?\n)",
        r"\1                timeout=_OPENAI_REQUEST_TIMEOUT_SECONDS,\n",
        text,
    )
    if patched != text:
        llm_file.write_text(patched, encoding="utf-8")
        log("configured MoneyPrinterTurbo LLM request timeout: 120s")


# 函数「ensure_config」负责完成该步骤的输入处理、核心逻辑和结果返回。
def ensure_config(root: Path) -> Path:
    """Create the initial configuration without overwriting an existing file."""
    config_path = root / "config.toml"
    if not config_path.exists():
        shutil.copy2(root / "config.example.toml", config_path)
        log(f"created configuration file: {config_path}")
    return config_path


def _detect_discrete_gpu_codec() -> str | None:
    """Detect a discrete GPU and map it to the matching FFmpeg encoder."""
    # Probe NVIDIA directly when the utility is available.  This is the most
    # reliable Windows signal for a discrete adapter and is bounded so a
    # broken driver cannot hold an unattended workflow forever.  The legacy
    # environment switch is still accepted as an explicit opt-out for hosts
    # where process creation is restricted.
    probe_disabled = str(
        os.environ.get("MPT_DISABLE_GPU_DETECTION", "")
    ).strip().casefold() in {"1", "true", "yes"}
    nvidia_smi = shutil.which("nvidia-smi") or shutil.which("nvidia-smi.exe")
    if not probe_disabled and nvidia_smi:
        try:
            result = subprocess.run(
                [nvidia_smi, "--query-gpu=name", "--format=csv,noheader"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                return "h264_nvenc"
        except (OSError, subprocess.TimeoutExpired, KeyboardInterrupt):
            pass
    # On Windows, query adapter names so AMD discrete cards and Intel Arc are
    # also preferred without treating Intel UHD/Iris integrated graphics as a
    # discrete adapter. The env override is useful for headless/CI hosts.
    hinted = str(os.environ.get("MPT_DISCRETE_GPU", "")).strip().casefold()
    if hinted in {"nvidia", "nvenc"}:
        return "h264_nvenc"
    if hinted in {"amd", "radeon", "amf"}:
        return "h264_amf"
    if hinted in {"intel_arc", "arc", "qsv"}:
        return "h264_qsv"
    if hinted in {"1", "true", "yes"}:
        return "h264_nvenc"
    # Do not launch a WMI/PowerShell query by default.  On some Windows hosts
    # (especially when PowerShell is being initialized by policy software),
    # CreateProcess itself can block and cannot be bounded by subprocess's
    # timeout.  Opt in explicitly when adapter-name detection is needed.
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    powershell_enabled = str(
        os.environ.get("MPT_ENABLE_POWERSHELL_GPU_DETECTION", "")
    ).strip().casefold() in {"1", "true", "yes"}
    if powershell and powershell_enabled:
        try:
            result = subprocess.run(
                [powershell, "-NoProfile", "-Command", "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=5,
                check=False,
            )
            for name in result.stdout.splitlines():
                lowered = name.casefold()
                if any(token in lowered for token in ("geforce", "quadro", "rtx", "nvidia")):
                    return "h264_nvenc"
                if any(token in lowered for token in ("radeon", "amd")) and not any(token in lowered for token in ("vega", "graphics")):
                    return "h264_amf"
                if "arc" in lowered:
                    return "h264_qsv"
        except (OSError, subprocess.TimeoutExpired, KeyboardInterrupt):
            pass
    return None


def _has_discrete_gpu() -> bool:
    """Compatibility helper for callers that only need a yes/no result."""
    return _detect_discrete_gpu_codec() is not None


def _configure_hardware_acceleration(root: Path, config_path: Path) -> str:
    """Prefer NVENC by default and return the selected acceleration mode."""
    text = config_path.read_text(encoding="utf-8")
    requested = _plain_config_value(text, "video_codec").strip().strip('"')
    detected_codec = _detect_discrete_gpu_codec()
    # A configured hardware encoder is only honored when a discrete GPU is
    # actually present. This prevents stale NVENC/AMF/QSV settings from
    # making a CPU-only machine repeatedly fail before falling back.
    codec = detected_codec or "libx264"
    if detected_codec and requested and requested not in {"libx264", ""}:
        codec = requested
    if re.search(r"(?m)^\s*#?\s*video_codec\s*=", text):
        text = re.sub(r"(?m)^\s*#?\s*video_codec\s*=.*$", f'video_codec = "{codec}"', text, count=1)
    else:
        app_match = re.search(r"(?m)^\[app\]\s*$", text)
        if app_match:
            insert_at = app_match.end()
            text = text[:insert_at] + f'\nvideo_codec = "{codec}"' + text[insert_at:]
        else:
            text += f'\nvideo_codec = "{codec}"\n'
    config_path.write_text(text, encoding="utf-8")
    # Whisper subtitles should use the same policy when that provider is
    # selected: CUDA on a detected discrete GPU, CPU only when none exists.
    whisper_device = "cuda" if codec != "libx264" else "cpu"
    whisper_compute = "float16" if whisper_device == "cuda" else "int8"
    text = re.sub(
        r"(?ms)(^\[whisper\].*?^device\s*=\s*)\"[^\"]*\"",
        rf'\1"{whisper_device}"',
        text,
        count=1,
    )
    text = re.sub(
        r"(?ms)(^\[whisper\].*?^compute_type\s*=\s*)\"[^\"]*\"",
        rf'\1"{whisper_compute}"',
        text,
        count=1,
    )
    config_path.write_text(text, encoding="utf-8")
    log(f"video acceleration: {codec} ({'discrete GPU detected' if codec != 'libx264' else 'no discrete GPU detected, CPU fallback'})")
    return codec


# 函数「_plain_config_value」负责完成该步骤的输入处理、核心逻辑和结果返回。
def _plain_config_value(text: str, key: str) -> str:
    """Read a simple top-level TOML value without printing its contents."""
    match = re.search(rf"(?m)^{re.escape(key)}\s*=\s*(.*)$", text)
    if not match:
        return ""
    value = match.group(1).split("#", 1)[0].strip()
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    return value


# 函数「_replace_config_value」负责完成该步骤的输入处理、核心逻辑和结果返回。
def _replace_config_value(text: str, key: str, value: object) -> str:
    """Replace one active field while preserving the configuration layout."""
    pattern = re.compile(rf"(?m)^({re.escape(key)}\s*=\s*).*$")
    if not pattern.search(text):
        raise SkillError(f"configuration field not found in config.toml: {key}")
    encoded = json.dumps(value, ensure_ascii=False)
    return pattern.sub(lambda match: f"{match.group(1)}{encoded}", text, count=1)


# 函数「_has_configured_value」负责完成该步骤的输入处理、核心逻辑和结果返回。
def _has_configured_value(value: str) -> bool:
    """Treat empty strings and whitespace-only key arrays as unconfigured."""
    if not value:
        return False
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return bool(value.strip())
    if isinstance(parsed, list):
        return any(str(item).strip() for item in parsed)
    return bool(str(parsed).strip())


# 函数「_parse_string_list」负责完成该步骤的输入处理、核心逻辑和结果返回。
def _parse_string_list(value: str) -> list[str]:
    """Parse a configured string list while removing blanks and duplicates."""
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return list(dict.fromkeys(str(item).strip() for item in parsed if str(item).strip()))


# 函数「apply_environment_config」负责完成该步骤的输入处理、核心逻辑和结果返回。
def apply_environment_config(config_path: Path) -> None:
    """Write supplied credentials while logging field names only."""
    provider = os.environ.get("MPT_LLM_PROVIDER", "").strip().lower()
    if provider == "openai_compatible":
        provider = CUSTOM_OPENAI_PROVIDER
    llm_key = os.environ.get("MPT_LLM_API_KEY", "").strip()
    base_url = os.environ.get("MPT_LLM_BASE_URL", "").strip()
    model_name = os.environ.get("MPT_LLM_MODEL_NAME", "").strip()
    pexels_key = os.environ.get("MPT_PEXELS_API_KEY", "").strip()
    if not any((provider, llm_key, base_url, model_name, pexels_key)):
        return

    text = config_path.read_text(encoding="utf-8")
    current_provider = _plain_config_value(text, "llm_provider") or "moonshot"
    provider = provider or current_provider
    changes: list[str] = []
    if os.environ.get("MPT_LLM_PROVIDER", "").strip():
        text = _replace_config_value(text, "llm_provider", provider)
        changes.append("llm_provider")
    if llm_key:
        text = _replace_config_value(text, f"{provider}_api_key", llm_key)
        changes.append(f"{provider}_api_key")
    if base_url:
        text = _replace_config_value(text, f"{provider}_base_url", base_url)
        changes.append(f"{provider}_base_url")
    if model_name:
        text = _replace_config_value(text, f"{provider}_model_name", model_name)
        changes.append(f"{provider}_model_name")
    if pexels_key:
        text = _replace_config_value(text, "pexels_api_keys", [pexels_key])
        changes.append("pexels_api_keys")
    config_path.write_text(text, encoding="utf-8")
    log("updated configuration fields: " + ", ".join(changes))


# 函数「_provider_is_ready」负责完成该步骤的输入处理、核心逻辑和结果返回。
def _provider_is_ready(text: str, provider: str) -> bool:
    """Return whether a provider has enough configuration to generate."""
    if provider in KEYLESS_LLM_PROVIDERS:
        return True
    if not _has_configured_value(
        _plain_config_value(text, f"{provider}_api_key")
    ):
        return False
    if provider == CUSTOM_OPENAI_PROVIDER:
        return all(
            _has_configured_value(_plain_config_value(text, f"{provider}_{suffix}"))
            for suffix in ("base_url", "model_name")
        )
    return True


# 函数「reuse_existing_llm_provider」负责完成该步骤的输入处理、核心逻辑和结果返回。
def reuse_existing_llm_provider(config_path: Path) -> str:
    """
    Reuse existing LLM credentials before asking the user for another key.

    Keep the current provider when it is ready. Otherwise, scan configured
    recommended providers in UI order and update ``llm_provider``. Credential
    values are inspected in memory and are never logged.
    """
    text = config_path.read_text(encoding="utf-8")
    current_provider = _plain_config_value(text, "llm_provider") or "moonshot"
    if _provider_is_ready(text, current_provider):
        return current_provider

    reusable_providers = (
        *RECOMMENDED_LLM_PROVIDERS,
        *ADDITIONAL_REUSABLE_PROVIDERS,
    )
    for provider in reusable_providers:
        if _provider_is_ready(text, provider):
            text = _replace_config_value(text, "llm_provider", provider)
            config_path.write_text(text, encoding="utf-8")
            log(f"reusing configured LLM provider: {provider}")
            return provider
    return current_provider


# 函数「selected_video_source」负责完成该步骤的输入处理、核心逻辑和结果返回。
def selected_video_source(cli_args: list[str]) -> str:
    """Read the effective material source from forwarded CLI arguments."""
    for index, item in enumerate(cli_args):
        if item == "--video-source" and index + 1 < len(cli_args):
            return cli_args[index + 1].strip().lower()
        if item.startswith("--video-source="):
            return item.split("=", 1)[1].strip().lower()
    return "pexels"


# 函数「has_cli_option」负责完成该步骤的输入处理、核心逻辑和结果返回。
def has_cli_option(cli_args: list[str], option: str) -> bool:
    """Return whether forwarded arguments explicitly set a CLI option."""
    return any(item == option or item.startswith(f"{option}=") for item in cli_args)


# 函数「missing_config」负责完成该步骤的输入处理、核心逻辑和结果返回。
def missing_config(config_path: Path, cli_args: list[str]) -> tuple[str, list[str]]:
    """Return the active provider and only the fields required by this run."""
    text = config_path.read_text(encoding="utf-8")
    provider = _plain_config_value(text, "llm_provider") or "moonshot"
    missing: list[str] = []
    if provider not in KEYLESS_LLM_PROVIDERS and not _has_configured_value(
        _plain_config_value(text, f"{provider}_api_key")
    ):
        missing.append(f"{provider}_api_key")
    if provider == CUSTOM_OPENAI_PROVIDER:
        for suffix in ("base_url", "model_name"):
            field = f"{provider}_{suffix}"
            if not _has_configured_value(_plain_config_value(text, field)):
                missing.append(field)

    source = selected_video_source(cli_args)
    if source not in SUPPORTED_SOURCES:
        raise SkillError(f"unsupported video source: {source}")
    if source != "local":
        value = _plain_config_value(text, f"{source}_api_keys")
        if not _has_configured_value(value):
            missing.append(f"{source}_api_keys")
    return provider, missing


# 函数「report_missing_config」负责完成该步骤的输入处理、核心逻辑和结果返回。
def report_missing_config(provider: str, missing: list[str]) -> int:
    """Tell the agent exactly which credentials must be requested."""
    print("MPT_NEEDS_INPUT")
    print(f"LLM_PROVIDER={provider}")
    for field in missing:
        print(f"MISSING={field}")
    if any(field.endswith("_api_key") for field in missing):
        print("LLM_PROVIDER_OPTIONS_BEGIN")
        for provider_id, (label, url) in RECOMMENDED_LLM_PROVIDERS.items():
            print(f"LLM_PROVIDER_OPTION={provider_id}|{label}|{url}")
        print(
            "LLM_PROVIDER_OPTION=oneapi|Other OpenAI-compatible provider|"
            "requires an API key, API base URL, and model name"
        )
        print("LLM_PROVIDER_OPTIONS_END")
    if any(field.startswith(f"{CUSTOM_OPENAI_PROVIDER}_") for field in missing):
        print(
            "OPENAI_COMPATIBLE_REQUIRED="
            "API key, API base URL, model name"
        )
    if "pexels_api_keys" in missing:
        print(f"PEXELS_API_KEY_URL={PEXELS_API_KEY_URL}")
        print(f"PEXELS_API_KEY_HELP_URL={PEXELS_API_KEY_HELP_URL}")
    print("Request only the listed values, set the environment variables, and rerun the same command.")
    return NEEDS_INPUT_EXIT_CODE


# 函数「report_invalid_pexels_config」负责完成该步骤的输入处理、核心逻辑和结果返回。
def report_invalid_pexels_config() -> int:
    """Request only a new Pexels key when every configured key is rejected."""
    print("MPT_NEEDS_INPUT")
    print("INVALID=pexels_api_keys")
    print(f"PEXELS_API_KEY_URL={PEXELS_API_KEY_URL}")
    print(f"PEXELS_API_KEY_HELP_URL={PEXELS_API_KEY_HELP_URL}")
    print("All configured Pexels API keys were rejected or are unavailable. Provide a new key.")
    return NEEDS_INPUT_EXIT_CODE


# 函数「_validate_pexels_key」负责完成该步骤的输入处理、核心逻辑和结果返回。
def _validate_pexels_key(api_key: str) -> str:
    """
    Return ``valid``, ``rejected``, or ``unknown`` for a Pexels key.

    HTTP 401, 403, and rate-limited 429 responses make a key unusable for this
    run. Network and server errors return unknown so the configuration is kept.
    """
    # Curated and popular search requests may hit a public cache and return 200
    # without valid authorization. My Collections is account-specific, requires
    # authentication, and still returns 200 for an empty collection list.
    request = urllib.request.Request(
        PEXELS_VALIDATION_URL,
        headers={
            "Authorization": api_key,
            "User-Agent": "MoneyPrinterTurbo-Agent-Skill",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return "valid" if 200 <= response.status < 300 else "unknown"
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403, 429}:
            return "rejected"
        return "unknown"
    except (TimeoutError, urllib.error.URLError):
        return "unknown"


# 函数「validate_pexels_config」负责完成该步骤的输入处理、核心逻辑和结果返回。
def validate_pexels_config(config_path: Path, cli_args: list[str]) -> bool:
    """
    Validate all Pexels keys used by the default material source.

    Downstream code selects configured keys randomly. Keeping rejected keys can
    cause intermittent 401 responses and missing material results. If at least
    one key is verified, retain only verified keys. If validation is impossible
    because of a transient network failure, keep the original configuration.
    """
    if selected_video_source(cli_args) != "pexels":
        return True

    text = config_path.read_text(encoding="utf-8")
    keys = _parse_string_list(_plain_config_value(text, "pexels_api_keys"))
    if not keys:
        return False

    valid_keys: list[str] = []
    rejected_count = 0
    unknown_count = 0
    for api_key in keys:
        status = _validate_pexels_key(api_key)
        if status == "valid":
            valid_keys.append(api_key)
        elif status == "rejected":
            rejected_count += 1
        else:
            unknown_count += 1
    # 这里汇总前半段结果，继续执行后续校验、转换或输出。

    if valid_keys:
        if valid_keys != keys:
            text = _replace_config_value(text, "pexels_api_keys", valid_keys)
            config_path.write_text(text, encoding="utf-8")
        log(
            "Pexels key validation completed: "
            f"valid={len(valid_keys)}, rejected={rejected_count}, "
            f"unknown={unknown_count}"
        )
        return True
    if unknown_count:
        log("Pexels keys could not be verified due to a network or service error; keeping the existing configuration")
        return True

    log(f"Pexels key validation failed: all {rejected_count} configured keys are unusable")
    return False


# 函数「result_manifest_path」负责完成该步骤的输入处理、核心逻辑和结果返回。
def result_manifest_path(root: Path) -> Path:
    return root / ".agent-logs" / "moneyprinterturbo-video" / "latest-result.json"


# 函数「write_result_manifest」负责完成该步骤的输入处理、核心逻辑和结果返回。
def write_result_manifest(root: Path, payload: dict[str, object]) -> Path:
    """
    Atomically write the stable result file for agents that cannot wait.

    The file contains task status and result paths only, never configuration
    contents, credentials, or full logs.
    """
    result_path = result_manifest_path(root)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
    unique_suffix = str(uuid.uuid4()).replace("-", "")
    temp_path = result_path.with_name(
        f".{result_path.name}.{os.getpid()}.{unique_suffix}.tmp"
    )
    temp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temp_path.replace(result_path)
    return result_path.resolve()


# 函数「run_checked」负责完成该步骤的输入处理、核心逻辑和结果返回。
def run_checked(command: list[str], *, cwd: Path) -> None:
    """Run dependency sync quietly and show only the last 30 lines on failure."""
    log("installing or verifying project dependencies with uv")
    result = subprocess.run(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        output_tail = (result.stdout or "").splitlines()[-30:]
        if output_tail:
            print("\n".join(output_tail), file=sys.stderr)
        raise SkillError(f"dependency installation failed with exit code {result.returncode}")


# 函数「generate_video」负责完成该步骤的输入处理、核心逻辑和结果返回。
def generate_video(
    root: Path,
    subject: str,
    cli_args: list[str],
    output_dir: Path | None = None,
    target_duration: float | None = None,
) -> tuple[list[Path], Path, Path, Path]:
    """Run one traceable CLI task and return only its final video files."""
    uv = shutil.which("uv")
    if not uv:
        raise SkillError("uv was not found; reopen the terminal or add uv to PATH")
    run_checked([uv, "sync", "--frozen"], cwd=root)

    task_id = str(uuid.uuid4())
    task_dir = root / "storage" / "tasks" / task_id
    log_dir = root / ".agent-logs" / "moneyprinterturbo-video"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"run-{task_id}.log"
    write_result_manifest(
        root,
        {
            "status": "running",
            "subject": subject,
            "task_id": task_id,
            "task_dir": str(task_dir.resolve()),
            "log_file": str(log_path.resolve()),
            "video_files": [],
        },
    )
    voice_args = (
        []
        if has_cli_option(cli_args, "--voice-name")
        else ["--voice-name", DEFAULT_VOICE_NAME]
    )
    command = [
        uv,
        "run",
        "python",
        "cli.py",
        *cli_args,
        "--video-subject",
        subject,
        "--task-id",
        task_id,
        # Older CLI versions leave voice_name empty and fail during Edge TTS
        # with ``Invalid voice ''``. Supply a stable Chinese voice unless the
        # user has explicitly selected another voice.
        *voice_args,
        # Always enable subtitle generation for finished videos, regardless of
        # a stale WebUI setting from a previous task.
        "--subtitle-enabled",
        # A Skill request must produce a finished video. Force the final stage
        # so forwarded options cannot stop at script, audio, or materials.
        "--stop-at",
        "video",
    ]
    # A supplied script is the source of truth for both narration and visuals.
    # Keep material search/concatenation in script order so the final shot is
    # the script's closing shot rather than an arbitrary earlier result.
    if (
        any(item == "--video-script" and index + 1 < len(cli_args) and cli_args[index + 1].strip() for index, item in enumerate(cli_args))
        and not has_cli_option(cli_args, "--match-materials-to-script")
        and not has_cli_option(cli_args, "--no-match-materials-to-script")
    ):
        command.append("--match-materials-to-script")
    log(f"starting video generation, task ID: {task_id}")
    log(f"full generation log: {log_path}")
    with log_path.open("w", encoding="utf-8") as log_file:
        result = subprocess.run(
            command,
            cwd=root,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    # 这里汇总前半段结果，继续执行后续校验、转换或输出。
    if result.returncode != 0:
        tail = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-30:]
        if tail:
            print("\n".join(tail), file=sys.stderr)
        error = (
            f"video generation failed with exit code {result.returncode}; "
            f"log: {log_path}"
        )
        write_result_manifest(
            root,
            {
                "status": "failed",
                "subject": subject,
                "task_id": task_id,
                "task_dir": str(task_dir.resolve()),
                "log_file": str(log_path.resolve()),
                "video_files": [],
                "error": error,
            },
        )
        raise SkillError(error)

    videos = sorted(
        path.resolve()
        for path in task_dir.glob("final-*.mp4")
        if path.is_file() and path.stat().st_size > 0
    )
    if not videos:
        error = f"generation completed without a valid final MP4; log: {log_path}"
        write_result_manifest(
            root,
            {
                "status": "failed",
                "subject": subject,
                "task_id": task_id,
                "task_dir": str(task_dir.resolve()),
                "log_file": str(log_path.resolve()),
                "video_files": [],
                "error": error,
            },
        )
        raise SkillError(error)
    if target_duration and target_duration > 0:
        videos = [_normalize_duration(video, target_duration, root=root) for video in videos]
    if output_dir:
        destination = output_dir.expanduser().resolve()
        destination.mkdir(parents=True, exist_ok=True)
        copied: list[Path] = []
        for video in videos:
            target = destination / video.name
            shutil.copy2(video, target)
            copied.append(target.resolve())
        videos = copied
    result_path = write_result_manifest(
        root,
        {
            "status": "completed",
            "subject": subject,
            "task_id": task_id,
            "task_dir": str(task_dir.resolve()),
            "log_file": str(log_path.resolve()),
            "video_files": [str(video) for video in videos],
        },
    )
    return videos, task_dir.resolve(), log_path.resolve(), result_path


def _normalize_duration(video: Path, target_duration: float, *, root: Path | None = None) -> Path:
    """Pad short output, but never cut spoken content from a complete script.

    A hard ``-t`` trim can leave the last subtitle/audio sentence half-spoken.
    The caller is responsible for fitting TTS into the requested duration; this
    function only adds a tail when the renderer produced a short file.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return video
    probe = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(video)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False,
    )
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", probe.stderr or "")
    if not match:
        return video
    current = int(match.group(1)) * 3600 + int(match.group(2)) * 60 + float(match.group(3))
    if abs(current - target_duration) < 0.5:
        return video
    if current > target_duration:
        return video
    fd, temp_name = tempfile.mkstemp(suffix=".mp4", dir=str(video.parent))
    os.close(fd)
    temp = Path(temp_name)
    codec = "libx264"
    if root is not None:
        config_path = root / "config.toml"
        if config_path.is_file():
            configured = _plain_config_value(config_path.read_text(encoding="utf-8"), "video_codec")
            if configured in {"h264_nvenc", "h264_amf", "h264_qsv", "h264_mf", "h264_videotoolbox"}:
                codec = configured
    command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(video)]
    if current < target_duration:
        command += ["-vf", f"tpad=stop_mode=clone:stop_duration={target_duration-current:.3f}", "-af", "apad"]
    command += ["-t", f"{target_duration:.3f}", "-c:v", codec, "-c:a", "aac", str(temp)]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    if result.returncode != 0 and codec != "libx264":
        # Keep the existing safe fallback for machines whose driver became
        # unavailable between the main render and duration normalization.
        temp.unlink(missing_ok=True)
        fallback = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(video)]
        if current < target_duration:
            fallback += ["-vf", f"tpad=stop_mode=clone:stop_duration={target_duration-current:.3f}", "-af", "apad"]
        fallback += ["-t", f"{target_duration:.3f}", "-c:v", "libx264", "-c:a", "aac", str(temp)]
        result = subprocess.run(fallback, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    if result.returncode != 0 or not temp.exists() or temp.stat().st_size == 0:
        temp.unlink(missing_ok=True)
        return video
    temp.replace(video)
    return video


# 函数「main」负责完成该步骤的输入处理、核心逻辑和结果返回。
def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.expanduser().resolve()
    try:
        ensure_project(root)
        ensure_llm_timeout(root)
        config_path = ensure_config(root)
        apply_environment_config(config_path)
        _configure_hardware_acceleration(root, config_path)
        reuse_existing_llm_provider(config_path)
        provider, missing = missing_config(config_path, args.cli_args)
        if missing:
            write_result_manifest(
                root,
                {
                    "status": "needs_input",
                    "subject": args.subject,
                    "missing": missing,
                },
            )
            return report_missing_config(provider, missing)
        if not validate_pexels_config(config_path, args.cli_args):
            write_result_manifest(
                root,
                {
                    "status": "needs_input",
                    "subject": args.subject,
                    "invalid": ["pexels_api_keys"],
                },
            )
            return report_invalid_pexels_config()
        videos, task_dir, log_path, result_path = generate_video(
            root, args.subject, args.cli_args, args.output_dir, args.target_duration
        )
    except (OSError, SkillError, urllib.error.URLError, zipfile.BadZipFile) as exc:
        print(f"MPT_ERROR={exc}", file=sys.stderr)
        return 1

    print("MPT_RESULT")
    for video in videos:
        print(f"VIDEO_FILE={video}")
    print(f"TASK_DIR={task_dir}")
    print(f"LOG_FILE={log_path}")
    print(f"RESULT_FILE={result_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

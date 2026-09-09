"""视频剪辑员独显优先策略测试。"""

import importlib.util
import os
from pathlib import Path
from tempfile import TemporaryDirectory


PATH = Path(__file__).resolve().parents[1] / "workspaces/agents/video_editor/skills/moneyprinterturbo-video/mpt_agent.py"
spec = importlib.util.spec_from_file_location("mpt_gpu_test", PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_gpu_policy_falls_back_to_cpu_without_discrete_gpu(monkeypatch=None):
    old = os.environ.get("MPT_DISCRETE_GPU")
    os.environ["MPT_DISCRETE_GPU"] = "0"
    try:
        with TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text('[app]\n# video_codec = "libx264"\n\n[whisper]\ndevice = "cpu"\ncompute_type = "int8"\n', encoding="utf-8")
            module._detect_discrete_gpu_codec = lambda: None
            assert module._configure_hardware_acceleration(Path(directory), config) == "libx264"
            assert 'video_codec = "libx264"' in config.read_text(encoding="utf-8")
    finally:
        if old is None:
            os.environ.pop("MPT_DISCRETE_GPU", None)
        else:
            os.environ["MPT_DISCRETE_GPU"] = old


def test_gpu_policy_prefers_hardware_encoder(monkeypatch=None):
    with TemporaryDirectory() as directory:
        config = Path(directory) / "config.toml"
        config.write_text('[app]\n# video_codec = "libx264"\n\n[whisper]\ndevice = "cpu"\ncompute_type = "int8"\n', encoding="utf-8")
        module._detect_discrete_gpu_codec = lambda: "h264_nvenc"
        assert module._configure_hardware_acceleration(Path(directory), config) == "h264_nvenc"
        text = config.read_text(encoding="utf-8")
        assert 'video_codec = "h264_nvenc"' in text
        assert 'device = "cuda"' in text

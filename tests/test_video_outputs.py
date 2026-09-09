"""视频配音输入与运营封面输出测试。"""

from pathlib import Path
from tempfile import TemporaryDirectory

from backend.app.schemas import Topic
from backend.app.workflows import _cover_title_from_operator, _write_operator_cover
import importlib.util


_MPT_PATH = Path(__file__).resolve().parents[1] / "workspaces/agents/video_editor/skills/moneyprinterturbo-video/mpt_agent.py"
_SPEC = importlib.util.spec_from_file_location("mpt_agent_test", _MPT_PATH)
assert _SPEC and _SPEC.loader
_MPT = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MPT)
_spoken_script = _MPT._spoken_script


def test_spoken_script_removes_shot_directions() -> None:
    value = """【00:00-00:06】
镜头：快切三张素材：GPU机柜/数据中心俯视。
口播：今天我们看一个重要变化。
字幕：重要变化
"""
    spoken = _spoken_script(value)
    assert "今天我们看一个重要变化" in spoken
    assert "镜头" not in spoken
    assert "字幕" not in spoken
    assert "00:00" not in spoken


def test_spoken_script_removes_parenthesized_voice_metadata() -> None:
    spoken = _spoken_script("口播（语气放稳）：这意味着成本可能波动。\n口播（明确标注）：请进一步核对。")
    assert spoken == "这意味着成本可能波动。\n请进一步核对。"


def test_script_duration_normalizer_never_trims_spoken_content(monkeypatch) -> None:
    class Probe:
        stderr = "Duration: 00:02:48.800, start: 0.000000, bitrate: 1 kb/s"

    monkeypatch.setattr(_MPT.subprocess, "run", lambda *args, **kwargs: Probe())
    video = Path("already-rendered.mp4")
    assert _MPT._normalize_duration(video, 110) == video


def test_horizontal_cover_wraps_long_title() -> None:
    topic = Topic.model_construct(title="这是一个非常非常长的横版视频标题用于测试自动换行", sources=[])
    with TemporaryDirectory() as directory:
        path = Path(_write_operator_cover(topic, Path(directory), "horizontal"))
        svg = path.read_text(encoding="utf-8")
    assert 'width="1920" height="1080"' in svg
    assert "非常非常长的横版" in svg


def test_operator_can_choose_short_cover_title() -> None:
    topic = Topic.model_construct(title="一条很长的原始热点标题", sources=[])
    assert _cover_title_from_operator("- 主文案：AI服务器需求，先看交付", topic) == "AI服务器需求"


def test_horizontal_cover_keeps_text_above_wave_and_inside_canvas() -> None:
    topic = Topic.model_construct(title="这是一个横版封面标题", sources=[])
    with TemporaryDirectory() as directory:
        svg = Path(_write_operator_cover(topic, Path(directory), "horizontal")).read_text(encoding="utf-8")
    assert 'viewBox="0 0 1920 1080"' in svg
    assert "M0 820" in svg  # decorative wave is below the title block
    assert 'y="1040"' in svg  # footer remains inside the horizontal canvas

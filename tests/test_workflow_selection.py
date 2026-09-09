"""阶段间选题选择边界测试。"""

from datetime import datetime, timezone
import re

from backend.app.schemas import SourceEvidence, Topic, TopicSeed
from backend.app.workflows import _clean_script_output, _selected_hotspot_report


def _seconds(value: str) -> int:
    minutes, seconds = value.split(":")
    return int(minutes) * 60 + int(seconds)


def _topic(title: str) -> Topic:
    source = SourceEvidence(
        name="Fixture",
        url=f"https://example.com/{title}",
        published_at=datetime.now(timezone.utc),
        claim=f"事实：{title}",
    )
    return Topic(
        title=title,
        heat=90,
        source_hint="Fixture",
        source_url=source.url,
        source_published_at=source.published_at,
        sources=[source, source.model_copy(update={"name": "Fixture 2", "url": f"https://other.example/{title}"})],
        cross_check_note="已交叉验证",
        checked_at=datetime.now(timezone.utc),
        verification_status="verified",
        verification_note="已通过核验",
        angle="测试角度",
        risk="测试风险",
    )


def test_selected_hotspot_report_contains_only_selected_topic() -> None:
    report = _selected_hotspot_report(TopicSeed(domain="test"), _topic("topic-1"))
    assert "topic-1" in report
    assert "topic-2" not in report


def test_clean_script_output_removes_invalid_tail_and_fits_target_duration() -> None:
    content = """**目标时长：110 秒**

【01:36-01:50】
镜头：接口调用界面
口播：先查单位任务成本。
【01:50-02:04】
镜头：回到新闻卡片
口播：这些信号会影响成本环境。
【02:04-02:20】
镜头：老板要点卡片
口播：把成本降下来，把交付跑起来。
【02:20-01:50】（提示：本段不实际存在，脚本已在规定时长内结束）
"""

    cleaned = _clean_script_output(content, 110)

    assert "本段不实际存在" not in cleaned
    assert "02:20-01:50" not in cleaned
    assert "01:50-02:04" not in cleaned
    assert "01:36-01:50" not in cleaned
    ranges = re.findall(r"[【\[]([0-9]{1,2}:[0-9]{2})-([0-9]{1,2}:[0-9]{2})[】\]]", cleaned)
    assert ranges
    assert all(_seconds(end) <= 110 and _seconds(end) > _seconds(start) for start, end in ranges)
    assert _seconds(ranges[-1][1]) == 110


def test_clean_script_output_drops_only_line_with_reversed_range() -> None:
    content = """【00:00-00:08】
口播：开场。
【00:20-00:10】
口播：这段时间轴无效。
【00:08-01:00】
口播：收束。
"""

    cleaned = _clean_script_output(content, 60)

    assert "00:20-00:10" not in cleaned
    assert "这段时间轴无效" not in cleaned
    assert "0:00-0:08" in cleaned
    assert "0:08-1:00" in cleaned

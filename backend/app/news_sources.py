"""新闻 Skill、RSS 和本地 fixture 的统一来源适配。"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse
from xml.etree import ElementTree

import httpx

from backend.app.config import ROOT_DIR


# 新闻来源模块负责 Skill、RSS 回退和本地 fixture 的读取。
# 通过参数注入配置与日期解析器，避免与工作流编排模块形成循环依赖。
# 未配置自定义来源时使用的默认 RSS 列表。
DEFAULT_RSS_FEEDS = (
    ("BBC", "https://feeds.bbci.co.uk/news/rss.xml"),
    ("BBC 中文", "https://feeds.bbci.co.uk/zhongwen/simp/rss.xml"),
)


def configured_rss_feeds(configured_value: str | None) -> tuple[tuple[str, str], ...]:
    """函数“configured_rss_feeds”：解析环境变量中配置的 RSS 地址列表。
参数：
    configured_value: str | None
返回：tuple[tuple[str, str], ...]。"""
    configured = str(configured_value or "").strip()
    if not configured:
        return DEFAULT_RSS_FEEDS
    feeds: list[tuple[str, str]] = []
    for entry in configured.split(","):
        name, separator, url = entry.partition("|")
        if not separator:
            url = name
            name = urlparse(url).netloc or "RSS"
        if url.strip().startswith(("http://", "https://")):
            feeds.append((name.strip() or urlparse(url).netloc or "RSS", url.strip()))
    return tuple(feeds) or DEFAULT_RSS_FEEDS


def load_news_fixture(
    path_value: str | None,
    *,
    parse_datetime: Callable[[object], object],
) -> list[dict]:
    """函数“load_news_fixture”：读取本地新闻 fixture 并规范化字段。
参数：
    path_value: str | None
    parse_datetime: Callable[[object], object]
返回：list[dict]。"""
    path = Path(path_value).expanduser() if path_value else ROOT_DIR / "tests" / "fixtures" / "hotspots.json"
    if not path.is_absolute():
        path = ROOT_DIR / path
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"热点 fixture 不可用：{path}（{exc}）") from exc
    if not isinstance(payload, list):
        raise RuntimeError(f"热点 fixture 必须是新闻列表：{path}")
    normalized: list[dict] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        copy = dict(item, channel="local-fixture")
        published = parse_datetime(copy.get("pubdate") or copy.get("published_at") or copy.get("time"))
        if published:
            copy["pubdate"] = int(published.timestamp())
        normalized.append(copy)
    return normalized


async def run_news_skill(
    timeout_seconds: int,
    *,
    fetch_path: Path,
    skill_dir: Path,
    fetch_limit: int,
    parse_datetime: Callable[[object], object],
) -> list[dict]:
    """函数“run_news_skill”：执行新闻聚合 Skill 并返回原始结果。
参数：
    timeout_seconds: int
    fetch_path: Path
    skill_dir: Path
    fetch_limit: int
    parse_datetime: Callable[[object], object]
返回：list[dict]。"""
    command = [
        sys.executable,
        str(fetch_path),
        "--source", "weibo,wallstreetcn,bbc_top,bbc_chinese,reuters",
        "--limit", str(fetch_limit),
        "--no-save",
    ]
    run_options = {
        "cwd": skill_dir,
        "env": os.environ.copy(),
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "check": False,
    }
    if timeout_seconds > 0:
        run_options["timeout"] = timeout_seconds
    try:
        completed = await asyncio.to_thread(subprocess.run, command, **run_options)
    except subprocess.TimeoutExpired as exc:
        timeout_label = f"{timeout_seconds} seconds" if timeout_seconds > 0 else "the configured limit"
        raise RuntimeError(f"news-aggregator-skill fetch timed out after {timeout_label}") from exc
    stdout = completed.stdout or b""
    stderr = completed.stderr or b""
    if completed.returncode != 0:
        detail = stderr.decode("utf-8", errors="replace")[-1200:]
        raise RuntimeError(f"news-aggregator-skill 执行失败：{detail or stdout.decode('utf-8', errors='replace')[-500:]}")
    try:
        data = json.loads(stdout.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("news-aggregator-skill 返回了无效 JSON") from exc
    if not isinstance(data, list):
        raise RuntimeError("news-aggregator-skill 返回格式不是新闻列表")
    normalized: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        normalized_item = dict(item)
        if not normalized_item.get("pubdate"):
            published = normalized_item.get("time") or normalized_item.get("published_at")
            if published:
                parsed = parse_datetime(published)
                if parsed:
                    normalized_item["pubdate"] = int(parsed.timestamp())
        normalized.append(normalized_item)
    return normalized


async def run_builtin_news_aggregator(
    timeout_seconds: int,
    *,
    feeds: tuple[tuple[str, str], ...],
    fetch_limit: int,
    parse_datetime: Callable[[object], object],
) -> list[dict]:
    """在可选新闻 Skill 未安装时，仍通过内置来源保持热点雷达可用。"""
    timeout = None if timeout_seconds <= 0 else timeout_seconds

    async def fetch_feed(client: httpx.AsyncClient, name: str, url: str) -> list[dict]:
        """函数“fetch_feed”：请求一个 RSS 地址并解析其中的条目。
参数：
    client: httpx.AsyncClient
    name: str
    url: str
返回：list[dict]。"""
        response = await client.get(url)
        response.raise_for_status()
        root = ElementTree.fromstring(response.content)
        items: list[dict] = []
        for item in root.findall(".//item")[:fetch_limit]:
            def text(tag: str) -> str:
                """函数“text”：提取 XML 节点文本并去除首尾空白。
参数：
    tag: str
返回：str。"""
                return (item.findtext(tag) or "").strip()
            published = parse_datetime(text("pubDate"))
            link = text("link")
            title = text("title")
            if not title or not link or not published:
                continue
            items.append({
                "title": title, "url": link, "source": name,
                "summary": text("description"),
                "pubdate": int(published.timestamp()),
                "channel": "builtin-rss-fallback",
            })
        return items

    results: list[dict] = []
    errors: list[str] = []
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        responses = await asyncio.gather(
            *(fetch_feed(client, name, url) for name, url in feeds),
            return_exceptions=True,
        )
    for (name, _), response in zip(feeds, responses):
        if isinstance(response, Exception):
            errors.append(f"{name}: {response}")
        else:
            results.extend(response)
    if not results and errors:
        raise RuntimeError("news-aggregator-skill 未安装，内置 RSS 回退也失败：" + "; ".join(errors))
    return results


async def run_news_aggregator(
    timeout_seconds: int | None,
    *,
    source_mode: str,
    fixture_path: str | None,
    fetch_path: Path,
    skill_dir: Path,
    rss_feeds: tuple[tuple[str, str], ...],
    fetch_limit: int,
    parse_datetime: Callable[[object], object],
) -> list[dict]:
    """函数“run_news_aggregator”：按配置选择 Skill、RSS 或 fixture 新闻来源。
参数：
    timeout_seconds: int | None
    source_mode: str
    fixture_path: str | None
    fetch_path: Path
    skill_dir: Path
    rss_feeds: tuple[tuple[str, str], ...]
    fetch_limit: int
    parse_datetime: Callable[[object], object]
返回：list[dict]。"""
    mode = str(source_mode or "live_then_fixture").strip().lower()
    if mode == "fixture":
        return load_news_fixture(fixture_path, parse_datetime=parse_datetime)
    timeout = 30 if timeout_seconds is None else timeout_seconds
    try:
        if not fetch_path.exists():
            return await run_builtin_news_aggregator(timeout, feeds=rss_feeds, fetch_limit=fetch_limit, parse_datetime=parse_datetime)
        return await run_news_skill(timeout, fetch_path=fetch_path, skill_dir=skill_dir, fetch_limit=fetch_limit, parse_datetime=parse_datetime)
    except Exception:
        if mode != "live_then_fixture":
            raise
        return load_news_fixture(fixture_path, parse_datetime=parse_datetime)

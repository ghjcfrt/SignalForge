from __future__ import annotations

import json
import httpx
from xml.etree import ElementTree
from urllib.parse import urlparse
import asyncio
import os
import subprocess
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Awaitable, TypeVar
from uuid import uuid4

from backend.app.agents import AGENT_BY_ID
from backend.app.config import WORKSPACE_DIR, Settings, get_settings
from backend.app.llm import LlmGateway
from backend.app.schemas import (
    AgentOutput,
    GenerateScriptRequest,
    Topic,
    TopicSeed,
    WorkflowRun,
    StockAnalysisRequest,
    StockAnalysisResult,
    SourceEvidence,
    WorkflowLog,
    ViralAnalysisConfig,
    RunAgentRequest,
)


RUNS: dict[str, WorkflowRun] = {}
WORKFLOW_STAGES = ["hotspot_monitor", "viral_analyst", "copywriter", "video_editor", "operator"]
STOCK_SKILL_DIR = WORKSPACE_DIR / "agents" / "stock_assistant" / "skills" / "stock-analysis"
STOCK_DATA_SCRIPT = STOCK_SKILL_DIR / "references" / "stock_data_fetcher.py"
STOCK_ANALYSIS_PROMPT = STOCK_SKILL_DIR / "references" / "analysis-prompt-template.md"
STOCK_OUTPUT_TEMPLATE = STOCK_SKILL_DIR / "references" / "output-format-template.md"
NEWS_SKILL_DIR = WORKSPACE_DIR / "agents" / "hotspot_monitor" / "skills" / "news-aggregator-skill"
NEWS_FETCH = NEWS_SKILL_DIR / "scripts" / "fetch_news.py"
SOCIALDATAX_NOTE_SEARCH_PATH = "/socialdatax/api/v1/xhs/note/search"
SOCIALDATAX_VIDEO_TRANSCRIPT_PATH = "/socialdatax/api/v1/xhs/note/transcript"
NEWS_FETCH_LIMIT = 30
NEWS_RSS_FEEDS = (
    ("BBC", "https://feeds.bbci.co.uk/news/rss.xml"),
    ("BBC 中文", "https://feeds.bbci.co.uk/zhongwen/simp/rss.xml"),
)
NEWS_SOURCE_WEIGHTS = {
    "weibo": 1.00,
    "wallstreetcn": 0.95,
    "reuters": 0.92,
    "bbc_top": 0.88,
    "bbc_chinese": 0.88,
}
_T = TypeVar("_T")


def _require_skill(agent_id: str, skill_name: str) -> Path:
    skill_dir = WORKSPACE_DIR / "agents" / agent_id / "skills" / skill_name
    if not skill_dir.exists():
        raise RuntimeError(f"{agent_id} 的 Skill 不存在：{skill_dir}")
    return skill_dir


def _exception_detail(exc: Exception) -> str:
    return str(exc) or type(exc).__name__


async def _await_with_optional_timeout(awaitable: Awaitable[_T], timeout_seconds: int) -> _T:
    if timeout_seconds <= 0:
        return await awaitable
    return await asyncio.wait_for(awaitable, timeout=timeout_seconds)


def _parse_public_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (TypeError, ValueError, OverflowError):
            return None
    else:
        text = str(value or "").strip()
        if not text:
            return None
        if text.casefold() in {"real-time", "realtime", "today", "hot", "updated recently"}:
            return datetime.now().astimezone()
        try:
            parsed = parsedate_to_datetime(text)
        except (TypeError, ValueError, OverflowError):
            try:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                parsed = None
                for format_string in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                    try:
                        parsed = datetime.strptime(text, format_string)
                        break
                    except ValueError:
                        continue
                if parsed is None:
                    return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.now().astimezone().tzinfo or timezone.utc)
    return parsed


def _extract_json_payload(content: str) -> object:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for index, character in enumerate(text):
            if character not in "[{":
                continue
            try:
                payload, _ = decoder.raw_decode(text[index:])
                return payload
            except json.JSONDecodeError:
                continue
    raise ValueError("model response does not contain a JSON object or array")


def _coerce_heat(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return max(0, min(100, int(value)))
    text = str(value or "").strip().casefold()
    qualitative = {
        "极高": 95,
        "very high": 95,
        "高": 85,
        "high": 85,
        "中": 65,
        "medium": 65,
        "低": 40,
        "low": 40,
    }
    if text in qualitative:
        return qualitative[text]
    try:
        return max(0, min(100, int(float(text))))
    except (TypeError, ValueError):
        return 50


def _coerce_count(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def _source_domain(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _source_weight(item: dict) -> float:
    source = str(item.get("source") or item.get("channel") or "").casefold()
    for name, weight in NEWS_SOURCE_WEIGHTS.items():
        if name in source:
            return weight
    return 0.70


def _news_relevance(item: dict, seed: TopicSeed) -> float:
    haystack = f"{item.get('title', '')} {item.get('summary', '')}".casefold()
    terms = [term for term in f"{seed.domain} {seed.brief}".split() if len(term.strip()) > 1]
    matches = sum(1 for term in terms if term.casefold() in haystack)
    return min(1.0, matches / max(1, min(5, len(terms))))


def _rank_news_items(items: list[dict], seed: TopicSeed) -> list[dict]:
    """Rank every fetched item before the model sees it.

    Ranking is only a prioritisation hint. It never turns a single source into
    a verified fact; the later source-domain gate remains authoritative.
    """
    now = datetime.now().timestamp()
    ranked: list[dict] = []
    for index, item in enumerate(items):
        copy = dict(item)
        try:
            published = float(copy.get("pubdate") or 0)
        except (TypeError, ValueError):
            published = 0
        age_days = max(0.0, (now - published) / 86400) if published else 14.0
        recency = max(0.0, 1.0 - age_days / 14.0)
        engagement = _coerce_count(
            copy.get("engagement")
            or copy.get("hot")
            or copy.get("heat")
            or copy.get("read_count")
            or copy.get("view_count")
        )
        engagement_signal = min(1.0, engagement / 1_000_000) if engagement else 0.0
        score = (
            _source_weight(copy) * 45
            + recency * 25
            + _news_relevance(copy, seed) * 20
            + engagement_signal * 10
        )
        copy["rank_score"] = round(score, 3)
        copy["rank_reason"] = {
            "source_weight": _source_weight(copy),
            "recency": round(recency, 3),
            "relevance": round(_news_relevance(copy, seed), 3),
            "engagement": engagement,
        }
        copy["_fetch_order"] = index
        ranked.append(copy)
    ranked.sort(key=lambda value: (-float(value.get("rank_score", 0)), value.get("_fetch_order", 0)))
    return ranked


def _normalize_source_evidence(
    source: object,
    evidence_by_url: dict[str, dict],
) -> SourceEvidence | None:
    if not isinstance(source, dict):
        return None
    url = str(source.get("url") or "").strip()
    evidence = evidence_by_url.get(url)
    if not evidence:
        return None
    published_at = _parse_public_datetime(
        source.get("published_at")
        or source.get("time")
        or evidence.get("pubdate")
        or evidence.get("time")
    )
    name = str(source.get("name") or source.get("source") or evidence.get("source") or "").strip()
    claim = str(
        source.get("claim")
        or source.get("summary")
        or evidence.get("summary")
        or evidence.get("title")
        or ""
    ).strip()
    if not published_at or not name or not claim:
        return None
    return SourceEvidence(name=name, url=url, published_at=published_at, claim=claim)


def _normalize_model_topics(content: str, raw_items: list[dict]) -> list[Topic]:
    payload = _extract_json_payload(content)
    if isinstance(payload, dict):
        payload = payload.get("topics", [])
    if not isinstance(payload, list):
        return []

    evidence_by_url = {
        str(item.get("url")).strip(): item
        for item in raw_items
        if str(item.get("url") or "").strip().startswith(("http://", "https://"))
    }
    topics: list[Topic] = []
    for item in payload[:20]:
        if not isinstance(item, dict):
            continue
        raw_sources = item.get("sources")
        if not isinstance(raw_sources, list):
            continue
        sources = [
            normalized
            for raw_source in raw_sources
            if (normalized := _normalize_source_evidence(raw_source, evidence_by_url))
        ]
        title = str(item.get("title") or "").strip()
        if not title or not sources:
            continue
        domains = {_source_domain(source.url) for source in sources if _source_domain(source.url)}
        is_verified = len(sources) >= 2 and len(domains) >= 2
        status = "verified" if is_verified else "unverified"
        checked_at = _parse_public_datetime(item.get("checked_at")) or datetime.now().astimezone()
        source_names = "、".join(dict.fromkeys(source.name for source in sources))
        try:
            topics.append(
                Topic.model_validate(
                    {
                        "title": title,
                        "heat": _coerce_heat(item.get("heat")),
                        "source_hint": str(item.get("source_hint") or source_names).strip(),
                        "source_url": sources[0].url,
                        "source_published_at": sources[0].published_at,
                        "sources": [source.model_dump() for source in sources],
                        "cross_check_note": str(
                            item.get("cross_check_note") or f"已引用 {len(sources)} 个公开来源。"
                        ).strip(),
                        "checked_at": checked_at,
                        "verification_status": status,
                        "verification_note": str(
                            item.get("verification_note")
                            or ("已通过不同域名来源交叉验证。" if is_verified else "尚未完成独立来源交叉验证。")
                        ).strip(),
                        "angle": str(
                            item.get("angle") or f"围绕“{title}”解释事件本身及其影响，避免超出来源内容。"
                        ).strip(),
                        "risk": str(
                            item.get("risk") or "发布前仍需复核原文，不要把未核验信息当作事实。"
                        ).strip(),
                    }
                )
            )
        except Exception:
            continue
    return _validate_topics(topics)


def _evidence_only_topics(raw_items: list[dict]) -> list[Topic]:
    topics: list[Topic] = []
    seen_urls: set[str] = set()
    for item in raw_items:
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        source_name = str(item.get("source") or "公开来源").strip()
        published_at = _parse_public_datetime(item.get("pubdate") or item.get("time"))
        if not title or not url or not published_at or url in seen_urls:
            continue
        seen_urls.add(url)
        evidence = SourceEvidence(
            name=source_name,
            url=url,
            published_at=published_at,
            claim=str(item.get("summary") or title).strip(),
        )
        topics.append(
            Topic(
                title=title,
                heat=_coerce_heat(item.get("heat")),
                source_hint=f"{source_name}：{title}",
                source_url=url,
                source_published_at=published_at,
                sources=[evidence],
                cross_check_note="仅引用一条公开来源，尚未完成独立来源交叉验证。",
                checked_at=datetime.now().astimezone(),
                verification_status="unverified",
                verification_note="模型未返回可用结构；此候选仅来自公开来源原始条目。",
                angle=f"围绕“{title}”梳理公开信息，避免超出来源内容。",
                risk="单一来源，发布前必须复核原文，不要把未核验信息当作事实。",
            )
        )
        # Continue traversing the complete source result. The limit is applied
        # after validation so an early single-source item cannot hide a later
        # independently corroborated candidate.
    topics = topics[:20]
    return _validate_topics(topics)


def _validate_topics(topics: list[Topic]) -> list[Topic]:
    """Validate all candidates before selecting one for downstream work.

    The model may suggest a verification flag, but it is not trusted. Every
    candidate is checked locally against its cited URLs, and only independent
    domains can pass the gate. Sorting happens after the complete pass so the
    first valid candidate cannot short-circuit validation of the rest.
    """
    merged: dict[str, Topic] = {}
    for topic in topics:
        key = " ".join(topic.title.casefold().split())
        previous = merged.get(key)
        if previous is None:
            merged[key] = topic
            continue
        known_urls = {source.url for source in previous.sources}
        previous.sources.extend(source for source in topic.sources if source.url not in known_urls)
        previous.heat = max(previous.heat, topic.heat)
        if not previous.angle.strip() and topic.angle.strip():
            previous.angle = topic.angle
        if not previous.risk.strip() and topic.risk.strip():
            previous.risk = topic.risk

    validated: list[Topic] = []
    for topic in merged.values():
        domains = {_source_domain(source.url) for source in topic.sources if _source_domain(source.url)}
        independent = len(topic.sources) >= 2 and len(domains) >= 2
        topic.verification_status = "verified" if independent else "unverified"
        topic.checked_at = topic.checked_at or _now()
        if independent:
            topic.cross_check_note = f"已完成全量候选核验：引用 {len(topic.sources)} 个来源，覆盖 {len(domains)} 个独立域名。"
            topic.verification_note = "已通过不同域名来源交叉验证；仍需人工复核原文。"
        else:
            topic.cross_check_note = f"已完成全量候选核验：当前仅有 {len(domains)} 个独立域名来源。"
            topic.verification_note = "来源不足或域名不独立，不得作为已核实事实发布。"
        validated.append(topic)
    return sorted(validated, key=lambda topic: (-topic.heat, topic.title))


async def _run_news_aggregator(timeout_seconds: int | None = None) -> list[dict]:
    if timeout_seconds is None:
        timeout_seconds = get_settings().news_fetch_timeout_seconds
    if not NEWS_FETCH.exists():
        return await _run_builtin_news_aggregator(timeout_seconds)
    command = [
        sys.executable,
        str(NEWS_FETCH),
        "--source",
        "weibo,wallstreetcn,bbc_top,bbc_chinese,reuters",
        "--limit",
        str(NEWS_FETCH_LIMIT),
        "--no-save",
    ]
    run_options = {
        "cwd": NEWS_SKILL_DIR,
        "env": os.environ.copy(),
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "check": False,
    }
    if timeout_seconds > 0:
        run_options["timeout"] = timeout_seconds
    try:
        # Windows selector event loops do not implement asyncio subprocesses.
        # Run the blocking process in a worker so both loop policies work.
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
        normalized_item = dict(item)
        if not normalized_item.get("pubdate"):
            published = normalized_item.get("time") or normalized_item.get("published_at")
            if published:
                try:
                    if isinstance(published, (int, float)):
                        normalized_item["pubdate"] = int(published)
                    else:
                        parsed = _parse_public_datetime(published)
                        if parsed:
                            normalized_item["pubdate"] = int(parsed.timestamp())
                except (TypeError, ValueError, OverflowError):
                    pass
        normalized.append(normalized_item)
    return normalized


async def _run_builtin_news_aggregator(timeout_seconds: int) -> list[dict]:
    """Keep the radar usable when the optional news skill is not installed."""
    timeout = None if timeout_seconds <= 0 else timeout_seconds

    async def fetch_feed(client: httpx.AsyncClient, name: str, url: str) -> list[dict]:
        response = await client.get(url)
        response.raise_for_status()
        root = ElementTree.fromstring(response.content)
        items: list[dict] = []
        for item in root.findall(".//item")[:NEWS_FETCH_LIMIT]:
            def text(tag: str) -> str:
                return (item.findtext(tag) or "").strip()

            published = _parse_public_datetime(text("pubDate"))
            link = text("link")
            title = text("title")
            if not title or not link or not published:
                continue
            items.append(
                {
                    "title": title,
                    "url": link,
                    "source": name,
                    "summary": text("description"),
                    "pubdate": int(published.timestamp()),
                    "channel": "builtin-rss-fallback",
                }
            )
        return items

    results: list[dict] = []
    errors: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            responses = await asyncio.gather(
                *(fetch_feed(client, name, url) for name, url in NEWS_RSS_FEEDS),
                return_exceptions=True,
            )
    except httpx.HTTPError as exc:
        raise RuntimeError(f"内置 RSS 热点回退网络错误：{exc}") from exc
    for (name, _), response in zip(NEWS_RSS_FEEDS, responses):
        if isinstance(response, Exception):
            errors.append(f"{name}: {response}")
        else:
            results.extend(response)
    if not results and errors:
        raise RuntimeError("news-aggregator-skill 未安装，内置 RSS 回退也失败：" + "; ".join(errors))
    return results


def _socialdatax_error(response: httpx.Response, payload: object) -> str:
    if isinstance(payload, dict):
        message = str(payload.get("message") or "").strip()
        code = payload.get("code")
        if message and code is not None:
            return f"{message}（code {code}）"
        if message:
            return message
    return f"HTTP {response.status_code}"


def _socialdatax_payload_failed(payload: object) -> bool:
    if not isinstance(payload, dict) or "code" not in payload:
        return False
    code = payload.get("code")
    if code in (0, 200, "0", "200", "success", "SUCCESS"):
        return False
    return payload.get("success") is not True


def _normalize_socialdatax_notes(payload: object) -> list[dict]:
    if not isinstance(payload, dict):
        raise RuntimeError("SocialDataX 返回格式不是笔记列表")
    raw_items = payload.get("items") or payload.get("data")
    if isinstance(raw_items, dict):
        raw_items = raw_items.get("items") or raw_items.get("list") or raw_items.get("notes")
    if not isinstance(raw_items, list):
        raise RuntimeError("SocialDataX 返回格式不是笔记列表")

    notes: list[dict] = []
    for rank, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        note_url = str(item.get("note_url") or item.get("url") or item.get("link") or "").strip()
        if not title or not note_url.startswith(("http://", "https://")):
            continue
        published_at = _parse_public_datetime(
            item.get("publish_time") or item.get("published_at") or item.get("time")
        )
        if not published_at:
            continue
        author = item.get("author") if isinstance(item.get("author"), dict) else {}
        content = str(
            item.get("transcript")
            or item.get("speech_text")
            or item.get("content")
            or item.get("description")
            or ""
        ).strip()
        note_type = str(item.get("note_type") or item.get("type") or "").strip().casefold()
        notes.append(
            {
                "title": title,
                "summary": str(item.get("summary") or "").strip(),
                "note_url": note_url,
                "note_type": note_type,
                "like_count": _coerce_count(item.get("like_count")),
                "collect_count": _coerce_count(item.get("collect_count")),
                "comment_count": _coerce_count(item.get("comment_count")),
                "share_count": _coerce_count(item.get("share_count")),
                "publish_time": published_at.isoformat(),
                "author": str(author.get("name") or "").strip(),
                "content": content,
                "rank": rank,
            }
        )
    return notes


async def _run_socialdatax_note_search(
    keyword: str,
    settings: Settings,
    *,
    sort_type: str = "like_count_descending",
) -> list[dict]:
    """Fetch high-engagement XHS samples for the viral-analysis stage only."""
    api_key = (settings.socialdatax_api_key or "").strip()
    if not api_key:
        return []
    request = {
        "keyword": keyword.strip(),
        "sort_type": sort_type,
        "note_type": "all",
        "publish_time_range": "half_year",
        "page_token": "",
    }
    timeout = None if settings.socialdatax_timeout_seconds <= 0 else settings.socialdatax_timeout_seconds
    base_url = settings.socialdatax_base_url.strip().rstrip("/") or "https://mcp.socialdatax.com"
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
        "X-API-Key": api_key,
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            follow_redirects=True,
        ) as client:
            response = await client.post(SOCIALDATAX_NOTE_SEARCH_PATH, headers=headers, json=request)
    except httpx.TimeoutException as exc:
        raise RuntimeError("SocialDataX 笔记搜索超时") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"SocialDataX 笔记搜索网络错误：{exc}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"SocialDataX 返回了无效 JSON（HTTP {response.status_code}）") from exc
    if response.status_code >= 400 or _socialdatax_payload_failed(payload):
        raise RuntimeError(f"SocialDataX 笔记搜索失败：{_socialdatax_error(response, payload)}")
    return _normalize_socialdatax_notes(payload)


async def _run_socialdatax_transcript(note_url: str, settings: Settings) -> str:
    """Try the paid video-to-speech step for a video sample.

    Transcript extraction is best-effort: an unavailable transcript must not
    discard otherwise valid ranking samples or stop the whole workflow.
    """
    api_key = (settings.socialdatax_api_key or "").strip()
    timeout = None if settings.socialdatax_timeout_seconds <= 0 else settings.socialdatax_timeout_seconds
    base_url = settings.socialdatax_base_url.strip().rstrip("/") or "https://mcp.socialdatax.com"
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
        "X-API-Key": api_key,
    }
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=timeout, follow_redirects=True) as client:
            response = await client.post(
                SOCIALDATAX_VIDEO_TRANSCRIPT_PATH,
                headers=headers,
                json={"url": note_url, "note_url": note_url},
            )
            payload = response.json()
    except (httpx.HTTPError, ValueError, asyncio.TimeoutError) as exc:
        raise RuntimeError(f"视频口播提取失败：{exc}") from exc
    if response.status_code >= 400 or _socialdatax_payload_failed(payload):
        raise RuntimeError(f"视频口播提取失败：{_socialdatax_error(response, payload)}")
    if isinstance(payload, dict):
        value = payload.get("transcript") or payload.get("speech_text") or payload.get("content")
        if isinstance(value, str) and value.strip():
            return value.strip()
        data = payload.get("data")
        if isinstance(data, dict):
            value = data.get("transcript") or data.get("speech_text") or data.get("content")
            if isinstance(value, str) and value.strip():
                return value.strip()
    raise RuntimeError("视频口播提取返回为空")


async def _enrich_socialdatax_notes(notes: list[dict], settings: Settings) -> tuple[list[dict], int, list[str]]:
    enriched: list[dict] = []
    transcript_count = 0
    errors: list[str] = []
    for note in notes:
        current = dict(note)
        is_video = current.get("note_type", "") in {"video", "视频", "videonote"}
        if is_video and not current.get("content"):
            try:
                current["content"] = await _run_socialdatax_transcript(current["note_url"], settings)
                current["transcript_source"] = "socialdatax-video-transcript"
                transcript_count += 1
            except Exception as exc:
                current["transcript_error"] = str(exc)
                errors.append(f"{current['title']}：{exc}")
        enriched.append(current)
    return enriched, transcript_count, errors


def _socialdatax_context(notes: list[dict], *, label: str = "样本") -> str:
    if not notes:
        return (
            "## SocialDataX 小红书样本\n\n"
            "本次没有可用的 SocialDataX 样本；不要编造点赞、收藏、评论、分享数据，"
            "只能基于选题本身给出待验证的传播假设。"
        )
    lines = [
        f"## SocialDataX 小红书{label}（原始数据）",
        "",
        "以下互动量来自 SocialDataX 搜索结果，仅用于样本比较，不代表平台整体趋势：",
        "",
    ]
    for index, note in enumerate(notes, start=1):
        lines.extend(
            [
                f"{index}. 排名：{note.get('rank', index)}；标题：{note['title']}",
                f"   - 笔记链接：{note['note_url']}",
                f"   - 作者：{note.get('author') or '未提供'}；类型：{note.get('note_type') or '未提供'}；发布时间：{note.get('publish_time') or '未提供'}",
                f"   - 点赞：{note.get('like_count', 0)}；收藏：{note.get('collect_count', 0)}；评论：{note.get('comment_count', 0)}；分享：{note.get('share_count', 0)}",
                f"   - 摘要/口播：{note.get('content') or note.get('summary') or '未提供'}",
                *( [f"   - 口播提取：{note['transcript_source']}"] if note.get("transcript_source") else [] ),
                *( [f"   - 口播提取失败：{note['transcript_error']}"] if note.get("transcript_error") else [] ),
            ]
        )
    return "\n".join(lines)


async def analyze_stocks(request: StockAnalysisRequest, settings: Settings) -> StockAnalysisResult:
    """Run the installed Stock Analysis Skill for finance/stock requests."""
    if not STOCK_DATA_SCRIPT.exists():
        raise FileNotFoundError(f"Stock Analysis Skill data script not found: {STOCK_DATA_SCRIPT}")

    env = os.environ.copy()
    for name, value in {
        "TUSHARE_TOKEN": settings.tushare_token,
        "TAVILY_API_KEY": settings.tavily_api_key,
        "SERPAPI_KEY": settings.serpapi_key,
    }.items():
        if value:
            env[name] = value

    command = [sys.executable, str(STOCK_DATA_SCRIPT), "--stocks", request.stocks, "--days", str(request.days)]
    if request.include_news:
        command.append("--news")
    process_error: str | None = None
    stdout = b""
    stderr = b""
    try:
        completed = await asyncio.wait_for(
            asyncio.to_thread(
                subprocess.run,
                command,
                cwd=STOCK_SKILL_DIR,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            ),
            timeout=120,
        )
        stdout, stderr = completed.stdout or b"", completed.stderr or b""
    except asyncio.TimeoutError:
        process_error = "Stock Analysis Skill data fetch exceeded 120 seconds"

    raw_text = stdout.decode("utf-8", errors="replace")
    if process_error is None and completed.returncode != 0:
        process_error = stderr.decode("utf-8", errors="replace").strip() or raw_text.strip()
    try:
        raw_data = json.loads(raw_text)
    except json.JSONDecodeError:
        raw_data = {}
        process_error = process_error or f"Stock Analysis Skill returned invalid JSON: {raw_text[-500:]}"

    if process_error:
        raw_data = {
            **(raw_data if isinstance(raw_data, dict) else {}),
            "errors": [
                *((raw_data.get("errors") or []) if isinstance(raw_data, dict) else []),
                {"type": "data_fetch", "error": process_error},
            ],
            "total_success": 0,
        }

    fallback = json.dumps(raw_data, ensure_ascii=False, indent=2)
    prompt = STOCK_ANALYSIS_PROMPT.read_text(encoding="utf-8") if STOCK_ANALYSIS_PROMPT.exists() else ""
    template = STOCK_OUTPUT_TEMPLATE.read_text(encoding="utf-8") if STOCK_OUTPUT_TEMPLATE.exists() else ""
    gateway = LlmGateway(settings)
    result = await gateway.complete(
        system=(
            "你是 SignalForge 的股票助手林量。严格依据输入的真实数据和新闻输出中文股票决策看板。"
            "不得编造价格或新闻；缺失数据必须明确标注。必须包含数据来源、分析时间、风险和免责声明。"
            "这不是投资建议。\n\n分析框架：\n" + prompt + "\n\n输出模板：\n" + template
        ),
        user="请分析以下 Stock Analysis Skill 数据：\n" + fallback,
        fallback=(
            (f"# 股票数据暂不可用\n\n{process_error}\n\n请稍后重试。\n\n" if process_error else "")
            + fallback
            + "\n\n> 免责声明：以上分析仅供参考，不构成投资建议。投资有风险，入市需谨慎。"
        ),
    )
    return StockAnalysisResult(
        skill_source="https://github.com/liusai0820/Stock-Analysis-Skill",
        stocks=request.stocks,
        report=result.content,
        raw_data=raw_data,
        data_script=str(STOCK_DATA_SCRIPT),
        news_enabled=request.include_news,
        disclaimer="以上分析仅供参考，不构成投资建议。投资有风险，入市需谨慎。",
    )


def _now() -> datetime:
    return datetime.now().astimezone()


def _write_artifact(run_dir: Path, agent_id: str, filename: str, content: str) -> str:
    agent_dir = run_dir / agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    path = agent_dir / filename
    path.write_text(content, encoding="utf-8")
    return str(path)


def _output(run_dir: Path, agent_id: str, title: str, content: str) -> AgentOutput:
    agent = AGENT_BY_ID[agent_id]
    path = _write_artifact(run_dir, agent_id, f"{agent_id}.md", content)
    return AgentOutput(
        agent_id=agent_id,
        agent_name=agent.name,
        title=title,
        content=content,
        artifact_path=path,
        created_at=_now(),
    )


def _checkpoint(workflow: WorkflowRun) -> None:
    run_dir = Path(workflow.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "run-state.json"
    temporary = run_dir / "run-state.json.tmp"
    temporary.write_text(
        json.dumps(workflow.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def _log(
    workflow: WorkflowRun,
    message: str,
    *,
    stage: str | None = None,
    level: str = "info",
    detail: str | None = None,
) -> None:
    """Persist a human-readable event and a JSONL diagnostic immediately."""
    entry = WorkflowLog(
        timestamp=_now(),
        level=level if level in {"info", "warning", "error"} else "info",
        stage=stage,
        message=message,
        detail=detail,
    )
    workflow.logs.append(entry)
    run_dir = Path(workflow.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    if not workflow.log_file:
        workflow.log_file = str(run_dir / "run.log.jsonl")
    with Path(workflow.log_file).open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(entry.model_dump(mode="json"), ensure_ascii=False) + "\n")
    _checkpoint(workflow)


def _load_persisted_runs() -> None:
    runs_dir = WORKSPACE_DIR / "runs"
    if not runs_dir.exists():
        return
    for state_path in runs_dir.glob("*/run-state.json"):
        try:
            workflow = WorkflowRun.model_validate_json(state_path.read_text(encoding="utf-8"))
            _ensure_workflow_state(workflow)
            if workflow.status == "running":
                if workflow.current_stage in workflow.stage_status:
                    workflow.stage_status[workflow.current_stage] = "failed"
                workflow.status = "failed"
                workflow.resumable = True
                workflow.error = (
                    f"{workflow.current_stage or 'unknown'}: 服务在该阶段中断，已恢复为可继续任务"
                )
                _log(
                    workflow,
                    "检测到服务重启，任务已恢复为可继续状态",
                    stage=workflow.current_stage,
                    level="warning",
                )
            RUNS[workflow.id] = workflow
        except Exception:
            continue


def _ensure_workflow_state(workflow: WorkflowRun) -> None:
    """Backfill fields for checkpoints created before the staged runner."""
    for stage in WORKFLOW_STAGES:
        if stage not in workflow.stage_status:
            workflow.stage_status[stage] = "completed" if any(
                output.agent_id == stage for output in workflow.outputs
            ) else "pending"
    if not workflow.log_file:
        workflow.log_file = str(Path(workflow.run_dir) / "run.log.jsonl")


def _fallback_topics(seed: TopicSeed) -> list[Topic]:
    return [
        Topic(
            title="AI 编程 Agent 从演示走向日常生产",
            heat=92,
            source_hint="公开新闻/RSS：AI Agent 编程 / 一人公司 / 自动化工作流",
            verification_note="仅为本地模板线索，未连接实时来源核验。",
            angle="强调普通创作者也能把 Agent 当员工调度，而不是只看模型发布会。",
            risk="避免夸大自动化能力，明确仍需要老板决策和事实核查。",
        ),
        Topic(
            title="短视频自动成片工具正在重塑内容团队",
            heat=86,
            source_hint="GitHub/社区：MoneyPrinterTurbo、自动字幕、TTS、素材抓取",
            verification_note="仅为本地模板线索，未连接实时来源核验。",
            angle="从脚本、配音、字幕到剪辑方案，解释自动成片链路的真实边界。",
            risk="版权素材、声音授权、平台重复内容审核需要重点提醒。",
        ),
        Topic(
            title="个人知识库 + Skill 让 AI 员工更像专员",
            heat=81,
            source_hint="博客/开源技能库：mattpocock/skills、Qclaw 教程思路",
            verification_note="仅为本地模板线索，未连接实时来源核验。",
            angle="Skill 不是魔法，而是把固定流程和工具说明封装给 Agent。",
            risk="避免把第三方教程说成唯一方案，保留开源项目致谢。",
        ),
    ]


def _fallback_hotspot_report(seed: TopicSeed, topics: list[Topic]) -> str:
    lines = [
        f"# 热点监控报告：{seed.domain}",
        "",
        f"老板方向：{seed.brief}",
        f"目标观众：{seed.audience}",
        "",
    ]
    for index, topic in enumerate(topics, start=1):
        lines.extend(
            [
                f"## {index}. {topic.title}",
                f"- 热度：{topic.heat}/100",
                f"- 线索：{topic.source_hint}",
                f"- 多方来源：{len(topic.sources)} 个",
                f"- 交叉验证：{topic.cross_check_note}",
                f"- 核验状态：{topic.verification_status}（{topic.verification_note}）",
                f"- 推荐角度：{topic.angle}",
                f"- 风险提示：{topic.risk}",
                "",
            ]
        )
    return "\n".join(lines)


def _parse_topics(raw: str, seed: TopicSeed) -> list[Topic]:
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            payload = payload.get("topics", [])
        topics = [Topic.model_validate(item) for item in payload]
    except Exception:
        topics = []
    return topics[:5]


def _verified_topics(topics: list[Topic]) -> list[Topic]:
    validated = _validate_topics(topics)
    return [topic for topic in validated if topic.verification_status == "verified"]


def create_workflow(seed: TopicSeed, viral_analysis: ViralAnalysisConfig | None = None) -> WorkflowRun:
    """Create and persist a queued run without doing any work yet."""
    run_id = uuid4().hex[:12]
    run_dir = WORKSPACE_DIR / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    analysis = viral_analysis or ViralAnalysisConfig()
    workflow = WorkflowRun(
        id=run_id,
        status="queued",
        seed=seed,
        topics=[],
        outputs=[],
        run_dir=str(run_dir),
        created_at=_now(),
        resumable=True,
        stage_status={
            stage: ("completed" if stage == "viral_analyst" and not analysis.enabled else "pending")
            for stage in WORKFLOW_STAGES
        },
        log_file=str(run_dir / "run.log.jsonl"),
        viral_analysis=analysis,
    )
    RUNS[run_id] = workflow
    _log(workflow, "任务已创建并自动保存，等待调度")
    return workflow


def next_workflow_stage(workflow: WorkflowRun) -> str | None:
    if workflow.current_stage in WORKFLOW_STAGES:
        return workflow.current_stage
    active_stages = [
        stage for stage in WORKFLOW_STAGES
        if stage != "viral_analyst" or workflow.viral_analysis.enabled
    ]
    return next(
        (stage for stage in active_stages if workflow.stage_status.get(stage) != "completed"),
        None,
    )


async def scout_topics(seed: TopicSeed, settings: Settings) -> tuple[list[Topic], AgentOutput]:
    run_dir = WORKSPACE_DIR / "runs" / f"radar-{uuid4().hex[:12]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    raw_items: list[dict] = []
    source_status: dict[str, str] = {}
    try:
        news_items = await _run_news_aggregator(settings.news_fetch_timeout_seconds)
        raw_items.extend({**item, "channel": "news-aggregator-skill"} for item in news_items)
        source_status["news-aggregator"] = f"ok:{len(news_items)}"
    except Exception as exc:
        source_status["news-aggregator"] = f"error:{_exception_detail(exc)}"
    if not raw_items:
        detail = "; ".join(f"{name}={status}" for name, status in source_status.items())
        raise RuntimeError(
            "所有热点来源均未返回公开结果，已停止，不使用模型记忆补齐热点。"
            f"来源状态：{detail}"
        )
    cutoff = datetime.now().timestamp() - 14 * 24 * 60 * 60
    recent_items: list[dict] = []
    for item in raw_items:
        try:
            if float(item.get("pubdate") or 0) >= cutoff:
                recent_items.append(item)
        except (TypeError, ValueError):
            continue
    raw_items = _rank_news_items(recent_items, seed)
    if not raw_items:
        raise RuntimeError("热点来源返回结果全部早于最近14天，已停止展示旧热点")
    evidence = json.dumps(raw_items[:NEWS_FETCH_LIMIT], ensure_ascii=False)
    prompt_contract = (
        "Return one JSON object only. heat must be an integer from 0 to 100; "
        "verification_status must be verified or unverified; each sources item must contain "
        "name, url, published_at in ISO-8601 format, and claim. Do not wrap the response in Markdown."
    )
    gateway = LlmGateway(settings)

    try:
        result = await _await_with_optional_timeout(gateway.complete(
        system=(
            prompt_contract +
            "你是热讯工坊的热点监控员赵爽。你只输出 JSON，不输出解释。"
            "字段必须是 topics 数组，每个元素包含 title, heat, source_hint, sources, "
            "cross_check_note, checked_at, verification_status, verification_note, angle, risk。"
            "必须先遍历输入中的全部候选来源，再返回 3-5 个候选；不得找到一个候选后提前停止。"
            "sources 必须引用输入中的真实来源；来源可以来自微博、BBC、Reuters fallback 或华尔街见闻。"
            "不得凭模型记忆补充旧新闻或编造来源；verification_status 只是建议，系统会再次本地核验。"
        ),
        user=(
            f"领域：{seed.domain}\n方向：{seed.brief}\n受众：{seed.audience}\n"
            "请先遍历下面最近14天的全部公开来源结果，按 rank_score 综合时效、来源可靠性、方向相关性和热度，"
            "去重后给出 3-5 个热点候选；每个候选尽量列出支持它的全部独立来源：\n" + evidence
        ),
        fallback=json.dumps({"topics": []}, ensure_ascii=False),
        ), settings.model_timeout_seconds)
    except (asyncio.TimeoutError, RuntimeError):
        result = None
    topics: list[Topic] = []
    if result is not None:
        try:
            topics = _normalize_model_topics(result.content, raw_items)
        except (TypeError, ValueError, json.JSONDecodeError):
            topics = []
    if not topics:
        topics = _evidence_only_topics(raw_items)
    if not topics:
        raise RuntimeError("赵爽没有基于公开实时结果返回有效热点，已拒绝展示模型记忆内容")
    topics = _validate_topics(topics)
    report = _fallback_hotspot_report(seed, topics)
    output = _output(run_dir, "hotspot_monitor", "热点监控报告", report)
    return topics, output


async def generate_script(request: GenerateScriptRequest, settings: Settings) -> AgentOutput:
    run_id = f"script-{uuid4().hex[:8]}"
    run_dir = WORKSPACE_DIR / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    gateway = LlmGateway(settings)
    fallback = f"""# 90-120 秒短视频脚本：{request.topic}

## 开场钩子（0-8 秒）
你有没有发现，最近大家聊 AI 已经不只是在聊模型，而是在聊“一个人能不能开一家公司”。

## 事件经过（8-65 秒）
这次的核心看点是：{request.topic}。它背后的变化不是某个工具突然变强，而是工作流开始被拆成多个 AI 员工：有人盯热点，有人拆爆款，有人写脚本，有人给出剪辑方案，还有人负责运营复盘。

## 关键分析（65-95 秒）
真正有价值的地方，是老板不用把所有事情都交给一个 AI。每个 Agent 只负责一个清晰岗位，拥有自己的工作区和技能，输出也能被追踪和复用。

## 收束观点（95-{request.duration_seconds} 秒）
所以这不是“AI 替你躺赚”，而是把过去团队里的重复劳动，拆成可管理、可检查、可迭代的流程。你仍然要做判断，但生产速度会完全不一样。
"""
    result = await gateway.complete(
        system=(
            "你是热讯工坊的文案助手洛一。请写中文短视频口播脚本，"
            "结构必须包含开场钩子、事件经过、关键分析、收束观点，语气克制但有传播性。"
        ),
        user=(
            f"选题：{request.topic}\n角度：{request.angle}\n"
            f"目标时长：{request.duration_seconds} 秒\n目标受众：{request.audience}"
        ),
        fallback=fallback,
    )
    return _output(run_dir, "copywriter", "短视频脚本", result.content)


def _viral_analysis_fallback(topic: Topic, seed: TopicSeed, *, manual_content: str = "") -> str:
    facts = "\n".join(f"- {source.name}：{source.claim}" for source in topic.sources) or "- 仅使用已核验选题中的事实，不补充来源之外的内容。"
    if manual_content.strip():
        return f"""# 爆款分析：{topic.title}

## 用户手写分析依据
{manual_content.strip()}

## 推荐角度
从普通用户可能受影响的具体利益切入，保持与已核验事实一致。

## 核心观点
说明这件事影响哪些人、影响是什么，以及来源目前能支持到什么程度。

## 标题结构
风险 + 具体对象，不直接公布未经核验的结论。

## 开头策略
前 3 秒先抛出用户可能遇到的影响，再交代事实边界。

## 内容顺序
1. 先说影响\n2. 交代已确认事实\n3. 解释已知原因\n4. 说明普通人怎么办

## 必须包含的事实
{facts}

## 不能出现
- 未核实动机\n- 夸张结论\n- 情绪化定性

## 表达风格
{seed.duration_seconds} 秒口播，面向{seed.audience}，通俗、紧凑。
"""
    return f"""# 爆款分析：{topic.title}

## 推荐角度
从普通用户利益可能受影响的具体场景切入。

## 核心观点
这件事会影响哪些人，以及公开事实目前能证明什么。

## 标题结构
风险 + 具体对象，不直接公布未经核验的结论。

## 开头策略
前 3 秒先抛出用户可能损失的结果，再交代已确认事实。

## 内容顺序
1. 先说影响\n2. 交代已确认事实\n3. 解释事件原因\n4. 说明普通人怎么办

## 必须包含的事实
{facts}

## 不能出现
- 未核实动机\n- 夸张结论\n- 情绪化定性

## 表达风格
{seed.duration_seconds} 秒口播，面向{seed.audience}，通俗、紧凑。
"""


def _ensure_viral_analysis_sections(content: str, topic: Topic, seed: TopicSeed) -> str:
    """Make the analyst contract explicit even when a model omits headings."""
    required = ("推荐角度", "核心观点", "标题结构", "开头策略", "内容顺序", "必须包含的事实", "不能出现", "表达风格")
    missing = [section for section in required if section not in content]
    if not missing:
        return content.strip()
    fallback = _viral_analysis_fallback(topic, seed)
    return content.rstrip() + "\n\n---\n\n" + "\n\n".join(
        section for section in fallback.split("\n\n") if any(f"## {name}" in section for name in missing)
    )


async def run_agent(agent_id: str, request: RunAgentRequest, settings: Settings) -> AgentOutput:
    """Run one employee independently without creating a pipeline checkpoint."""
    if agent_id != request.agent_id:
        raise ValueError("员工 ID 不一致")
    if agent_id not in AGENT_BY_ID:
        raise ValueError(f"未知员工：{agent_id}")
    prompt = request.prompt.strip() or "请根据当前工作台设置执行你的职责，并输出可直接使用的结果。"
    run_dir = WORKSPACE_DIR / "runs" / f"agent-{agent_id}-{uuid4().hex[:8]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    gateway = LlmGateway(settings)
    agent = AGENT_BY_ID[agent_id]
    if agent_id == "hotspot_monitor":
        seed = TopicSeed(
            domain=str(request.settings.get("domain") or "AI 圈"),
            brief=prompt,
            audience=str(request.settings.get("audience") or TopicSeed().audience),
            duration_seconds=int(request.settings.get("duration_seconds") or 110),
        )
        topics, _ = await scout_topics(seed, settings)
        return _output(run_dir, agent_id, "热点监控报告", _fallback_hotspot_report(seed, topics))
    if agent_id == "copywriter":
        result = await generate_script(
            GenerateScriptRequest(
                topic=str(request.settings.get("topic") or prompt),
                angle=str(request.settings.get("angle") or ""),
                duration_seconds=int(request.settings.get("duration_seconds") or 110),
                audience=str(request.settings.get("audience") or TopicSeed().audience),
            ),
            settings,
        )
        return result
    if agent_id == "stock_assistant":
        stock_request = StockAnalysisRequest(
            stocks=str(request.settings.get("stocks") or prompt),
            days=int(request.settings.get("days") or 120),
            include_news=bool(request.settings.get("include_news", True)),
        )
        analysis = await analyze_stocks(stock_request, settings)
        return _output(run_dir, agent_id, "股票助手独立分析", analysis.report)
    if agent_id == "viral_analyst":
        notes: list[dict] = []
        source = str(request.settings.get("source") or "socialdatax")
        manual_content = str(request.settings.get("manual_content") or "").strip()
        if source == "manual":
            fallback = f"""# 爆款分析师独立分析

## 用户手写分析依据
{manual_content or prompt}

## 推荐角度
从具体受众的实际影响切入。

## 核心观点
只围绕用户提供的主题和事实下结论。

## 标题结构
风险 + 具体对象，不直接公布未经核验的结论。

## 开头策略
前 3 秒先抛出用户可能遇到的影响，再交代事实边界。

## 内容顺序
1. 先说影响\n2. 交代已确认事实\n3. 解释已知原因\n4. 说明普通人怎么办

## 必须包含的事实
- 仅使用输入主题和手写依据中明确出现的事实。

## 不能出现
- 未核实动机\n- 夸张结论\n- 情绪化定性

## 表达风格
通俗、紧凑，供文案助手继续成稿。
"""
            return _output(run_dir, agent_id, "爆款分析师独立分析", fallback)
        if source == "socialdatax" and settings.socialdatax_api_key:
            notes = await _run_socialdatax_note_search(prompt, settings)
            notes, _, _ = await _enrich_socialdatax_notes(notes, settings)
        context = _socialdatax_context(notes)
        fallback = f"""# 爆款分析师独立分析

## 推荐角度
从具体受众的实际影响切入：{prompt}

## 核心观点
只围绕用户提供的主题和样本事实下结论，不补充未经核验的动机。

## 标题结构
风险 + 具体对象，不直接公布未经核验的结论。

## 开头策略
前 3 秒先抛出用户可能遇到的影响，再交代已确认事实。

## 内容顺序
1. 先说影响\n2. 交代已确认事实\n3. 解释已知原因\n4. 说明普通人怎么办

## 必须包含的事实
- 仅使用输入主题和样本中明确出现的事实。

## 不能出现
- 未核实动机\n- 夸张结论\n- 情绪化定性

## 表达风格
通俗、紧凑，供文案助手继续成稿。
"""
        result = await gateway.complete(
            system=(
                "你是爆款分析师。只负责定角度、定结构、定规则，严格输出推荐角度、核心观点、标题结构、"
                "开头策略、内容顺序、必须包含的事实、不能出现、表达风格；不要直接写完整成稿。"
            ),
            user=f"主题：{prompt}\n分析来源：{source}\n{context}",
            fallback=fallback,
        )
        return _output(run_dir, agent_id, "爆款分析师独立分析", _ensure_standalone_viral_sections(result.content, fallback))
    fallback = f"# {agent.title}独立执行\n\n任务：{prompt}\n\n请结合你的职责“{agent.role}”给出结构化、可执行结果。"
    result = await gateway.complete(
        system=f"你是热讯工坊员工{agent.name}（{agent.title}）。你的职责是：{agent.role}。输出中文 Markdown。",
        user=prompt,
        fallback=fallback,
    )
    return _output(run_dir, agent_id, f"{agent.title}独立产物", result.content)


def _ensure_standalone_viral_sections(content: str, fallback: str) -> str:
    required = ("推荐角度", "核心观点", "标题结构", "开头策略", "内容顺序", "必须包含的事实", "不能出现", "表达风格")
    if all(section in content for section in required):
        return content.strip()
    return content.rstrip() + "\n\n---\n\n" + fallback


async def run_hot_video_workflow(
    seed: TopicSeed,
    settings: Settings,
    existing: WorkflowRun | None = None,
    stop_after_stage: str | None = None,
    viral_analysis: ViralAnalysisConfig | None = None,
) -> WorkflowRun:
    """Run from the first incomplete checkpoint, optionally stopping after one stage."""
    if stop_after_stage is not None and stop_after_stage not in WORKFLOW_STAGES:
        raise ValueError(f"未知流水线阶段：{stop_after_stage}")

    run_id = existing.id if existing else uuid4().hex[:12]
    run_dir = Path(existing.run_dir) if existing else WORKSPACE_DIR / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    workflow = existing or WorkflowRun(
        id=run_id,
        status="queued",
        seed=seed,
        topics=[],
        outputs=[],
        run_dir=str(run_dir),
        created_at=_now(),
        current_stage=None,
        resumable=True,
        log_file=str(run_dir / "run.log.jsonl"),
        viral_analysis=viral_analysis or ViralAnalysisConfig(),
    )
    _ensure_workflow_state(workflow)
    workflow.seed = seed
    if viral_analysis is not None:
        workflow.viral_analysis = viral_analysis
    if not workflow.viral_analysis.enabled:
        workflow.stage_status["viral_analyst"] = "completed"
    workflow.status = "running"
    workflow.error = None
    workflow.completed_at = None
    workflow.resumable = True
    RUNS[run_id] = workflow
    _checkpoint(workflow)
    _log(workflow, "任务开始执行" if not existing else "从检查点继续执行")
    gateway = LlmGateway(settings)

    def output_for(agent_id: str) -> AgentOutput | None:
        return next((item for item in workflow.outputs if item.agent_id == agent_id), None)

    def save_output(agent_id: str, title: str, content: str) -> AgentOutput:
        current = output_for(agent_id)
        if current:
            return current
        output = _output(run_dir, agent_id, title, content)
        workflow.outputs.append(output)
        _checkpoint(workflow)
        return output

    try:
        start_index = 0
        if workflow.current_stage in WORKFLOW_STAGES:
            start_index = WORKFLOW_STAGES.index(workflow.current_stage)
        else:
            for index, stage in enumerate(WORKFLOW_STAGES):
                if workflow.stage_status.get(stage) != "completed":
                    start_index = index
                    break
            else:
                start_index = len(WORKFLOW_STAGES)

        selected: Topic | None = None
        analyst_content = ""
        script_content = ""
        for stage in WORKFLOW_STAGES[start_index:]:
            if stage == "viral_analyst" and not workflow.viral_analysis.enabled:
                workflow.stage_status[stage] = "completed"
                workflow.current_stage = None
                _log(workflow, "已关闭爆款分析师，跳过该阶段", stage=stage)
                continue
            workflow.current_stage = stage
            workflow.stage_status[stage] = "running"
            _checkpoint(workflow)
            _log(workflow, f"开始执行：{stage}", stage=stage)

            if stage == "hotspot_monitor":
                if not workflow.topics:
                    try:
                        workflow.topics, _ = await scout_topics(seed, settings)
                        workflow.source_status["news-aggregator"] = f"ok:{len(workflow.topics)} candidates"
                    except Exception as exc:
                        workflow.source_status["news-aggregator"] = f"error:{_exception_detail(exc)}"
                        raise
                save_output(
                    "hotspot_monitor",
                    "热点监控报告",
                    _fallback_hotspot_report(seed, workflow.topics),
                )
            elif stage == "viral_analyst":
                verified_topics = _verified_topics(workflow.topics)
                if not verified_topics:
                    raise RuntimeError(
                        "热点候选已完成全量核验，但没有候选通过双来源交叉核验；"
                        f"当前候选数：{len(workflow.topics)}，请检查热点来源后重试。"
                    )
                selected = verified_topics[0]
                analyst_output = output_for("viral_analyst")
                if analyst_output:
                    analyst_content = analyst_output.content
                else:
                    analysis_config = workflow.viral_analysis
                    if analysis_config.source == "manual":
                        if not analysis_config.manual_content.strip():
                            raise RuntimeError("爆款分析已选择手动模式，但没有填写分析依据")
                        workflow.source_status["viral-analysis"] = "manual:user input"
                        analyst_content = _viral_analysis_fallback(
                            selected,
                            seed,
                            manual_content=analysis_config.manual_content,
                        )
                    else:
                        socialdatax_notes: list[dict] = []
                        ranked_notes: list[dict] = []
                        transcript_errors: list[str] = []
                        if settings.socialdatax_api_key and settings.socialdatax_api_key.strip():
                            try:
                                # First obtain the platform's highest-engagement
                                # ranking, then search the selected topic for
                                # comparable samples. Both passes complete
                                # before the analyst is called.
                                ranked_notes = await _run_socialdatax_note_search(
                                    f"{seed.domain} {seed.brief}", settings
                                )
                                socialdatax_notes = await _run_socialdatax_note_search(
                                    selected.title, settings
                                )
                                socialdatax_notes, transcript_count, transcript_errors = await _enrich_socialdatax_notes(
                                    socialdatax_notes, settings
                                )
                                ranked_notes, ranked_transcripts, ranked_errors = await _enrich_socialdatax_notes(
                                    ranked_notes[:10], settings
                                )
                                transcript_errors.extend(ranked_errors)
                                transcript_count += ranked_transcripts
                                workflow.source_status["socialdatax-xhs"] = (
                                    f"ok:{len(ranked_notes)} ranked/{len(socialdatax_notes)} samples/"
                                    f"{transcript_count} transcripts"
                                )
                                if transcript_errors:
                                    workflow.source_status["socialdatax-video"] = (
                                        f"warning:{len(transcript_errors)} failed"
                                    )
                            except Exception as exc:
                                workflow.source_status["socialdatax-xhs"] = f"error:{_exception_detail(exc)}"
                                raise
                        else:
                            workflow.source_status["socialdatax-xhs"] = "disabled:no SOCIALDATAX_API_KEY"
                        socialdatax_context = _socialdatax_context(socialdatax_notes)
                        ranking_context = _socialdatax_context(ranked_notes, label="热点排行")
                        analyst_fallback = _viral_analysis_fallback(selected, seed)
                        result = await gateway.complete(
                            system=(
                                "你是爆款分析师星辰。输出中文 Markdown，严格包含：推荐角度、核心观点、标题结构、"
                                "开头策略、内容顺序、必须包含的事实、不能出现、表达风格。"
                                "你的职责是定角度、定结构、定规则，不替文案助手写成稿。"
                                "SocialDataX 数据只是公开样本，互动量只能用于样本比较，不得编造缺失数据或平台总体结论。"
                                "必须从全部输入样本中提取可复用的表达结构，并标明它们是样本观察而非事实。"
                            ),
                            user=(
                                f"请分析这个已核验选题：{selected.model_dump_json()}\n"
                                "先检查热点排行，再检查该选题的爆款样本；输出一份可直接交给文案助手的分析规范。\n"
                                + ranking_context
                                + "\n\n"
                                + socialdatax_context
                            ),
                            fallback=analyst_fallback,
                        )
                        analyst_content = _ensure_viral_analysis_sections(result.content, selected, seed)
                    save_output("viral_analyst", "爆款分析", analyst_content)
            elif stage == "copywriter":
                selected = (_verified_topics(workflow.topics) or [None])[0]
                if selected is None:
                    raise RuntimeError("找不到已核验选题，无法生成脚本")
                analyst_content = output_for("viral_analyst").content if output_for("viral_analyst") else analyst_content
                script_output = output_for("copywriter")
                script_fallback = f"""# 口播脚本：{selected.title}

## 开场钩子（0-8 秒）
如果你把 AI 当成一个聊天框，它只能帮你省一点时间；但如果你把它拆成一家公司，事情就变了。

## 事件经过（8-60 秒）
今天这个热点是：{selected.title}。它之所以值得关注，是因为内容生产已经开始被拆成岗位：赵爽负责找热点，星辰负责判断能不能爆，洛一写脚本，小李给出剪辑方案，尤道理负责发布和复盘。

## 关键分析（60-95 秒）
这里最重要的不是名字，而是边界。每个 AI 员工有自己的任务、产物和工作区，老板只负责决策和验收。

## 总结（95-{seed.duration_seconds} 秒）
一人公司不是让 AI 替你思考，而是让你的判断力有一条生产线。
"""
                if script_output:
                    script_content = script_output.content
                else:
                    result = await gateway.complete(
                        system="你是文案助手洛一。写中文短视频脚本，含时间段、口播、镜头提示。",
                        user=f"请基于爆款分析写 {seed.duration_seconds} 秒脚本：\n{analyst_content}",
                        fallback=script_fallback,
                    )
                    script_content = result.content
                    save_output("copywriter", "短视频脚本", script_content)
            elif stage == "video_editor":
                selected = (_verified_topics(workflow.topics) or [None])[0]
                if selected is None:
                    raise RuntimeError("找不到已核验选题，无法生成剪辑方案")
                script_content = output_for("copywriter").content if output_for("copywriter") else script_content
                if not output_for("video_editor"):
                    edit_fallback = f"""# 自动剪辑方案：{selected.title}

## 工具
- 首选：MoneyPrinterTurbo 官方 Agent Skill
- 上游出处：https://github.com/harry0703/MoneyPrinterTurbo

## 画幅与素材
- 竖版 1080x1920；屏幕录制热讯工坊看板，搭配 AI 工具界面和脚本文档 B-roll。
- 字幕每 12-16 字断行，关键字高亮“AI员工”“工作区”“老板决策”。

## 配音与导出
- 语速：每分钟 260-300 字；情绪：冷静、清晰、带一点兴奋。
- `uv run --no-project --python 3.11 python mpt_agent.py --subject "{selected.title}"`
"""
                    result = await gateway.complete(
                        system="你是视频剪辑员小李。输出可执行剪辑方案，包含工具出处、画幅、素材、字幕、配音和导出命令。",
                        user=f"请根据脚本生成剪辑计划：\n{script_content}",
                        fallback=edit_fallback,
                    )
                    save_output("video_editor", "自动剪辑方案", result.content)
            elif stage == "operator":
                selected = (_verified_topics(workflow.topics) or [None])[0]
                if selected is None:
                    raise RuntimeError("找不到已核验选题，无法生成运营方案")
                script_content = output_for("copywriter").content if output_for("copywriter") else script_content
                if not output_for("operator"):
                    op_fallback = f"""# 运营发布方案：{selected.title}

- 标题 1：{selected.title}
- 标题 2：从数据看，{selected.title}意味着什么？
- 封面文案：{selected.title}
- 发布时间：工作日 12:00 或 20:30，先测试 B 站和视频号
- 评论引导：你怎么看这条热点对行业和普通用户的影响？
- 复盘指标：完播率、3 秒留存、收藏率、评论问题密度
- 来源提示：{selected.source_hint}
- 发布前复核：{selected.risk}
"""
                    result = await gateway.complete(
                        system="你是运营大师尤道理。输出发布标题、封面文案、发布时间、评论引导和复盘指标。",
                        user=f"请为这个脚本生成运营方案：\n{script_content}",
                        fallback=op_fallback,
                    )
                    save_output("operator", "运营发布方案", result.content)

            workflow.stage_status[stage] = "completed"
            workflow.current_stage = None
            workflow.error = None
            _log(workflow, f"阶段完成，产物已保存：{stage}", stage=stage)
            if stop_after_stage == stage:
                next_stage = next(
                    (candidate for candidate in WORKFLOW_STAGES if workflow.stage_status[candidate] != "completed"),
                    None,
                )
                if next_stage:
                    workflow.current_stage = next_stage
                    workflow.status = "paused"
                    workflow.completed_at = None
                    _log(workflow, "已按手动模式暂停，可审核产物后执行下一步", stage=next_stage)
                    _checkpoint(workflow)
                    return workflow

        summary = {
            "id": workflow.id,
            "seed": seed.model_dump(),
            "topics": [topic.model_dump(mode="json") for topic in workflow.topics],
            "outputs": [output.model_dump(mode="json") for output in workflow.outputs],
            "stage_status": workflow.stage_status,
        }
        _write_artifact(run_dir, "boss", "run-summary.json", json.dumps(summary, ensure_ascii=False, indent=2))
        workflow.status = "completed"
        workflow.current_stage = None
        workflow.resumable = False
        workflow.completed_at = _now()
        _log(workflow, "全部阶段完成，已生成老板摘要")
    except Exception as exc:
        stage = workflow.current_stage or "unknown"
        if stage in workflow.stage_status:
            workflow.stage_status[stage] = "failed"
        workflow.status = "failed"
        detail = _exception_detail(exc)
        workflow.error = f"{stage}: {detail}"
        workflow.resumable = True
        workflow.completed_at = _now()
        _log(workflow, "阶段执行失败，可从当前检查点继续", stage=stage, level="error", detail=detail)
    _checkpoint(workflow)
    RUNS[run_id] = workflow
    return workflow


def list_runs() -> list[WorkflowRun]:
    return sorted(RUNS.values(), key=lambda run: run.created_at, reverse=True)


def get_run(run_id: str) -> WorkflowRun | None:
    return RUNS.get(run_id)

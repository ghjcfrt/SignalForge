from __future__ import annotations

import json
import httpx
from xml.etree import ElementTree
from urllib.parse import urlparse
import asyncio
import os
import subprocess
import sys
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Awaitable, TypeVar
from uuid import uuid4

from backend.app.agents import AGENT_BY_ID
from backend.app.config import WORKSPACE_DIR, Settings, get_output_directory_settings, get_settings
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
from backend.app.video_tools import MoneyPrinterTurboRequest, run_moneyprinterturbo


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


def _evidence_domain(source: SourceEvidence) -> str:
    """Return the publisher domain, including known RSS/search fallbacks.

    Reuters items can arrive through Google News RSS, so the transport host
    (news.google.com) is not the publishing domain. Using the declared source
    name here preserves the independent-domain gate without weakening it.
    """
    name = source.name.casefold()
    aliases = (
        (("reuters",), "reuters.com"),
        (("bbc",), "bbc.co.uk"),
        (("华尔街", "wallstreet"), "wallstreetcn.com"),
        (("微博", "weibo"), "weibo.com"),
    )
    for needles, domain in aliases:
        if any(needle in name for needle in needles):
            return domain
    return _source_domain(source.url)


def _source_weight(item: dict) -> float:
    source = str(item.get("source") or item.get("channel") or "").casefold()
    for name, weight in NEWS_SOURCE_WEIGHTS.items():
        if name in source:
            return weight
    return 0.70


def _news_relevance(item: dict, seed: TopicSeed) -> float:
    """Estimate whether a fetched item is about the requested direction.

    The old whitespace split treated a Chinese brief as one giant token, so
    unrelated headlines could all reach the evidence-only fallback.  Keep the
    score deliberately conservative: ASCII words are matched as words and
    Chinese text is matched using meaningful 2+ character chunks.
    """
    haystack = f"{item.get('title', '')} {item.get('summary', '')}".casefold()
    seed_text = f"{seed.domain} {seed.brief}".casefold()
    ascii_terms = re.findall(r"[a-z0-9][a-z0-9+#.-]{1,}", seed_text)
    cjk_terms: list[str] = []
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", seed_text):
        cjk_terms.extend(run[index : index + 2] for index in range(len(run) - 1))
    # Very generic words would make an unrelated feed look relevant.
    stopwords = {"近期", "热点", "内容", "生产", "关注", "普通", "一线", "创作者", "创业者"}
    terms = list(dict.fromkeys([term for term in ascii_terms + cjk_terms if term not in stopwords]))
    if not terms:
        return 0.0
    matches = sum(1 for term in terms if term in haystack)
    return min(1.0, matches / max(1, min(5, len(terms))))


def _task_overlap_score(text: str, seed: TopicSeed) -> float:
    """Score overlap with the requested domain, keeping audience boilerplate out."""
    domain_score = _news_relevance({"title": text}, TopicSeed(domain=seed.domain, brief="", audience=""))
    brief_score = _news_relevance({"title": text}, TopicSeed(domain="", brief=seed.brief, audience=""))
    # The explicit domain is the strongest signal; the brief adds context.
    return min(1.0, domain_score * 0.70 + brief_score * 0.30)


def _topic_heat_score(topic: Topic, seed: TopicSeed) -> int:
    """Compute a deterministic 0-100 score from relevance and evidence quality.

    Weights intentionally put task fit first, then independent corroboration.
    A second URL on the same publisher does not count as a second source.
    """
    title_hint_overlap = _task_overlap_score(f"{topic.title} {topic.source_hint}", seed)
    claim_overlap = _task_overlap_score(" ".join(source.claim for source in topic.sources), seed)
    # Claims support the headline but cannot rescue an unrelated title.
    overlap = title_hint_overlap * 0.80 + claim_overlap * 0.20
    if title_hint_overlap < 0.10:
        overlap *= 0.25
    source_count = len(topic.sources)
    domain_count = len({_evidence_domain(source) for source in topic.sources if _evidence_domain(source)})
    corroboration = min(1.0, domain_count / 3) * 0.75 + min(1.0, source_count / 4) * 0.25
    timestamps = [source.published_at.timestamp() for source in topic.sources if source.published_at]
    if timestamps:
        age_days = max(0.0, (datetime.now().timestamp() - max(timestamps)) / 86400)
        recency = max(0.0, 1.0 - age_days / 14.0)
    else:
        recency = 0.0
    # Source reliability is a small tie-breaker; it must not overpower fit or
    # independent corroboration.
    reliability = 0.0
    for source in topic.sources:
        name = source.name.casefold()
        reliability = max(
            reliability,
            1.0 if any(token in name for token in ("reuters", "bbc", "华尔街", "wallstreet")) else 0.6,
        )
    return max(0, min(100, round(overlap * 55 + corroboration * 30 + recency * 10 + reliability * 5)))


_DIAGNOSTIC_TOPIC_PATTERNS = (
    r"缺乏可用来源",
    r"不构成.{0,12}(热点|候选)",
    r"本批次",
    r"仅检测到",
    r"未出现",
    r"无法从.{0,20}(确认|判断)",
    r"缺少.{0,8}(核验|证据|来源)",
    r"来源不足",
    r"模型未返回",
    r"需补充",
    r"提示[:：]",
    r"作为泛.{0,8}(舆情|叙事)",
    r"报错",
    r"(?:执行|请求|抓取|来源|模型|搜索|接口).{0,8}(?:失败|错误|超时)",
    r"(?:失败|错误|超时).{0,8}(?:执行|请求|抓取|来源|模型|搜索|接口)",
    r"输入中.{0,8}(为\s*0|为零)",
    r"\b(?:error|failed|failure|exception|timeout)\b",
)


def _is_diagnostic_topic(topic: Topic) -> bool:
    """Reject model prose that reports a collection/validation problem.

    Such prose used to be wrapped in a valid ``Topic`` object and displayed as
    a headline.  Check the title and supporting hint because models often put
    the diagnostic sentence in one of those fields.
    """
    text = " ".join((topic.title, topic.source_hint, topic.angle)).casefold()
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in _DIAGNOSTIC_TOPIC_PATTERNS)


def _clean_topic_title(title: str) -> str:
    # ``（候选）`` is a model label, not part of the actual headline.
    return re.sub(r"^\s*[（(]\s*候选\s*[）)]\s*", "", title).strip()


def _topic_match_tokens(text: str) -> set[str]:
    aliases = {
        "戴尔": "dell", "服务器": "server", "算力": "compute", "英伟达": "nvidia",
        "黄仁勋": "jensen", "开放人工智能": "openai", "人工智能": "ai", "代理": "agent",
    }
    normalized = text.casefold()
    for source, target in aliases.items():
        normalized = normalized.replace(source, f" {target} ")
    ascii_tokens = set(re.findall(r"[a-z0-9][a-z0-9+#.-]{2,}", normalized))
    cjk_tokens: set[str] = set()
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", normalized):
        cjk_tokens.update(run[index : index + 2] for index in range(len(run) - 1))
    return (ascii_tokens | cjk_tokens) - {
        "AI", "人工", "智能", "需求", "市场", "股价", "行业", "公司", "模型", "产品", "新闻", "热点"
    }


def _source_supports_topic(topic: Topic, item: dict) -> bool:
    topic_tokens = _topic_match_tokens(f"{topic.title} {topic.source_hint}")
    item_tokens = _topic_match_tokens(f"{item.get('title', '')} {item.get('summary', '')}")
    overlap = topic_tokens & item_tokens
    strong_ascii = {token for token in overlap if re.fullmatch(r"[a-z0-9+#.-]{4,}", token)}
    # Two shared content terms are enough for translated headlines; a single
    # distinctive long token (e.g. Dell, OpenAI, Astra) is also acceptable.
    return len(overlap) >= 2 or bool(strong_ascii)


def _augment_topic_sources(topics: list[Topic], raw_items: list[dict]) -> None:
    """Attach corroborating fetched items the model omitted from ``sources``."""
    for topic in topics:
        known_urls = {source.url for source in topic.sources}
        for item in raw_items:
            url = str(item.get("url") or "").strip()
            if not url or url in known_urls or not _source_supports_topic(topic, item):
                continue
            published_at = _parse_public_datetime(item.get("pubdate") or item.get("time"))
            name = str(item.get("source") or "公开来源").strip()
            title = str(item.get("title") or "").strip()
            if not published_at or not name or not title:
                continue
            topic.sources.append(
                SourceEvidence(
                    name=name,
                    url=url,
                    published_at=published_at,
                    claim=str(item.get("summary") or title).strip(),
                )
            )
            known_urls.add(url)


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
            # Domain overlap is the primary filter. Engagement is only a small
            # tie-breaker so a generic hot-search list cannot dominate.
            _task_overlap_score(f"{copy.get('title', '')} {copy.get('summary', '')}", seed) * 70
            + _source_weight(copy) * 15
            + recency * 10
            + engagement_signal * 5
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


def _diversify_news_items(items: list[dict], limit: int = NEWS_FETCH_LIMIT) -> list[dict]:
    """Keep the model evidence window representative across source labels.

    Ranking by engagement alone can fill all 30 slots with Weibo's real-time
    hot list, hiding BBC/Wall Street/Reuters entries that could corroborate an
    event.  Take a small round-robin sample from every source, then fill any
    remaining slots by rank.
    """
    if len(items) <= limit:
        return items
    groups: dict[str, list[dict]] = {}
    for item in items:
        key = str(item.get("source") or item.get("channel") or "unknown")
        groups.setdefault(key, []).append(item)
    selected: list[dict] = []
    # One item per source per round gives every configured source a chance.
    round_index = 0
    while len(selected) < limit:
        progressed = False
        for group in groups.values():
            if round_index < len(group):
                selected.append(group[round_index])
                progressed = True
                if len(selected) >= limit:
                    break
        if not progressed:
            break
        round_index += 1
    return selected


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
        title = _clean_topic_title(str(item.get("title") or ""))
        if not title or not sources:
            continue
        domains = {_evidence_domain(source) for source in sources if _evidence_domain(source)}
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


def _evidence_only_topics(raw_items: list[dict], seed: TopicSeed | None = None) -> list[Topic]:
    topics: list[Topic] = []
    seen_urls: set[str] = set()
    for item in raw_items:
        if seed is not None and _news_relevance(item, seed) <= 0:
            continue
        title = _clean_topic_title(str(item.get("title") or ""))
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
        topic = Topic(
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
        # Do not turn collection diagnostics or clearly off-topic headlines
        # into user-facing candidates when the model fallback is used.
        if _is_diagnostic_topic(topic):
            continue
        topics.append(topic)
        # Continue traversing the complete source result. The limit is applied
        # after validation so an early single-source item cannot hide a later
        # independently corroborated candidate.
    topics = topics[:20]
    return _validate_topics(topics, seed)


def _validate_topics(topics: list[Topic], seed: TopicSeed | None = None) -> list[Topic]:
    """Validate all candidates before selecting one for downstream work.

    The model may suggest a verification flag, but it is not trusted. Every
    candidate is checked locally against its cited URLs, and only independent
    domains can pass the gate. Sorting happens after the complete pass so the
    first valid candidate cannot short-circuit validation of the rest.
    """
    merged: dict[str, Topic] = {}
    for topic in topics:
        topic.title = _clean_topic_title(topic.title)
        if not topic.title or _is_diagnostic_topic(topic):
            continue
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
        domains = {_evidence_domain(source) for source in topic.sources if _evidence_domain(source)}
        independent = len(topic.sources) >= 2 and len(domains) >= 2
        topic.verification_status = "verified" if independent else "unverified"
        topic.checked_at = topic.checked_at or _now()
        if independent:
            topic.cross_check_note = f"已完成全量候选核验：引用 {len(topic.sources)} 个来源，覆盖 {len(domains)} 个独立域名。"
            topic.verification_note = "已通过不同域名来源交叉验证；仍需人工复核原文。"
        else:
            topic.cross_check_note = f"已完成全量候选核验：当前仅有 {len(domains)} 个独立域名来源。"
            topic.verification_note = "来源不足或域名不独立，不得作为已核实事实发布。"
        if seed is not None:
            topic.heat = _topic_heat_score(topic, seed)
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


def _output(run_dir: Path, agent_id: str, title: str, content: str, output_dir: str | None = None) -> AgentOutput:
    agent = AGENT_BY_ID[agent_id]
    if output_dir is None:
        configured = get_output_directory_settings()
        if agent_id == "operator":
            output_dir = configured.operator_output_dir.strip() or None
        elif agent_id == "video_editor":
            output_dir = configured.video_output_dir.strip() or None
    path = _write_artifact(Path(output_dir).expanduser().resolve(), agent_id, f"{agent_id}.md", content) if output_dir else _write_artifact(run_dir, agent_id, f"{agent_id}.md", content)
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
    # Older checkpoints may contain model-generated diagnostics as topics.
    # Re-apply the current boundary when loading them so a service restart (or
    # an already-open UI) cannot keep displaying those pseudo-candidates.
    original_topics = workflow.topics
    workflow.topics = _validate_topics(workflow.topics)
    if len(workflow.topics) != len(original_topics) or any(
        left.model_dump(mode="json") != right.model_dump(mode="json")
        for left, right in zip(workflow.topics, original_topics)
    ):
        _checkpoint(workflow)
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


def _fallback_hotspot_report(
    seed: TopicSeed,
    topics: list[Topic],
    source_inventory: dict[str, int] | None = None,
) -> str:
    lines = [
        f"# 热点监控报告：{seed.domain}",
        "",
        f"老板方向：{seed.brief}",
        f"目标观众：{seed.audience}",
        "",
    ]
    if source_inventory:
        inventory = "、".join(f"{name} {count} 条" for name, count in source_inventory.items())
        lines.extend([f"本轮抓取来源：{inventory}", ""])
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


def reset_workflow_from_stage(workflow: WorkflowRun, stage: str) -> None:
    """Reset a stage and all downstream outputs, retaining upstream work."""
    if stage not in WORKFLOW_STAGES:
        raise ValueError(f"未知流水线阶段：{stage}")
    index = WORKFLOW_STAGES.index(stage)
    for downstream in WORKFLOW_STAGES[index:]:
        workflow.stage_status[downstream] = (
            "completed" if downstream == "viral_analyst" and not workflow.viral_analysis.enabled else "pending"
        )
        workflow.outputs = [output for output in workflow.outputs if output.agent_id != downstream]
    if stage == "hotspot_monitor":
        # A hotspot rerun must fetch fresh candidates; later-stage reruns keep
        # the already selected and verified topic list.
        workflow.topics = []
        workflow.selected_topic_title = None
        workflow.source_status.pop("news-aggregator", None)
    workflow.current_stage = stage
    workflow.status = "paused"
    workflow.error = None
    workflow.completed_at = None
    workflow.resumable = True
    _log(workflow, f"已请求重跑阶段：{stage}（保留上游产物）", stage=stage)
    _checkpoint(workflow)


async def scout_topics(seed: TopicSeed, settings: Settings) -> tuple[list[Topic], AgentOutput]:
    run_dir = WORKSPACE_DIR / "runs" / f"radar-{uuid4().hex[:12]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    raw_items: list[dict] = []
    source_status: dict[str, str] = {}
    try:
        news_items = await _run_news_aggregator(settings.news_fetch_timeout_seconds)
        raw_items.extend({**item, "channel": "news-aggregator-skill"} for item in news_items)
        source_counts: dict[str, int] = {}
        for item in news_items:
            name = str(item.get("source") or "未知来源")
            source_counts[name] = source_counts.get(name, 0) + 1
        source_status["news-aggregator"] = "ok:" + ", ".join(
            f"{name}={count}" for name, count in source_counts.items()
        )
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
    evidence_items = _diversify_news_items(raw_items, NEWS_FETCH_LIMIT)
    evidence = json.dumps(evidence_items, ensure_ascii=False)
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
        topics = _evidence_only_topics(raw_items, seed)
    if not topics:
        raise RuntimeError("赵爽没有基于公开实时结果返回有效热点，已拒绝展示模型记忆内容")
    _augment_topic_sources(topics, raw_items)
    # A topic must be grounded in at least one fetched item relevant to the
    # requested direction.  This blocks model-generated "all sources were
    # unrelated" diagnostics from leaking into the candidate list.
    evidence_by_url = {str(item.get("url") or "").strip(): item for item in raw_items}
    topics = [
        topic
        for topic in _validate_topics(topics, seed)
        if any(_news_relevance(evidence_by_url.get(source.url, {}), seed) > 0 for source in topic.sources)
    ]
    if not topics:
        raise RuntimeError("公开来源中没有与当前方向匹配的热点候选，已停止展示诊断或无关条目")
    source_inventory: dict[str, int] = {}
    for item in raw_items:
        source_name = str(item.get("source") or item.get("channel") or "未知来源")
        source_inventory[source_name] = source_inventory.get(source_name, 0) + 1
    report = _fallback_hotspot_report(seed, topics, source_inventory)
    output = _output(run_dir, "hotspot_monitor", "热点监控报告", report)
    return topics, output


async def generate_script(request: GenerateScriptRequest, settings: Settings) -> AgentOutput:
    run_id = f"script-{uuid4().hex[:8]}"
    run_dir = WORKSPACE_DIR / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    gateway = LlmGateway(settings)
    fact_end = max(12, round(request.duration_seconds * 0.58))
    analysis_end = max(fact_end + 8, round(request.duration_seconds * 0.86))
    fallback = f"""# {request.duration_seconds} 秒短视频脚本：{request.topic}

## 开场钩子（0-8 秒）
你有没有发现，最近大家聊 AI 已经不只是在聊模型，而是在聊“一个人能不能开一家公司”。

## 事件经过（8-{fact_end} 秒）
这次的核心看点是：{request.topic}。它背后的变化不是某个工具突然变强，而是工作流开始被拆成多个 AI 员工：有人盯热点，有人拆爆款，有人写脚本，有人给出剪辑方案，还有人负责运营复盘。

## 关键分析（{fact_end}-{analysis_end} 秒，事实与推测分开）
真正有价值的地方，是老板不用把所有事情都交给一个 AI。每个 Agent 只负责一个清晰岗位，拥有自己的工作区和技能，输出也能被追踪和复用。

## 收束观点（{analysis_end}-{request.duration_seconds} 秒）
所以这不是“AI 替你躺赚”，而是把过去团队里的重复劳动，拆成可管理、可检查、可迭代的流程。你仍然要做判断，但生产速度会完全不一样。
"""
    result = await gateway.complete(
        system=(
            "你是热讯工坊的文案助手洛一。请写中文短视频口播脚本，"
            "结构必须包含开场钩子、事件经过、关键分析、收束观点，语气克制但有传播性。"
            f"严格控制为约 {request.duration_seconds} 秒，时间轴最后一段必须结束在 {request.duration_seconds} 秒；"
            "只输出成稿，不要输出‘如你愿意我可以’等助手元话术。"
        ),
        user=(
            f"选题：{request.topic}\n角度：{request.angle}\n"
            f"目标时长：{request.duration_seconds} 秒\n目标受众：{request.audience}"
        ),
        fallback=fallback,
    )
    return _output(run_dir, "copywriter", "短视频脚本", _clean_script_output(result.content, request.duration_seconds))


def _clean_script_output(content: str, duration_seconds: int) -> str:
    """Remove assistant meta-talk and make the requested duration explicit."""
    text = content.strip()
    # Model responses sometimes append an offer to do more work. It is not
    # part of a publishable script and must never reach downstream agents.
    text = re.split(
        r"(?m)^\s*(?:如你愿意|如果你需要|我也可以|如需我|以上脚本之外)",
        text,
        maxsplit=1,
    )[0].rstrip()
    # Keep a stable duration contract even when a model omits it from the
    # heading. Do not rewrite spoken copy or invent additional facts.
    # If the model supplied a timeline with a different endpoint, scale only
    # mm:ss labels so the final segment lands on the requested duration.
    stamps = list(re.finditer(r"(?<!\d)(\d{1,2}):(\d{2})(?!\d)", text))
    if len(stamps) >= 2:
        last_seconds = int(stamps[-1].group(1)) * 60 + int(stamps[-1].group(2))
        if last_seconds > 0 and abs(last_seconds - duration_seconds) >= 3:
            scale = duration_seconds / last_seconds
            def replace_stamp(match: re.Match[str]) -> str:
                current = int(match.group(1)) * 60 + int(match.group(2))
                adjusted = max(0, round(current * scale))
                return f"{adjusted // 60}:{adjusted % 60:02d}"
            text = re.sub(r"(?<!\d)(\d{1,2}):(\d{2})(?!\d)", replace_stamp, text)
    if text and not re.search(rf"(?m){duration_seconds}\s*秒", text):
        text = f"**目标时长：{duration_seconds} 秒**\n\n" + text
    return text


def _video_edit_fallback(subject: str, script: str, settings: dict[str, object] | None = None) -> str:
    """Return a usable edit brief even when the model is unavailable.

    The editor's output is consumed by a person (or MoneyPrinterTurbo), so a
    generic ``please provide a script`` response is not an acceptable result.
    Keep the contract deterministic and make the input script visible for
    traceability.
    """
    options = settings or {}
    fmt = str(options.get("format") or "vertical").lower()
    canvas = "1920×1080（16:9）" if fmt in {"horizontal", "landscape", "横版"} else "1080×1920（9:16）"
    requirements = str(options.get("editing_requirements") or "字幕逐句跟随口播，关键词高亮").strip()
    duration = int(options.get("duration_seconds") or 110)
    duration = max(30, min(duration, 240))
    def stamp(seconds: int) -> str:
        return f"{seconds // 60}:{seconds % 60:02d}"
    t1, t2, t3, t4 = min(8, duration), min(45, duration), min(85, duration), duration
    source = script.strip() or subject.strip() or "（未提供脚本，请按主题先制作占位版）"
    return f"""# 视频剪辑执行单：{subject or '未命名选题'}

## 成片规格
- 画幅：{canvas}
- 时长：目标 {duration} 秒，成片不得超出该时长
- 帧率/编码：25fps，MP4（H.264），音频 AAC 48kHz
- 剪辑要求：{requirements}

## 时间轴与分镜
| 时间 | 画面/素材 | 口播与字幕 | 剪辑动作 |
|---|---|---|---|
| 0:00-{stamp(t1)} | 标题卡 + 主题相关屏录或 B-roll | 开场钩子逐句上屏，关键词高亮 | 快切、轻微缩放，前 3 秒给出冲突点 |
| {stamp(t1)}-{stamp(t2)} | 事实来源卡、主体画面、数据/图表 | 每句不超过两行，跟随口播出现 | 事实与推测使用不同颜色标签 |
| {stamp(t2)}-{stamp(t3)} | 流程图、对比卡或操作录屏 | 按“第一/第二/第三”分段 | 用滑动/淡入转场，避免无依据画面 |
| {stamp(t3)}-{stamp(t4)} | 总结卡 + 评论引导 | 收束观点和互动问题 | 音乐渐弱，保留 0.3 秒尾帧 |

## 字幕与配音
- 字幕：白字黑描边，单条不超过 16 个汉字；事实、待验证、风险分别用颜色标记。
- 配音：中文新闻解读风，260–300 字/分钟；配音峰值约 -1 dB，BGM 低于人声 12–18 dB。
- 口播脚本输入（仅作剪辑依据，不新增事实）：

> {source.replace(chr(10), chr(10) + '> ')}

## 素材来源与版权
- 优先使用用户提供的屏录、原创图表和可授权素材；外部素材逐条记录来源和授权状态。
- 不把素材库示例链接当成已下载素材；缺素材时以纯色卡/文字卡占位并标记待补。

## MoneyPrinterTurbo 导出命令
```bash
uv run --no-project --python 3.11.15 python mpt_agent.py --subject "{subject or '未命名选题'}"
```
该命令需要在 MoneyPrinterTurbo Skill 目录执行；它是生成尝试，不代表本次已经生成 MP4。

## 发布前验收
- [ ] 时间轴从 0 开始且不超过 {duration} 秒
- [ ] 字幕与口播逐句对齐，无整段长驻或遮挡主体
- [ ] 所有外部素材有来源/授权记录
- [ ] 导出后检查画幅、音量、字幕错别字和片尾尾帧
"""


def _ensure_video_edit_sections(content: str, fallback: str) -> str:
    required = ("成片规格", "时间轴", "字幕", "配音", "素材", "MoneyPrinterTurbo", "验收")
    text = content.strip()
    if all(section in text for section in required):
        return text
    return text + "\n\n---\n\n" + fallback


async def _append_video_generation(
    content: str,
    subject: str,
    *,
    timeout_seconds: int | None = 0,
    output_dir: str | None = None,
) -> str:
    """Run the installed MoneyPrinterTurbo helper and record its result.

    The editor's primary deliverable is now a generated video.  We retain the
    execution plan in the artifact so a failed/credential-gated generation is
    still diagnosable and resumable, while a successful run exposes the exact
    MP4 path emitted by the helper.
    """
    try:
        if output_dir is None:
            output_dir = get_output_directory_settings().video_output_dir.strip() or None
        result = await run_moneyprinterturbo(
            MoneyPrinterTurboRequest(subject=subject, output_dir=output_dir),
            get_settings(),
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:
        return content + f"\n\n## 成片结果\n- 状态：failed\n- 错误：{_exception_detail(exc)}\n"
    lines = ["\n\n## 成片结果", f"- 状态：{result.status}"]
    if result.video_files:
        lines.append("- 视频文件：" + "、".join(result.video_files))
    elif result.stderr.strip():
        lines.append("- 错误：" + result.stderr.strip()[-1200:])
    elif result.stdout.strip():
        # Keep only the helper's concise status markers; never copy arbitrary
        # credential-bearing configuration into the artifact.
        markers = [line for line in result.stdout.splitlines() if line.startswith(("MPT_", "TASK_DIR=", "LOG_FILE="))]
        if markers:
            lines.append("- 详情：" + "；".join(markers))
    if result.result_file:
        lines.append("- 结果记录：" + result.result_file)
    return content + "\n" + "\n".join(lines) + "\n"


def _looks_like_analysis_prompt(content: str) -> bool:
    text = content.casefold()
    markers = ("你是爆款分析师", "严格输出", "请围绕用户提供", "不要直接写完整", "## 推荐角度")
    return sum(marker.casefold() in text for marker in markers) >= 2


def _relevant_topic_sources(topic: Topic) -> list[SourceEvidence]:
    terms = {term for term in re.split(r"[^\w\u4e00-\u9fff]+", topic.title) if len(term) >= 2}
    primary = [source for source in topic.sources if topic.source_url and source.url == topic.source_url]
    relevant = [source for source in topic.sources if any(term.casefold() in (source.claim + source.name).casefold() for term in terms)]
    relevant = primary + [source for source in relevant if source not in primary]
    return relevant[:8] or topic.sources[:2]


def _viral_analysis_fallback(topic: Topic, seed: TopicSeed, *, manual_content: str = "") -> str:
    facts = "\n".join(f"- {source.name}：{source.claim}" for source in _relevant_topic_sources(topic)) or "- 仅使用已核验选题中的事实，不补充来源之外的内容。"
    if _looks_like_analysis_prompt(manual_content):
        manual_content = "未提供具体爆款样本或分析结论；以下仅依据已核验选题生成施工图，不能宣称为数据驱动规律。"
    if manual_content.strip():
        return f"""# 爆款分析：{topic.title}

## 用户手写分析依据
{manual_content.strip()}

## 推荐角度
从“AI 基础设施需求变化对{seed.audience}的实际影响”切入，回答受众最关心的成本、交付和机会变化。

## 核心观点
已核验报道支持“{topic.title}”这一事实；它提示基础设施需求可能增强，但不能直接推出某个细分赛道必然获利。

## 标题结构
1. 事实变化 + 受众疑问：戴尔上调全年指引，AI 创业者该关注哪一环？
2. 反常现象 + 核心疑问：AI 服务器需求变强，机会真的只在卖模型吗？
3. 热点事件 + 实际影响：从戴尔预期上调，看 AI 工具团队的成本变化。

## 开头策略
“戴尔上调全年预期，报道指向 AI 服务器需求；这对做 AI 工具的人意味着什么？”随后立即交代来源，并标明机会判断待验证。

## 内容顺序
1. 先抛出算力、交付和成本影响\n2. 交代已确认事实\n3. 区分事实与推测，列出等待验证的机会方向\n4. 给出查订单、交付周期和毛利的验证动作

## 必须包含的事实
{facts}

## 不能出现
- 未核实动机\n- 夸张结论\n- 情绪化定性

## 表达风格
{seed.duration_seconds} 秒口播，面向{seed.audience}，通俗、紧凑。
"""
    return f"""# 爆款分析：{topic.title}

## 样本依据
未接入 SocialDataX 或其他平台样本；以下建议是针对本选题的创作假设，不代表平台总体规律。

## 推荐角度
从“AI 基础设施需求变化对{seed.audience}的实际影响”切入，回答受众最关心的成本、交付和机会变化。

## 核心观点
已核验报道支持“{topic.title}”这一事实；它提示基础设施需求可能增强，但不能直接推出某个细分赛道必然获利。

## 标题结构
1. 事实变化 + 受众疑问：戴尔上调全年指引，AI 创业者该关注哪一环？
2. 反常现象 + 核心疑问：AI 服务器需求变强，机会真的只在卖模型吗？
3. 热点事件 + 实际影响：从戴尔预期上调，看 AI 工具团队的成本变化。

## 开头策略
“戴尔上调全年预期，报道指向 AI 服务器需求；这对做 AI 工具的人意味着什么？”随后立即交代来源，并标明机会判断待验证。

## 内容顺序
1. 先抛出算力、交付和成本影响\n2. 交代已确认事实\n3. 区分事实与推测，列出等待验证的机会方向\n4. 给出查订单、交付周期和毛利的验证动作

## 必须包含的事实
{facts}

## 不能出现
- 未核实动机\n- 夸张结论\n- 情绪化定性\n- 将单一公司表现说成行业确定趋势

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
    if agent_id == "video_editor":
        # This employee has a distinct deliverable contract.  Previously it
        # fell through to the generic agent branch, which often produced a
        # request for a script or a testing checklist instead of an edit plan.
        edit_settings = request.settings or {}
        subject = str(edit_settings.get("topic") or "").strip()
        script = str(edit_settings.get("script") or "").strip()
        if prompt and not prompt.startswith("请根据当前工作台设置"):
            # In the standalone workbench the task box is the most useful
            # script input; retain the topic separately when supplied.
            script = script or prompt
        subject = subject or script[:80] or "未命名选题"
        duration = int(edit_settings.get("duration_seconds") or 110)
        fallback = _video_edit_fallback(subject, script, edit_settings)
        result = await gateway.complete(
            system=(
                "你是热讯工坊视频剪辑员小李。只输出可执行的视频剪辑执行单，不要索要更多信息，"
                "不要输出测试方案或助手元话术。必须包含：成片规格、时间轴与分镜（逐段时间/画面/字幕/动作）、"
                "字幕与配音、素材来源与版权、MoneyPrinterTurbo 导出命令、发布前验收。"
                f"目标时长约 {max(30, min(duration, 240))} 秒；不得新增脚本中没有的事实。"
            ),
            user=(
                f"主题：{subject}\n画幅：{edit_settings.get('format') or 'vertical'}\n"
                f"剪辑要求：{edit_settings.get('editing_requirements') or '字幕逐句跟随口播，关键词高亮'}\n"
                f"脚本/口播：\n{script or '未提供脚本，请按主题制作占位版并明确标记待补'}"
            ),
            fallback=fallback,
        )
        edit_content = _ensure_video_edit_sections(result.content, fallback)
        edit_content = await _append_video_generation(edit_content, subject, output_dir=str(edit_settings.get("output_dir") or "") or None)
        return _output(run_dir, agent_id, "视频成片", edit_content, str(edit_settings.get("artifact_output_dir") or "") or None)
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
            if not manual_content:
                raise ValueError("爆款分析手动模式需要填写分析依据或爆款样本")
            if _looks_like_analysis_prompt(manual_content):
                manual_content = "检测到输入是角色提示词而非分析依据；请补充具体爆款样本、数据或你的分析结论。"
            fallback = f"""# 爆款分析师独立分析

## 用户手写分析依据
{manual_content}

## 样本依据
仅使用用户提供的样本或事实；没有平台样本时，不得声称已发现数据规律。

## 推荐角度
从具体受众的实际影响切入。

## 核心观点
只围绕用户提供的主题和事实下结论。

## 标题结构
1. 事实变化 + 受众疑问
2. 反常现象 + 核心疑问
3. 热点事件 + 普通人的实际影响

## 开头策略
前 3 秒先抛出受众最关心的影响，再用一句话交代事实来源和待核验边界。

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


def _write_operator_cover(topic: Topic, run_dir: Path) -> str:
    """Create a deterministic 9:16 cover asset for the operator deliverable."""
    cover_dir = run_dir / "operator"
    cover_dir.mkdir(parents=True, exist_ok=True)
    path = cover_dir / "cover.svg"
    title = "AI服务器需求变强"
    subtitle = "成本会怎么变？"
    detail = "查订单  ·  看交付  ·  算毛利"
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1920" viewBox="0 0 1080 1920">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#071426"/><stop offset="1" stop-color="#102d4d"/></linearGradient>
    <linearGradient id="line" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#23d5ab"/><stop offset="1" stop-color="#ffd166"/></linearGradient>
  </defs>
  <rect width="1080" height="1920" fill="url(#bg)"/>
  <circle cx="850" cy="280" r="260" fill="#1b4965" opacity=".42"/><circle cx="160" cy="1580" r="360" fill="#123b5d" opacity=".45"/>
  <path d="M0 1420 C260 1320 360 1510 600 1390 S900 1280 1080 1370" fill="none" stroke="url(#line)" stroke-width="8" opacity=".8"/>
  <rect x="84" y="110" width="230" height="58" rx="29" fill="#ffd166"/><text x="199" y="150" text-anchor="middle" font-family="Microsoft YaHei, sans-serif" font-size="28" font-weight="700" fill="#071426">AI 行业观察</text>
  <text x="84" y="580" font-family="Microsoft YaHei, sans-serif" font-size="78" font-weight="800" fill="#ffffff">{title}</text>
  <text x="84" y="700" font-family="Microsoft YaHei, sans-serif" font-size="104" font-weight="900" fill="#ffd166">{subtitle}</text>
  <text x="84" y="850" font-family="Microsoft YaHei, sans-serif" font-size="40" fill="#cfe8ff">别只看股价，先看业务指标</text>
  <g font-family="Microsoft YaHei, sans-serif" font-size="42" font-weight="700" fill="#ffffff">
    <rect x="84" y="1030" width="912" height="112" rx="20" fill="#0d2238" stroke="#23d5ab" stroke-width="3"/><text x="540" y="1102" text-anchor="middle">{detail}</text>
  </g>
  <text x="84" y="1770" font-family="Microsoft YaHei, sans-serif" font-size="30" fill="#9fc3df">事实信号 ≠ 行业确定机会</text>
  <text x="84" y="1830" font-family="Microsoft YaHei, sans-serif" font-size="26" fill="#7195b2">热讯工坊 · 运营发布封面</text>
</svg>'''
    path.write_text(svg, encoding="utf-8")
    return str(path.resolve())


def _operator_fallback(topic: Topic, cover_path: str | None = None) -> str:
    """Return a complete operator plan with platform and evidence boundaries."""
    topic_terms = {token.casefold() for token in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,}", topic.title)}
    sources = [
        source for source in (topic.sources or [])
        if topic_terms & {token.casefold() for token in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,}", source.claim)}
    ][:5]
    if not sources and topic.sources:
        sources = topic.sources[:1]
    source_lines = "\n".join(
        f"- {source.name}：{source.url}（{source.claim}）" for source in sources[:5]
    ) or f"- {topic.source_hint or '公开来源'}：{topic.source_url}（{topic.title}）"
    return f"""# 运营发布方案：{topic.title}

## 1. 发布定位
- 目标受众：关注 AI 工具的一线创作者、产品/运营和创业者。
- 核心承诺：把新闻信号落到成本、交付和机会三个可核验动作。
- 承接规则：只推广文案脚本已有观点，不新增事实，不把股价表现扩大为行业结论。

## 1.1 行业分析
- 内容赛道：AI 基础设施、算力成本与 AI 工具团队经营决策。
- 用户需求：理解新闻如何影响成本、交付和毛利，并获得可执行的验证步骤。
- 内容边界：本报告只基于本次已核验选题，不推断行业整体趋势。

## 1.2 竞品分析
- 对标内容类型：财经快讯、算力行业解读、AI 创业实操分享。
- 差异化切口：把“戴尔预期上调”转译为查订单、看交付、算毛利的行动清单。
- 发布前动作：人工抽查同题材近 7 天标题和封面，避免重复表述；未抓取到竞品数据时标记为待补。

## 1.3 账号设置建议
- 简介定位：用数据拆解 AI 新闻，帮助工具团队做成本与交付判断。
- 置顶内容：账号方法论介绍、事实/推测标注规则、代表性案例。
- 视觉规范：深蓝/黑灰底色，黄/绿/橙分别表示重点、事实和待验证。

## 2. 平台适配
| 平台 | 标题 | 封面/首屏 | 发布时间 | 话题 |
|---|---|---|---|---|
| 抖音 | 别只看戴尔股价：AI工具团队先查这3项 | 成本｜交付｜机会 | 工作日 19:30-21:30 | #AI服务器 #AI工具 #算力成本 |
| 视频号 | 戴尔上调预期，AI工具团队该怎么验证影响？ | 事实信号 vs 待验证 | 工作日 12:00-13:30 或 20:00-21:30 | #AI创业 #行业观察 #商业分析 |
| 小红书 | 从戴尔预期上调，看 AI 工具团队的成本与交付 | 三个验证动作 | 工作日 12:00-14:00 | #AI服务器 #供应链 #ToB运营 |

## 3. 封面与发布文案
- 主文案：AI服务器需求变强，成本会怎么变？
- 副文案：查订单｜看交付｜算毛利
- 发布简介：戴尔预期上调是基础设施需求信号；本文只提供验证路径，不将单一公司表现等同于行业趋势。
- 封面文件：{cover_path or '待生成'}
- 封面规格：1080×1920（9:16），深蓝科技风；可直接上传或转 PNG 使用。

## 4. 评论与回复流程
- 置顶问题：评论区报三个数：交付周期、单请求成本、订单兑现率。
- 首轮回复：先确认用户所在环节，再建议对照近三个月数据；不替用户补齐缺失事实。
- 争议回复：引用来源并标注“事实/推测”，必要时更正并保留修改记录。

## 5. 可执行复盘清单（发布后 24 小时）
- [ ] 标题、封面、口播未出现“必然上涨/一定获利”等过度承诺。
- [ ] 来源链接、发布时间和事实/推测标签已展示。
- [ ] 三个平台的素材规格、字幕和话题已按上表配置。
- [ ] 评论按“成本/交付/机会/其他”归类，记录代表性问题和待补证据。
- [ ] 将用户反馈回写下一版选题，不新增未经核验的事实。

## 5.1 30 天内容计划（主题日历）
| 周期 | 内容主线 | 执行动作 |
|---|---|---|
| 第 1 周 | 算力成本信号 | 3 条新闻拆解，统一使用“查订单/看交付/算毛利”框架 |
| 第 2 周 | 交付与供应链 | 2 条案例 + 1 条用户问题答复，记录待补证据 |
| 第 3 周 | 模型与推理效率 | 2 条成本优化方法 + 1 条事实核验说明 |
| 第 4 周 | 月度复盘 | 汇总评论问题，筛选下月 5 个可核验选题 |

## 6. 来源与发布前核验
{source_lines}
- 核验状态：{topic.verification_status}；{topic.verification_note or '发布前仍需人工复核原文。'}
- 风险提示：{topic.risk or '避免把单一公司表现表述为行业确定趋势。'}

## 7. 与文案助手的一致性检查
- 主题、事实边界、成本/交付/机会三条主线、查订单/看交付/算毛利三个动作与文案脚本一致。
- 运营环节只负责包装、发布和反馈记录，不改写口播事实。

## 8. 互动话术库
- 首评：你们最近的交付周期和单请求成本，有变化吗？请只分享可公开的大致区间。
- 追问：这个变化发生在服务器到货、云资源获取，还是模型调用价格？
- 资料引导：需要指标核对表的，回复“指标”，我发公开模板；不收集敏感业务数据。
- 纠错：感谢指出，我会回到来源原文核对，并在更正处标注更新时间。
"""


def _ensure_operator_sections(content: str, fallback: str, topic: Topic) -> str:
    required = ("行业分析", "竞品分析", "账号设置", "30 天", "平台适配", "互动话术", "评论", "复盘", "来源", "核验")
    text = (content or "").strip()
    # The operator artifact is consumed directly by users. If the model omits
    # any required operational section, use the deterministic evidence-linked
    # plan instead of returning a partial report.
    if not text or sum(marker in text for marker in required) < len(required):
        return fallback
    # No real distribution data is available; remove claims that imply results.
    if re.search(r"完播率|互动率|转化率|CTR|ROI|播放完成率|3秒留存|平均观看时长|点赞率|收藏率|转发率", text):
        return fallback
    if topic.source_url and topic.source_url not in text:
        text += f"\n\n## 来源与发布前核验\n- {topic.source_hint or '公开来源'}：{topic.source_url}\n- 核验状态：{topic.verification_status}；发布前仍需人工复核原文。\n"
    cover_match = re.search(r"封面文件：([^\n]+)", fallback)
    if cover_match and "封面文件：" not in text:
        text += f"\n\n## 封面资产\n- 封面文件：{cover_match.group(1).strip()}\n- 规格：1080×1920（9:16），可直接预览或转 PNG 上传。\n"
    return text.strip()


async def run_hot_video_workflow(
    seed: TopicSeed,
    settings: Settings,
    existing: WorkflowRun | None = None,
    stop_after_stage: str | None = None,
    viral_analysis: ViralAnalysisConfig | None = None,
    selected_topic_title: str | None = None,
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
    if selected_topic_title is not None:
        workflow.selected_topic_title = selected_topic_title.strip() or None
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
                selected = next(
                    (topic for topic in verified_topics if topic.title == workflow.selected_topic_title),
                    verified_topics[0],
                )
                analyst_output = output_for("viral_analyst")
                if analyst_output:
                    analyst_content = analyst_output.content
                else:
                    analysis_config = workflow.viral_analysis
                    if analysis_config.source == "manual":
                        if not analysis_config.manual_content.strip():
                            raise RuntimeError("爆款分析已选择手动模式，但没有填写分析依据")
                        if _looks_like_analysis_prompt(analysis_config.manual_content):
                            # Older checkpoints could have persisted the UI's
                            # role prompt as manual content. Do not make a
                            # stage rerun impossible; discard that invalid
                            # input and fall back to the verified topic facts.
                            workflow.source_status["viral-analysis"] = "manual:invalid prompt ignored"
                            _log(workflow, "检测到旧的角色提示词，已忽略并按选题事实生成爆款分析", stage=stage, level="warning")
                            analyst_content = _viral_analysis_fallback(selected, seed)
                        else:
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
                selected = next(
                    (topic for topic in _verified_topics(workflow.topics) if topic.title == workflow.selected_topic_title),
                    (_verified_topics(workflow.topics) or [None])[0],
                )
                if selected is None:
                    raise RuntimeError("找不到已核验选题，无法生成脚本")
                analyst_content = output_for("viral_analyst").content if output_for("viral_analyst") else analyst_content
                script_output = output_for("copywriter")
                script_fallback = f"""# 口播脚本：{selected.title}

**目标时长：{seed.duration_seconds} 秒（时间轴须落在 0-{seed.duration_seconds} 秒）**

## 开场钩子（0-8 秒）
如果你把 AI 当成一个聊天框，它只能帮你省一点时间；但如果你把它拆成一家公司，事情就变了。

## 事件经过（8-60 秒）
今天这个热点是：{selected.title}。它之所以值得关注，是因为内容生产已经开始被拆成岗位：赵爽负责找热点，星辰负责判断能不能爆，洛一写脚本，小李给出剪辑方案，尤道理负责发布和复盘。

## 关键分析（60-95 秒，事实与推测分开）
这里最重要的不是名字，而是边界。每个 AI 员工有自己的任务、产物和工作区，老板只负责决策和验收。

## 总结（95-{seed.duration_seconds} 秒）
一人公司不是让 AI 替你思考，而是让你的判断力有一条生产线。
"""
                if script_output:
                    script_content = script_output.content
                else:
                    result = await gateway.complete(
                        system=(
                            "你是文案助手洛一。写中文短视频脚本，含时间段、口播、镜头提示。"
                            f"严格控制为约 {seed.duration_seconds} 秒，时间轴最后一段必须结束在 {seed.duration_seconds} 秒。"
                            "必须区分已确认事实与推测/待验证判断；只输出成稿，不要输出助手元话术。"
                        ),
                        user=f"请基于爆款分析写 {seed.duration_seconds} 秒脚本：\n{analyst_content}",
                        fallback=script_fallback,
                    )
                    script_content = _clean_script_output(result.content, seed.duration_seconds)
                    save_output("copywriter", "短视频脚本", script_content)
            elif stage == "video_editor":
                selected = next(
                    (topic for topic in _verified_topics(workflow.topics) if topic.title == workflow.selected_topic_title),
                    (_verified_topics(workflow.topics) or [None])[0],
                )
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
- `uv run --no-project --python 3.11.15 python mpt_agent.py --subject "{selected.title}"`
"""
                    result = await gateway.complete(
                        system="你是视频剪辑员小李。输出可执行剪辑方案，包含工具出处、画幅、素材、字幕、配音和导出命令。",
                        user=f"请根据脚本生成剪辑计划：\n{script_content}",
                        fallback=edit_fallback,
                    )
                    # Models occasionally answer with a generic request for
                    # more information.  Enforce the same executable editor
                    # contract used by standalone calls before persisting the
                    # pipeline artifact.
                    pipeline_fallback = _video_edit_fallback(
                        selected.title,
                        script_content,
                        {"duration_seconds": seed.duration_seconds, "format": "vertical"},
                    )
                    edit_content = _ensure_video_edit_sections(result.content, pipeline_fallback)
                    edit_content = await _append_video_generation(edit_content, selected.title)
                    save_output(
                        "video_editor",
                        "视频成片",
                        edit_content,
                    )
            elif stage == "operator":
                selected = next(
                    (topic for topic in _verified_topics(workflow.topics) if topic.title == workflow.selected_topic_title),
                    (_verified_topics(workflow.topics) or [None])[0],
                )
                if selected is None:
                    raise RuntimeError("找不到已核验选题，无法生成运营方案")
                script_content = output_for("copywriter").content if output_for("copywriter") else script_content
                if not output_for("operator"):
                    cover_path = _write_operator_cover(selected, run_dir)
                    op_fallback = _operator_fallback(selected, cover_path)
                    result = await gateway.complete(
                        system=(
                            "你是运营大师尤道理。输出完整的中文 Markdown 运营方案，必须包含：发布定位、"
                            "抖音/视频号/小红书平台适配、封面与发布文案、评论与回复流程、可执行复盘清单、"
                            "来源与发布前核验、与文案助手的一致性检查。只承接脚本已有事实，不新增事实；"
                            "不要声称已经验证完播率、互动率、转化率、CTR、ROI 等效果。"
                        ),
                        user=(
                            f"请为这个脚本生成运营方案，并严格按已核验选题约束：\n{script_content}\n\n"
                            f"选题证据：{selected.model_dump_json()}\n"
                            f"如无法满足完整结构，直接使用以下基准方案：\n{op_fallback}"
                        ),
                        fallback=op_fallback,
                    )
                    operator_content = _ensure_operator_sections(result.content, op_fallback, selected)
                    save_output("operator", "运营发布方案", operator_content)

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

        workflow.status = "completed"
        workflow.current_stage = None
        workflow.resumable = False
        workflow.completed_at = _now()
        summary = {
            "id": workflow.id,
            "status": workflow.status,
            "completed_at": workflow.completed_at.isoformat() if workflow.completed_at else None,
            "seed": seed.model_dump(),
            "topics": [topic.model_dump(mode="json") for topic in workflow.topics],
            "outputs": [output.model_dump(mode="json") for output in workflow.outputs],
            "stage_status": workflow.stage_status,
        }
        _write_artifact(run_dir, "boss", "run-summary.json", json.dumps(summary, ensure_ascii=False, indent=2))
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
    for workflow in RUNS.values():
        _ensure_workflow_state(workflow)
    return sorted(RUNS.values(), key=lambda run: run.created_at, reverse=True)


def get_run(run_id: str) -> WorkflowRun | None:
    workflow = RUNS.get(run_id)
    if workflow is not None:
        # Keep API responses consistent for runs created before the diagnostic
        # filtering was added (the UI may still have one open).
        _ensure_workflow_state(workflow)
    return workflow

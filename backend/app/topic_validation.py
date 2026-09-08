from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Callable
from urllib.parse import urlparse

from backend.app.schemas import SourceEvidence, Topic, TopicSeed


def extract_json_payload(content: str) -> object:
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


def coerce_heat(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return max(0, min(100, int(value)))
    qualitative = {"极高": 95, "very high": 95, "高": 85, "high": 85, "中": 65, "medium": 65, "低": 40, "low": 40}
    text = str(value or "").strip().casefold()
    if text in qualitative:
        return qualitative[text]
    try:
        return max(0, min(100, int(float(text))))
    except (TypeError, ValueError):
        return 50


def coerce_count(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def source_domain(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def evidence_domain(source: SourceEvidence) -> str:
    """Return the publisher domain, including known RSS/search fallbacks."""
    name = source.name.casefold()
    for needles, domain in ((("reuters",), "reuters.com"), (("bbc",), "bbc.co.uk"), (("华尔街", "wallstreet"), "wallstreetcn.com"), (("微博", "weibo"), "weibo.com")):
        if any(needle in name for needle in needles):
            return domain
    return source_domain(source.url)


def news_relevance(item: dict, seed: TopicSeed) -> float:
    """Estimate whether a fetched item is about the requested direction."""
    haystack = f"{item.get('title', '')} {item.get('summary', '')}".casefold()
    seed_text = f"{seed.domain} {seed.brief}".casefold()
    ascii_terms = re.findall(r"[a-z0-9][a-z0-9+#.-]{1,}", seed_text)
    cjk_terms: list[str] = []
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", seed_text):
        cjk_terms.extend(run[index:index + 2] for index in range(len(run) - 1))
    stopwords = {"近期", "热点", "内容", "生产", "关注", "普通", "一线", "创作者", "创业者"}
    terms = list(dict.fromkeys(term for term in ascii_terms + cjk_terms if term not in stopwords))
    if not terms:
        return 0.0
    return min(1.0, sum(1 for term in terms if term in haystack) / max(1, min(5, len(terms))))


def task_overlap_score(text: str, seed: TopicSeed) -> float:
    """Score overlap with the requested domain, keeping audience boilerplate out."""
    return min(1.0, news_relevance({"title": text}, TopicSeed(domain=seed.domain, brief="", audience="")) * 0.70 + news_relevance({"title": text}, TopicSeed(domain="", brief=seed.brief, audience="")) * 0.30)


_DIAGNOSTIC_TOPIC_PATTERNS = (r"缺乏可用来源", r"不构成.{0,12}(热点|候选)", r"本批次", r"仅检测到", r"未出现", r"无法从.{0,20}(确认|判断)", r"缺少.{0,8}(核验|证据|来源)", r"来源不足", r"模型未返回", r"需补充", r"提示[:：]", r"作为泛.{0,8}(舆情|叙事)", r"报错", r"(?:执行|请求|抓取|来源|模型|搜索|接口).{0,8}(?:失败|错误|超时)", r"(?:失败|错误|超时).{0,8}(?:执行|请求|抓取|来源|模型|搜索|接口)", r"\b(?:error|failed|failure|exception|timeout)\b")


def is_diagnostic_topic(topic: Topic) -> bool:
    """Reject model prose that reports a collection/validation problem."""
    text = " ".join((topic.title, topic.source_hint, topic.angle)).casefold()
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in _DIAGNOSTIC_TOPIC_PATTERNS)


def clean_topic_title(title: str) -> str:
    # ``（候选）`` is a model label, not part of the actual headline.
    return re.sub(r"^\s*[（(]\s*候选\s*[）)]\s*", "", title).strip()


def _topic_tokens(text: str) -> set[str]:
    aliases = {"戴尔": "dell", "服务器": "server", "算力": "compute", "英伟达": "nvidia", "黄仁勋": "jensen", "开放人工智能": "openai", "人工智能": "ai", "代理": "agent"}
    normalized = text.casefold()
    for source, target in aliases.items():
        normalized = normalized.replace(source, f" {target} ")
    ascii_tokens = set(re.findall(r"[a-z0-9][a-z0-9+#.-]{2,}", normalized))
    cjk_tokens: set[str] = set()
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", normalized):
        cjk_tokens.update(run[index:index + 2] for index in range(len(run) - 1))
    return (ascii_tokens | cjk_tokens) - {"AI", "人工", "智能", "需求", "市场", "股价", "行业", "公司", "模型", "产品", "新闻", "热点"}


def augment_topic_sources(topics: list[Topic], raw_items: list[dict], parse_datetime: Callable[[object], object]) -> None:
    """Attach corroborating fetched items the model omitted from ``sources``."""
    for topic in topics:
        known_urls = {source.url for source in topic.sources}
        topic_tokens = _topic_tokens(f"{topic.title} {topic.source_hint}")
        for item in raw_items:
            url = str(item.get("url") or "").strip()
            item_tokens = _topic_tokens(f"{item.get('title', '')} {item.get('summary', '')}")
            overlap = topic_tokens & item_tokens
            if not url or url in known_urls or not (len(overlap) >= 2 or any(re.fullmatch(r"[a-z0-9+#.-]{4,}", token) for token in overlap)):
                continue
            published_at = parse_datetime(item.get("pubdate") or item.get("time"))
            name = str(item.get("source") or "公开来源").strip()
            title = str(item.get("title") or "").strip()
            if not published_at or not name or not title:
                continue
            topic.sources.append(SourceEvidence(name=name, url=url, published_at=published_at, claim=str(item.get("summary") or title).strip()))
            known_urls.add(url)


def rank_news_items(items: list[dict], seed: TopicSeed, source_weights: dict[str, float]) -> list[dict]:
    """Rank every fetched item before the model sees it.

    Ranking is only a prioritisation hint. It never turns a single source into
    a verified fact; the later source-domain gate remains authoritative.
    """
    now = datetime.now().timestamp()
    ranked: list[dict] = []
    for index, item in enumerate(items):
        copy = dict(item)
        try: published = float(copy.get("pubdate") or 0)
        except (TypeError, ValueError): published = 0
        age_days = max(0.0, (now - published) / 86400) if published else 14.0
        recency = max(0.0, 1.0 - age_days / 14.0)
        engagement = coerce_count(copy.get("engagement") or copy.get("hot") or copy.get("heat") or copy.get("read_count") or copy.get("view_count"))
        source = str(copy.get("source") or copy.get("channel") or "").casefold()
        weight = next((weight for name, weight in source_weights.items() if name in source), 0.70)
        # Domain overlap is the primary filter. Engagement is only a small
        # tie-breaker so a generic hot-search list cannot dominate.
        score = task_overlap_score(f"{copy.get('title', '')} {copy.get('summary', '')}", seed) * 70 + weight * 15 + recency * 10 + min(1.0, engagement / 1_000_000) * 5
        copy["rank_score"] = round(score, 3)
        copy["rank_reason"] = {"source_weight": weight, "recency": round(recency, 3), "relevance": round(news_relevance(copy, seed), 3), "engagement": engagement}
        copy["_fetch_order"] = index
        ranked.append(copy)
    return sorted(ranked, key=lambda value: (-float(value.get("rank_score", 0)), value.get("_fetch_order", 0)))


def diversify_news_items(items: list[dict], limit: int) -> list[dict]:
    """Keep the model evidence window representative across source labels.

    Ranking by engagement alone can fill all slots with one real-time hot list,
    hiding entries that could corroborate an event. Round-robin sampling gives
    every configured source a chance.
    """
    if len(items) <= limit:
        return items
    groups: dict[str, list[dict]] = {}
    for item in items:
        groups.setdefault(str(item.get("source") or item.get("channel") or "unknown"), []).append(item)
    selected: list[dict] = []
    round_index = 0
    while len(selected) < limit:
        progressed = False
        for group in groups.values():
            if round_index < len(group):
                selected.append(group[round_index]); progressed = True
                if len(selected) >= limit: break
        if not progressed: break
        round_index += 1
    return selected


def validate_topics(topics: list[Topic], seed: TopicSeed | None = None, now: Callable[[], datetime] | None = None) -> list[Topic]:
    """Validate all candidates before selecting one for downstream work."""
    merged: dict[str, Topic] = {}
    for topic in topics:
        topic.title = clean_topic_title(topic.title)
        if not topic.title or is_diagnostic_topic(topic): continue
        key = " ".join(topic.title.casefold().split())
        previous = merged.get(key)
        if previous is None: merged[key] = topic; continue
        known_urls = {source.url for source in previous.sources}
        previous.sources.extend(source for source in topic.sources if source.url not in known_urls)
        previous.heat = max(previous.heat, topic.heat)
    validated: list[Topic] = []
    for topic in merged.values():
        domains = {evidence_domain(source) for source in topic.sources if evidence_domain(source)}
        independent = len(topic.sources) >= 2 and len(domains) >= 2
        topic.verification_status = "verified" if independent else "unverified"
        topic.checked_at = topic.checked_at or (now() if now else datetime.now().astimezone())
        topic.cross_check_note = (f"已完成全量候选核验：引用 {len(topic.sources)} 个来源，覆盖 {len(domains)} 个独立域名。" if independent else f"已完成全量候选核验：当前仅有 {len(domains)} 个独立域名来源。")
        topic.verification_note = "已通过不同域名来源交叉验证；仍需人工复核原文。" if independent else "来源不足或域名不独立，不得作为已核实事实发布。"
        if seed is not None: topic.heat = max(0, min(100, round(task_overlap_score(f"{topic.title} {topic.source_hint}", seed) * 55 + min(1.0, len(domains) / 3) * 22.5 + min(1.0, len(topic.sources) / 4) * 7.5 + 5)))
        validated.append(topic)
    return sorted(validated, key=lambda topic: (-topic.heat, topic.title))

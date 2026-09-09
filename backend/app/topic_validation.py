"""热点候选解析、相关性评分和来源核验。"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Callable
from urllib.parse import urlparse

from backend.app.schemas import SourceEvidence, Topic, TopicSeed


def extract_json_payload(content: str) -> object:
    """函数“extract_json_payload”：从模型文本中提取 JSON 对象或数组。
参数：
    content: str
返回：object。"""
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
    """函数“coerce_heat”：将热度输入安全转换为 0 到 100 的整数。
参数：
    value: object
返回：int。"""
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
    """函数“coerce_count”：将数量输入安全转换为非负整数。
参数：
    value: object
返回：int。"""
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def source_domain(url: str) -> str:
    """函数“source_domain”：从 URL 提取来源域名。
参数：
    url: str
返回：str。"""
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def evidence_domain(source: SourceEvidence) -> str:
    """返回发布方域名，并处理已知 RSS 或搜索中转域名。"""
    name = source.name.casefold()
    for needles, domain in ((("reuters",), "reuters.com"), (("bbc",), "bbc.co.uk"), (("华尔街", "wallstreet"), "wallstreetcn.com"), (("微博", "weibo"), "weibo.com")):
        if any(needle in name for needle in needles):
            return domain
    return source_domain(source.url)


def news_relevance(item: dict, seed: TopicSeed) -> float:
    """估算抓取条目是否属于请求的内容方向。"""
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
    """计算文本与请求领域的重合度，并排除受众模板语句。"""
    return min(1.0, news_relevance({"title": text}, TopicSeed(domain=seed.domain, brief="", audience="")) * 0.70 + news_relevance({"title": text}, TopicSeed(domain="", brief=seed.brief, audience="")) * 0.30)


# 用于识别“来源不足/抓取失败”等诊断文本的正则模式。
_DIAGNOSTIC_TOPIC_PATTERNS = (r"缺乏可用来源", r"不构成.{0,12}(热点|候选)", r"本批次", r"仅检测到", r"未出现", r"无法从.{0,20}(确认|判断)", r"缺少.{0,8}(核验|证据|来源)", r"来源不足", r"模型未返回", r"需补充", r"提示[:：]", r"作为泛.{0,8}(舆情|叙事)", r"报错", r"(?:执行|请求|抓取|来源|模型|搜索|接口).{0,8}(?:失败|错误|超时)", r"(?:失败|错误|超时).{0,8}(?:执行|请求|抓取|来源|模型|搜索|接口)", r"\b(?:error|failed|failure|exception|timeout)\b")


def is_diagnostic_topic(topic: Topic) -> bool:
    """拒绝描述采集或核验问题的模型伪选题。"""
    text = " ".join((topic.title, topic.source_hint, topic.angle)).casefold()
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in _DIAGNOSTIC_TOPIC_PATTERNS)


def clean_topic_title(title: str) -> str:
    # “（候选）”是模型标签，不属于正式标题。
    """函数“clean_topic_title”：清理模型标题中的标签和多余空白。
参数：
    title: str
返回：str。"""
    return re.sub(r"^\s*[（(]\s*候选\s*[）)]\s*", "", title).strip()


def _topic_tokens(text: str) -> set[str]:
    """内部辅助函数“_topic_tokens”，负责topic tokens。
参数：
    text: str
返回：set[str]。"""
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
    """将模型遗漏的抓取条目补充到选题佐证来源中。"""
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
    """在交给模型前为全部抓取条目排序。

    排序只是优先级提示，不会把单一来源变成已核验事实；最终仍由来源域名门槛决定。
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
        # 先按领域重合度筛选，互动量只用于少量并列排序，避免泛热点压过相关内容。
        score = task_overlap_score(f"{copy.get('title', '')} {copy.get('summary', '')}", seed) * 70 + weight * 15 + recency * 10 + min(1.0, engagement / 1_000_000) * 5
        copy["rank_score"] = round(score, 3)
        copy["rank_reason"] = {"source_weight": weight, "recency": round(recency, 3), "relevance": round(news_relevance(copy, seed), 3), "engagement": engagement}
        copy["_fetch_order"] = index
        ranked.append(copy)
    return sorted(ranked, key=lambda value: (-float(value.get("rank_score", 0)), value.get("_fetch_order", 0)))


def diversify_news_items(items: list[dict], limit: int) -> list[dict]:
    """保持模型证据窗口覆盖多个来源标签。

    仅按互动量排序可能让单一实时榜占满全部位置，遮挡可用于事件佐证的条目；轮询抽样让每个配置来源都有机会进入证据窗口。
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
    """在选择下游选题前，校验全部候选项。"""
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

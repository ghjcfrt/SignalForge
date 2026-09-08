from __future__ import annotations

import asyncio
from collections.abc import Callable

import httpx

from backend.app.config import Settings

SOCIALDATAX_NOTE_SEARCH_PATH = "/socialdatax/api/v1/xhs/note/search"
SOCIALDATAX_VIDEO_TRANSCRIPT_PATH = "/socialdatax/api/v1/xhs/note/transcript"


# 函数「socialdatax_error」负责完成该步骤的输入处理、核心逻辑和结果返回。
def socialdatax_error(response: httpx.Response, payload: object) -> str:
    if isinstance(payload, dict):
        message = str(payload.get("message") or "").strip()
        code = payload.get("code")
        if message and code is not None:
            return f"{message}（code {code}）"
        if message:
            return message
    return f"HTTP {response.status_code}"


# 函数「socialdatax_payload_failed」负责完成该步骤的输入处理、核心逻辑和结果返回。
def socialdatax_payload_failed(payload: object) -> bool:
    if not isinstance(payload, dict) or "code" not in payload:
        return False
    code = payload.get("code")
    if code in (0, 200, "0", "200", "success", "SUCCESS"):
        return False
    return payload.get("success") is not True


# 函数「normalize_socialdatax_notes」负责完成该步骤的输入处理、核心逻辑和结果返回。
def normalize_socialdatax_notes(
    payload: object,
    parse_datetime: Callable[[object], object | None],
    coerce_count: Callable[[object], int],
) -> list[dict]:
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
        published_at = parse_datetime(item.get("publish_time") or item.get("published_at") or item.get("time"))
        if not published_at:
            continue
        author = item.get("author") if isinstance(item.get("author"), dict) else {}
        content = str(item.get("transcript") or item.get("speech_text") or item.get("content") or item.get("description") or "").strip()
        notes.append({
            "title": title,
            "summary": str(item.get("summary") or "").strip(),
            "note_url": note_url,
            "note_type": str(item.get("note_type") or item.get("type") or "").strip().casefold(),
            "like_count": coerce_count(item.get("like_count")),
            "collect_count": coerce_count(item.get("collect_count")),
            "comment_count": coerce_count(item.get("comment_count")),
            "share_count": coerce_count(item.get("share_count")),
            "publish_time": published_at.isoformat(),
            "author": str(author.get("name") or "").strip(),
            "content": content,
            "rank": rank,
        })
    return notes


# 异步函数「run_socialdatax_note_search」负责完成该步骤的输入处理、核心逻辑和结果返回。
async def run_socialdatax_note_search(
    keyword: str,
    settings: Settings,
    normalize_notes: Callable[[object], list[dict]],
    *,
    sort_type: str = "like_count_descending",
) -> list[dict]:
    """Fetch high-engagement XHS samples for the viral-analysis stage only."""
    api_key = (settings.socialdatax_api_key or "").strip()
    if not api_key:
        return []
    request = {"keyword": keyword.strip(), "sort_type": sort_type, "note_type": "all", "publish_time_range": "half_year", "page_token": ""}
    timeout = None if settings.socialdatax_timeout_seconds <= 0 else settings.socialdatax_timeout_seconds
    base_url = settings.socialdatax_base_url.strip().rstrip("/") or "https://mcp.socialdatax.com"
    headers = {"Accept": "application/json", "Authorization": f"Bearer {api_key}", "X-API-Key": api_key, "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=timeout, follow_redirects=True) as client:
            response = await client.post(SOCIALDATAX_NOTE_SEARCH_PATH, headers=headers, json=request)
    except httpx.TimeoutException as exc:
        raise RuntimeError("SocialDataX 笔记搜索超时") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"SocialDataX 笔记搜索网络错误：{exc}") from exc
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"SocialDataX 返回了无效 JSON（HTTP {response.status_code}）") from exc
    if response.status_code >= 400 or socialdatax_payload_failed(payload):
        raise RuntimeError(f"SocialDataX 笔记搜索失败：{socialdatax_error(response, payload)}")
    return normalize_notes(payload)


# 异步函数「run_socialdatax_transcript」负责完成该步骤的输入处理、核心逻辑和结果返回。
async def run_socialdatax_transcript(note_url: str, settings: Settings) -> str:
    """Try the paid video-to-speech step for a video sample.

    Transcript extraction is best-effort: an unavailable transcript must not
    discard otherwise valid ranking samples or stop the whole workflow.
    """
    api_key = (settings.socialdatax_api_key or "").strip()
    timeout = None if settings.socialdatax_timeout_seconds <= 0 else settings.socialdatax_timeout_seconds
    base_url = settings.socialdatax_base_url.strip().rstrip("/") or "https://mcp.socialdatax.com"
    headers = {"Accept": "application/json", "Authorization": f"Bearer {api_key}", "X-API-Key": api_key}
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=timeout, follow_redirects=True) as client:
            response = await client.post(SOCIALDATAX_VIDEO_TRANSCRIPT_PATH, headers=headers, json={"url": note_url, "note_url": note_url})
            payload = response.json()
    except (httpx.HTTPError, ValueError, asyncio.TimeoutError) as exc:
        raise RuntimeError(f"视频口播提取失败：{exc}") from exc
    if response.status_code >= 400 or socialdatax_payload_failed(payload):
        raise RuntimeError(f"视频口播提取失败：{socialdatax_error(response, payload)}")
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


# 异步函数「enrich_socialdatax_notes」负责完成该步骤的输入处理、核心逻辑和结果返回。
async def enrich_socialdatax_notes(notes: list[dict], settings: Settings) -> tuple[list[dict], int, list[str]]:
    enriched: list[dict] = []
    transcript_count = 0
    errors: list[str] = []
    for note in notes:
        current = dict(note)
        is_video = current.get("note_type", "") in {"video", "视频", "videonote"}
        if is_video and not current.get("content"):
            try:
                current["content"] = await run_socialdatax_transcript(current["note_url"], settings)
                current["transcript_source"] = "socialdatax-video-transcript"
                transcript_count += 1
            except Exception as exc:
                current["transcript_error"] = str(exc)
                errors.append(f"{current['title']}：{exc}")
        enriched.append(current)
    return enriched, transcript_count, errors


# 函数「socialdatax_context」负责完成该步骤的输入处理、核心逻辑和结果返回。
def socialdatax_context(notes: list[dict], *, label: str = "样本") -> str:
    if not notes:
        return "## SocialDataX 小红书样本\n\n本次没有可用的 SocialDataX 样本；不要编造点赞、收藏、评论、分享数据，只能基于选题本身给出待验证的传播假设。"
    lines = [f"## SocialDataX 小红书{label}（原始数据）", "", "以下互动量来自 SocialDataX 搜索结果，仅用于样本比较，不代表平台整体趋势：", ""]
    for index, note in enumerate(notes, start=1):
        lines.extend([f"{index}. 排名：{note.get('rank', index)}；标题：{note['title']}", f"   - 笔记链接：{note['note_url']}", f"   - 作者：{note.get('author') or '未提供'}；类型：{note.get('note_type') or '未提供'}；发布时间：{note.get('publish_time') or '未提供'}", f"   - 点赞：{note.get('like_count', 0)}；收藏：{note.get('collect_count', 0)}；评论：{note.get('comment_count', 0)}；分享：{note.get('share_count', 0)}", f"   - 摘要/口播：{note.get('content') or note.get('summary') or '未提供'}", *([f"   - 口播提取：{note['transcript_source']}"] if note.get("transcript_source") else []), *([f"   - 口播提取失败：{note['transcript_error']}"] if note.get("transcript_error") else [])])
    return "\n".join(lines)

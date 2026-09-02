from __future__ import annotations

import asyncio
from dataclasses import dataclass

from openai import AsyncOpenAI

from backend.app.config import Settings


@dataclass(frozen=True)
class ChatResult:
    content: str
    live: bool


class LlmGateway:
    """Thin OpenAI-compatible gateway with a deterministic local fallback."""

    MODEL_CHECK_RETRIES = 3

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: AsyncOpenAI | None = None
        if settings.ai_api_key:
            self._client = AsyncOpenAI(
                api_key=settings.ai_api_key,
                base_url=settings.ai_base_url,
            )

    def _failure_detail(self, exc: Exception) -> str:
        """Return provider context instead of hiding the real fallback cause."""
        detail = str(exc).strip() or type(exc).__name__
        cause = exc.__cause__ or exc.__context__
        if cause and str(cause).strip() and str(cause).strip() not in detail:
            detail = f"{detail}; cause={str(cause).strip()}"
        return (
            f"provider={self.settings.ai_base_url.rstrip('/')} "
            f"model={self.settings.ai_model or '<unset>'}; "
            f"error_type={type(exc).__name__}; detail={detail}"
        )

    @staticmethod
    def _is_retryable_network_error(exc: Exception) -> bool:
        name = type(exc).__name__.casefold()
        module = type(exc).__module__.casefold()
        if any(token in name for token in ("connection", "timeout", "network")):
            return True
        if "httpx" in module or "httpcore" in module:
            return True
        return getattr(exc, "status_code", None) in {408, 429, 500, 502, 503, 504}

    async def complete(
        self,
        *,
        system: str,
        user: str,
        fallback: str,
        temperature: float = 0.6,
        _retry_attempt: int = 0,
    ) -> ChatResult:
        if not self._client:
            return ChatResult(content=fallback, live=False)

        if not self.settings.ai_model or not self.settings.ai_model.strip():
            raise RuntimeError("AI_MODEL 必须配置；当前中转站不支持省略 model")

        try:
            request = {
                "model": self.settings.ai_model.strip(),
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": temperature,
            }
            response = await self._client.chat.completions.create(**request)
        except Exception as exc:
            if self._is_retryable_network_error(exc) and _retry_attempt < 5:
                await asyncio.sleep(min(2 ** _retry_attempt, 8))
                return await self.complete(
                    system=system,
                    user=user,
                    fallback=fallback,
                    temperature=temperature,
                    _retry_attempt=_retry_attempt + 1,
                )
            if self._is_retryable_network_error(exc):
                detail = f"{self._failure_detail(exc)}; 已自动重连5次仍失败"
                raise RuntimeError(f"实时 AI 调用失败，未使用本地回退：{detail}") from exc
            return ChatResult(
                content=f"{fallback}\n\n[本地回退] 实时 AI 调用失败：{exc}",
                live=False,
            )

        content = response.choices[0].message.content or fallback
        return ChatResult(content=content.strip(), live=True)

    async def check_model(self) -> tuple[bool, str | None]:
        """Verify that the configured model is actually routable before UI claims live mode."""
        if not self._client:
            return False, "AI_API_KEY 未配置"
        if not self.settings.ai_model:
            return False, "AI_MODEL 未配置"
        last_error: Exception | None = None
        for attempt in range(self.MODEL_CHECK_RETRIES + 1):
            try:
                models = await self._client.models.list()
                ids = {item.id for item in models.data}
                if self.settings.ai_model not in ids:
                    return False, f"模型 {self.settings.ai_model} 不在服务商可用模型列表中"
                return True, None
            except Exception as exc:
                last_error = exc
                if not self._is_retryable_network_error(exc) or attempt >= self.MODEL_CHECK_RETRIES:
                    break
                # A short exponential backoff smooths over transient provider/network failures.
                await asyncio.sleep(min(2 ** attempt, 4))

        assert last_error is not None
        detail = self._failure_detail(last_error)
        if self._is_retryable_network_error(last_error):
            detail = f"{detail}; 已重试{self.MODEL_CHECK_RETRIES}次"
        return False, detail

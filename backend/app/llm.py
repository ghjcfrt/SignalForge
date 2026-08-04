from __future__ import annotations

from dataclasses import dataclass

from openai import AsyncOpenAI

from backend.app.config import Settings


@dataclass(frozen=True)
class ChatResult:
    content: str
    live: bool


class LlmGateway:
    """Thin OpenAI-compatible gateway with a deterministic local fallback."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: AsyncOpenAI | None = None
        if settings.ai_api_key:
            self._client = AsyncOpenAI(
                api_key=settings.ai_api_key,
                base_url=settings.ai_base_url,
            )

    async def complete(
        self,
        *,
        system: str,
        user: str,
        fallback: str,
        temperature: float = 0.6,
    ) -> ChatResult:
        if not self._client:
            return ChatResult(content=fallback, live=False)

        try:
            request = {
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": temperature,
            }
            # 不填写 AI_MODEL 时不传 model，让兼容中转站自动选择模型。
            if self.settings.ai_model and self.settings.ai_model.strip():
                request["model"] = self.settings.ai_model.strip()
            response = await self._client.chat.completions.create(**request)
        except Exception as exc:
            return ChatResult(
                content=f"{fallback}\n\n[本地回退] 实时 AI 调用失败：{exc}",
                live=False,
            )

        content = response.choices[0].message.content or fallback
        return ChatResult(content=content.strip(), live=True)

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
        if settings.openai_api_key_yw_sf:
            self._client = AsyncOpenAI(
                api_key=settings.openai_api_key_yw_sf,
                base_url=settings.openai_base_url_yw_sf,
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
            response = await self._client.chat.completions.create(
                model=self.settings.openai_model_yw_sf,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
            )
        except Exception as exc:
            return ChatResult(
                content=f"{fallback}\n\n[本地回退] 实时 AI 调用失败：{exc}",
                live=False,
            )

        content = response.choices[0].message.content or fallback
        return ChatResult(content=content.strip(), live=True)


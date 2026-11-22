"""Stateless Gemini invocation boundary; no tool execution, history or HTTP routing."""

from collections.abc import AsyncIterator, Sequence
from typing import Literal, Protocol

import httpx
from google import genai
from google.genai import types

from .settings import ChatSettings


class ProviderUnavailable(RuntimeError):
    """Safe prerequisite failure; do not expose provider exceptions to the browser."""


class ChatProvider(Protocol):
    def stream(
        self, contents: Sequence[types.Content], *, system_instruction: str,
        tools: Sequence[types.Tool] = (),
        function_mode: Literal["AUTO", "ANY", "NONE"] = "AUTO",
    ) -> AsyncIterator[types.GenerateContentResponse]: ...

    async def aclose(self) -> None: ...


def generation_config(
    settings: ChatSettings, *, system_instruction: str, tools: Sequence[types.Tool] = (),
    function_mode: Literal["AUTO", "ANY", "NONE"] = "AUTO",
) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        system_instruction=system_instruction,
        candidate_count=1,
        max_output_tokens=settings.output_token_budget,
        temperature=1.0,
        response_modalities=["TEXT"],
        thinking_config=types.ThinkingConfig(thinking_level=settings.thinking_level, include_thoughts=False),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        tools=list(tools) or None,
        tool_config=types.ToolConfig(function_calling_config=types.FunctionCallingConfig(
            # SDK 2.28 rejects stream_function_call_arguments even when False on
            # Developer API. Do not enable it; validate calls after stream closure.
            mode=function_mode,
        )) if tools else None,
    )


def wire_content(content: types.Content) -> types.Content:
    """The orchestrator tags function results as "tool"; the API carries them as "user"."""
    return content.model_copy(update={"role": "user"}) if content.role == "tool" else content


class GeminiProvider:
    """Yields SDK chunks intact so transient function IDs/signatures are preserved.

    The orchestrator must validate complete function arguments before executing tools,
    hide thought parts, enforce input/turn/tool budgets, and discard raw packets after
    each turn. It must not persist SDK chunks in messages or artifact metadata.
    """

    def __init__(self, settings: ChatSettings):
        if settings.gemini_api_key is None:
            raise ProviderUnavailable("GEMINI_API_KEY is not configured")
        self.settings = settings
        self._client = genai.Client(
            api_key=settings.gemini_api_key.get_secret_value(),
            vertexai=False, enterprise=False,
            http_options=types.HttpOptions(
                api_version=settings.api_version,
                timeout=settings.provider_timeout_seconds * 1000,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )

    async def stream(
        self, contents: Sequence[types.Content], *, system_instruction: str,
        tools: Sequence[types.Tool] = (),
        function_mode: Literal["AUTO", "ANY", "NONE"] = "AUTO",
    ) -> AsyncIterator[types.GenerateContentResponse]:
        for attempt in range(2):
            received = False
            try:
                chunks = await self._client.aio.models.generate_content_stream(
                    model=self.settings.model, contents=[wire_content(c) for c in contents],
                    config=generation_config(self.settings, system_instruction=system_instruction,
                                             tools=tools, function_mode=function_mode),
                )
                try:
                    async for chunk in chunks:
                        received = True
                        yield chunk
                finally:
                    await chunks.aclose()
                return
            except httpx.ReadTimeout:
                if received or attempt:
                    raise

    async def aclose(self) -> None:
        await self._client.aio.aclose()
        self._client.close()

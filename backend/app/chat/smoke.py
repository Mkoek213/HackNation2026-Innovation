"""Explicit, billable provider smoke check: python -m app.chat.smoke.

Uses synthetic Polish text only. At most three generation calls, no real tools,
database, retrieval startup, persistent context, or raw provider logging.
"""

import asyncio
from typing import Literal

from pydantic import BaseModel, ConfigDict
from google.genai import types

from .provider import GeminiProvider, ProviderUnavailable
from .settings import load_chat_settings


class EchoArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: Literal["Zażółć gęślą jaźń."]


async def check() -> None:
    settings = load_chat_settings().model_copy(update={"output_token_budget": 512})
    provider = GeminiProvider(settings)
    instruction = "Odpowiadaj krótko po polsku. To test z danymi syntetycznymi."
    try:
        async with asyncio.timeout(settings.turn_deadline_seconds):
            deltas = []
            async for chunk in provider.stream(
                [types.Content(role="user", parts=[types.Part(text="Przywitaj się po polsku.")])],
                system_instruction=instruction,
            ):
                for candidate in chunk.candidates or []:
                    for part in candidate.content.parts if candidate.content else []:
                        if part.text and not part.thought:
                            deltas.append(part.text)
            if not "".join(deltas).strip():
                raise RuntimeError("No streamed text")
            print(f"Polish streaming check: text received in {len(deltas)} delta(s)")

            tools = [types.Tool(function_declarations=[types.FunctionDeclaration(
                name="echo", description="Harmless synthetic echo; no side effects.",
                parameters_json_schema=EchoArguments.model_json_schema(),
            )])]
            prompt = types.Content(role="user", parts=[types.Part(
                text='Wywołaj echo z text równym "Zażółć gęślą jaźń.".'
            )])
            parts = []
            async for chunk in provider.stream(
                [prompt], system_instruction=instruction, tools=tools, function_mode="ANY",
            ):
                for candidate in chunk.candidates or []:
                    if candidate.content:
                        parts.extend(candidate.content.parts or [])
            # Execute only after the stream has closed and the full arguments validate.
            calls = [part.function_call for part in parts if part.function_call]
            if len(calls) != 1 or calls[0].name != "echo":
                raise RuntimeError("Expected one echo function call")
            call = calls[0]
            args = EchoArguments.model_validate(call.args)
            result = types.Part(function_response=types.FunctionResponse(
                id=call.id, name="echo", response={"text": args.text},
            ))
            answer = []
            async for chunk in provider.stream(
                [prompt, types.Content(role="model", parts=parts),
                 types.Content(role="tool", parts=[result])],
                system_instruction=instruction, tools=tools, function_mode="NONE",
            ):
                for candidate in chunk.candidates or []:
                    for part in candidate.content.parts if candidate.content else []:
                        if part.text and not part.thought:
                            answer.append(part.text)
            if not "".join(answer).strip():
                raise RuntimeError("No response after the stub result")
            print("Function-call check: validated echo and result continuation passed")
    finally:
        await provider.aclose()


def main() -> int:
    try:
        asyncio.run(check())
    except ProviderUnavailable:
        print("BLOCKED: export an authorized backend GEMINI_API_KEY; no request was made")
        return 2
    except Exception:
        # Provider exceptions and validation errors may contain request/secret content.
        print("FAILED: provider smoke check did not complete; no raw payload is logged")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Backend-only configuration loaded explicitly, without import-time side effects."""

import os
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class ChatSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    gemini_api_key: SecretStr | None = Field(default=None, repr=False)
    model: Literal["gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-3.8-flash"] = "gemini-3.1-flash-lite"
    api_version: Literal["v1beta"] = "v1beta"
    provider_timeout_seconds: int = Field(default=60, ge=1, le=120)
    turn_deadline_seconds: int = Field(default=600, ge=1, le=600)
    # UTF-8 bytes per model request. System prompt, tool declarations and the tool result
    # reserve alone take about 40 KB, so a smaller budget leaves no room for the conversation.
    input_token_budget: int = Field(default=250000, ge=256, le=1000000)
    output_token_budget: int = Field(default=8192, ge=64, le=8192)
    tool_call_budget: int = Field(default=128, ge=0, le=512)
    source_timeout_seconds: int = Field(default=15, ge=1, le=60)
    source_max_bytes: int = Field(default=10000000, ge=1024, le=34000000)
    owner_cookie_name: Literal["radar_chat_owner"] = "radar_chat_owner"
    owner_cookie_secure: bool = True

    @property
    def thinking_level(self) -> Literal["minimal", "low"]:
        """Lowest thinking level the model accepts; newer models reject "minimal"."""
        return "low" if self.model == "gemini-3.8-flash" else "minimal"

    @field_validator("gemini_api_key")
    @classmethod
    def nonblank_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not value.get_secret_value().strip():
            return None
        return value


def load_chat_settings() -> ChatSettings:
    """Use exported GEMINI_API_KEY only; never inherit another provider/key implicitly."""
    mapping = {
        "gemini_api_key": "GEMINI_API_KEY", "model": "CHAT_GEMINI_MODEL",
        "api_version": "CHAT_GEMINI_API_VERSION",
        "provider_timeout_seconds": "CHAT_PROVIDER_TIMEOUT_SECONDS",
        "turn_deadline_seconds": "CHAT_TURN_DEADLINE_SECONDS",
        "input_token_budget": "CHAT_INPUT_TOKEN_BUDGET",
        "output_token_budget": "CHAT_OUTPUT_TOKEN_BUDGET",
        "tool_call_budget": "CHAT_TOOL_CALL_BUDGET",
        "source_timeout_seconds": "CHAT_SOURCE_TIMEOUT_SECONDS",
        "source_max_bytes": "CHAT_SOURCE_MAX_BYTES",
        "owner_cookie_secure": "CHAT_OWNER_COOKIE_SECURE",
    }
    return ChatSettings(**{field: os.environ[name] for field, name in mapping.items() if name in os.environ})

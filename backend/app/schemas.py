"""Public API contract (request/response bodies). Field names follow the assignment exactly."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

ResolutionSource = Literal["LIVE_INFERENCE", "LLM_CACHE"]

MAX_MESSAGE_CHARS = 4000
MAX_SESSION_ID_CHARS = 128
MAX_SYSTEM_PROMPT_CHARS = 8000


class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=False)

    session_id: Annotated[str, StringConstraints(min_length=1, max_length=MAX_SESSION_ID_CHARS)]
    # Trimmed *before* the 1–4000 length check, as the contract requires.
    message: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_MESSAGE_CHARS)
    ]
    system_prompt: Annotated[str, StringConstraints(max_length=MAX_SYSTEM_PROMPT_CHARS)] | None = None

    @field_validator("session_id")
    @classmethod
    def _session_id_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("session_id must not be blank")
        return value

    @field_validator("system_prompt")
    @classmethod
    def _blank_system_prompt_is_unset(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class ChatMetadata(BaseModel):
    resolution_source: ResolutionSource
    model: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    key_id: str | None
    fallback_attempts: int


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    metadata: ChatMetadata


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    metadata: ChatMetadata | None = Field(default=None)
    created_at: str


class HistoryResponse(BaseModel):
    session_id: str
    messages: list[HistoryMessage]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    keys_configured: int
    cache_enabled: bool
    model: str
    failure_simulation_enabled: bool

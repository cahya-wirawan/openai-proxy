from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ExtraAllowModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class ChatMessage(ExtraAllowModel):
    role: Literal["system", "developer", "user", "assistant", "tool"]
    content: Any
    name: str | None = None
    tool_call_id: str | None = None


class ChatCompletionsRequest(ExtraAllowModel):
    model: str
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None
    max_completion_tokens: int | None = None
    reasoning_effort: Literal["minimal", "low", "medium", "high", "xhigh"] | None = None
    user: str | None = None


class ResponsesRequest(ExtraAllowModel):
    model: str
    input: Any
    instructions: str | None = None
    stream: bool = False
    previous_response_id: str | None = None
    reasoning: dict[str, Any] | None = None
    max_output_tokens: int | None = None
    metadata: dict[str, Any] | None = None
    user: str | None = None


class ErrorDetail(BaseModel):
    message: str
    type: str = "invalid_request_error"
    param: str | None = None
    code: str | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorDetail

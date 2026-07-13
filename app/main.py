from __future__ import annotations

import asyncio
import hmac
import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from .codex_service import CodexNotAuthenticated, codex_service
from .config import settings
from .schemas import ChatCompletionsRequest, ResponsesRequest
from .utils import (
    chat_messages_to_prompt,
    model_to_dict,
    new_id,
    responses_input_to_prompt,
    sse,
    sse_done,
    unix_time,
    usage_to_openai,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await codex_service.start()
    try:
        yield
    finally:
        await codex_service.stop()


app = FastAPI(
    title="Local Codex OpenAI-Compatible Proxy",
    version="0.1.0",
    docs_url="/docs" if settings.expose_docs else None,
    redoc_url="/redoc" if settings.expose_docs else None,
    lifespan=lifespan,
)


async def verify_api_key(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> None:
    supplied = x_api_key
    if authorization and authorization.lower().startswith("bearer "):
        supplied = authorization[7:].strip()

    if not supplied or not hmac.compare_digest(supplied, settings.proxy_api_key):
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "message": "Invalid proxy API key",
                    "type": "invalid_request_error",
                    "code": "invalid_api_key",
                }
            },
        )


@app.exception_handler(CodexNotAuthenticated)
async def auth_error_handler(_: Request, exc: CodexNotAuthenticated):
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "message": str(exc),
                "type": "authentication_error",
                "code": "codex_not_authenticated",
            }
        },
    )


@app.exception_handler(Exception)
async def generic_error_handler(_: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "message": str(exc),
                "type": "server_error",
                "code": exc.__class__.__name__,
            }
        },
    )


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/models", dependencies=[Depends(verify_api_key)])
async def list_models() -> dict[str, Any]:
    models = await codex_service.models()
    return {
        "object": "list",
        "data": [
            {
                "id": model["id"],
                "object": "model",
                "created": 0,
                "owned_by": "openai-codex",
            }
            for model in models
        ],
    }


def reasoning_effort_from_responses(body: ResponsesRequest) -> str | None:
    if not body.reasoning:
        return None
    effort = body.reasoning.get("effort")
    return str(effort) if effort else None


@app.post("/v1/responses", dependencies=[Depends(verify_api_key)])
async def create_response(body: ResponsesRequest):
    response_id = new_id("resp")
    created_at = unix_time()
    prompt = responses_input_to_prompt(body.input)
    instructions = body.instructions
    effort = reasoning_effort_from_responses(body)

    if body.stream:
        async def event_stream() -> AsyncIterator[bytes]:
            sequence = 0
            yield sse(
                {
                    "type": "response.created",
                    "sequence_number": sequence,
                    "response": {
                        "id": response_id,
                        "object": "response",
                        "created_at": created_at,
                        "status": "in_progress",
                        "model": body.model,
                        "output": [],
                    },
                }
            )
            sequence += 1

            full_text = ""
            async with codex_service.stream(
                prompt=prompt,
                model=body.model,
                developer_instructions=instructions,
                effort=effort,
                thread_id=body.previous_response_id,
            ) as (deltas, result_box, thread_id):
                output_item_id = new_id("msg")
                yield sse(
                    {
                        "type": "response.output_item.added",
                        "sequence_number": sequence,
                        "output_index": 0,
                        "item": {
                            "id": output_item_id,
                            "type": "message",
                            "status": "in_progress",
                            "role": "assistant",
                            "content": [],
                        },
                    }
                )
                sequence += 1

                async for delta in deltas:
                    full_text += delta
                    yield sse(
                        {
                            "type": "response.output_text.delta",
                            "sequence_number": sequence,
                            "item_id": output_item_id,
                            "output_index": 0,
                            "content_index": 0,
                            "delta": delta,
                        }
                    )
                    sequence += 1

                result = result_box.get("result")
                if result is not None and not full_text:
                    full_text = result.final_response or ""

                usage = usage_to_openai(
                    getattr(result, "usage", None) if result else None
                )
                response_obj = {
                    "id": response_id,
                    "object": "response",
                    "created_at": created_at,
                    "status": "completed",
                    "model": body.model,
                    "output": [
                        {
                            "id": output_item_id,
                            "type": "message",
                            "status": "completed",
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": full_text,
                                    "annotations": [],
                                }
                            ],
                        }
                    ],
                    "output_text": full_text,
                    "usage": {
                        "input_tokens": usage["prompt_tokens"],
                        "output_tokens": usage["completion_tokens"],
                        "total_tokens": usage["total_tokens"],
                    },
                    "metadata": {
                        **(body.metadata or {}),
                        "codex_thread_id": thread_id,
                    },
                }

                yield sse(
                    {
                        "type": "response.completed",
                        "sequence_number": sequence,
                        "response": response_obj,
                    }
                )
                yield sse_done()

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    result, thread_id = await codex_service.run(
        prompt=prompt,
        model=body.model,
        developer_instructions=instructions,
        effort=effort,
        thread_id=body.previous_response_id,
    )
    text = result.final_response or ""
    usage = usage_to_openai(result.usage)

    return {
        "id": response_id,
        "object": "response",
        "created_at": created_at,
        "status": "completed",
        "model": body.model,
        "output": [
            {
                "id": new_id("msg"),
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": text,
                        "annotations": [],
                    }
                ],
            }
        ],
        "output_text": text,
        "usage": {
            "input_tokens": usage["prompt_tokens"],
            "output_tokens": usage["completion_tokens"],
            "total_tokens": usage["total_tokens"],
        },
        "metadata": {
            **(body.metadata or {}),
            "codex_thread_id": thread_id,
        },
    }


@app.post("/v1/chat/completions", dependencies=[Depends(verify_api_key)])
async def create_chat_completion(body: ChatCompletionsRequest):
    completion_id = new_id("chatcmpl")
    created = unix_time()
    prompt, developer_instructions = chat_messages_to_prompt(body.messages)

    if body.stream:
        async def event_stream() -> AsyncIterator[bytes]:
            yield sse(
                {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": body.model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"role": "assistant", "content": ""},
                            "finish_reason": None,
                        }
                    ],
                }
            )

            async with codex_service.stream(
                prompt=prompt,
                model=body.model,
                developer_instructions=developer_instructions,
                effort=body.reasoning_effort,
            ) as (deltas, result_box, _thread_id):
                async for delta in deltas:
                    yield sse(
                        {
                            "id": completion_id,
                            "object": "chat.completion.chunk",
                            "created": created,
                            "model": body.model,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {"content": delta},
                                    "finish_reason": None,
                                }
                            ],
                        }
                    )

                result = result_box.get("result")
                usage = usage_to_openai(
                    getattr(result, "usage", None) if result else None
                )
                yield sse(
                    {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": body.model,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {},
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": usage,
                    }
                )
                yield sse_done()

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    result, thread_id = await codex_service.run(
        prompt=prompt,
        model=body.model,
        developer_instructions=developer_instructions,
        effort=body.reasoning_effort,
    )
    usage = usage_to_openai(result.usage)

    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "model": body.model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": result.final_response or "",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": usage,
        "system_fingerprint": None,
        "codex_thread_id": thread_id,
    }

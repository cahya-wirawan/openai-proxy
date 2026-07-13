from __future__ import annotations

import json
import time
import uuid
from collections.abc import Iterable
from typing import Any


def unix_time() -> int:
    return int(time.time())


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def model_to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=True)
    if hasattr(value, "dict"):
        return value.dict(exclude_none=True)
    if hasattr(value, "__dict__"):
        return {
            key: item
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    return {"value": value}


def find_first(obj: Any, keys: Iterable[str]) -> Any:
    wanted = set(keys)
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in wanted and value is not None:
                return value
        for value in obj.values():
            found = find_first(value, wanted)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = find_first(value, wanted)
            if found is not None:
                return found
    return None


def extract_event_method(event: Any) -> str:
    data = model_to_dict(event)
    return str(
        data.get("method")
        or data.get("type")
        or data.get("event")
        or event.__class__.__name__
    )


def extract_text_delta(event: Any) -> str | None:
    data = model_to_dict(event)
    method = extract_event_method(event).lower()

    # Codex app-server's canonical streaming notification.
    if "agentmessage" in method and "delta" in method:
        value = find_first(data, ("delta", "text"))
        return value if isinstance(value, str) else None

    # Keep this tolerant across beta SDK protocol model changes.
    if method.endswith("delta") or "message_delta" in method:
        value = find_first(data, ("delta", "text", "content"))
        return value if isinstance(value, str) else None

    return None


def sse(data: Any, *, event: str | None = None) -> bytes:
    prefix = f"event: {event}\n" if event else ""
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"{prefix}data: {payload}\n\n".encode("utf-8")


def sse_done() -> bytes:
    return b"data: [DONE]\n\n"


def flatten_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                item_type = item.get("type")
                if item_type in {"text", "input_text", "output_text"}:
                    parts.append(str(item.get("text", "")))
                elif "content" in item:
                    parts.append(flatten_content(item["content"]))
        return "\n".join(part for part in parts if part)
    if isinstance(content, dict):
        if "text" in content:
            return str(content["text"])
        if "content" in content:
            return flatten_content(content["content"])
    return str(content)


def responses_input_to_prompt(value: Any) -> str:
    if isinstance(value, str):
        return value

    if isinstance(value, list):
        sections: list[str] = []
        for item in value:
            if isinstance(item, dict):
                role = item.get("role", "user")
                content = flatten_content(item.get("content", item))
                if content:
                    sections.append(f"{str(role).upper()}:\n{content}")
            else:
                text = flatten_content(item)
                if text:
                    sections.append(text)
        return "\n\n".join(sections)

    if isinstance(value, dict):
        role = value.get("role")
        content = flatten_content(value.get("content", value))
        return f"{str(role).upper()}:\n{content}" if role else content

    return str(value)


def chat_messages_to_prompt(messages: list[Any]) -> tuple[str, str | None]:
    transcript: list[str] = []
    developer_instructions: list[str] = []

    for message in messages:
        data = model_to_dict(message)
        role = data.get("role", "user")
        content = flatten_content(data.get("content"))

        if role in {"system", "developer"}:
            if content:
                developer_instructions.append(content)
            continue

        if role == "tool":
            tool_id = data.get("tool_call_id", "unknown")
            transcript.append(f"TOOL RESULT ({tool_id}):\n{content}")
        else:
            transcript.append(f"{str(role).upper()}:\n{content}")

    prompt = "\n\n".join(transcript).strip()
    instructions = "\n\n".join(developer_instructions).strip() or None
    return prompt, instructions


def usage_to_openai(usage: Any) -> dict[str, int]:
    data = model_to_dict(usage) if usage is not None else {}

    input_tokens = find_first(
        data,
        ("input_tokens", "inputTokens", "total_input_tokens", "totalInputTokens"),
    )
    output_tokens = find_first(
        data,
        ("output_tokens", "outputTokens", "total_output_tokens", "totalOutputTokens"),
    )

    input_count = int(input_tokens or 0)
    output_count = int(output_tokens or 0)

    return {
        "prompt_tokens": input_count,
        "completion_tokens": output_count,
        "total_tokens": input_count + output_count,
    }

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from openai_codex import ApprovalMode, AsyncCodex, Sandbox

from .config import settings
from .utils import extract_text_delta, model_to_dict


class CodexNotAuthenticated(RuntimeError):
    pass


class CodexService:
    def __init__(self) -> None:
        self.client: AsyncCodex | None = None
        self.semaphore = asyncio.Semaphore(settings.max_concurrency)

    async def start(self) -> None:
        self.client = AsyncCodex()
        await self.client.__aenter__()

        account = await self.client.account(refresh_token=True)
        account_data = model_to_dict(account)
        if not account_data.get("account"):
            raise CodexNotAuthenticated(
                "Codex is not authenticated. Run `codex login` first, "
                "or run `python subscription_codex.py login`."
            )

    async def stop(self) -> None:
        if self.client is not None:
            await self.client.__aexit__(None, None, None)
            self.client = None

    def _require_client(self) -> AsyncCodex:
        if self.client is None:
            raise RuntimeError("Codex service is not initialized")
        return self.client

    def _sandbox(self) -> Sandbox:
        return (
            Sandbox.workspace_write
            if settings.allow_workspace_write
            else Sandbox.read_only
        )

    async def models(self) -> list[dict[str, Any]]:
        response = await self._require_client().models()
        data = model_to_dict(response)
        candidates = (
            data.get("data")
            or data.get("models")
            or data.get("items")
            or []
        )

        output: list[dict[str, Any]] = []
        for model in candidates:
            item = model_to_dict(model)
            model_id = (
                item.get("id")
                or item.get("model")
                or item.get("slug")
                or item.get("name")
            )
            if model_id:
                output.append(item | {"id": str(model_id)})
        return output

    async def run(
        self,
        *,
        prompt: str,
        model: str,
        developer_instructions: str | None = None,
        effort: str | None = None,
        thread_id: str | None = None,
    ) -> tuple[Any, str]:
        async with self.semaphore:
            client = self._require_client()
            kwargs = {
                "model": model,
                "cwd": str(settings.workspace),
                "sandbox": self._sandbox(),
                "approval_mode": ApprovalMode.deny_all,
                "developer_instructions": developer_instructions,
            }

            if thread_id:
                thread = await client.thread_resume(thread_id, **kwargs)
            else:
                thread = await client.thread_start(ephemeral=True, **kwargs)

            result = await asyncio.wait_for(
                thread.run(prompt, effort=effort),
                timeout=settings.request_timeout_seconds,
            )
            return result, thread.id

    @asynccontextmanager
    async def stream(
        self,
        *,
        prompt: str,
        model: str,
        developer_instructions: str | None = None,
        effort: str | None = None,
        thread_id: str | None = None,
    ) -> AsyncIterator[tuple[AsyncIterator[str], Any, str]]:
        await self.semaphore.acquire()
        client = self._require_client()

        try:
            kwargs = {
                "model": model,
                "cwd": str(settings.workspace),
                "sandbox": self._sandbox(),
                "approval_mode": ApprovalMode.deny_all,
                "developer_instructions": developer_instructions,
            }

            if thread_id:
                thread = await client.thread_resume(thread_id, **kwargs)
            else:
                thread = await client.thread_start(ephemeral=True, **kwargs)

            handle = await thread.turn(prompt, effort=effort)
            result_box: dict[str, Any] = {}

            async def deltas() -> AsyncIterator[str]:
                async for event in handle.stream():
                    delta = extract_text_delta(event)
                    if delta:
                        yield delta
                result_box["result"] = await handle.run()

            yield deltas(), result_box, thread.id
        finally:
            self.semaphore.release()


codex_service = CodexService()

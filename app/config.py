from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    proxy_api_key: str = os.getenv("PROXY_API_KEY", "local-secret")
    default_model: str = os.getenv("CODEX_DEFAULT_MODEL", "gpt-5.4")
    workspace: Path = Path(os.getenv("CODEX_WORKSPACE", ".")).expanduser().resolve()
    allow_workspace_write: bool = os.getenv(
        "CODEX_ALLOW_WORKSPACE_WRITE", "false"
    ).lower() in {"1", "true", "yes", "on"}
    max_concurrency: int = int(os.getenv("CODEX_MAX_CONCURRENCY", "4"))
    request_timeout_seconds: int = int(
        os.getenv("CODEX_REQUEST_TIMEOUT_SECONDS", "600")
    )
    expose_docs: bool = os.getenv("EXPOSE_DOCS", "true").lower() in {
        "1", "true", "yes", "on"
    }


settings = Settings()

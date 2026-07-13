# Local Codex OpenAI-Compatible Proxy

A local FastAPI service that exposes a subset of the OpenAI API while using
the official `openai-codex` Python SDK and your existing ChatGPT/Codex login.

Supported routes:

- `GET /v1/models`
- `POST /v1/responses`
- `POST /v1/chat/completions`
- SSE streaming for both generation routes
- `GET /healthz`

> This is a compatibility adapter, not the official OpenAI Platform API.
> Keep it local/private. It does not convert a ChatGPT plan into general API
> credits, and it supports only the subset implemented here.

## 1. Install

Python 3.10 or newer:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Authenticate with ChatGPT/Codex

Use the helper:

```bash
python subscription_codex.py login
```

For a headless server:

```bash
python subscription_codex.py login --device-code
```

Alternatively, install the official Codex CLI and run:

```bash
codex login
```

Verify:

```bash
python subscription_codex.py account
```

## 3. Start the proxy

```bash
export PROXY_API_KEY="local-secret"
export CODEX_WORKSPACE="$PWD"
export CODEX_ALLOW_WORKSPACE_WRITE=false

uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Interactive API documentation is at:

```text
http://127.0.0.1:8000/docs
```

## 4. Use the official OpenAI Python client

Install it only in the client environment:

```bash
pip install openai
```

### Responses API

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8000/v1",
    api_key="local-secret",
)

response = client.responses.create(
    model="gpt-5.4",
    input="Explain this repository in three bullets.",
)

print(response.output_text)
print(response.metadata)
```

### Responses streaming

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8000/v1",
    api_key="local-secret",
)

with client.responses.stream(
    model="gpt-5.4",
    input="Write a concise explanation of RAG.",
) as stream:
    for event in stream:
        if event.type == "response.output_text.delta":
            print(event.delta, end="", flush=True)
```

### Chat Completions

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8000/v1",
    api_key="local-secret",
)

completion = client.chat.completions.create(
    model="gpt-5.4",
    messages=[
        {"role": "system", "content": "Answer concisely."},
        {"role": "user", "content": "What is atrial fibrillation?"},
    ],
)

print(completion.choices[0].message.content)
```

### Chat Completions streaming

```python
stream = client.chat.completions.create(
    model="gpt-5.4",
    messages=[{"role": "user", "content": "Explain FastAPI."}],
    stream=True,
)

for chunk in stream:
    text = chunk.choices[0].delta.content
    if text:
        print(text, end="", flush=True)
```

## 5. curl examples

```bash
curl http://127.0.0.1:8000/v1/models \
  -H 'Authorization: Bearer local-secret'
```

```bash
curl http://127.0.0.1:8000/v1/responses \
  -H 'Authorization: Bearer local-secret' \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "gpt-5.4",
    "input": "Say hello in Indonesian."
  }'
```

```bash
curl -N http://127.0.0.1:8000/v1/chat/completions \
  -H 'Authorization: Bearer local-secret' \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "gpt-5.4",
    "stream": true,
    "messages": [
      {"role": "user", "content": "Explain OAuth PKCE."}
    ]
  }'
```

## Docker

Authenticate on the host first so that `$HOME/.codex` exists, then run:

```bash
export PROXY_API_KEY="local-secret"
docker compose up --build
```

The Compose file mounts your host Codex credential directory read/write because
the Codex runtime may refresh the OAuth token. Never copy this credential
directory into an image.

## Security

- Bind to `127.0.0.1`; do not expose this directly to the internet.
- Use a strong `PROXY_API_KEY`.
- Keep `CODEX_ALLOW_WORKSPACE_WRITE=false` unless file modification is needed.
- Treat `$HOME/.codex` as a password-equivalent credential store.
- Do not operate this as a public, shared, or resale service.
- Put remote access behind SSH forwarding or a private VPN.

## Compatibility notes

This project translates basic text requests. It does not currently implement:

- OpenAI hosted tools
- function/tool calling
- image/audio/video endpoints
- embeddings
- fine-tuning
- batches
- full Responses item parity
- `n`, logprobs, penalties, or deterministic sampling controls

`previous_response_id` is interpreted as a Codex thread ID only. For explicit
thread reuse, read `metadata.codex_thread_id` from a prior response and provide
that value as `previous_response_id`.

The `openai-codex` package is beta, so SDK types may change before version 1.0.

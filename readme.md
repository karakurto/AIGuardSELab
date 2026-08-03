# AI Guard Demo Agent

A demo project showing how Zscaler AI Guard an be integrated into a LangChain / LangGraph agent pipeline. AI Guard inspects prompts (IN) and responses (OUT) and can **allow**, **mask**, or **block** traffic before it reaches — or leaves — the LLM.

It allows to demo the integration of an AI Agent with AI Guard where AI Guard can be used to inspect and protect prompts/responses. It also showcases the integration with external MCP servers. A default MCP server is configured and points to dlptest.com for DLP testing. 


It ships two entry points that share the same agent core:

| Component | File | Port | Purpose |
|-----------|------|------|---------|
| Streamlit UI | `app.py` | `8501` | Interactive chat demo with sidebar controls (mode, provider, MCP tools, RAG upload) |
| SPLX proxy API | `api.py` | `8000` | `splx-proxy-sdk` server: `/open-session`, `/send-message`, `/close-session` |

Both are built on `agent_core.py` (agent construction + chat loop) and `aiguard_utils.py` (the AI Guard HTTP client).

## Inspection modes

- **DAS** (Detection as a Service) — AI Guard runs as LangChain middleware. The prompt/response is sent to the AI Guard policy engine and blocked/masked according to the policy. Requires `GUARDRAIL_DAS_API_KEY` **and** `GUARDRAIL_DAS_POLICY_ID`.
- **Proxy** — traffic is routed through the Zscaler reverse proxy (`proxy.zseclipse.net`) via a request header. Requires `GUARDRAIL_PROXY_API_KEY`.

A mode only appears in the UI if its required environment variables are set.

---

## Prerequisites

- **Python 3.14+** (see `.python-version`)
- **[uv](https://docs.astral.sh/uv/)** — used for dependency management and running the app
- **[Ollama](https://ollama.com/)** running locally — **required even when using Anthropic**, because the RAG vector store uses the `nomic-embed-text` embedding model. Pull it once:
  ```bash
  ollama pull nomic-embed-text
  ```
  (If you plan to use the local `Ollama` LLM provider too, also pull that model.)
- API keys — at minimum an `ANTHROPIC_API_KEY`, plus the AI Guard key(s) for whichever inspection mode you want to demo.

---

## Configure environment variables

The app loads configuration from a `.env` file in the project root (via `python-dotenv`). Create one by copying the example below.

> ⚠️ `.env` contains secrets — it should **never** be committed. Confirm it is in `.gitignore`.

### `.env` example

```dotenv
# ── LLM provider ─────────────────────────────────────────────
# Required when using Anthropic as the provider (the default).
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxxxxx
# Optional — override the default Anthropic endpoint (e.g. a gateway).
# Only used when Proxy mode is NOT active.
# ANTHROPIC_BASE_URL=https://your-anthropic-compatible-endpoint

# Required when using the OpenAI provider.
# OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
# Optional — override the default OpenAI endpoint (e.g. an OpenAI-compatible
# gateway). Only used when Proxy mode is NOT active.
# OPENAI_BASE_URL=https://your-openai-compatible-endpoint/v1

# ── AI Guard: DAS mode (Detection as a Service) ──────────────
# Both are required for "DAS" mode to appear and work.
GUARDRAIL_DAS_API_KEY=your-das-bearer-token
GUARDRAIL_DAS_POLICY_ID=your-policy-id

# ── AI Guard: Proxy mode ─────────────────────────────────────
# Required for "Proxy" mode.
GUARDRAIL_PROXY_API_KEY=your-proxy-api-key

# ── SPLX proxy API (api.py) ──────────────────────────────────
# Required to run the API. Validated against the incoming x-api-key header.
SPLX_PROXY_API_KEY=your-splx-proxy-key

# ── LangSmith tracing (all optional) ─────────────────────────
# LANGSMITH_TRACING=true
# LANGSMITH_ENDPOINT=https://api.smith.langchain.com
# LANGSMITH_API_KEY=lsv2_xxxxxxxxxxxxxxxxxxxxxxxx
# LANGSMITH_PROJECT=xxxxx
```

### Variable reference

| Variable | Required? | Used for |
|----------|-----------|----------|
| `ANTHROPIC_API_KEY` | Yes (for Anthropic provider) | Authenticates calls to Claude models |
| `ANTHROPIC_BASE_URL` | Optional | Overrides the default Anthropic endpoint for the Anthropic provider; ignored in Proxy mode |
| `GUARDRAIL_DAS_API_KEY` | For DAS mode | Bearer token for the AI Guard policy engine |
| `GUARDRAIL_DAS_POLICY_ID` | For DAS mode | Which AI Guard policy to enforce |
| `GUARDRAIL_PROXY_API_KEY` | For Proxy mode | `X-ApiKey` header sent to the Zscaler proxy |
| `SPLX_PROXY_API_KEY` | Yes (to run the API) | Validated against the `x-api-key` header by the SPLX proxy SDK; required at startup |
| `OPENAI_API_KEY` | Optional | Only if using the OpenAI provider |
| `OPENAI_BASE_URL` | Optional | Overrides the default OpenAI endpoint for the OpenAI provider; ignored in Proxy mode |
| `LANGSMITH_TRACING` / `LANGSMITH_ENDPOINT` / `LANGSMITH_API_KEY` / `LANGSMITH_PROJECT` | Optional | LangSmith run tracing/observability |
| `OLLAMA_HOST` | Optional | Overrides the Ollama base URL (set automatically in Docker to reach the host) |
| `MCP_CONFIG_FILE` | Optional | Path to the MCP tool config file (default `mcp_tools.json`) — see [MCP tool configuration](#mcp-tool-configuration) |

> 💡 The Streamlit sidebar has an **AI Guard Configuration** section that lets you edit any `GUARDRAIL_*` value at runtime and save it back to `.env`.

---

## Run locally

Install dependencies (creates a `.venv` from `uv.lock`):

```bash
uv sync
```

Make sure Ollama is running (`ollama serve`) and `nomic-embed-text` is pulled. Otherwise, you won't be able to use the RAG database. RAG only supports .txt files at this time for testing.

### Streamlit UI - To run the UI

```bash
uv run streamlit run app.py
```

Then open http://localhost:8501.

### SPLX proxy API - To run in API mode (useful to test against AI Red Teaming)

The API implements the [splx-proxy-sdk](https://pypi.org/project/splx-proxy-sdk/) `Server` contract, so it can be driven by the SPLX platform (or any client that speaks the SDK's protocol).

**`SPLX_PROXY_API_KEY` must be set before startup** — the SDK validates the `x-api-key` header against it and raises at import time if it is missing.

```bash
SPLX_PROXY_API_KEY=your-secret uv run uvicorn api:app --reload --port 8000
```

- Testing UI: http://localhost:8000/ (mounted by the SDK)
- Health check: `GET http://localhost:8000/health`
- Interactive docs: http://localhost:8000/docs

### API usage

The API is **session-based**. You open a session (which builds the agent for a given provider/model/mode), send one or more messages referencing that session, then close it (which discards the agent). Conversation history is kept per session.

Every request must include the `x-api-key` header matching `SPLX_PROXY_API_KEY`. Provider/model/mode and the AI Guard inspection flags are passed in the SDK's `extra_args` object.

#### Endpoints

| Method & path | Purpose |
|---------------|---------|
| `POST /open-session` | Create an agent and start a session; returns a `session_id` |
| `POST /send-message` | Send a message to an open session |
| `POST /close-session` | Terminate a session and discard its agent |
| `GET /health` | Liveness check |

#### `POST /open-session`

Request body:

| Field | Type | Notes |
|-------|------|-------|
| `session_id` | string \| null | Optional. A new UUID is generated if omitted |
| `extra_args` | object \| null | Optional session config (see below) |

`extra_args` fields:

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `provider` | string | `"Anthropic"` | `Anthropic`, `OpenAI`, or `Ollama` |
| `model` | string | `"claude-haiku-4-5-20251001"` | Model id for the provider |
| `mode` | string | `"DAS"` | `DAS` (AI Guard middleware) or `Proxy` (Zscaler reverse proxy) |
| `inspect_prompt` | bool | `true` | Run AI Guard on the prompt (IN) |
| `inspect_response` | bool | `true` | Run AI Guard on the response (OUT) |

Response: `{ "session_id": "<uuid>" }`

#### `POST /send-message`

Request body:

| Field | Type | Notes |
|-------|------|-------|
| `session_id` | string | **Required.** From `/open-session` |
| `message` | string | **Required.** The user message |

Response: `{ "session_id": "<uuid>", "message": "<assistant text>" }`

Returns **404** (`NOT_FOUND`) if the `session_id` does not match an open session.

#### `POST /close-session`

Request body: `{ "session_id": "<uuid>" }` → Response: `{}` (idempotent — closing an unknown session still succeeds).

#### Full example

```bash
KEY=your-secret

# 1. Open a session (builds the agent). Config goes in extra_args.
SID=$(curl -s -X POST http://localhost:8000/open-session \
  -H "Content-Type: application/json" -H "x-api-key: $KEY" \
  -d '{"extra_args":{"provider":"Anthropic","model":"claude-haiku-4-5-20251001","mode":"DAS"}}' \
  | jq -r .session_id)

# 2. Send a message
curl -s -X POST http://localhost:8000/send-message \
  -H "Content-Type: application/json" -H "x-api-key: $KEY" \
  -d "{\"session_id\":\"$SID\",\"message\":\"Hello!\"}"

# 3. Close the session (discards the agent)
curl -s -X POST http://localhost:8000/close-session \
  -H "Content-Type: application/json" -H "x-api-key: $KEY" \
  -d "{\"session_id\":\"$SID\"}"
```

> Reuse the same `session_id` across multiple `/send-message` calls to continue a conversation with memory.

---

## MCP tool configuration

The agent can call external [MCP](https://modelcontextprotocol.io/) tools. Their configuration is stored in a JSON file — **`mcp_tools.json`** by default (override the path with the `MCP_CONFIG_FILE` environment variable).

The file is **created automatically on first run**, seeded with the `dlptest` DLP testing tool as an example:

```json
{
  "dlptest": {
    "url": "https://mcp.dlptest.com/api/mcp/",
    "headers": {}
  }
}
```

Each entry is keyed by the tool name and has:
- `url` — the MCP server endpoint (HTTP transport).
- `headers` — optional HTTP headers sent with every request (e.g. an `Authorization` bearer token).

### Editing via the UI (recommended)

In the Streamlit sidebar, open the **MCP Tools** section:
- **Add** a tool with a name, URL, and optional headers (as a JSON object). On save, the tool is added and `mcp_tools.json` is rewritten.
- **Remove** a tool with its **Remove** button; the file is updated too.

Changes take effect immediately — the agent is rebuilt with the new tool set.

### Editing the file directly

You can also edit `mcp_tools.json` by hand, for example to add a tool with an auth header:

```json
{
  "dlptest": {
    "url": "https://mcp.dlptest.com/api/mcp/",
    "headers": {}
  },
  "weather": {
    "url": "https://example.com/mcp/",
    "headers": { "Authorization": "Bearer <token>" }
  }
}
```

Restart the app (or refresh the Streamlit session) for hand-edited changes to load.

> ⚠️ `mcp_tools.json` can contain secrets (tokens in `headers`), so it is **git-ignored** by default. Delete the file to reset back to the seeded `dlptest` example on the next run.

---

## Run with Docker

The `Dockerfile` + `docker-compose.yml` run **both** the Streamlit UI and the FastAPI server in a single container. The `.env` file is loaded via `env_file`, and `OLLAMA_HOST` is set to `http://host.docker.internal:11434` so the container can reach Ollama running on your host.

```bash
docker compose up --build
```

- Streamlit UI → http://localhost:8501
- FastAPI REST → http://localhost:8000

> On **Linux**, `host.docker.internal` isn't available by default — add `extra_hosts: ["host.docker.internal:host-gateway"]` to the `app` service (or run Ollama in its own container; a commented-out service is included in `docker-compose.yml`).

---

## Project layout

```
app.py            # Streamlit UI
api.py            # FastAPI REST layer
agent_core.py     # Agent construction, AI Guard middleware, chat loop
aiguard_utils.py  # AIGuardClient — HTTP client for the AI Guard policy API
Dockerfile        # Builds the combined UI + API image
docker-compose.yml
entrypoint.sh     # Starts uvicorn (bg) + streamlit (fg) in the container
pyproject.toml    # Dependencies (managed by uv)
.streamlit/       # Streamlit theme config
```

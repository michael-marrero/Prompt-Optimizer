# Stack Research — Prompt-Optimizer Chat Milestone

**Domain:** Open-source, BYOK, multi-turn AI chat app with classifier-based prompt routing (chat + agentic coding + computer-use) — brownfield addition to an existing scikit-learn pipeline.
**Researched:** 2026-05-11
**Overall confidence:** HIGH for web/Python infra, FastAPI, Vercel AI SDK, claude-agent-sdk, computer-use, uv, SQLModel, keyring, testing. MEDIUM for OpenRouter Python SDK (two viable canonical paths) and for `assistant-ui` vs raw `@ai-sdk/react`.

**Scope guard:** This file only covers the *new* additions (FastAPI server, Next.js front-end, live LLM/agent integrations, BYOK, persistent threads, new agentic-intent head). The existing `scikit-learn / pandas / numpy / scipy / joblib / sentence-transformers / nltk` Python stack stays as-is and is *not* re-researched here.

---

## TL;DR — Recommended Stack

| Layer | Choice | Why |
|---|---|---|
| Python package manager | **uv 0.5+** (with `pyproject.toml` + `uv.lock`) | 10-100x faster than pip, replaces pip+venv+pyenv, single tool, lockfile is canonical in 2026 |
| Backend framework | **FastAPI 0.135+** on **Uvicorn 0.32+** | Built-in `EventSourceResponse` from `fastapi.sse` since 0.135, pydantic v2 native, async-first |
| ASGI workers | **single `uvicorn --workers N` process**, no gunicorn wrapper | Modern uvicorn supports `--workers` directly; gunicorn no longer needed for FastAPI |
| Sklearn model sharing | **Load once in module scope** under `--workers 1` for dev; `--preload` with gunicorn-uvicorn for multi-worker prod | joblib artifacts are ~1-4 MB each — fork-after-load via `--preload` shares pages COW |
| Validation | **pydantic v2** (already required by FastAPI 0.135+) | Pydantic v1 deprecated in FastAPI; v2 is the only safe target |
| Streaming protocol | **SSE via the AI SDK UI Message Stream Protocol** (`x-vercel-ai-ui-message-stream: v1` header) | Industry standard; works with `useChat` directly; reconnect/keep-alive built in |
| Frontend framework | **Next.js 15.2.x** (stable, App Router, React 19) | Next.js 16 is GA but new; 15.x is the conservative "boring" production choice for an OSS demo |
| Chat UI | **`@ai-sdk/react` `useChat` v5** + **`assistant-ui` primitives** | `useChat` for transport, `assistant-ui` for composable React thread/composer primitives |
| Chat persistence | **SQLite via SQLModel 0.0.22+** (FastAPI-native; built on SQLAlchemy 2.0) | One file, zero ops, type-safe, perfect for local BYOK |
| OpenRouter | **OpenAI Python SDK 1.x pointed at `https://openrouter.ai/api/v1`** (BYOK env var) | Still the canonical OpenRouter-recommended path; their own `openrouter` Python SDK exists but is newer/less proven |
| Claude Code (agentic coding) | **`claude-agent-sdk` 0.1.80+** | Official 2026 successor to `claude-code-sdk` (renamed March 2026); CLI bundled in package |
| Anthropic computer-use | **`anthropic` SDK 0.40+** with `computer_20251124` tool + `anthropic-beta: computer-use-2025-11-24` header against **Claude Opus 4.7** (or Sonnet 4.6 to save cost) | Newest tool version (Nov 2025); Opus 4.7/Sonnet 4.6 are the only models supporting it |
| Sandbox host for computer-use | **Reference Docker container** `ghcr.io/anthropics/anthropic-quickstarts:computer-use-demo-latest` | Anthropic-maintained Xvfb + Mutter + Tint2 + Firefox/LibreOffice container; ports 5900/6080/8080/8501 |
| New agentic-intent head | **Logistic Regression on top of `all-MiniLM-L6-v2` embeddings** (mirrors existing `embedding_router` recipe), with **SetFit** as an upgrade path if labels are <100 | Cheapest, fastest, debuggable; reuses existing pattern |
| BYOK key storage | **`keyring` 25+** (OS keychain) primary, **`.env` via `python-dotenv`** fallback | Keychain is the secure default; `.env` for headless/CI dev |
| Repo layout | **Monorepo:** `apps/web` (Next.js), `apps/api` (FastAPI), preserve existing `src/` (Python ML), `models/`, `config/`, `data_processed/` at root | Minimal disruption to existing pipeline + clean app boundaries |
| Python testing | **pytest 8.4+** + **pytest-anyio** + **httpx 0.27+ AsyncClient with ASGITransport** | The 2026 default; do NOT use `TestClient` for async streaming |
| Frontend testing | **Vitest 2.x** + **React Testing Library 16+** + **Playwright 1.45+** for E2E | Vitest replaces Jest for new projects; Playwright for streaming/E2E across the whole stack |

---

## Recommended Stack — Detailed

### Backend: FastAPI + Uvicorn

| Technology | Version | Purpose | Why Recommended |
|---|---|---|---|
| FastAPI | **>= 0.135.0** | HTTP/SSE server, pydantic v2 validation, OpenAPI generation | 0.135 ships `EventSourceResponse` in `fastapi.sse` with Rust-side pydantic serialization; first FastAPI that *natively* streams SSE without a third-party shim. Pydantic v1 path is deprecated. |
| Uvicorn | **>= 0.32.0** | ASGI server | Modern uvicorn supports `--workers` directly; do not wrap in gunicorn unless you also need a process supervisor. |
| pydantic | **>= 2.7** | Request/response models, settings | Native FastAPI 0.135 path; faster than v1; required for new SSE serialization |
| pydantic-settings | **>= 2.4** | `.env` loading for BYOK keys | Replaces `BaseSettings` in pydantic v1 |
| httpx | **>= 0.27** | Async HTTP client for OpenRouter forwarding, tests | Async streams, ASGITransport for tests; `requests` is sync-only and unsuitable |
| python-multipart | **>= 0.0.9** | Form-data (avatar / attachment upload, if any) | Required by FastAPI for file uploads |
| anyio | **>= 4.4** | Async runtime primitives | Required by `claude-agent-sdk`; matches FastAPI's anyio backend |
| sse-starlette | optional, **>= 2.1** | Older SSE response class | Only needed if pinning FastAPI < 0.135. Prefer `fastapi.sse.EventSourceResponse` on 0.135+. |

**Minimum viable wiring (one process, models loaded once):**

```python
# apps/api/src/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.sse import EventSourceResponse, ServerSentEvent
import joblib

ML = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    ML["task"] = joblib.load("models/task_type_classifier.joblib")
    ML["router"] = joblib.load("models/model_router.joblib")
    ML["intent"] = joblib.load("models/agentic_intent.joblib")  # new milestone
    yield
    ML.clear()

app = FastAPI(lifespan=lifespan)

@app.post("/api/chat")
async def chat(req: ChatRequest):
    async def stream():
        async for evt in route_and_stream(req, ML):
            yield ServerSentEvent(data=evt.model_dump_json())
    return EventSourceResponse(stream(), headers={"x-vercel-ai-ui-message-stream": "v1"})
```

**Async vs sync for LLM streaming:** All LLM calls MUST be async. Wrap any blocking sklearn `predict` call in `asyncio.to_thread()` if it ever gets large; today's joblib classifiers (~1-4 MB) are fast enough to call synchronously inside an async handler with negligible blocking.

**Worker model for production:**
- **Dev:** `uvicorn apps.api.src.main:app --reload --workers 1` (models load once, hot reload works).
- **Prod (single-user local app):** `uvicorn apps.api.src.main:app --workers 1`. Workers don't help an open-source single-user app; they 4x memory.
- **Prod (if multi-user ever needed):** `gunicorn -w 4 -k uvicorn.workers.UvicornWorker --preload apps.api.src.main:app`. `--preload` loads the FastAPI app (and the joblib models) once in the parent, then forks workers; COW page sharing keeps RSS down.

**DO NOT** put joblib loading inside a per-request dependency — it'll reload on every request. Load once in `lifespan` and reach into the module-level `ML` dict.

### Frontend: Next.js + AI SDK + assistant-ui

| Technology | Version | Purpose | Why Recommended |
|---|---|---|---|
| Next.js | **15.2.x** (latest stable 15.x as of May 2026) | App Router, RSC, routing | Conservative pick. Next.js 16 (Oct 2025) is GA but introduces Cache Components, `proxy.ts` rename, async `params/searchParams`, Turbopack-default — too much churn for an OSS demo. Stay on 15 unless we need Cache Components. |
| React | **19.x** | UI library | Required by Next.js 15+; stable since 2024 |
| TypeScript | **>= 5.4** | Type safety | Next.js 16 requires 5.1+; 5.4 gives `using` declarations and faster project references |
| `ai` | **>= 5.0** | AI SDK core (server-side helpers + stream protocol) | v5 redesigned `useChat` with custom transports — required for our FastAPI backend |
| `@ai-sdk/react` | **>= 2.0** | `useChat`, `useCompletion` hooks | v5-aligned package; consumes the SSE UI Message Stream protocol our FastAPI produces |
| `assistant-ui` | **>= 0.10** (`@assistant-ui/react` + `@assistant-ui/react-ai-sdk`) | Composable thread / composer / message-list primitives | YC W25, ~50k monthly downloads, dominant chat-UI primitive lib in 2026; plays nicely with `useChat` |
| Tailwind CSS | **>= 4.0** | Styling | Tailwind v4 is GA, ships with `@tailwindcss/postcss`, faster, zero-config |
| shadcn/ui | latest | Component primitives (Button, Dialog, Sidebar) | Pairs with `assistant-ui` (same Radix-based primitives) |
| Zustand | **>= 5.0** | Minimal client state (selected thread, settings panel) | Lighter than Redux/Jotai for our needs; AI SDK already owns the message-state |
| Zod | **>= 3.23** | Runtime parsing of API responses, route schema | Pairs with AI SDK tool calling |

**Why both `@ai-sdk/react` AND `assistant-ui`:**
- `useChat` from `@ai-sdk/react` is the *transport* (POST to `/api/chat`, parse SSE stream, append messages). Use it as-is.
- `assistant-ui` is the *components* (ThreadPrimitive, ComposerPrimitive, MessagePrimitive, sidebar/history). Bring it in for the actual UI rather than building from scratch.
- The two integrate via `@assistant-ui/react-ai-sdk`'s `useChatRuntime({ api: "/api/chat" })`.

**Streaming from FastAPI to `useChat`:** Use the **AI SDK UI Message Stream Protocol** (SSE-based, v5+). Your FastAPI route must:
1. Return `text/event-stream` media type.
2. Set header `x-vercel-ai-ui-message-stream: v1`.
3. Emit events of the shape `{"type":"start","messageId":...}`, `{"type":"text-start","id":...}`, `{"type":"text-delta","id":...,"delta":"..."}`, `{"type":"text-end","id":...}`, `{"type":"finish"}`.
4. End with the literal `data: [DONE]\n\n`.

**DO NOT** use the older "Data Stream Protocol" (text-only) — it's been replaced by the UI Message Stream protocol in AI SDK v5 and gives you tool-call and metadata channels for free.

**DO NOT** use Next.js as an API host for the routing backend. Run FastAPI as a separate process on `localhost:8000`; Next.js dev proxies `/api/chat` to it via `next.config.ts` `rewrites`. The Python ML pipeline cannot live inside Next.js.

### LLM/Agent Backends

#### 1. OpenRouter (chat models)

| Technology | Version | Purpose |
|---|---|---|
| `openai` (Python SDK) | **>= 1.40** | Canonical OpenRouter client (BYOK) — point `base_url` at OpenRouter |

OpenRouter publishes their own `openrouter` Python SDK in 2026, but the **OpenAI-SDK-pointed-at-OpenRouter** pattern is still officially supported, more battle-tested, and gives us streaming + tool calls with zero learning curve. Use the OpenAI SDK.

**Minimum viable wiring:**

```python
from openai import AsyncOpenAI

client = AsyncOpenAI(
    api_key=settings.OPENROUTER_API_KEY,   # from keyring or .env
    base_url="https://openrouter.ai/api/v1",
    default_headers={
        "HTTP-Referer": "https://github.com/<user>/Prompt-Optimizer",
        "X-Title": "Prompt-Optimizer",
    },
)

async def stream_openrouter(model: str, messages: list[dict]):
    stream = await client.chat.completions.create(
        model=model,                  # e.g. "openai/gpt-5" — from config/model_mapping.json
        messages=messages,
        stream=True,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
```

**DO NOT** use the OpenAI Python SDK v0.x (legacy, removed in 2024) — it's `import openai; openai.ChatCompletion.create(...)` style. The v1.x SDK is `from openai import OpenAI; client.chat.completions.create(...)`. Our pinned `>= 1.40` ensures correct path.

**Headers:** `HTTP-Referer` and `X-Title` are optional (only affect OpenRouter leaderboard attribution). Always send them; they cost nothing.

**Tool calling on OpenRouter:** Works identically to OpenAI tool calling — `tools=[...]`, `tool_choice="auto"`. Streaming tool calls arrive as `delta.tool_calls[...]` deltas; reassemble per `index`. Same code path as OpenAI direct.

**Key handling:** Read `OPENROUTER_API_KEY` from `keyring` first, fall back to `os.getenv`. Never log it. The OpenAI SDK does not log the API key by default.

#### 2. Claude Agent SDK (agentic coding)

| Technology | Version | Purpose |
|---|---|---|
| `claude-agent-sdk` | **>= 0.1.80** (May 2026) | Spawn Claude agents for coding/build-and-edit work |

**Critical naming history (do NOT confuse):**
- **`claude-code-sdk`** (PyPI) — **DEPRECATED** March 2026, no longer maintained. Do not install.
- **`claude-agent-sdk`** (PyPI) — current package, renamed from `claude-code-sdk` to reflect broader-than-just-coding scope.
- API symbol rename: `ClaudeCodeOptions` → **`ClaudeAgentOptions`**. Any stale tutorial referencing `ClaudeCodeOptions` is pre-March 2026 and broken.
- The Claude Code **CLI is automatically bundled** with `claude-agent-sdk`. No separate `npm install -g claude-code` needed — but the user must have the Anthropic API key set (`ANTHROPIC_API_KEY`).

**Minimum viable wiring (FastAPI handler → streaming agent → SSE to UI):**

```python
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

async def run_coding_agent(prompt: str, cwd: str):
    options = ClaudeAgentOptions(
        allowed_tools=["Read", "Write", "Edit", "Bash"],  # auto-approve
        permission_mode="acceptEdits",                     # auto-accept file edits
        cwd=cwd,                                            # workspace dir
        system_prompt="You are a build-and-edit coding agent.",
    )
    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt)
        async for message in client.receive_response():
            yield message    # AssistantMessage / ToolUseBlock / ToolResultBlock / etc.
```

**Permission model for an open-source BYOK product:**
- Default to `permission_mode="acceptEdits"` only when the agent's `cwd` is inside a user-designated **workspace directory** (e.g. `~/prompt-optimizer-workspaces/<thread_id>/`). Never point it at the user's home dir or the repo root.
- For any tool not in `allowed_tools`, install a `can_use_tool` async callback that posts back to the front-end and waits for a human approval click. Pattern is documented in the Agent SDK ref.
- Surface tool calls to the UI as a separate stream channel — emit `{"type":"tool-call","name":"Bash","input":{"command":"..."}}` and `{"type":"tool-result", ...}` deltas in the SSE stream so the user sees what the agent did.

**DO NOT** run the agent as a fire-and-forget background task without storing its output stream. Wrap each agent run in a per-thread async task whose generator pipes into the SSE response — if the user disconnects mid-run, cancel the task (use `anyio.create_task_group` + cancellation).

#### 3. Anthropic computer-use (browser/desktop actions)

| Technology | Version | Purpose |
|---|---|---|
| `anthropic` (Python SDK) | **>= 0.40** | Direct Claude API client for computer-use beta calls |
| Docker | **>= 24** | Runs the reference sandbox container locally |
| Reference container | `ghcr.io/anthropics/anthropic-quickstarts:computer-use-demo-latest` | Anthropic-maintained Xvfb + Mutter + Tint2 + Firefox + LibreOffice + tool implementations + agent loop |

**Tool version (verify before you ship):**
- **`computer_20251124`** (Nov 2025) — newest. Adds `zoom` action. Requires beta header **`computer-use-2025-11-24`**. Supported on **Claude Opus 4.7, Opus 4.6, Sonnet 4.6, Opus 4.5**.
- **`computer_20250124`** (Jan 2025) — older. Supported on Sonnet 4.5, Haiku 4.5, Opus 4.1, Sonnet 4, Opus 4, Sonnet 3.7 (deprecated). Requires beta header **`computer-use-2025-01-24`**.

**Recommended target:** `claude-opus-4-7` with `computer_20251124`. If cost matters, **`claude-sonnet-4-6`** with `computer_20251124` is the lighter-cost option that still supports the new zoom action and was specifically optimized for computer-use (61.4% OSWorld on Sonnet 4.5).

**Companion tool versions** (use these alongside computer-use in the same request):
- `text_editor_20250728` (str_replace_based_edit_tool) — required for Claude 4.x models
- `bash_20250124`

**Required HTTP beta header:** `anthropic-beta: computer-use-2025-11-24`

**Minimum viable wiring — host the sandbox:**

```bash
export ANTHROPIC_API_KEY=$(security find-generic-password -s prompt-optimizer/anthropic -w)
docker run \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  -v $HOME/.anthropic:/home/computeruse/.anthropic \
  -p 5900:5900 -p 8501:8501 -p 6080:6080 -p 8080:8080 \
  -it ghcr.io/anthropics/anthropic-quickstarts:computer-use-demo-latest
```

Ports: 5900 = raw VNC; 6080 = web-based VNC (noVNC); 8501 = the demo's built-in Streamlit UI; 8080 = combined chat + desktop iframe.

**Wiring the sandbox to OUR FastAPI:** We do **not** use the demo container's bundled Streamlit UI. We use the container as a *display + execution sandbox* and run our own agent loop inside FastAPI:
1. User prompts "open lakers.com and tell me tonight's score" → router classifies as agentic-browse.
2. FastAPI calls `anthropic.beta.messages.create` with `tools=[computer_20251124, text_editor_20250728, bash_20250124]` and `betas=["computer-use-2025-11-24"]`.
3. For each `tool_use` block, FastAPI translates to a screenshot/click/type request against the Docker container's VNC port. (Easiest path: re-use the action handlers from `computer_use_demo/computer_use_demo/tools/` — they're open source.)
4. Pipe screenshots back to Claude as `tool_result` blocks.
5. Stream both Claude's text output AND each screenshot URL/blob to the UI via SSE so the user sees the desktop live alongside the chat.

**Coordinate scaling caveat:** API constrains images to 1568px on the long edge for older models (1.15 MP total). Opus 4.7 supports 2576px on the long edge with 1:1 coordinates. Implement the scale-factor helper from the docs (`get_scale_factor`) or you'll get clicks that miss their targets.

**DO NOT** ship computer-use without a Docker prerequisite check in the FastAPI startup hook. A user without Docker will hit a confusing tool-call failure mid-stream. Surface "Docker not detected — install Docker Desktop to enable browse-and-act agent" in the settings panel.

### New Agentic-Intent Classifier (Binary)

| Technology | Version | Purpose |
|---|---|---|
| sentence-transformers | already pinned | `all-MiniLM-L6-v2` embeddings (existing pattern) |
| scikit-learn | already pinned | LogisticRegression (existing pattern) |
| setfit | **>= 1.1** (optional upgrade) | Few-shot fine-tune sentence-transformer + LR head when labels < 100 |

**Recommended recipe (matches existing `embedding_router` exactly):**
1. Label ~500-2000 prompts as `agentic={0,1}` (conversational vs build-me/do-this).
2. Encode each prompt with `SentenceTransformer("all-MiniLM-L6-v2")` (same model already cached by existing pipeline; **reuses existing `data_processed/emb_router_*_l2_fam.npy` cache infrastructure**).
3. Fit `LogisticRegression(class_weight="balanced", solver="lbfgs", C=4.0, max_iter=2000)` on the 384-dim embeddings.
4. Persist as `models/agentic_intent.joblib` with the same artifact-dict shape:
   `{"model", "scaler" (None), "label_encoder", "target_column", "embedding_model_name": "sentence-transformers/all-MiniLM-L6-v2", ...}`.
5. Inference: encode prompt once, predict_proba → threshold at 0.5 (tunable on holdout).

**Why this over alternatives:**
- vs **TF-IDF + handcrafted features** (existing `task_type_classifier` recipe): embeddings generalize better to phrasings the training set didn't see — exactly what an intent head needs ("build me an app" vs "make me an app" vs "scaffold an app" should all cluster).
- vs **fine-tuning a tiny BERT**: 100x training cost, no quality gain at this dataset size.
- vs **LLM-as-judge** (call Sonnet to classify): per-turn cost + latency unacceptable for a router that runs *before* the real LLM call.

**Upgrade path if labels are scarce (< 100 examples):** Switch to **SetFit** (`huggingface/setfit`). Trains the sentence-transformer contrastively on label pairs, then LR head. Outperforms zero-shot + LR with as few as 8 examples per class. Costs ~30s on a CPU. Same artifact-dict output shape, so the routing decision layer stays unchanged.

**Latency budget:** `all-MiniLM-L6-v2` encode + LR predict is < 30ms on CPU. Run synchronously in the FastAPI handler (no `to_thread` needed).

### Persistence

| Technology | Version | Purpose |
|---|---|---|
| SQLite | bundled with Python 3.10+ | Local single-file DB for chat threads and messages |
| SQLModel | **>= 0.0.22** | FastAPI-native ORM (SQLAlchemy 2.0 + pydantic v2 hybrid) |
| Alembic | **>= 1.13** | Schema migrations |
| aiosqlite | **>= 0.20** | Async SQLite driver |

**Recommended schema (per-backend message shape via JSON):**

```python
from sqlmodel import SQLModel, Field, JSON, Column

class Thread(SQLModel, table=True):
    id: str = Field(primary_key=True)           # uuid7
    title: str
    created_at: datetime
    updated_at: datetime

class Message(SQLModel, table=True):
    id: str = Field(primary_key=True)
    thread_id: str = Field(foreign_key="thread.id", index=True)
    role: str                                   # "user" | "assistant" | "tool"
    backend: str                                # "openrouter" | "claude_agent" | "computer_use"
    model_id: str | None = None                 # "openai/gpt-5", "claude-opus-4-7", etc.
    content: dict = Field(sa_column=Column(JSON))   # variable shape per backend
    rationale: str | None = None                # router rationale chip text
    created_at: datetime
```

**Why JSON for `content`:** Each backend produces a different message shape (OpenRouter = OpenAI-style text/tool_calls; Claude agent SDK = tool_use/tool_result blocks; computer-use = screenshots + actions). Forcing a unified schema loses information. Store the raw per-backend payload; the front-end uses `backend` to discriminate-render.

**Connection:** `sqlite+aiosqlite:///./chat.db` (single file at repo root, gitignored).

**Why not Postgres / Redis / file-based JSON:**
- Postgres: zero benefit for a single-user local app; adds ops burden.
- Redis: not durable by default; chat history must survive restarts.
- File-based JSON: doesn't support queries; horrible at concurrent writes.

**Why SQLModel over raw SQLAlchemy 2.0:** Pydantic v2 + SQLAlchemy 2.0 typing baked in, perfect FastAPI integration. The repo already uses `dict | None` PEP 604 syntax so SQLModel's type-first DX is a natural fit. The only downside (less control for exotic queries) doesn't apply to chat history CRUD.

**Why not SQLAlchemy 1.x style:** Async support is bolted on; 2.0 is async-native and the only version SQLModel >= 0.0.22 targets.

### BYOK Key Management

| Technology | Version | Purpose |
|---|---|---|
| `keyring` | **>= 25** | OS-native credential vault (macOS Keychain, Windows Credential Locker, GNOME libsecret) |
| `python-dotenv` | **>= 1.0** | `.env` file fallback for headless/CI |
| `pydantic-settings` | **>= 2.4** | Composes both sources into a single `Settings` model |

**Recommended pattern:**

```python
# apps/api/src/config.py
import keyring
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    OPENROUTER_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None
    GOOGLE_API_KEY: str | None = None

    @classmethod
    def from_keyring_then_env(cls) -> "Settings":
        kr = lambda name: keyring.get_password("prompt-optimizer", name)
        return cls(
            OPENROUTER_API_KEY=kr("OPENROUTER_API_KEY"),
            ANTHROPIC_API_KEY=kr("ANTHROPIC_API_KEY"),
            GOOGLE_API_KEY=kr("GOOGLE_API_KEY"),
        )

settings = Settings.from_keyring_then_env() or Settings()  # env fallback
```

**Front-end settings panel writes:** Next.js settings page POSTs `{ provider, api_key }` to `/api/settings/keys`. FastAPI handler calls `keyring.set_password("prompt-optimizer", provider, api_key)`. The key never lands on disk in plaintext (keyring uses the OS secure store).

**Never** store keys in `localStorage`, IndexedDB, or any frontend store. The user's browser is not a secure vault.

**DO NOT** commit `.env` files. `.env.example` ships in the repo with placeholders; `.gitignore` excludes `.env`.

**Sandbox note:** The repo's existing `.claude/settings.local.json` deny-list already protects `/Library/Application Support/ClaudeCode/`, but does NOT protect `keyring` vault — that's fine because keyring delegates to the OS keychain (out-of-process), and the OS prompts for unlock on each access.

### Repo / Package Layout

**Recommended layout (extends current repo, doesn't move anything):**

```
Prompt-Optimizer/
├── pyproject.toml                # NEW — uv-managed, single source of truth
├── uv.lock                       # NEW — committed
├── .python-version               # NEW — uv-managed, "3.11"
├── package.json                  # NEW — pnpm workspace root
├── pnpm-workspace.yaml           # NEW
├── apps/
│   ├── web/                      # NEW — Next.js 15 app
│   │   ├── package.json
│   │   ├── next.config.ts
│   │   └── src/
│   └── api/                      # NEW — FastAPI app
│       ├── pyproject.toml        # nested project, refers back to root via workspace
│       └── src/
│           ├── main.py
│           ├── routing.py        # composes existing classifiers + new intent head
│           ├── backends/
│           │   ├── openrouter.py
│           │   ├── claude_agent.py
│           │   └── computer_use.py
│           └── persistence/
├── src/                          # EXISTING — ML pipeline, untouched
│   ├── feature_extraction/
│   ├── task_classifier/
│   ├── model_router/
│   ├── model_router_tier/
│   ├── evaluation/
│   └── demo/
├── models/                       # EXISTING — joblib artifacts (now includes agentic_intent.joblib)
├── config/                       # EXISTING — model_mapping.json
├── data_processed/               # EXISTING — git-LFS CSVs
└── tests/
    ├── api/                      # NEW — pytest
    └── web/                      # NEW — vitest
```

**Why this layout (and not `frontend/` + `backend/`):**
- `apps/` is the Turborepo/pnpm convention; adding `apps/admin/` or `apps/cli/` later is trivial.
- Existing `src/` is the Python ML library, NOT a generic app — keeping it at the root preserves all the brittle `PROJECT_ROOT = .../src/...` path conventions catalogued in `CONVENTIONS.md`. Moving `src/` would break every training script.
- `models/`, `config/`, `data_processed/`, `evaluation/` stay at root because the existing training scripts compute paths relative to them and the FastAPI app needs to load `models/*.joblib` at startup.

**Python package manager: `uv`** (NOT poetry, NOT pip-tools).

| Tool | Verdict | Reason |
|---|---|---|
| **uv** | **PICK THIS** | 10-100x faster, single tool for venv + install + lock + python install + script entrypoints, drop-in for pip. The 2026 consensus default. |
| poetry | skip | Still good for library publishing, but uv is catching up and faster. No reason to add a slower tool to an OSS project that wants minimum dev friction. |
| pip-tools | skip | Enterprise-plain choice; perfectly fine but no advantages over uv in 2026. |
| conda | skip | Heavyweight; not needed since we don't have GPU/CUDA pinning concerns (sentence-transformers wheels are sufficient). |
| pip + requirements.txt | skip | No lockfile; current repo state is exactly this and it's the cause of the "no requirements lockfile committed" gap noted in `STACK.md`. |

**Lockfile:** `uv.lock` committed. Pinned versions for every transitive dep.

**Python version:** Adopt **Python 3.11** as the target (existing codebase requires 3.10+; 3.11 gives ~15% perf boost on FastAPI workloads, ExceptionGroups for cleaner async error handling). Pin via `.python-version`.

**Node package manager: `pnpm` 9+.** Lighter than npm, supports workspaces natively for `apps/web` + future packages. Tracker-free.

**Optional later: Turborepo** for caching `pnpm build` across CI. Not needed for v1.

### Testing

| Technology | Version | Purpose | Why Recommended |
|---|---|---|---|
| pytest | **>= 8.4** | Python test runner | Standard; required by other libs |
| pytest-anyio | **>= 0.4** | Async test support | Cleaner than pytest-asyncio for FastAPI (which already uses anyio) |
| httpx | **>= 0.27** | Async test client | Use `AsyncClient(transport=ASGITransport(app=app))` for full async stack |
| pytest-cov | **>= 5.0** | Coverage | Standard |
| respx | **>= 0.21** | Mock httpx for OpenRouter calls in unit tests | Mocks at httpx layer, doesn't need full HTTP server |
| Vitest | **>= 2.0** | Frontend unit/component tests | Replaces Jest; 5-10x faster; shares Vite config; standard in 2026 |
| @testing-library/react | **>= 16** | React component test helpers | Canonical |
| Playwright | **>= 1.45** | E2E across Next.js + FastAPI + (optionally) Anthropic stub | Replaces Cypress as default in 2026; multi-tab, less flaky |
| MSW | **>= 2.4** | Mock fetch at network boundary in vitest | Replaces hand-rolled fetch mocks |

**Minimum viable backend test:**

```python
import pytest
from httpx import AsyncClient, ASGITransport
from apps.api.src.main import app

@pytest.mark.anyio
async def test_route_chat_prompt_returns_sse_stream():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        async with ac.stream("POST", "/api/chat", json={"prompt": "What is 2+2?"}) as r:
            assert r.status_code == 200
            assert r.headers["x-vercel-ai-ui-message-stream"] == "v1"
            chunks = [c async for c in r.aiter_text()]
            assert any("text-delta" in c for c in chunks)
```

**DO NOT** use FastAPI's `TestClient` for streaming tests — it's sync (built on `requests`) and will deadlock or buffer the full SSE stream. Use `httpx.AsyncClient + ASGITransport`.

**Minimum viable frontend test:**

```ts
// apps/web/src/components/__tests__/ChatComposer.test.tsx
import { render, screen } from "@testing-library/react";
import { ChatComposer } from "../ChatComposer";

test("renders composer with placeholder", () => {
  render(<ChatComposer />);
  expect(screen.getByPlaceholderText(/ask anything/i)).toBeInTheDocument();
});
```

**E2E plan:** Playwright spec that boots both servers (uvicorn + next), drives the chat input through a known prompt (`"what is the capital of France"`), and asserts (a) routing chip shows `gemini-2.5-flash` (cheap), (b) streamed answer ends with "Paris". This validates the **routing thesis** end-to-end and matches the "Demo path" requirement in `PROJECT.md`.

### Development Tools

| Tool | Purpose | Notes |
|---|---|---|
| **ruff** >= 0.6 | Python linter + formatter | Replaces black/isort/flake8; 10-100x faster; current repo has no linter — adopt ruff now |
| **mypy** >= 1.11 | Type checker | Optional but recommended for the new `apps/api/src/` code; do NOT run on existing `src/` until conventions doc gaps are fixed |
| **eslint** >= 9 + flat config | JS/TS linter | Next.js 16 deprecated `next lint`; if we ever upgrade, use ESLint directly. On Next 15, use built-in `next lint` for now. |
| **prettier** >= 3.3 | JS/TS formatter | Pair with ESLint via `eslint-config-prettier` |
| **pre-commit** >= 3.8 | Git hook runner | Wraps ruff, mypy, eslint, prettier into a `.pre-commit-config.yaml` |
| **just** or **make** | Task runner | `justfile` with `dev`, `test`, `lint`, `train`, `eval` recipes — saves on Docker-compose complexity |

---

## Installation

```bash
# === Python (uv-managed) ===
curl -LsSf https://astral.sh/uv/install.sh | sh
uv init                                          # creates pyproject.toml + .python-version + uv.lock
uv add fastapi[standard]>=0.135 \
       pydantic>=2.7 pydantic-settings>=2.4 \
       sqlmodel>=0.0.22 aiosqlite>=0.20 alembic>=1.13 \
       httpx>=0.27 anyio>=4.4 \
       openai>=1.40 \
       claude-agent-sdk>=0.1.80 \
       anthropic>=0.40 \
       keyring>=25 python-dotenv>=1.0 \
       setfit>=1.1                               # optional, for low-label intent head

uv add --dev pytest>=8.4 pytest-anyio>=0.4 pytest-cov>=5.0 respx>=0.21 ruff>=0.6 mypy>=1.11 pre-commit>=3.8

# === Node (pnpm-managed) ===
corepack enable && corepack prepare pnpm@9 --activate
mkdir -p apps/web && cd apps/web
pnpm create next-app@latest . --typescript --tailwind --app --src-dir --import-alias "@/*"
pnpm add ai@^5 @ai-sdk/react@^2 @assistant-ui/react@^0.10 @assistant-ui/react-ai-sdk@^0.10 zustand@^5 zod@^3.23
pnpm add -D vitest@^2 @testing-library/react@^16 @testing-library/jest-dom @vitejs/plugin-react jsdom msw@^2.4 @playwright/test@^1.45

# === Docker (computer-use sandbox) ===
# Install Docker Desktop separately. Then:
docker pull ghcr.io/anthropics/anthropic-quickstarts:computer-use-demo-latest
```

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not the Alternative |
|---|---|---|---|
| Backend framework | FastAPI | Flask + flask-sse | No native async; would need quart for async; you'd reinvent SSE; pydantic v2 + OpenAPI gen is missing |
| Backend framework | FastAPI | Django + DRF + Channels | Heavyweight; ORM you don't need; WSGI default; channels adds complexity for streaming |
| Backend framework | FastAPI | LiteStar | Smaller community, fewer FastAPI-native libs (claude-agent-sdk examples all assume FastAPI) |
| Frontend framework | Next.js 15 | Remix / React Router 7 | Smaller AI ecosystem; Vercel AI SDK examples are all Next.js |
| Frontend framework | Next.js 15 | Vite + React SPA | Loses RSC, route prefetch, image optimization; benefits don't justify for a chat app |
| Chat UI | `@ai-sdk/react` + `assistant-ui` | Build from scratch with shadcn | 2-3 weeks of work to reinvent thread/composer/streaming-message primitives |
| Chat UI | `@ai-sdk/react` + `assistant-ui` | CopilotKit | More opinionated, less flexible for multi-backend rendering |
| Streaming | SSE (AI SDK UI Message Stream) | WebSockets | Bidirectional we don't need; harder to debug in browser devtools; SSE is the AI SDK default |
| Streaming | SSE (AI SDK UI Message Stream) | HTTP/2 streaming | No special advantage over SSE for this workload; not supported by `useChat` |
| Streaming | SSE (AI SDK UI Message Stream) | Plain JSONL stream | `useChat` v5 expects the UI Message Stream protocol; raw JSONL means writing a custom transport |
| OpenRouter SDK | OpenAI SDK pointed at OpenRouter | Official `openrouter` Python SDK | Newer (2026), less coverage of edge cases, less StackOverflow surface area. Switch later if attrition pain. |
| OpenRouter SDK | OpenAI SDK | Bare `httpx` POST | Have to reimplement streaming chunk parsing, retry logic, tool-call delta merging |
| Persistence | SQLite + SQLModel | DuckDB | Great for analytics but overkill for chat; embedded write contention is worse than SQLite |
| Persistence | SQLite + SQLModel | LMDB / leveldb | KV store, not relational; chat queries (threads ordered by updated_at) are awkward |
| Persistence | SQLite + SQLModel | LangChain ChatMessageHistory + SQLite | Adds LangChain as a dep we otherwise don't need; chat history schemas are too prescriptive |
| Python pkg mgr | uv | poetry | Slower; uv won the 2026 popularity contest; uv's `uv pip` is drop-in pip compatible |
| Python pkg mgr | uv | conda / mamba | Heavyweight; we have no CUDA pinning concerns |
| Intent classifier | Embedding + LR (existing recipe) | Fine-tune DistilBERT | 10-100x training cost, no quality gain at our dataset size |
| Intent classifier | Embedding + LR (existing recipe) | LLM-as-judge (Sonnet rates intent) | Adds 1-2s latency + per-turn cost to every prompt — fatal for a *router* |
| Intent classifier | Embedding + LR (existing recipe) | Zero-shot NLI with `facebook/bart-large-mnli` | Worse than supervised LR on a small labeled set; ~10x slower per inference |
| Key storage | OS keyring | Local file (`~/.config/prompt-optimizer/keys.json`) | Plaintext on disk; trivial to exfiltrate |
| Key storage | OS keyring | Encrypted file with master password | Re-implementing what the OS already gives you |
| Repo layout | `apps/web` + `apps/api` + `src/` | Two separate repos | Loses atomic commits across UI + API + ML changes; slower onboarding |
| Testing | Vitest | Jest 30 | Jest is fine, but slower; Vitest is the 2026 default for new React projects |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|---|---|---|
| **`claude-code-sdk`** (PyPI) | Deprecated March 2026, no longer maintained, API renamed | **`claude-agent-sdk`** |
| **`ClaudeCodeOptions`** symbol | Renamed in v0.1.0 of the agent SDK | **`ClaudeAgentOptions`** |
| `openai` Python SDK **0.x** (`import openai; openai.ChatCompletion.create`) | Removed in 2024; tutorials predating Nov 2023 use this | `openai` SDK **>= 1.x** (`from openai import OpenAI; client.chat.completions.create`) |
| Pydantic v1 (`from pydantic import BaseModel` from `pydantic.v1`) | Deprecated by FastAPI; will be removed soon | Pydantic v2 (default `from pydantic import BaseModel`) |
| Next.js **Pages Router** | Pre-RSC, hard-coded server lifecycle, missing AI SDK examples | App Router (`app/` dir) |
| Next.js **`getServerSideProps`** | Pages Router only; useless for App Router | Server Components / Route Handlers / Server Actions |
| FastAPI **`TestClient` for streaming tests** | Sync; deadlocks on long streams | `httpx.AsyncClient(transport=ASGITransport(app=app))` |
| `requests` (sync) in FastAPI handlers | Blocks the event loop; will starve the worker under load | `httpx.AsyncClient` |
| Older `computer_20241022` tool type | Replaced by `computer_20250124` (Jan 2025) and `computer_20251124` (Nov 2025) | `computer_20251124` for Claude Opus 4.6+ / Sonnet 4.6+; `computer_20250124` for Sonnet 4.5 and older |
| `sse-starlette` on FastAPI 0.135+ | Redundant — FastAPI now ships `fastapi.sse.EventSourceResponse` natively | `from fastapi.sse import EventSourceResponse` |
| **AI SDK v4 `useChat`** | Pre-v5 transport API; doesn't support custom FastAPI backends cleanly | AI SDK v5+ `useChat` with custom transport |
| AI SDK **Data Stream Protocol** (text-only) | Superseded by UI Message Stream Protocol in v5 | UI Message Stream Protocol (SSE-based) |
| Storing API keys in `.env` committed to git | Obvious; will leak on first push | `.env` in `.gitignore` + keyring as primary store |
| Storing API keys in `localStorage` | Accessible to any third-party script that XSSes the page | Send to FastAPI `/api/settings/keys`, store via `keyring` |
| `pytest-asyncio` (specifically) | Works but `pytest-anyio` is cleaner with FastAPI (which uses anyio internally) | `pytest-anyio` |
| Jest for new React tests in 2026 | Slower, more config, no Vite integration | Vitest |
| Cypress | Replaced by Playwright as 2026 default | Playwright |
| `gunicorn` for single-user OSS desktop app | Adds a process supervisor we don't need | `uvicorn --workers 1` |
| Loading joblib inside a per-request dependency | Reloads on every request (slow + wastes memory) | Load once in FastAPI `lifespan` context manager |

---

## Stack Patterns by Variant

**If user is on macOS / Linux dev box and wants the full demo:**
- Native Python via uv + native pnpm/Next dev server + Docker Desktop for computer-use sandbox.

**If user is on Windows:**
- Same, but Docker Desktop on WSL2. Anthropic container is Linux-only.
- `keyring` uses Windows Credential Locker — works the same.

**If user explicitly skips computer-use:**
- Skip Docker. Skip the computer-use backend wiring. Router falls through to OpenRouter for any prompt the agentic-intent head classifies as agentic-browse — degrade-gracefully banner: "Browse-and-act unavailable; routed to chat model".

**If user wants Claude Code agentic backend OFF (e.g. no Anthropic key):**
- Same degrade pattern. Router falls back to OpenRouter for any prompt classified as agentic-code → routes to a strong coding model (gpt-5 or qwen3-235b-thinking).

**If we ever ship a hosted SaaS version (out of scope today):**
- Switch SQLite → Postgres (SQLModel is compatible).
- Add a real auth layer.
- Add a worker queue (Celery/Arq) so computer-use sandboxes don't block FastAPI workers.
- Move keys from `keyring` to a real secrets manager (AWS Secrets Manager / Doppler).

---

## Version Compatibility

| Package A | Compatible With | Notes |
|---|---|---|
| FastAPI >= 0.135 | pydantic v2 ONLY | Pydantic v1 is deprecated; pinning v1 will break SSE response serialization |
| `claude-agent-sdk` >= 0.1.80 | Python >= 3.10, anyio >= 4 | CLI auto-bundled; conflicts with parallel `claude-code-sdk` install — uninstall the old one first |
| `anthropic` >= 0.40 | Python >= 3.8 | Used for direct computer-use beta calls; agent SDK is separate |
| `computer_20251124` tool | Claude Opus 4.7, Opus 4.6, Sonnet 4.6, Opus 4.5 ONLY | Older models (Sonnet 4.5, Haiku 4.5, etc.) require `computer_20250124` |
| Beta header `computer-use-2025-11-24` | Goes with `computer_20251124` ONLY | Mismatching versions = 400 from the API |
| Next.js 15.2 | React 19 | React 18 is supported but missing useful concurrent features |
| Next.js 16 | React 19.2 + Node.js 20.9+ + TypeScript 5.1+ | Async `params`/`searchParams` mandatory — codemod available but breaks pre-existing Pages Router code |
| AI SDK v5 (`ai@>=5`) | `@ai-sdk/react@>=2` | v4 and v5 are not API-compatible; check imports |
| `useChat` v5 | UI Message Stream Protocol | Old Data Stream Protocol still parses but lacks tool/metadata channels |
| SQLModel >= 0.0.22 | SQLAlchemy 2.0+, pydantic 2.0+ | Don't pin SQLAlchemy < 2 |
| `setfit` >= 1.1 | sentence-transformers >= 3, transformers >= 4.40, torch >= 2.1 | Heavier deps; only add if low-label scenario |
| `keyring` 25+ | macOS Keychain, Windows Credential Locker, libsecret (GNOME) | On headless Linux without libsecret, falls back to plaintext-on-disk — detect this and warn |
| Uvicorn >= 0.32 | httptools, uvloop (on Linux/macOS) | `uv add fastapi[standard]` pulls both |

---

## Sources

**HIGH confidence (Context7/official docs/Anthropic/Vercel/Next.js primary sources):**
- [Anthropic computer use tool docs (current as of 2026)](https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool) — verified `computer_20251124` + beta header + model support
- [Anthropic computer-use-demo Docker reference](https://github.com/anthropics/anthropic-quickstarts/blob/main/computer-use-demo/README.md) — verified port mappings + env vars + image URL
- [Claude Agent SDK Python GitHub](https://github.com/anthropics/claude-agent-sdk-python) — verified package name, version 0.1.80, ClaudeAgentOptions, streaming pattern
- [Claude Agent SDK migration guide (rename from claude-code-sdk)](https://platform.claude.com/docs/en/agent-sdk/migration-guide) — verified deprecation of claude-code-sdk
- [claude-agent-sdk on PyPI](https://pypi.org/project/claude-agent-sdk/) — verified install command + bundled CLI
- [Next.js 16 release notes (Oct 2025)](https://nextjs.org/blog/next-16) — verified React 19.2, Cache Components, Turbopack default
- [AI SDK UI Stream Protocol](https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol) — verified `x-vercel-ai-ui-message-stream: v1` header + event shape
- [AI SDK Python Streaming template (Vercel)](https://vercel.com/templates/next.js/ai-sdk-python-streaming) — verified FastAPI + useChat pattern
- [FastAPI release notes (0.135+ EventSourceResponse)](https://fastapi.tiangolo.com/release-notes/) — verified `fastapi.sse` exists
- [OpenRouter OpenAI SDK integration](https://openrouter.ai/docs/guides/community/openai-sdk) — verified base_url + headers
- [OpenRouter quickstart](https://openrouter.ai/docs/quickstart) — verified BYOK auth pattern

**MEDIUM confidence (community/blog with multiple corroborating sources):**
- [uv vs poetry vs pip-tools 2026 comparison (Scopir / Cuttlesoft / DataCamp)](https://scopir.com/posts/best-python-package-managers-2026/) — multiple 2026 articles agree on uv as default
- [assistant-ui review 2026](https://dev.to/alexander_lukashov/i-evaluated-every-ai-chat-ui-library-in-2026-heres-what-i-found-and-what-i-built-4p10) — community survey of chat UI libs
- [SQLModel vs SQLAlchemy 2.0 guidance](https://sqlmodel.tiangolo.com/) — FastAPI-author-maintained recommendation
- [Vitest + Playwright Next.js testing guide (Strapi blog, official Next.js docs)](https://strapi.io/blog/nextjs-testing-guide-unit-and-e2e-tests-with-vitest-and-playwright) — corroborated by [Next.js Vitest setup docs](https://nextjs.org/docs/app/guides/testing/vitest)
- [SetFit (HuggingFace blog + GitHub)](https://huggingface.co/blog/setfit) — primary maintainer source for few-shot path
- [FastAPI Best Practices monorepo guidance (Vintasoftware)](https://www.vintasoftware.com/blog/nextjs-fastapi-monorepo) — `apps/web` + `apps/api` layout

**LOW confidence (single source, verify before depending):**
- The exact AI SDK v5 → FastAPI message format — verified manually against the AI SDK docs page; subject to revision since v5 is recent. Have a small Playwright E2E test that exercises this end-to-end to catch protocol drift.
- OpenRouter's own `openrouter` Python SDK maturity — listed in their 2026 docs but I have not seen widespread production usage; keeping the OpenAI-SDK-pointed-at-OpenRouter path as the primary recommendation.

---

*Stack research for: Prompt-Optimizer chat-milestone (open-source BYOK chat app over existing scikit-learn router pipeline)*
*Researched: 2026-05-11*

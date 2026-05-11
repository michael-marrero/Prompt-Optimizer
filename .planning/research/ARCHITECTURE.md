# Architecture Research

**Domain:** Auto-routing chat app — Python ML pipeline + FastAPI + Next.js + multi-agent dispatch (OpenRouter / Claude Code SDK / Anthropic computer-use)
**Researched:** 2026-05-11
**Confidence:** HIGH (component shape, data flow, build order — drawn from existing repo conventions + current FastAPI/Next.js streaming patterns); MEDIUM (computer-use adapter shape — Anthropic's surface here is more bespoke and warrants a thin spike in the phase that touches it)

---

## Executive Recommendation

A clean addition layers onto the existing repo without disturbing the offline ML pipeline:

- A new **`src/routing/`** package holds the **pure routing decision module** (composes existing classifier joblibs + new agentic-intent classifier + scoring policy + `model_mapping.json`). It lives under `src/` (not `apps/api/`) so the offline evaluation harness can replay routing on benchmark data without spinning up FastAPI.
- A new **`apps/api/`** FastAPI process loads the joblibs at startup, calls `src/routing/` for the decision, and dispatches via a **uniform backend adapter interface** that produces a single discriminated-union **`ChatChunk`** stream type. The same chunk shape flows over SSE to the UI.
- A new **`apps/web/`** Next.js 15 App Router project owns the chat UI. Messages are POSTed to a Next.js **route handler** that proxies to FastAPI (server-side proxy keeps BYOK keys off the browser-to-FastAPI direct wire path).
- **SQLite via `aiosqlite`** persists threads, messages, and routing decisions in a single file under `~/.prompt-optimizer/` (BYOK-local, open-source posture). One `messages` table; rich content (tool calls, screenshots, diffs) lives in a `content_blocks` JSON column on each message.
- **`pydantic-settings`** centralizes all config: joblib paths, `model_mapping.json` path, backend keys, sandbox URLs. Per-user runtime keys (BYOK) layer on top via an in-process key store seeded from `.env` and overridable from the Settings UI.

The decision module is the keystone — get its interface right and the backend adapters, UI, and storage shape fall out cleanly.

---

## System Overview

```text
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                  USER BROWSER                                        │
│  ┌──────────────────────────────────────────────────────────────────────────┐       │
│  │ Next.js 15 App Router  (apps/web/)                                       │       │
│  │   app/page.tsx                 app/threads/[id]/page.tsx                 │       │
│  │   app/settings/page.tsx        app/api/chat/route.ts  (proxy + SSE pipe) │       │
│  │   components/Composer  MessageList  RoutingChip  BackendBubble/*         │       │
│  │   state: Zustand store (threads, currentThread, streaming chunks)        │       │
│  └─────────────────────────────────┬────────────────────────────────────────┘       │
└─────────────────────────────────────│───────────────────────────────────────────────┘
                                      │ POST /api/chat  (Next.js route handler)
                                      │ SSE downstream  (Next.js → browser)
┌─────────────────────────────────────▼────────────────────────────────────────────────┐
│                       FASTAPI BACK-END  (apps/api/)                                  │
│                                                                                       │
│  POST /threads/{id}/turn  ─────────┐                                                 │
│  GET  /threads                     │                                                 │
│  GET  /threads/{id}                │  EventSourceResponse (SSE)  ──▶ chunks downstream│
│  PATCH /settings                   │                                                 │
│                                    ▼                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐         │
│  │  apps/api/turn_service.py    (orchestrates one chat turn)               │         │
│  │     1. load thread history (storage)                                    │         │
│  │     2. call src.routing.decide(...)                                     │         │
│  │     3. resolve adapter from registry                                    │         │
│  │     4. stream adapter.stream(...), persist on completion                │         │
│  └────────────┬──────────────────────────┬──────────────────────────────┬──┘         │
│               │                          │                              │            │
│               ▼                          ▼                              ▼            │
│  ┌──────────────────────┐  ┌──────────────────────────┐  ┌──────────────────────┐   │
│  │ src.routing.decide() │  │  apps/api/backends/*     │  │  apps/api/storage/*  │   │
│  │  (pure)              │  │  - openrouter.py         │  │  - sqlite.py (aio)   │   │
│  │                      │  │  - claude_code.py        │  │  - schema.sql        │   │
│  │  pipeline of fns:    │  │  - computer_use.py       │  │  - models.py (pyd)   │   │
│  │   classify_task →    │  │  each: async def stream()│  │                      │   │
│  │   classify_agentic → │  │  yielding ChatChunk      │  │                      │   │
│  │   apply_policy →     │  │                          │  │                      │   │
│  │   resolve_route      │  │  shared: chunks.py       │  │                      │   │
│  └──────────┬───────────┘  │  (ChatChunk types)       │  └──────────────────────┘   │
│             │              └──────────┬───────────────┘                              │
│             │                         │                                              │
│             ▼                         ▼                                              │
│  ┌──────────────────────┐  ┌────────────────────────────────────────────┐           │
│  │  Loaded at startup:  │  │  External services (BYOK):                 │           │
│  │   task_type.joblib   │  │   - openrouter.ai/api/v1                   │           │
│  │   model_router.joblib│  │   - claude-agent-sdk (subprocess / lib)    │           │
│  │   agentic_intent     │  │   - Anthropic computer-use (HTTP + tools)  │           │
│  │     .joblib (NEW)    │  └────────────────────────────────────────────┘           │
│  │   model_mapping.json │                                                            │
│  │   PromptFeatureExtr. │                                                            │
│  └──────────────────────┘                                                            │
└──────────────────────────────────────────────────────────────────────────────────────┘
                                      ▲
                                      │ trains, writes joblib
┌─────────────────────────────────────┴────────────────────────────────────────────────┐
│                  EXISTING OFFLINE TRAINING PIPELINE (UNCHANGED)                      │
│  src/data/  src/feature_extraction/  src/task_classifier/  src/model_router*/        │
│  src/evaluation/  src/demo/   →   models/*.joblib + evaluation/*                     │
│                                                                                       │
│  NEW: src/agentic_intent/  (trainer for the new binary head)                         │
│  NEW: src/routing/         (decision module — used by BOTH demo and FastAPI)         │
│  NEW: src/evaluation/evaluate_routing.py  (routes through src/routing/ end-to-end)   │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

**Legend:** Boxes labelled `NEW` are added in this milestone. `apps/api/` and `apps/web/` are new top-level directories. Everything under `src/data/`, `src/feature_extraction/`, `src/task_classifier/`, `src/model_router/`, `src/model_router_tier/`, `src/demo/`, and `src/evaluation/` stays put and stays working.

---

## Component Responsibilities

| Component | Layer | Responsibility | New/Existing |
|-----------|-------|----------------|--------------|
| `PromptFeatureExtractor` | Shared | Handcrafted numeric features from prompt text | Existing (`src/feature_extraction/Feature_extractor.py`) |
| `model_mapping.json` | Shared config | Benchmark slug → `{display_name, provider, tier, api_model, openrouter_verified}` | Existing (`config/model_mapping.json`) |
| `task_type_classifier.joblib` | ML artifact | Stage-1 task type prediction | Existing |
| `model_router.joblib` | ML artifact | Stage-2 exact-model prediction | Existing |
| `agentic_intent_classifier.joblib` | ML artifact | Binary "is this prompt agentic?" head | **New** (trained in `src/agentic_intent/`) |
| `src/routing/loaders.py` | Routing | Pure functions that load joblibs into a frozen `RoutingArtifacts` dataclass | **New** |
| `src/routing/heads.py` | Routing | Pure prediction functions: `classify_task(prompt, artifacts) -> TaskTypeResult` etc. | **New** |
| `src/routing/policy.py` | Routing | "Quality-first within budget, cost as tiebreaker" policy (config-driven) | **New** |
| `src/routing/decide.py` | Routing | Top-level `decide(turn, history, artifacts, settings) -> RoutingDecision` | **New** |
| `src/routing/types.py` | Routing | `RoutingDecision`, `TaskTypeResult`, `AgenticResult`, `Backend` pydantic models | **New** |
| `apps/api/main.py` | API | FastAPI app, lifespan loads artifacts once, mounts routers | **New** |
| `apps/api/turn_service.py` | API | One-turn orchestrator (load history → decide → dispatch → stream → persist) | **New** |
| `apps/api/backends/base.py` | API | `BackendAdapter` Protocol + `ChatChunk` discriminated union | **New** |
| `apps/api/backends/openrouter.py` | API | OpenRouter adapter (text streaming) | **New** |
| `apps/api/backends/claude_code.py` | API | Claude Code SDK adapter (text + tool calls + file diffs) | **New** |
| `apps/api/backends/computer_use.py` | API | Anthropic computer-use adapter (text + tool calls + screenshots) | **New** |
| `apps/api/backends/registry.py` | API | `{Backend.OPENROUTER: OpenRouterAdapter, ...}` + factory function | **New** |
| `apps/api/storage/sqlite.py` | Storage | `aiosqlite` thread/message/routing CRUD | **New** |
| `apps/api/config.py` | Config | `pydantic-settings` Settings class + key store | **New** |
| `apps/web/app/page.tsx` | UI | Landing / new-thread surface | **New** |
| `apps/web/app/threads/[id]/page.tsx` | UI | Active thread view | **New** |
| `apps/web/app/api/chat/route.ts` | UI | Next.js route handler that proxies POST to FastAPI and pipes SSE back | **New** |
| `apps/web/components/Composer.tsx` | UI | Single input box | **New** |
| `apps/web/components/MessageList.tsx` | UI | Renders messages with discriminated-union dispatch | **New** |
| `apps/web/components/RoutingChip.tsx` | UI | "Routed to X because Y" pill per assistant turn | **New** |
| `apps/web/components/BackendBubble/*.tsx` | UI | Per-backend renderer (`ChatBubble`, `CodeBubble`, `ComputerUseBubble`) | **New** |
| `apps/web/store/chat.ts` | UI | Zustand store: threads, currentThread, streamingChunks | **New** |

---

## Recommended Project Structure

```
Prompt-Optimizer/
├── config/
│   └── model_mapping.json                # (existing) benchmark slug → route metadata
│
├── models/                               # (existing) joblib artifacts
│   ├── task_type_classifier.joblib
│   ├── model_router.joblib
│   ├── tier_router.joblib
│   ├── embedding_router.joblib
│   └── agentic_intent_classifier.joblib  # NEW
│
├── src/                                  # (existing tree + new packages)
│   ├── data/                             # unchanged
│   ├── feature_extraction/               # unchanged (Feature_extractor.py reused)
│   ├── task_classifier/                  # unchanged
│   ├── model_router/                     # unchanged
│   ├── model_router_tier/                # unchanged
│   ├── evaluation/
│   │   ├── evaluate_baselines.py         # unchanged
│   │   ├── compare_router_results.py     # unchanged
│   │   └── evaluate_routing.py           # NEW — routes through src/routing/
│   ├── demo/                             # unchanged (still uses joblibs directly)
│   │
│   ├── agentic_intent/                   # NEW — Stage-1.5 trainer
│   │   ├── __init__.py
│   │   ├── build_agentic_dataset.py      # labels prompts agentic vs chat
│   │   └── train_agentic_intent.py       # mirrors train_task_classifier_robust.py
│   │
│   └── routing/                          # NEW — pure decision module
│       ├── __init__.py
│       ├── types.py                      # pydantic models (RoutingDecision, ...)
│       ├── loaders.py                    # load_artifacts() → RoutingArtifacts
│       ├── heads.py                      # classify_task, classify_agentic, predict_model
│       ├── policy.py                     # apply_quality_first_policy
│       ├── decide.py                     # decide(turn, history, artifacts, settings)
│       └── tests/                        # pytest cases with fixture artifacts
│
├── apps/                                 # NEW — runtime applications
│   ├── api/                              # FastAPI service
│   │   ├── __init__.py
│   │   ├── main.py                       # FastAPI app + lifespan
│   │   ├── config.py                     # pydantic-settings
│   │   ├── deps.py                       # DI providers (settings, artifacts, db)
│   │   ├── routers/
│   │   │   ├── threads.py                # /threads CRUD
│   │   │   ├── chat.py                   # /threads/{id}/turn (SSE)
│   │   │   └── settings.py               # /settings GET/PATCH (BYOK keys)
│   │   ├── turn_service.py               # orchestrator
│   │   ├── backends/
│   │   │   ├── __init__.py
│   │   │   ├── base.py                   # BackendAdapter Protocol, ChatChunk types
│   │   │   ├── chunks.py                 # ChatChunk discriminated union + ser/de
│   │   │   ├── registry.py               # adapter factory
│   │   │   ├── openrouter.py
│   │   │   ├── claude_code.py
│   │   │   └── computer_use.py
│   │   ├── storage/
│   │   │   ├── sqlite.py                 # aiosqlite CRUD
│   │   │   ├── schema.sql                # DDL
│   │   │   └── models.py                 # pydantic row models
│   │   └── tests/
│   │
│   └── web/                              # Next.js 15 (App Router, TypeScript)
│       ├── app/
│       │   ├── layout.tsx
│       │   ├── page.tsx                  # landing / new thread
│       │   ├── threads/
│       │   │   └── [id]/page.tsx         # thread view
│       │   ├── settings/page.tsx
│       │   └── api/
│       │       ├── chat/route.ts         # POST proxy + SSE pipe to FastAPI
│       │       └── threads/route.ts      # thin proxy for GET/PATCH/DELETE
│       ├── components/
│       │   ├── Composer.tsx
│       │   ├── MessageList.tsx
│       │   ├── RoutingChip.tsx
│       │   ├── SettingsPanel.tsx
│       │   ├── ThreadSidebar.tsx
│       │   └── BackendBubble/
│       │       ├── index.tsx             # dispatcher
│       │       ├── ChatBubble.tsx        # OpenRouter text
│       │       ├── CodeBubble.tsx        # Claude Code: text + diffs + tool calls
│       │       └── ComputerUseBubble.tsx # screenshots + actions
│       ├── lib/
│       │   ├── chunks.ts                 # ChatChunk TS types (mirror Python)
│       │   ├── sse.ts                    # SSE consumer hook
│       │   └── api.ts                    # fetch wrappers
│       ├── store/
│       │   └── chat.ts                   # Zustand
│       └── package.json
│
├── pyproject.toml                        # NEW — make src/ + apps/api/ proper packages
├── ReadMe.md                             # (existing) update with new run modes
└── .env.example                          # NEW — documents BYOK env vars
```

### Structure Rationale

- **`src/routing/` lives under `src/` (not `apps/api/`)** because the offline evaluation script (`src/evaluation/evaluate_routing.py`) must reuse it to replay end-to-end routing decisions on benchmark data. Putting it under `apps/api/` would either duplicate the logic in the offline harness or force the offline harness to import from `apps.api`, coupling it to FastAPI's runtime dependencies (uvicorn, aiosqlite). Keep `src/routing/` framework-free.
- **`apps/api/` and `apps/web/` are sibling app folders, not nested under `src/`.** This mirrors the conventional Python monorepo split where `src/` is reusable libraries and `apps/` is deployables. It also makes the Next.js `package.json` boundary unambiguous.
- **No barrel files / no `__all__`** — match the existing convention (`CONVENTIONS.md`, Module Design).
- **The new `src/agentic_intent/` package mirrors `src/task_classifier/` exactly** — same artifact dict shape (`model`, `vectorizer`, `scaler`, `label_encoder`, `feature_columns`, `target_column`), same TF-IDF + numeric stack, same artifact location convention `models/agentic_intent_classifier.joblib`. This is deliberate: it lets `src/routing/heads.py` load all three classifiers with one helper.
- **One `chunks.py` on each side (Python + TS).** Either by hand-mirroring the pydantic models in TypeScript, or by generating TS from the FastAPI OpenAPI schema. Recommend hand-mirroring for v1 — the chunk taxonomy will stabilize quickly and code-gen overhead isn't worth it at this scope.

### One-off Repo Hygiene (Side Effect of This Milestone)

- Make `src/` a proper package by adding root `pyproject.toml` so `apps/api/` can `from src.routing.decide import decide` cleanly instead of via `sys.path` injection. This subsumes one of the existing "anti-patterns" the codebase mapping flagged.
- Move the duplicated `build_text_input` format into `src/routing/heads.py` (or a sibling helper) so the demo, the new agentic-intent trainer, and the FastAPI heads all share one definition. Existing trainers still work via direct import.

---

## Architectural Patterns

### Pattern 1: Pure-Function Pipeline for the Routing Decision

**What:** The routing decision is a composition of five pure functions, not a class. Each function takes typed inputs and returns a typed result. The top-level `decide(...)` chains them.

**When to use:** When the decision is deterministic given inputs, and testability + offline replay matter more than encapsulating state.

**Trade-offs:**
- **Pro:** Trivially testable — pass synthetic `RoutingArtifacts` fixtures, assert on the returned `RoutingDecision`. No mocking of `self` or method-resolution order.
- **Pro:** Offline harness can replay `decide()` over thousands of benchmark rows without any FastAPI bootstrap.
- **Pro:** Adding a new classifier head (e.g. context-window-fit, language) is purely additive — a new `heads.predict_X(...)` function plus one new field on `RoutingDecision.signals`.
- **Con:** No place to hang per-instance config (which is fine because we want config to flow through arguments, not state).

**Shape:**

```python
# src/routing/types.py
from pydantic import BaseModel
from enum import Enum

class Backend(str, Enum):
    OPENROUTER = "openrouter"
    CLAUDE_CODE = "claude_code"
    COMPUTER_USE = "computer_use"

class TaskTypeResult(BaseModel):
    task_type: str         # e.g. "coding"
    confidence: float

class AgenticResult(BaseModel):
    is_agentic: bool
    confidence: float
    flavor: str | None     # "code" | "browse" | None

class ModelChoice(BaseModel):
    benchmark_slug: str    # e.g. "gpt-5"
    display_name: str
    api_model: str | None  # OpenRouter ID; None if simulated
    tier: str              # "cheap" | "medium" | "strong"
    openrouter_verified: bool

class RoutingDecision(BaseModel):
    backend: Backend
    model_or_agent: ModelChoice | None   # None for non-OpenRouter backends
    rationale: str                       # human-readable
    confidence: float                    # composite
    signals: dict                        # raw classifier outputs for debugging
```

```python
# src/routing/decide.py
def decide(
    *,
    prompt: str,
    history: list[Message],
    artifacts: RoutingArtifacts,
    settings: RoutingSettings,
) -> RoutingDecision:
    task = heads.classify_task(prompt, artifacts)
    agentic = heads.classify_agentic(prompt, artifacts)
    model = heads.predict_model(prompt, task, artifacts)
    return policy.apply_quality_first(
        task=task, agentic=agentic, model=model,
        mapping=artifacts.model_mapping, settings=settings,
    )
```

### Pattern 2: Backend Adapter as a Protocol Yielding a Discriminated Union

**What:** Each backend implements one Protocol — `async def stream(turn, history, settings) -> AsyncIterator[ChatChunk]`. `ChatChunk` is a discriminated union (`type: "text_delta" | "tool_call" | "screenshot" | "diff" | "error" | "done"`) carrying backend-agnostic payloads.

**When to use:** When backends have wildly different surfaces but the UI needs one renderer. This is the canonical pattern used by the AssistantStream protocol and AG-UI — emit a unified chunk taxonomy across providers.

**Trade-offs:**
- **Pro:** UI has one streaming reducer and one renderer dispatch. Adding a fourth backend is a single new file.
- **Pro:** Storage layer persists chunks verbatim (or rolled up) without backend-specific schemas.
- **Con:** The chunk taxonomy is design-load-bearing. Get it wrong and you'll be migrating.

**Shape:**

```python
# apps/api/backends/chunks.py
from typing import Literal, Annotated, Union
from pydantic import BaseModel, Field

class TextDelta(BaseModel):
    type: Literal["text_delta"] = "text_delta"
    text: str

class ToolCall(BaseModel):
    type: Literal["tool_call"] = "tool_call"
    tool_name: str
    input: dict
    call_id: str
    status: Literal["started", "completed", "failed"]
    output: dict | None = None

class Screenshot(BaseModel):
    type: Literal["screenshot"] = "screenshot"
    image_b64: str           # or a URL if we offload to disk
    caption: str | None = None

class FileDiff(BaseModel):
    type: Literal["file_diff"] = "file_diff"
    path: str
    diff: str                # unified diff

class StreamError(BaseModel):
    type: Literal["error"] = "error"
    message: str
    recoverable: bool

class Done(BaseModel):
    type: Literal["done"] = "done"
    final_text: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    latency_ms: int | None = None

ChatChunk = Annotated[
    Union[TextDelta, ToolCall, Screenshot, FileDiff, StreamError, Done],
    Field(discriminator="type"),
]
```

```python
# apps/api/backends/base.py
from typing import Protocol, AsyncIterator

class BackendAdapter(Protocol):
    async def stream(
        self,
        *,
        prompt: str,
        history: list[Message],
        settings: BackendSettings,
    ) -> AsyncIterator[ChatChunk]: ...
```

Each backend adapter translates its native event stream into this taxonomy. Examples:
- **OpenRouter** emits `TextDelta` + a terminating `Done` with cost/tokens.
- **Claude Code SDK** maps its native message types: `AssistantMessage` text deltas → `TextDelta`; tool use messages → `ToolCall(started/completed)`; file writes inferred from tool outputs → `FileDiff`.
- **Computer-use** maps `tool_use` for `computer` → `ToolCall`; screenshots returned in `tool_result` → `Screenshot`.

### Pattern 3: Config-Driven Quality-First Policy (Not Inline Heuristics)

**What:** The "quality first, cost as tiebreaker" rule lives in `src/routing/policy.py` as a pure function whose behaviour is controlled by a small `RoutingSettings` pydantic model — not by hard-coded `if/else` chains.

**When to use:** Always for routing policies you'll iterate on. You will tune thresholds and re-order rules; you do not want to redeploy the wheel to flip a number.

**Trade-offs:**
- **Pro:** Tweaking budget / quality balance is one config change.
- **Pro:** Settings can be exposed in the UI under `/settings` without code changes.
- **Con:** Don't over-engineer it into a DSL — keep it data, not code.

**Recommendation: Configuration model, not DSL.** A small pydantic model with named fields is enough. A rule DSL is overkill for this surface area (≤ 3 backends, ≤ 5 decision factors). Revisit if the rule set crosses ~10 dimensions.

**Shape:**

```python
# src/routing/policy.py
class RoutingSettings(BaseModel):
    agentic_threshold: float = 0.6       # agentic if P(agentic) >= this
    code_keywords_boost: float = 0.1     # bumps agentic head when "build/edit/fix" tokens present
    enabled_backends: set[Backend] = {Backend.OPENROUTER, Backend.CLAUDE_CODE, Backend.COMPUTER_USE}
    quality_preferred_tiers: list[str] = ["strong", "medium", "cheap"]  # ordered
    require_verified_route: bool = True  # only call OpenRouter when openrouter_verified=True
    fallback_model_slug: str = "gpt-5"   # when classifier abstains

def apply_quality_first(
    *,
    task: TaskTypeResult,
    agentic: AgenticResult,
    model: ModelChoice,
    mapping: dict,
    settings: RoutingSettings,
) -> RoutingDecision:
    # 1. agentic gate
    if agentic.is_agentic and agentic.confidence >= settings.agentic_threshold:
        backend = Backend.CLAUDE_CODE if agentic.flavor == "code" else Backend.COMPUTER_USE
        if backend in settings.enabled_backends:
            return RoutingDecision(backend=backend, model_or_agent=None, ...)
    # 2. quality-first within the chat tier
    if not model.openrouter_verified and settings.require_verified_route:
        model = resolve_fallback(settings.fallback_model_slug, mapping)
    return RoutingDecision(backend=Backend.OPENROUTER, model_or_agent=model, ...)
```

### Pattern 4: SSE for Streaming, Not WebSockets

**What:** FastAPI emits an `EventSourceResponse` (via `sse-starlette` or the built-in `StreamingResponse` with `text/event-stream`). The Next.js route handler reads it and pipes through to the browser as another SSE stream. The browser uses the native `EventSource` API (or a `fetch` + `ReadableStream` consumer to support POST).

**When to use:** One-direction server-to-client streams. Chat responses are exactly that — the client doesn't send mid-stream traffic.

**Trade-offs:**
- **Pro:** Simpler than WebSockets (HTTP semantics, automatic reconnect, no upgrade dance).
- **Pro:** Plays cleanly with FastAPI's `StreamingResponse` and Next.js Route Handlers.
- **Con:** Native `EventSource` is GET-only — for POST you use `fetch` + `ReadableStreamDefaultReader`. Both `apps/web/lib/sse.ts` and the AI SDK ship this pattern.
- **Con:** No mid-stream interrupt without a separate side channel (we'll use a separate `POST /threads/{id}/turn/abort` for cancel).

### Pattern 5: Server-Side Proxy for SSE (Next.js Route Handler)

**What:** The browser never talks directly to FastAPI. It POSTs to `/api/chat` (a Next.js Route Handler), which forwards to FastAPI and re-streams the SSE response.

**When to use:** When BYOK keys live in environment / settings on the Node side or when CORS / origin policy matters. Even though this is local-only OSS, the proxy keeps the architecture portable to a future "hosted" mode without UI changes.

**Trade-offs:**
- **Pro:** One known origin in the browser; no CORS gymnastics.
- **Pro:** Future-proofs the UI for any auth that needs Next.js middleware.
- **Con:** Adds one process hop. Negligible at localhost RTT; the streaming chunks pipe through.

### Pattern 6: One Process Per Concern (Training Stays Out of FastAPI)

**What:** FastAPI loads joblibs at startup and never trains. Training stays in standalone CLI scripts under `src/`. The two never share a process.

**When to use:** Whenever model training is heavy enough that a server crash during training would be unacceptable, or whenever training requires the full data tree (`data_processed/` here).

**Trade-offs:**
- **Pro:** FastAPI memory footprint stays small (one set of joblibs, no pandas DataFrames in scope).
- **Pro:** Training scripts already work and don't need rewriting.
- **Pro:** Re-training is a CLI invocation; the server restarts and picks up the new artifact.
- **Con:** No "retrain from the UI" affordance — but the PROJECT.md explicitly puts live retraining out of scope.

---

## Data Flow

### Single Chat Turn — End to End

```
[User hits Enter in Composer.tsx]
   │
   ▼
[POST apps/web/app/api/chat/route.ts]
   │  body: {thread_id, message, settings}
   ▼
[Next.js Route Handler forwards to FastAPI]
   │  POST /threads/{id}/turn  (Content-Type: application/json)
   ▼
┌─────────────────────────────── apps/api/turn_service.py ──────────────────────┐
│   1. storage.persist_user_message(thread_id, message)                          │
│   2. history = storage.load_recent_messages(thread_id, limit=N)                │
│   3. decision = routing.decide(prompt=message, history=history, ...)           │
│   4. storage.persist_routing_decision(thread_id, message_id, decision)         │
│   5. adapter = registry.get(decision.backend)                                  │
│   6. response_id = storage.create_pending_assistant_message(...)               │
│   7. async for chunk in adapter.stream(prompt, history, settings):             │
│        yield  chunk  ────────────► EventSourceResponse                         │
│        if chunk.type == "done":                                                │
│            storage.finalize_assistant_message(response_id, chunk)              │
│        elif chunk.type in {"tool_call","screenshot","file_diff"}:              │
│            storage.append_content_block(response_id, chunk)                    │
└────────────────────────────────────────────────────────────────────────────────┘
   │  (SSE event stream)
   ▼
[Next.js Route Handler streams response through]
   │  ReadableStream piped back out as text/event-stream
   ▼
[apps/web/lib/sse.ts consumer hook]
   │  pushes chunks into Zustand store
   ▼
[MessageList re-renders → BackendBubble dispatches by chunk.type]
   │
   ▼
[On chunk.type == "done": store marks message complete, RoutingChip shows rationale]
```

**Failure / boundary points that need explicit design:**

| Point | Failure | Handling |
|-------|---------|----------|
| Step 3 (`routing.decide`) | classifier predicts a slug not in `model_mapping.json` | Fall back to `OTHER` entry (existing pattern in `choose_final_route`) and emit a `RoutingDecision` with `rationale="fallback: classifier returned unknown slug"`. |
| Step 5 (`adapter.stream`) starts | backend returns 401 / 429 / 5xx immediately | Adapter emits one `StreamError(recoverable=...)` chunk then `Done(...)`. UI shows error bubble; offers retry which re-invokes the same turn (idempotent because user message is already persisted). |
| Mid-stream backend error | network drop / token quota mid-stream | Adapter emits `StreamError` and `Done`. Storage saves whatever partial text + chunks accumulated. UI shows a "(stream interrupted)" badge and a retry button on the partial response. |
| Client disconnect mid-stream | user closes tab | FastAPI detects via `Request.is_disconnected()`; cancels the adapter task; calls `storage.finalize_assistant_message(...)` with whatever was accumulated. |
| User aborts mid-stream | abort button in UI | UI POSTs `/threads/{id}/turn/abort` with the in-flight message_id; FastAPI cancels the task via `asyncio.Task.cancel()`; persists partial. |
| BYOK key missing | adapter selected but key not in key store | `turn_service` checks key availability before invoking adapter; if missing, short-circuits with `StreamError("Missing API key for backend X — set in Settings")` + `Done`. No backend call attempted. |
| Rate limit | OpenRouter 429 | Adapter emits `StreamError(recoverable=True)` and `Done`. The orchestrator can implement a single retry with one fallback model (lower-tier in `quality_preferred_tiers`) — opt-in via settings, off by default to keep behavior predictable. |
| Persistence after stream ends | SQLite write fails | Log and emit a server-only error; UI already has the stream, but a refresh would lose history. Acceptable for v1 OSS; surface a `Failed to save turn` toast. |

### Multi-Turn Thread

```
Turn N-1 routed to backend A, completed and persisted.
User sends turn N.

[turn_service.handle_turn(thread_id, message=N)]
   │
   ▼
[storage.load_recent_messages(thread_id)] → list[Message]
   │  Each Message has:
   │    role: "user" | "assistant"
   │    content: str               # the flattened text
   │    backend_used: Backend|None # set on assistant messages
   │    content_blocks: list[dict] # tool calls, screenshots, diffs as JSON
   ▼
[routing.decide(prompt=message_N.text, history=messages, ...)]
   │  decide() sees the full history but:
   │    - classify_task() / classify_agentic() only look at message_N.text
   │      (matches existing demo: prompt-only classification)
   │    - policy.apply_quality_first() COULD look at history for "sticky
   │      backend" heuristics, but for v1 each turn is routed independently.
   │  Independent routing is intentional: a thread can mix chat and agentic turns.
   ▼
[adapter.stream(prompt=message_N.text, history=messages, settings)]
   │  Each adapter formats history for its native API:
   │    - OpenRouter: list of {role, content} OpenAI-style messages
   │      (lossy: tool calls / screenshots from prior agentic turns are flattened
   │       to text summaries by adapter.history_formatter)
   │    - Claude Code SDK: uses ClaudeSDKClient.continue_conversation pattern
   │      with the agent's native session resumption if available; otherwise
   │      replays the user turns and a text summary of assistant turns.
   │    - Computer-use: replays user turns as Anthropic messages array; prior
   │      tool_use blocks are summarized to text (sandboxes don't survive
   │      across turns in v1).
   │
   │  Each adapter exposes:
   │    def format_history(history: list[Message]) -> NativeRequest: ...
   ▼
[stream chunks back as before]
```

**Key design points for multi-turn:**

- **Routing decision sees history but doesn't use it (v1).** History is plumbed through `decide()` for forward compatibility (future "sticky backend" or "did the prior turn fail?" heuristics) but the v1 policy ignores it. This is the simpler and more debuggable choice.
- **History reformatting lives in the adapter, not the orchestrator.** Each backend has different rules for what carries across turns. The OpenRouter adapter flattens to OpenAI message format; the Claude Code adapter preserves session state when possible; the computer-use adapter summarizes prior screenshots.
- **`content_blocks` is the source of truth for "what did the assistant actually do".** Re-formatting for the next turn reads from `content_blocks` (structured) and falls back to `content` (text) if needed. This avoids text-summary-of-text-summary degradation.
- **No cross-backend handoff in v1.** If turn N-1 was Claude Code and turn N is routed to OpenRouter, OpenRouter sees a text-flattened version of the prior turn. The "agent transfers context to the chat model" problem is real but out of scope.

---

## Storage Schema

Single SQLite file at `~/.prompt-optimizer/app.db` (path configurable). Accessed via `aiosqlite`. One DDL file: `apps/api/storage/schema.sql`.

```sql
CREATE TABLE threads (
  id              TEXT PRIMARY KEY,        -- uuid7 ideally
  title           TEXT NOT NULL,           -- user-set or auto-generated from first user message
  created_at      TEXT NOT NULL,           -- ISO8601
  updated_at      TEXT NOT NULL,
  settings_json   TEXT                     -- thread-local overrides (rare); null = use global
);

CREATE TABLE messages (
  id              TEXT PRIMARY KEY,
  thread_id       TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
  role            TEXT NOT NULL CHECK (role IN ('user','assistant','system')),
  content         TEXT NOT NULL DEFAULT '',          -- flattened text
  content_blocks  TEXT NOT NULL DEFAULT '[]',        -- JSON: list of ChatChunk objects
                                                      -- (tool_call, screenshot, file_diff)
  backend_used    TEXT,                              -- 'openrouter' | 'claude_code' | 'computer_use'
                                                      -- null for user/system rows
  model_used      TEXT,                              -- e.g. 'openai/gpt-5'; null for non-OpenRouter
  routing_id      TEXT,                              -- FK to routing_decisions; null for user/system
  tokens_in       INTEGER,
  tokens_out      INTEGER,
  cost_usd        REAL,
  latency_ms      INTEGER,
  status          TEXT NOT NULL DEFAULT 'complete',  -- 'pending' | 'streaming' | 'complete' | 'error'
  error_message   TEXT,
  created_at      TEXT NOT NULL,
  FOREIGN KEY (routing_id) REFERENCES routing_decisions(id)
);

CREATE INDEX idx_messages_thread_created ON messages(thread_id, created_at);

CREATE TABLE routing_decisions (
  id              TEXT PRIMARY KEY,                  -- one row per user turn that triggered routing
  thread_id       TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
  user_message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  backend         TEXT NOT NULL,                     -- 'openrouter' | 'claude_code' | 'computer_use'
  model_slug      TEXT,                              -- benchmark slug, e.g. 'gpt-5'
  api_model       TEXT,                              -- resolved e.g. 'openai/gpt-5'
  rationale       TEXT NOT NULL,                     -- human string
  confidence      REAL NOT NULL,
  signals_json    TEXT NOT NULL,                     -- raw classifier outputs (task_type, agentic, etc.)
  policy_settings_json TEXT NOT NULL,                -- snapshot of RoutingSettings used
  created_at      TEXT NOT NULL
);

CREATE INDEX idx_routing_thread ON routing_decisions(thread_id);
```

**Design notes:**

- **`routing_decisions` is a separate table, not inlined.** It's one row per *user* turn (each user message triggers exactly one routing decision). Inlining onto `messages` would either repeat the columns on the assistant row (denormalizing) or leave most rows empty. Separate table cleanly answers "show me every routing decision in this thread" for the eventual analytics view.
- **`content_blocks` is JSON, not a child table.** Tool calls, screenshots (base64 strings or filepaths), and diffs all fit in JSON arrays. SQLite handles 1-MB column values without trouble; for screenshots, store the base64 or write the file to `~/.prompt-optimizer/blobs/<message_id>/<n>.png` and store the relative path in the JSON.
- **`status` lifecycle on assistant messages:** `pending` → `streaming` → `complete` (happy path) or → `error`. UI uses this to render the right loading / interrupted indicator.
- **No FTS yet.** Search across thread content can be added later via `messages_fts` (SQLite FTS5 virtual table) without schema changes to `messages`.
- **No migration framework needed for v1.** Ship `schema.sql` as the canonical DDL; on first run the storage layer executes it idempotently (`CREATE TABLE IF NOT EXISTS`). Bring in `alembic` or a hand-rolled migration runner the first time we change the schema after release.
- **Why `TEXT` for timestamps:** SQLite stores `TEXT` for ISO-8601 with no precision loss. Pydantic converts to `datetime` at the boundary. Avoids the `julianday` / `INTEGER` epoch debate.

---

## Configuration Architecture

Single `pydantic-settings` `Settings` class with nested groups, plus a runtime `KeyStore` for BYOK overrides.

```python
# apps/api/config.py
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

class PathsSettings(BaseModel):
    project_root: Path = Path(__file__).resolve().parents[2]
    models_dir: Path = project_root / "models"
    mapping_path: Path = project_root / "config" / "model_mapping.json"
    db_path: Path = Path.home() / ".prompt-optimizer" / "app.db"
    blobs_dir: Path = Path.home() / ".prompt-optimizer" / "blobs"

class BackendsSettings(BaseModel):
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    claude_code_working_dir: Path | None = None    # default: tempdir per thread
    computer_use_sandbox_url: str | None = None    # e.g. local Docker sandbox

class KeysSettings(BaseModel):
    # Seed values from env at startup; mutable at runtime via /settings PATCH
    openrouter_api_key: str | None = None
    anthropic_api_key: str | None = None
    google_api_key: str | None = None              # optional, future

class RoutingSettingsModel(BaseModel):
    agentic_threshold: float = 0.6
    enabled_backends: list[str] = ["openrouter", "claude_code", "computer_use"]
    quality_preferred_tiers: list[str] = ["strong", "medium", "cheap"]
    require_verified_route: bool = True
    fallback_model_slug: str = "gpt-5"
    history_window: int = 20                       # messages passed to adapter

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",                 # PATHS__MODELS_DIR, KEYS__OPENROUTER_API_KEY
        extra="ignore",
    )
    paths: PathsSettings = PathsSettings()
    backends: BackendsSettings = BackendsSettings()
    keys: KeysSettings = KeysSettings()
    routing: RoutingSettingsModel = RoutingSettingsModel()
```

**Loading order (per `pydantic-settings` semantics):**

1. Built-in defaults on the model.
2. `.env` file at repo root or `~/.prompt-optimizer/.env`.
3. Process environment variables.
4. Runtime overrides via `PATCH /settings` (writes to `~/.prompt-optimizer/settings.json` and the in-process `Settings` instance).

**BYOK at runtime:**

- The Settings UI POSTs keys to `PATCH /settings`. The API writes them to `~/.prompt-optimizer/settings.json` (chmod 600) and updates the in-memory `Settings` instance. Restart is not required.
- Keys are **never** logged. The `/settings GET` endpoint returns `{has_openrouter_key: bool, ...}` not the values.

**Recommendation: single Settings layer.** Don't split per-concern (`api_config.py`, `model_config.py`, etc.) — one Settings class with nested groups is easier to reason about and matches the FastAPI dependency-injection idiom (`Annotated[Settings, Depends(get_settings)]`). Cache with `@lru_cache` on `get_settings()`.

---

## Scaling Considerations

This is a local OSS app — each user runs their own instance. "Scale" means: does it stay snappy as one user accumulates threads / runs concurrent agent turns?

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 1 user, < 100 threads | Default architecture. SQLite + in-process joblibs. One uvicorn worker, default async pool. |
| 1 user, 1k+ threads, ~10k messages | Add SQLite FTS5 (`messages_fts` virtual table) for search. Lazy-load thread sidebar (paginate). |
| 1 user, multiple concurrent turns (agent doing long-running work in one thread while user chats in another) | Run uvicorn with `--workers 1` but rely on async concurrency — agent adapters use `asyncio.create_task` so SSE streams are independent. Make sure SQLite uses WAL mode (`PRAGMA journal_mode=WAL`). |
| Future: hosted multi-user | Not in scope. Would require a real DB (Postgres), proper auth, per-user key stores, and a worker queue for agent tasks. |

### Scaling Priorities

1. **First bottleneck:** SQLite writes during high-frequency token streaming. Mitigation: don't write per chunk. Batch the assistant message body in memory; persist the full body + content_blocks on `done`. Already encoded above (steps 6 and 7 in turn_service).
2. **Second bottleneck:** Loading the embedding router on startup if we ever add it to the routing decision. SentenceTransformer load is ~2-3s on first import. Lazy-load it inside `RoutingArtifacts` so cold start isn't slowed when the embedding head isn't enabled.

---

## Anti-Patterns

### Anti-Pattern 1: Mixing routing logic into the FastAPI route handler

**What people do:** `@app.post("/turn")` handler that calls `model.predict(...)`, applies `if agentic: ...` rules, then dispatches to an adapter.
**Why it's wrong:** Couples the routing brain to FastAPI request/response lifecycle. Offline evaluation has to mock `Request` to run. Tests need an `httpx.AsyncClient`.
**Do this instead:** Keep `src/routing/decide.py` framework-free. The route handler only ferries `(prompt, history, settings) -> RoutingDecision` and never inspects classifier internals.

### Anti-Pattern 2: One adapter per backend method (`stream_text`, `stream_tool_calls`, `stream_screenshots`)

**What people do:** Split the adapter Protocol into per-event-type methods because each backend produces different things.
**Why it's wrong:** UI now needs N renderers per backend (N × M). State machine for "is the assistant message complete?" becomes a knot.
**Do this instead:** One `stream(...)` method per adapter, yielding a single discriminated-union `ChatChunk`. UI dispatches on `chunk.type`.

### Anti-Pattern 3: Loading joblibs inside the request handler

**What people do:** Call `joblib.load(...)` per request to "stay fresh".
**Why it's wrong:** 200-500ms latency per turn for no value. Joblibs are stateless once loaded.
**Do this instead:** Load once in FastAPI's `lifespan` context, store on `app.state.artifacts`, inject via `Depends(get_artifacts)`. Re-training requires a server restart — that's fine.

### Anti-Pattern 4: Storing token deltas as separate `chunks` rows

**What people do:** Insert one DB row per `TextDelta`.
**Why it's wrong:** 100x write amplification, no value. Streaming is a UI affordance, not a persistence concern.
**Do this instead:** Accumulate in memory during the stream; persist the full assistant message + `content_blocks` once on `Done`.

### Anti-Pattern 5: Cross-importing from `apps/api/` into `src/`

**What people do:** `from apps.api.config import Settings` inside `src/routing/`.
**Why it's wrong:** Breaks offline evaluation; ties the offline harness to FastAPI's startup.
**Do this instead:** `src/routing/` defines its own `RoutingSettings` pydantic model. `apps/api/` constructs one from its global `Settings` and passes it in. One-way dependency: `apps/api → src/routing`. Never the reverse.

### Anti-Pattern 6: Reimplementing `PromptFeatureExtractor` for the agentic-intent classifier

**What people do:** Copy-paste the keyword groups into a new extractor.
**Why it's wrong:** Two extractors drift; feature changes have to be made twice.
**Do this instead:** Reuse `src/feature_extraction/Feature_extractor.PromptFeatureExtractor` for the new trainer. If the agentic head needs extra features (e.g. "has URL", "imperative verb at start"), add them to the existing `PromptFeatureExtractor` so all routers get them — the existing trainers' `get_numeric_feature_columns` helpers already auto-discover new numeric columns.

### Anti-Pattern 7: Per-user-key state inside global Settings

**What people do:** Put live API keys in the pydantic-settings Settings dataclass and mutate it.
**Why it's wrong:** `BaseSettings` instances are intended to be immutable after construction; mutating them after `@lru_cache` produces stale reads.
**Do this instead:** Have a separate `KeyStore` singleton seeded from Settings at startup but mutable at runtime. Adapters depend on `Annotated[KeyStore, Depends(get_keys)]`.

---

## Build Order (Roadmap-Phase Implications)

### Foundations (must come first — block everything else)

1. **`pyproject.toml` + package wiring.** Make `src/` and `apps/api/` importable as packages. Without this, the new `apps/api/` cannot cleanly import `src.routing` without resurrecting the `sys.path` hack. Tiny in scope; large in payoff.
2. **`src/routing/` decision module.** This is the keystone — the FastAPI orchestrator, the adapter dispatch, the storage `routing_decisions` table, and the offline evaluation rewrite all need it.
3. **`src/agentic_intent/` trainer + first artifact.** The decision module needs all three classifier joblibs. Until the agentic-intent classifier exists, `routing.decide()` can run with a stub (always returns `is_agentic=False`) — useful for unblocking downstream work, but the milestone isn't done until the real one is trained.
4. **`apps/api/backends/chunks.py` (ChatChunk discriminated union).** Storage, adapters, and UI all consume this taxonomy. Define it before writing any adapter.

### Leaf nodes (no other component blocks on these — parallelizable)

Once the foundations land, these can be built in parallel by independent contributors:

- **`apps/api/backends/openrouter.py`** — depends only on `chunks.py` + a single HTTPX session.
- **`apps/api/backends/claude_code.py`** — depends only on `chunks.py` + `claude-agent-sdk-python`.
- **`apps/api/backends/computer_use.py`** — depends only on `chunks.py` + Anthropic SDK + a sandbox URL.
- **`apps/api/storage/`** — depends only on the schema. Has no opinion about which backend produced a chunk.
- **`apps/web/components/BackendBubble/*.tsx`** — each renderer depends only on TS `ChatChunk` types.
- **`apps/web/components/ThreadSidebar.tsx`** — depends on `/threads` GET endpoint shape, which can be stubbed.
- **`apps/web/components/Composer.tsx`** — pure form; depends on the `POST /api/chat` shape only.
- **`src/evaluation/evaluate_routing.py`** — depends only on `src/routing/` and `data_processed/`. Doesn't need FastAPI at all.

### Joining components (block on multiple leaves)

- **`apps/api/turn_service.py`** — needs `src/routing/`, the adapter registry, `chunks.py`, and storage. The first end-to-end happy-path turn lands here.
- **`apps/api/main.py` + `apps/api/routers/chat.py`** — needs `turn_service`. First HTTP-exposed surface.
- **`apps/web/app/api/chat/route.ts`** + **`apps/web/lib/sse.ts`** — needs `chat.py` to exist; can be developed against a mocked FastAPI early.
- **`apps/web/app/threads/[id]/page.tsx` + `MessageList.tsx`** — needs the SSE consumer hook + the chunk renderers. First end-to-end UI surface.

### Suggested phase ordering for the roadmap

| Phase | Theme | Components |
|-------|-------|------------|
| Phase A | **Routing brain** (foundation) | `pyproject.toml`, `src/routing/`, `src/agentic_intent/` (trainer + artifact), `src/evaluation/evaluate_routing.py` to validate it works on benchmark data |
| Phase B | **Backend dispatch** (depends on A's `RoutingDecision` shape) | `apps/api/backends/{chunks,base,registry,openrouter,claude_code,computer_use}.py`, plus a CLI harness that calls one adapter end-to-end |
| Phase C | **Service layer** (depends on A + B) | `apps/api/main.py`, `turn_service.py`, `storage/`, `config.py`, `/threads/{id}/turn` SSE endpoint, plus `httpx` integration tests |
| Phase D | **UI shell** (depends on C's HTTP contract) | `apps/web/` scaffold, route handler proxy, chunk types in TS, basic single-thread chat with one backend (OpenRouter), no sidebar |
| Phase E | **UI feature-complete** | Multi-backend renderers (`CodeBubble`, `ComputerUseBubble`), `ThreadSidebar`, `SettingsPanel`, `RoutingChip`, abort + retry |
| Phase F | **Polish + demo path** | The README golden path, error-handling edge cases, BYOK onboarding flow, packaging |

**Why this ordering:** Each phase produces something runnable. Phase A leaves you with an upgraded CLI demo (`src/demo/`) that already shows the new routing brain working. Phase B leaves you with an adapter you can invoke from a script. Phase C is the first time anything streams over HTTP. By Phase D the UI exists end-to-end with at least one backend. Phases E and F are pure additive surface area.

**What can be parallelized within a phase:** Inside Phase B, all three adapters can be built simultaneously by different contributors once `chunks.py` lands. Inside Phase E, the `BackendBubble/*` renderers are independent.

---

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| OpenRouter | HTTPX async client; `POST /api/v1/chat/completions` with `stream=true`; parse SSE lines; map `delta.content` → `TextDelta`, final `usage` → `Done(tokens_in/out, cost_usd)`. | Resolved API model comes from `config/model_mapping.json` (`api_model` field) only when `openrouter_verified=true`. Otherwise `policy.apply_quality_first` rewrites to the fallback. |
| Claude Code SDK | `claude-agent-sdk` Python lib; use `ClaudeSDKClient` for multi-turn or `query()` for single-turn; iterate `async for message in client.receive_response():`; map `AssistantMessage` text deltas → `TextDelta`, `ToolUseBlock` → `ToolCall(started/completed)`, infer `FileDiff` from file-write tool outputs. | The SDK is built on `anyio`; prefer `anyio.run` semantics when wrapping. Do not `break` early from the async iterator — let it complete to avoid asyncio cleanup issues. (Per SDK docs.) |
| Anthropic computer-use | Anthropic SDK Messages API with `tools: [{type: "computer_20251022", ...}]`; stream over SSE; map `tool_use` events for the `computer` tool → `ToolCall`; map `tool_result` blocks containing screenshots → `Screenshot`. | Requires a controllable sandbox (Docker container, VM, etc.); `BackendsSettings.computer_use_sandbox_url` carries its address. Treat as v1-experimental; consider a stub adapter for the demo path if the sandbox is fragile. |
| Hugging Face (transitive) | `SentenceTransformer(...)` only if the embedding router gets into the live route. Cache under `~/.cache/huggingface/`. | Existing usage in offline training; keep out of the FastAPI startup path unless explicitly enabled. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `src/routing/` ↔ `apps/api/` | One-way Python import (`apps.api → src.routing`). | `src/routing/` is framework-free. Keep it that way. |
| `apps/api/turn_service.py` ↔ `apps/api/backends/*.py` | Adapter Protocol; called via `registry.get(backend).stream(...)`. | All adapters return the same `AsyncIterator[ChatChunk]`. |
| `apps/api/storage/` ↔ everything | Called from `turn_service` and routers via `Annotated[Storage, Depends(get_storage)]`. | Single point of DB access. No adapter writes directly to SQLite. |
| `apps/api/` ↔ `apps/web/` | HTTP (JSON for `/threads`, SSE for `/turn`). | Always proxy through Next.js route handler — never call FastAPI from the browser directly. |
| `apps/web/store/chat.ts` ↔ React components | Zustand subscription. | One store for threads + currentThread + streaming chunks. Server components fetch initial data; client components subscribe for streaming. |
| `src/` ↔ `data_processed/` and `models/` | Filesystem only (existing pattern). | The new offline `evaluate_routing.py` follows the existing CSV-based convention. |

---

## What Reuses What (Anti-Duplication Audit)

- **`PromptFeatureExtractor`** is imported by:
  - existing trainers (`src/task_classifier/train_task_classifier_robust.py`, the two Stage-2 trainers, embedding trainer) — unchanged.
  - new `src/agentic_intent/train_agentic_intent.py` (same import shape).
  - new `src/routing/heads.py` for live inference inside FastAPI.
  - existing `src/demo/demo_router.py` continues to import it for the CLI demo.
  - No new copies created.
- **`config/model_mapping.json`** is read by:
  - existing `src/demo/demo_router.choose_final_route` — unchanged.
  - new `src/routing/loaders.load_model_mapping` (one shared loader).
  - the FastAPI startup wires the loaded mapping into the `RoutingArtifacts` bundle.
  - No second copy of the JSON.
- **`build_text_input` format** (the `"<query> task_type_<qt> keyword_type_<kqt>"` string): currently duplicated across `src/model_router_tier/train_tier_router.py`, `src/model_router/train_model_router.py`, and `src/demo/demo_router.py`. **This milestone consolidates it** into `src/routing/heads.py` (or a sibling helper in `src/feature_extraction/`). The existing trainers can import from there going forward; old trainers that already wrote their joblibs are unaffected because the string format itself hasn't changed.
- **Joblib loaders** — the existing demo's `load_joblib_artifacts` (`src/demo/demo_router.py:35`) and the new `src/routing/loaders.py` should share one helper. Move the helper into `src/routing/loaders.py` and let the demo import from there. (Marginal but on the path.)

---

## Sources

- [Settings and Environment Variables — FastAPI](https://fastapi.tiangolo.com/advanced/settings/)
- [Pydantic Settings concepts](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [Server-Sent Events (SSE) — FastAPI](https://fastapi.tiangolo.com/tutorial/server-sent-events/)
- [Streaming APIs with FastAPI and Next.js — Sahan Serasinghe](https://sahansera.dev/streaming-apis-python-nextjs-part1/)
- [Using Server-Sent Events (SSE) to stream LLM responses in Next.js — Upstash](https://upstash.com/blog/sse-streaming-llm-responses)
- [Agent SDK reference — Python (Claude Code Docs)](https://code.claude.com/docs/en/agent-sdk/python)
- [claude-agent-sdk-python streaming_mode example](https://github.com/anthropics/claude-agent-sdk-python/blob/main/examples/streaming_mode.py)
- [Stream Protocol and Message Chunks — assistant-ui (DeepWiki)](https://deepwiki.com/assistant-ui/assistant-ui/4.1-typescript-streaming-engine)
- [Messages — Agent User Interaction Protocol (AG-UI)](https://docs.ag-ui.com/concepts/messages)
- Existing repo context (`.planning/codebase/ARCHITECTURE.md`, `STRUCTURE.md`, `INTEGRATIONS.md`, `CONVENTIONS.md`) — primary source for what reuses what.

---

*Architecture research for: auto-routing chat with Python ML + FastAPI + Next.js + multi-agent backends*
*Researched: 2026-05-11*

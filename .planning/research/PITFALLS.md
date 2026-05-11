# Pitfalls Research

**Domain:** Auto-routing multi-backend AI chat (OpenRouter + Claude Agent SDK + Anthropic computer-use) on top of an existing offline scikit-learn routing pipeline
**Researched:** 2026-05-11
**Confidence:** HIGH (Anthropic + OpenRouter docs verified; sklearn behavior verified; SDK rename + computer-use sandbox status checked against current 2026 sources)

Scope note: every pitfall here is specific to **this** project — a brownfield repo with a working two-stage `task_type_classifier` + `model_router` joblib pipeline being extended into a Comet-style chat product. Generic "AI app" advice has been excluded. The roadmap phases referenced are the working hypothesis: **R** = Router-brain extension, **B** = Backend integrations, **A** = FastAPI back-end, **U** = Next.js chat UI, **P** = Persistence, **H** = Hardening / open-source release.

---

## Critical Pitfalls

### Pitfall 1: Benchmark-trained router cratering on real chat prompts (LLMRouterBench distribution drift)

**What goes wrong:**
The existing `task_type_classifier.joblib` and `model_router.joblib` were trained on LLMRouterBench, which is a curated benchmark of standardized prompts across math / coding / logic / knowledge / affective / instruction-following / tool-use tasks. Real chat users do not write like LLMRouterBench rows. They write "yo can u write me a script that opens gmail", "fix the bug", "thoughts?", and 5-token follow-ups inside a thread. The router will hit out-of-distribution input on day one and produce confidently wrong task-type labels — which then poison the Stage-2 model router (see `CONCERNS.md` "Two-stage router dependence on stage-1 confidence", current Stage-2 macro F1 is already 0.17).

**Why it happens:**
- LLMRouterBench prompts are self-contained one-shots; chat is multi-turn with implicit context in prior turns.
- Benchmark prompts are full English sentences; real chat is fragmentary, lowercase, and ungrammatical.
- The current pipeline never sees thread context — it classifies one turn at a time.
- The repo's own `evaluation_summary.md` admits exact model routing is at 0.21 accuracy on the test split; production drift makes that a ceiling, not a floor.

**How to avoid:**
- In Phase R, define a **canary prompt set** of 30–50 real chat-style prompts hand-labeled with the intended backend and task type. Run it after every router change; treat regressions as blockers.
- Stage-2 router input must include the full thread context summary (or last-N turn task labels), not just the current turn's features.
- Add a `"unknown_or_oot"` task-type class trained on out-of-distribution sentinels (very short prompts, emoji-only, single tokens). Without it the classifier will jam everything into the nearest benchmark bucket.
- Log every routing decision with `{prompt, predicted_task, predicted_model, chosen_backend, confidence}` to local SQLite for offline review. Treat this as the v2 retraining set (without violating the "no live retraining loop" constraint in v1).

**Warning signs:**
- Short prompts (< 6 tokens) all routing to one task type (likely "factual").
- Coding follow-ups like "now add tests" routing to chat instead of Claude Code because the agentic-intent signal is on the prior turn.
- Confidence distribution stuck near 1.0 on prompts that clearly don't match any class.

**Phase to address:** R (canary set, OOD class, thread-context feature) and ongoing P (decision logging).

---

### Pitfall 2: Task type ≠ backend choice — complexity within a task collapses to one route

**What goes wrong:**
Both `"explain quicksort in two lines"` and `"refactor this 5000-line repo into a Next.js app"` classify as `coding`. The current pipeline will route both to whichever benchmark model the Stage-2 router prefers for `coding`. The first should go to a fast chat model (Sonnet via OpenRouter); the second is the canonical Claude Code SDK case. Conflating them is the most visible routing failure a Comet-style demo can have — users will instantly see "I asked you to build me an app and you returned a paragraph."

**Why it happens:**
- Task type is too coarse. The training data does not distinguish "explain X" from "do X."
- The new agentic-intent classifier (Active in PROJECT.md) is the right idea, but only as a binary it still cannot separate "10-line edit" from "build me a new repo."
- Features in `PromptFeatureExtractor` measure prompt length but not task scope (presence of "build", "create a new", URL references, file references, multi-step indicators).

**How to avoid:**
- Phase R: the agentic-intent classifier output must be combined with a **scope signal** — minimally a heuristic for: (a) explicit build/create verbs, (b) reference to existing files (`this`, `the repo`, code-block presence), (c) URL presence (computer-use signal), (d) multi-step indicators ("then", "after", "and also").
- Combine signals into a `{backend, agent_or_chat, scope}` triplet, not a single task label.
- Document the combination as a deterministic post-processing step over the trained model's output, not as new training. (Avoids the LLMRouterBench drift problem above.)

**Warning signs:**
- Demo prompts "build me a finance app" and "explain monad" both routing identically.
- Routing rationale chip says only "coding" with no scope qualifier.
- User complaints in the form "I wanted X but it picked Y."

**Phase to address:** R (combine agentic-intent + scope heuristics into the final decision layer).

---

### Pitfall 3: Confidence calibration — overconfident routes lock out tiebreak logic

**What goes wrong:**
Quality-first within budget, cost as tiebreaker (Constraints in PROJECT.md) only works if the router exposes calibrated probabilities. Raw `predict_proba` from a `LogisticRegression` can look well-calibrated in aggregate but is routinely over-confident on out-of-distribution inputs. When the router reports 0.97 for "coding → claude-code-sdk" on a 3-word prompt, the tiebreak / fallback logic never triggers, and there is no way to say "we're not sure, ask user" or "fall back to cheapest verified model."

**Why it happens:**
- sklearn `LogisticRegression` is *generally* well-calibrated under the same distribution it trained on (verified against scikit-learn 1.8 docs), but breaks under distribution shift (Pitfall 1).
- Stage-2 model router is a multi-class problem with 16 classes, 7 of them unverified — calibration error is naturally higher on rare/imbalanced classes.
- The current pipeline never validates calibration; `evaluation/` plots show class distribution and PR curves but no reliability diagram.

**How to avoid:**
- Phase R: produce a reliability diagram (calibration curve) for each router as part of the regression pipeline. If calibration error exceeds a threshold, wrap the underlying estimator in `CalibratedClassifierCV(method="isotonic", cv=5)` before saving the joblib.
- Define an explicit **uncertainty threshold** (e.g., max-class probability < 0.45) that triggers fallback to the cheap, verified default chat model rather than an exotic class.
- Never combine raw `predict_proba` from Stage-1 and Stage-2 multiplicatively as a "joint confidence" — the errors are correlated and the product underflows fast.

**Warning signs:**
- Stage-2 router confidence histogram clusters near 1.0 (visible in `prediction_confidence.png` plots — the current `model_router_prediction_confidence.png` is the right place to look).
- High accuracy on benchmark test set but high fallback rate in real use (or vice versa: high overconfidence and zero fallback firing).
- "OTHER" sentinel class gets predicted with 0.99 confidence (mathematically impossible under correct calibration).

**Phase to address:** R (calibration + threshold definition) and B (fallback chain in the routing decision layer).

---

### Pitfall 4: Hardcoded rules drifting from the trained model's view

**What goes wrong:**
The natural temptation is to bolt rules on top of the ML router: `if "http://" in prompt → computer-use`, `if "build me" in prompt → claude-code`, `if len < 10 → cheap chat`. These rules look like "common sense" but they (a) bypass the trained model entirely, (b) are invisible in evaluation metrics, (c) cannot be regression-tested with the existing `evaluate_baselines.py`, and (d) silently override the quality-first scoring decision in PROJECT.md when they shouldn't.

**Why it happens:**
- ML routing is hard and slow to improve; rules are fast.
- The trained model has known weaknesses (Pitfall 1 and 2), and engineers paper over them with rules instead of fixing the training data or feature set.
- Rules accumulate one PR at a time and nobody owns the rule list.

**How to avoid:**
- Phase R: Define a single `RoutingDecisionLayer` module that takes the trained-model outputs as input and applies a **declarative, audited** rules table. No `if` statements scattered across the FastAPI handler.
- Every rule needs: (a) a name, (b) a written justification, (c) a unit test, (d) an entry in the routing-decision log so reviewers can see "rule X overrode model Y on N% of recent decisions."
- The canary prompt set (Pitfall 1) covers both model-only and rules-on top decisions to make rule drift visible.

**Warning signs:**
- Routing rationale chip says "claude-code-sdk" but the trained model's argmax was "openrouter/gpt-5-chat" — and the user has no way to see which signal won.
- The same prompt routes differently across commits without a model change.
- New collaborators add `if` branches to the router because "the model gets it wrong."

**Phase to address:** R (declarative rules table) and U (rationale chip exposes which signal won).

---

### Pitfall 5: SDK rename trap — pinning `claude-code-sdk` instead of `claude-agent-sdk`

**What goes wrong:**
The Python package was renamed from `claude-code-sdk` to `claude-agent-sdk` in March 2026 and the old package is deprecated and no longer maintained ([Anthropic migration guide](https://code.claude.com/docs/en/agent-sdk/migration-guide)). Pinning the old package gets you a deprecated dependency on day one. Worse, the rename came with a **silent behavior change**: the SDK no longer loads Claude Code's default system prompt or filesystem settings unless you explicitly pass the `claude_code` preset. An agent that "works" in the old SDK will look stripped-down and useless after migration unless you know about this flag.

**Why it happens:**
- Training data and tutorials still say `claude-code-sdk`; a casual `pip install claude-code-sdk` succeeds and looks healthy.
- Behavior change is in the migration guide, not in any runtime warning.
- This repo has no requirements manifest at all (`CONCERNS.md` "No dependency manifest, HIGH") so the package decision will be made informally inside an integration PR.

**How to avoid:**
- Phase B: install `claude-agent-sdk` only. Pin the version explicitly in the new `pyproject.toml` / `requirements.txt`. Document in INTEGRATIONS that `claude-code-sdk` is deprecated.
- Use the `claude_code` system-prompt preset explicitly when invoking the SDK for coding tasks — do not rely on defaults.
- Add a CI smoke test that imports `claude_agent_sdk` and asserts on the version string.

**Warning signs:**
- Imports of `claude_code_sdk` (underscore) anywhere in `src/backends/`.
- `ClaudeCodeOptions` type references (renamed to `ClaudeAgentOptions`).
- Agent runs produce minimal output / refuse to edit files even though prompts look right — likely the missing system-prompt preset.

**Phase to address:** B (pick correct package up front; codify in dep manifest).

---

### Pitfall 6: Claude Agent SDK long-running tasks blowing past HTTP/SSE timeouts

**What goes wrong:**
Agentic tasks routinely run for minutes. A `StreamingResponse` from FastAPI, an SSE connection from the Next.js app, an `nginx`/reverse-proxy timeout, the Anthropic API's own idle window — every layer has a timeout. The Claude Agent SDK itself has known stalls: ([anthropics/claude-code#25979](https://github.com/anthropics/claude-code/issues/25979)) "hangs indefinitely when API streaming connection stalls (no read timeout)." Without explicit watchdog flags (`CLAUDE_ENABLE_STREAM_WATCHDOG=1`, `CLAUDE_STREAM_IDLE_TIMEOUT_MS`), an agent run can hang the whole chat thread until the user kills the tab.

**Why it happens:**
- Default HTTP/SSE timeouts in `httpx`, `aiohttp`, and most proxies are tens of seconds, not minutes.
- The SDK doesn't surface a stall to the caller — partial output keeps the connection technically "alive" while no progress happens.
- An open-source app has no control over the user's reverse proxy, browser, or network.

**How to avoid:**
- Phase B: set `CLAUDE_ENABLE_STREAM_WATCHDOG=1` and a finite `CLAUDE_STREAM_IDLE_TIMEOUT_MS` (e.g., 90 s for chat agents) in the backend startup config.
- Phase A: emit SSE **heartbeat events** every 15 seconds during long agent runs so client-side and proxy timers reset. Document the heartbeat event type in the SSE protocol contract.
- Implement explicit cancellation: the chat UI's "stop" button must call an endpoint that triggers the SDK's `query.interrupt()` (Agent SDK reference) and a server-side abort event on the corresponding `asyncio.Task`.
- Surface per-turn elapsed time and a "still working…" indicator in the UI after 10 seconds so users do not assume a hang.

**Warning signs:**
- Browser network tab shows an SSE connection alive but no events in > 30 seconds.
- `kill -9` is the only way to stop a stuck run (the symptom in the upstream bug report).
- "Stop" button doesn't actually stop anything — the model keeps streaming after the UI hides the response.

**Phase to address:** B (watchdog env vars + cancellation), A (heartbeats), U (stop button, elapsed indicator).

---

### Pitfall 7: Concurrent Claude Code threads colliding on the working directory

**What goes wrong:**
Claude Code edits files in a working directory. If the user opens thread A asking "rewrite my README" and thread B asking "add a CHANGELOG", and both threads route to Claude Code, both SDK instances run against the same `cwd` simultaneously. They will: (a) read each other's stale writes, (b) trigger merge-conflict-like overwrites, (c) confuse the agent into believing earlier edits "disappeared." The user sees garbled output and lost work.

**Why it happens:**
- Claude Code is designed for one terminal, one user, one cwd. Wrapping it inside a multi-thread chat product breaks that assumption.
- Multi-turn threads suggest "long-running session" but the SDK has no built-in workspace-per-thread isolation.
- Open-source users run on their own machines with their own repos — collisions hit user files, not a sandbox.

**How to avoid:**
- Phase B: every Claude Code invocation runs inside a **per-thread ephemeral workspace** (a tmpdir under `~/.prompt-optimizer/workspaces/<thread_id>/`) by default, unless the user explicitly opts a thread into their real project directory via a settings toggle.
- Serialize Claude Code invocations per workspace with an `asyncio.Lock` keyed by `cwd`; queue concurrent calls and surface "agent busy" in the UI.
- Persist the per-thread workspace path in the thread record so re-opening a thread reuses the same scratch directory.
- Document the workspace model loudly in the README — surprise edits to a user's repo are a serious open-source trust violation.

**Warning signs:**
- Two threads open, both routing to Claude Code, files appearing/disappearing in the user's repo.
- Agent output references a file that another thread just deleted.
- Tests start failing in unrelated branches because the agent wrote into the wrong cwd.

**Phase to address:** B (per-thread workspace model, opt-in to real cwd).

---

### Pitfall 8: Computer-use shipped in an open-source app with no safe default

**What goes wrong:**
Anthropic's `computer-use-demo` reference container runs a full desktop in Docker (multi-GB image, X11, VNC, screenshot loop). Shipping that as the "browse-and-act" backend in an open-source app means: (a) most users cannot install it, (b) the ones who can are running an autonomous agent against their real browser unless sandboxed, (c) prompt injection inside a visited webpage can drive the agent to exfiltrate files or run shell commands ([prompt.security: Claude Computer Use: A Ticking Time Bomb](https://prompt.security/blog/claude-computer-use-a-ticking-time-bomb)). Enabling computer-use by default in a BYOK open-source app is a security event waiting to happen.

**Why it happens:**
- The reference container is "the easy way" and gets copy-pasted into integrations.
- New `anthropic-experimental/sandbox-runtime` (research preview) is a lighter-weight alternative, but it's not production-ready and not obvious to find.
- Open-source repos optimize for "works out of the box," which is the wrong default for an autonomous-browser tool.

**How to avoid:**
- Phase B: computer-use is **disabled by default**. The router can predict "computer-use is the right backend" but the actual call only happens if the user has explicitly enabled it in settings AND set `COMPUTER_USE_OPT_IN=1` in `.env`.
- When disabled, the router gracefully degrades: it tells the user "this looks like a browse-and-act task — enable computer-use in settings to run it, or rephrase as a question."
- Document the threat model in the README: prompt injection, screenshot exfiltration, autonomous keyboard control. Spell out that the user is responsible for sandboxing.
- Provide a recipe (not a bundled binary) for running computer-use inside Docker with the Anthropic reference container, and a second recipe pointing at `anthropic-experimental/sandbox-runtime` as the future-facing option.
- Surface a per-turn **cost cap** and **step cap** (max N tool calls per run) at the call site, not as a config-file knob.

**Warning signs:**
- README quickstart enables computer-use.
- Computer-use has no per-turn USD cost limit.
- Anti-malware/EDR on contributor machines starts flagging the app — a real signal that something is hijacking inputs.

**Phase to address:** B (opt-in, cost+step cap), H (threat model docs, sandbox recipes).

---

### Pitfall 9: Cost runaway with no per-turn / per-day spend cap

**What goes wrong:**
A single Claude Code agent can iterate for hundreds of tool calls. Computer-use can loop screenshot→tool-call indefinitely. A user types "fix all the bugs in this repo" and walks away. The bill, paid by the user via BYOK, runs into tens or hundreds of dollars per turn. In an open-source app, the **only** safety net is the one the project ships. The MindStudio writeup of a $47K multi-agent loop is the canonical horror story — that user had no per-tool budget check, no error-rate circuit breaker, no max-iteration cap.

**Why it happens:**
- The user typed one prompt and assumed it was bounded.
- The OpenRouter / Anthropic APIs do not enforce per-call USD caps for the caller — the caller has to enforce them.
- "Quality-first within budget, cost as tiebreaker" (PROJECT.md Constraints) is a routing principle, not a runtime spend-cap.

**How to avoid:**
- Phase B: every backend wrapper enforces a hard **per-turn USD cap** (default $0.50, configurable). When estimated cost crosses the cap mid-stream, abort and emit a `cost_cap_hit` event.
- Phase B: agentic backends additionally enforce a **max-iteration cap** (default 25 tool calls for Claude Code, 15 for computer-use).
- Phase P: maintain a rolling **daily spend total** across all backends; warn at 80%, hard-block at 100% of a user-configured daily cap.
- Phase A: when a user closes their browser tab mid-stream, **cancel the upstream request** (OpenRouter cancellation works for supported providers and stops billing when triggered, per the OpenRouter streaming docs). Do not let an abandoned stream silently keep billing.
- Surface the running cost of the current turn live in the UI — turn off the abstraction, make the price visible.

**Warning signs:**
- An agent run completes with > 30 tool calls and nobody flags it.
- A user reports their OpenRouter / Anthropic dashboard charge is wildly larger than what the UI displayed.
- Tabs closed during streaming don't reduce upstream cost.

**Phase to address:** B (per-turn + per-iteration caps), P (daily cap), A (cancellation on disconnect), U (live cost surface).

---

### Pitfall 10: API keys / prompts logged to disk, stdout, or analytics

**What goes wrong:**
BYOK is the project's entire trust model. The instant a user's OpenRouter or Anthropic key shows up in a `print()`, a server log file, an error trace posted to a public issue, or — worst — an outbound HTTP request to a "telemetry" endpoint, the trust is gone. The repo already has 354 `print()` calls (`CONCERNS.md` "Print-based logging across long-running trainers"); the same casual `print` habit will leak keys.

**Why it happens:**
- Debugging an OpenRouter integration usually involves printing the request headers, which include `Authorization: Bearer sk-...`.
- Default `httpx` / `requests` exception messages include the request URL but not headers; default `aiohttp` request logging can include them.
- Open-source telemetry "for product analytics" is a tempting addition and a reputational killer.

**How to avoid:**
- Phase H: enforce zero-key-leak via a **logger filter** that redacts anything matching `sk-`, `sk-ant-`, `Bearer\s+\S+`, `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY` before any log handler sees it. Apply globally.
- No `print()` of any object that might transitively contain headers. Replace progress prints with structured logging.
- No outbound network calls from the backend other than to the explicit BYOK-configured providers. Document this as a tested invariant.
- Phone-home is **never enabled by default**, even opt-in is suspect; if usage telemetry ships, it must be local-only (file under `~/.prompt-optimizer/`).
- Keys live in `.env` and the in-app settings panel only; never echo them back to the UI after save (show `sk-****` masked); never persist to SQLite.
- `.gitignore` includes `.env` from day one; CI grep blocks `sk-`, `sk-ant-` patterns on PR.

**Warning signs:**
- `grep -rn 'print.*api_key\|print.*headers\|print.*Authorization' src/` returns hits.
- A traceback in an issue report contains a token-shaped string.
- Any `requests.post` / `httpx.post` to a non-provider host.

**Phase to address:** H (logger redaction filter, telemetry policy), B (no key persistence), present from B onward.

---

## Significant Pitfalls

### Pitfall 11: Joblib model load × N workers = N× memory footprint

**What goes wrong:**
Uvicorn / Gunicorn with `--workers N` runs N separate Python processes. Each loads its own copy of `task_type_classifier.joblib` (1.8 MB), `model_router.joblib` (4.1 MB), and especially the `sentence-transformers` model used by the embedding router (~90 MB of weights + torch runtime overhead, easily 300–500 MB resident per worker). Default `--workers 4` × 500 MB = 2 GB of RAM gone before the first request. Memory is consumed linearly with worker count (verified in [FastAPI deployment docs](https://fastapi.tiangolo.com/deployment/server-workers/)).

**Why it happens:**
- "Use 4 workers" is cargo-cult advice for FastAPI.
- The embedding router was an experiment; if it stays in the production hot path, every worker pays the cost.
- Open-source users run on laptops with 8–16 GB RAM; one heavy app can choke the box.

**How to avoid:**
- Phase A: default to `--workers 1` for the local-app shape. Document `--workers N` as a deployment knob for hosted use only.
- Load models lazily on first use, not at import time. The agentic-intent classifier (small) at startup is fine; the sentence-transformer (huge) should be guarded by a "do we actually need it?" check.
- Profile resident memory after startup and after the first request; document the expected number in README.
- Consider a single inference subprocess that serves all workers via a local socket, if multi-worker is needed (out of scope for v1 BYOK local use).

**Warning signs:**
- Memory > 1 GB at idle with no requests served.
- OOM kills on a 8 GB machine when launching with default config.
- Cold-start request takes 5+ seconds (model loading on first request) and surprises users.

**Phase to address:** A (`--workers 1` default, lazy load, document memory).

---

### Pitfall 12: Blocking sklearn `predict` inside an async handler

**What goes wrong:**
sklearn's `predict` / `predict_proba` calls are synchronous and CPU-bound. Inside a FastAPI `async def` handler they hold the event loop and block every other concurrent request from making progress until they return. A 50 ms `predict` × 10 concurrent users = the 10th user waits 500 ms before the loop even gets to their request. In a streaming-heavy chat app where dozens of SSE connections are open simultaneously, this is a hard ceiling on responsiveness.

**Why it happens:**
- `async def` looks like the right idiom for everything in FastAPI.
- The router pipeline is fast in absolute terms (tens of ms), which hides the problem under low load.
- sklearn is C-extension code that releases the GIL inside numpy operations but holds it around Python overhead — async cannot rescue it.

**How to avoid:**
- Phase A: wrap every sklearn call in `await run_in_threadpool(...)`. Make this a code-review rule.
- Where the routing decision is hot-path, consider `def` handlers (not `async def`) so FastAPI runs them in the threadpool automatically.
- Benchmark p99 latency under N=20 concurrent SSE streams; if it climbs past target, that's the smoking gun.

**Warning signs:**
- Routing latency p99 grows linearly with concurrent SSE count.
- Profiling shows the event loop blocked in `_predict_proba_lr` or `_decision_function`.

**Phase to address:** A (threadpool wrapping convention).

---

### Pitfall 13: SQLite write contention with concurrent chat threads

**What goes wrong:**
Persistent thread storage in SQLite. Multiple turns in multiple threads stream simultaneously, each appending message rows. Default SQLite serializes writers with a global write lock; under any concurrency, writers hit "database is locked" errors unless WAL mode and busy_timeout are configured. WAL allows readers and a writer to coexist but **does not allow multiple concurrent writers** — that remains the immutable SQLite limit.

**Why it happens:**
- SQLite "just works" for single-user demos and hides the concurrency limit until production load.
- Default `journal_mode=DELETE` and `busy_timeout=0` make the failure mode "instant lock error" not "wait for the lock."
- The current repo has zero database experience (`INTEGRATIONS.md` "Databases: None").

**How to avoid:**
- Phase P: on connection open, run `PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA busy_timeout=5000;` — these three together drop "locked" errors dramatically.
- Use a single writer connection per process (long-lived, reused), and ephemeral connections for readers. Do **not** use SQLAlchemy default connection pooling without setting `check_same_thread=False` and confirming per-thread semantics.
- Serialize writes through an `asyncio.Queue` if you see lock contention; better than randomly failing under burst load.
- For an open-source local app one user is realistic — start with SQLite, design schema so a future Postgres swap is a connection-string change.

**Warning signs:**
- "database is locked" appearing in logs at all.
- Writes taking > 100 ms even at low concurrency (sign of lock-wait).
- Chat history occasionally missing the last user message after a backend crash (sync mode too aggressive, not committed).

**Phase to address:** P (WAL + busy_timeout + writer pattern on day 1).

---

### Pitfall 14: Schema migrations in an open-source app with no migration tool

**What goes wrong:**
v1 ships with `threads(id, title, ...)` and `messages(id, thread_id, role, content, ...)`. v1.1 adds `messages.cost_usd` and `messages.backend`. Users on v1 update via `git pull` — their existing SQLite DB has the old schema, the new code expects new columns, and the app crashes on first query. Without a migration tool, the user's only recovery is "delete your chat history."

**Why it happens:**
- Migration tooling feels heavy for "just SQLite."
- Open-source distribution has no central control over when users update.
- Schema changes look harmless during development (you just blow away the dev DB).

**How to avoid:**
- Phase P: use a real migration tool from day one. `yoyo-migrations` or `alembic` against SQLite are both fine; pick one and commit to it. Migrations live in `migrations/` and run on backend startup.
- Maintain a `schema_version` table; refuse to start if the code expects a newer version than the DB and migrations can't bring it forward.
- Never rely on `CREATE TABLE IF NOT EXISTS` for schema changes — it doesn't add columns.
- Document the upgrade path in README ("the app auto-migrates on first start; back up `~/.prompt-optimizer/chats.db` before upgrading major versions").

**Warning signs:**
- A user reports `OperationalError: no such column` after `git pull`.
- The repo has more than one `CREATE TABLE` for the same table across history.

**Phase to address:** P (migrations from v1, not retrofitted).

---

### Pitfall 15: Inline storage of agent traces and screenshots → DB bloat

**What goes wrong:**
Computer-use streams base64 PNG screenshots, each easily 500 KB–2 MB. Claude Code emits full tool-call records including file diffs. Stored inline as `messages.content` BLOBs, a single agent thread can be 20–100 MB of database. SQLite handles BLOBs but page bloat hits read perf, backups balloon, and the user's `~/.prompt-optimizer/chats.db` is the size of a video library.

**Why it happens:**
- Storing the whole event stream "for fidelity" feels right.
- Screenshots especially are easy to forget — they look like small JSON in the stream and turn out to be megabytes encoded.
- Backups / sync products choke on a multi-GB SQLite file.

**How to avoid:**
- Phase P: store large blobs (screenshots, full file diffs) on disk under `~/.prompt-optimizer/blobs/<sha256>` and reference by hash from the DB. Schema gets `attachments(id, message_id, kind, sha256, size_bytes)`.
- Hard-limit screenshot retention (e.g., last 20 per thread, older ones LRU-pruned to disk-only or deleted).
- Provide a "Clear attachments" action in the UI per thread.
- Document max expected DB size in README.

**Warning signs:**
- `~/.prompt-optimizer/chats.db` > 500 MB after a few sessions.
- Chat list rendering > 2 seconds (sign of large blob reads in the message preview path).

**Phase to address:** P (blob-by-reference schema), U (clear-attachments UX).

---

### Pitfall 16: Mixing OpenRouter SSE event types (text vs tool_use vs reasoning vs usage) in one parser

**What goes wrong:**
OpenRouter SSE responses interleave: `choices[].delta.content` (text), `choices[].delta.tool_calls` (tool-use deltas, often with partial JSON arguments split across chunks), `choices[].delta.reasoning_details` (for reasoning models — see [GitHub issue ai-sdk-provider#22 "No Reasoning tokens"](https://github.com/OpenRouterTeam/ai-sdk-provider/issues/22) and [litellm#8631](https://github.com/BerriAI/litellm/issues/8631) which is the same bug), `usage` (cost/usage block in the **last** event, but only on clean completion), and a final `[DONE]` sentinel. Writing one generic "stream chunks → concat strings" parser produces: scrambled text + tool calls, missing reasoning blocks, no cost data, and a UI that has no idea what type of content it is rendering.

**Why it happens:**
- The OpenAI-compatible streaming spec looks like just-text-deltas; the additional event types are documented but not obvious.
- Reasoning blocks (o1 / extended-thinking) are a 2025–2026 addition; older parsers silently drop them.
- Usage data arrives last and is conditional on clean stream termination (cancelled streams may not get it — confirmed in OpenRouter streaming docs).

**How to avoid:**
- Phase B: model the SSE event stream as a **discriminated union**: `{type: "text_delta" | "tool_call_delta" | "reasoning_delta" | "usage" | "error" | "done"}`. The OpenRouter wrapper translates the raw SSE into this union before anything else sees it.
- Phase A/U: the streaming protocol from server to client uses the same discriminated union plus app-specific events (`heartbeat`, `route_decided`, `cost_cap_hit`, `agent_tool_call`, `screenshot`).
- Buffer partial JSON in tool-call argument deltas — they routinely split mid-string. Reassemble per `tool_call.id`.
- Capture usage when present; track a fallback estimate (token count × model price) for cancelled streams. Never assume usage will arrive.

**Warning signs:**
- Tool-call JSON arguments are malformed (broken between chunks).
- Cost telemetry shows $0 for many turns (usage block missed).
- Reasoning models produce visible output but the UI shows nothing for the thinking phase.

**Phase to address:** B (discriminated union in OpenRouter wrapper), A (typed SSE protocol), U (per-type renderers).

---

### Pitfall 17: Hardcoded OpenRouter model slugs going stale

**What goes wrong:**
`config/model_mapping.json` hardcodes 16 specific OpenRouter slugs (`openai/gpt-5`, `qwen/qwen3-235b-a22b-2507`, etc.). OpenRouter providers deprecate models on no fixed schedule; a model that worked last month returns 404 today. The router predicts "qwen3-235b-a22b-thinking-2507" with high confidence → the request fails → there is no fallback because the existing demo only "prints" the model name (`CONCERNS.md` "Model mapping: 7 of 16 entries are unverified / simulated"). Half of those entries are already null today.

**Why it happens:**
- Pinning specific slugs is correct for reproducibility but wrong for "live" routing.
- OpenRouter's `openrouter/auto` is the safe fallback but isn't currently a target of the trained router.
- The mapping is loaded once at startup; nothing periodically validates it against `/api/v1/models`.

**How to avoid:**
- Phase B: on backend startup, hit `GET https://openrouter.ai/api/v1/models` and validate that every `api_model` in `config/model_mapping.json` still exists. Surface mismatches in logs and demote unavailable models in the router's allowed-set.
- For unverified mapping entries (the 7 `"provider": "simulated"` rows), fall back to a verified model in the same tier rather than crashing.
- Use OpenRouter's `models` parameter on requests to express a fallback chain (e.g., `[predicted_model, tier_fallback, "openrouter/auto"]`). Set `provider.only` to lock to the BYOK provider when applicable, per [OpenRouter provider routing](https://openrouter.ai/docs/guides/routing/provider-selection).

**Warning signs:**
- A 404 from OpenRouter at request time, not at startup.
- The "OTHER" sentinel class fires more than 5% of the time.
- Users report "this used to work."

**Phase to address:** B (startup validation + fallback chain), R (router output respects allowed-set).

---

### Pitfall 18: OpenRouter app-attribution headers missing → no analytics + maybe broken BYOK

**What goes wrong:**
OpenRouter expects `HTTP-Referer` (your app URL) and `X-Title` (your app name) on every request. Missing them means: (a) the app doesn't appear in OpenRouter's app rankings, (b) usage is uncategorized in the BYOK dashboard, and (c) some BYOK provider integrations behave differently when the attribution headers are absent ([OpenRouter app attribution docs](https://openrouter.ai/docs/app-attribution)). It's a minor cosmetic issue with a major debugging consequence: a user can't tell which app spent their money.

**Why it happens:**
- Headers are optional in the OpenAI-compatible spec; integrators forget them.
- Local-dev URLs (`http://localhost:3000`) feel wrong to send as `HTTP-Referer`, so people send nothing.

**How to avoid:**
- Phase B: every OpenRouter request includes `HTTP-Referer: https://github.com/<owner>/Prompt-Optimizer` and `X-Title: Prompt-Optimizer`. Hardcode them in the client wrapper.
- For BYOK preference, expose a provider-preferences toggle in settings that maps to OpenRouter's `provider.order` / `provider.only` fields.

**Warning signs:**
- OpenRouter dashboard shows usage attributed to "Unknown".
- BYOK keys behave inconsistently between curl and the app.

**Phase to address:** B (one-time wrapper configuration).

---

### Pitfall 19: Switching backends mid-thread breaks context

**What goes wrong:**
Thread starts on OpenRouter chat (Sonnet). Turn 5 the user says "now actually build me the app" → router decides Claude Code SDK → but the Claude Code SDK doesn't see the previous 5 turns of context in the same internal format the chat model was using. The agent acts blind to the conversation's earlier setup. Conversely, after a Claude Code run completes, the next chat-model turn needs the agent's output summarized into the chat history or it answers "what app?"

**Why it happens:**
- Each backend has its own conversation memory model. OpenRouter is stateless turn-by-turn; Claude Agent SDK maintains its own session; computer-use is single-shot.
- The chat UI shows a unified history, which **lies** about whether the backend saw all of it.

**How to avoid:**
- Phase A: maintain a **canonical thread history** in the FastAPI back-end. Every backend invocation receives a backend-appropriate **rendering** of that history (truncated, summarized, or formatted as system + user/assistant turns).
- For Claude Code transitions: write a context handoff message (`"Earlier in this thread the user discussed X, Y. Acting now on: <latest_turn>"`) into the SDK prompt.
- For computer-use transitions: pass only the latest action goal + a short context summary; do not dump 5 turns of chat.
- Phase U: surface a per-turn backend chip so users can see "this turn went to Claude Code with context from turns 1–4" — transparency defuses the "wait, what did it see?" question.

**Warning signs:**
- Agent runs in turn N start by asking the user to repeat information from turn N-1.
- Chat-model turns immediately after an agent turn forget what the agent did.
- Users say "it seemed to forget."

**Phase to address:** A (canonical history + per-backend rendering), U (backend chip with context summary).

---

### Pitfall 20: Backend chip too prominent (noise) or too hidden (no trust)

**What goes wrong:**
Two failure modes of the routing rationale UI:
1. **Too prominent:** every turn shows a multi-line "Routing decision: predicted task=coding (0.87), agentic-intent=false (0.62), backend=openrouter, model=openai/gpt-5-chat, fallbacks=[..], cost=$0.0023, latency=412ms." Users tune it out and miss the time it actually matters.
2. **Too hidden:** the chip is a single 🤖 emoji in the corner; users have no idea why responses vary in quality and assume the app is broken when one turn is markedly different.

**Why it happens:**
- Building the routing UI is done by people who built the router and want to see all the signal.
- Then it's pared back without user research.
- The Comet inspiration in PROJECT.md is explicit ("auto-routing + agent capability + slick single-input UX"), but Comet's chip is itself an active design problem.

**How to avoid:**
- Phase U: ship a compact default — backend name + 1-line rationale, e.g., `claude-code · agentic build task`. Click expands to full reasoning.
- Always show backend; never collapse to invisibility.
- Use color coding for backend (chat/code/computer-use) so visual scanning works without reading.
- A/B the chip wording with the canary prompt set; aim for "user reads chip in < 1 second."

**Warning signs:**
- User feedback "I don't understand why the answers vary."
- Chip text wider than half the message width.
- Demo viewers ask "wait, where does it say what model it used?"

**Phase to address:** U (chip design pass + interaction).

---

### Pitfall 21: User wants to override the route, no override UX exists

**What goes wrong:**
The router picks `openrouter/gpt-5-chat`. The user *knows* they want Claude Code instead. Today: they have to re-phrase the prompt to trigger the agentic-intent classifier, and they won't get this right on the first try. The Comet user-experience contract is "I shouldn't have to pick a model" — but the escape hatch when the router is wrong is critical for trust. Without it the product feels broken even when it routes correctly 90% of the time, because the 10% has no recovery.

**Why it happens:**
- "We removed the model picker" is taken too literally.
- Override UX wasn't scoped for v1.
- Engineers assume the router will be good enough; in reality early routers always need a manual override path.

**How to avoid:**
- Phase U: ship a per-turn override affordance ("Switch to Claude Code instead", "Use cheap chat") that **re-runs the current turn with the chosen backend**. Track usage as a signal — high override rates per backend are the strongest training signal you have without breaching "no live retraining loop" (v1 just logs; v2 may retrain).
- Phase U: a slash-command `/claude-code build me an app` syntax for power users.
- Surface the override in the rationale chip ("Routed to X. Wrong? → Use Y").

**Warning signs:**
- Demo users abandon a thread instead of correcting the route.
- Overrides in the decision log skew heavily toward one backend (free training signal).

**Phase to address:** U (override UX, slash commands), P (logging override events).

---

### Pitfall 22: Streaming code blocks re-highlighting on every chunk → UI flicker

**What goes wrong:**
A response containing a 200-line code block streams in 50-token chunks. Naïvely, on every chunk the markdown renderer re-parses the whole message and re-runs `highlight.js`/`shiki` over the partial code block. Result: a flickering, expensive re-render storm; on slower machines the typing appears jerky and lines flash white. Worse, partial code mid-stream often parses as a different language than the complete block, so syntax colors *change* as the code arrives.

**Why it happens:**
- Markdown rendering is fast; full document re-render every chunk feels okay at low message length.
- Syntax highlighting is expensive and language-detection is unstable on partial code.
- `useChat`-style hooks invalidate the whole message on each delta.

**How to avoid:**
- Phase U: render incoming chunks as plain text inside a `<pre>` until the fenced block closes; only run syntax highlighting on closed blocks.
- Memoize per-message rendering keyed on message ID + content length; don't re-render previous messages.
- For partial visible code (mid-stream), use a single neutral color or a stable hint from the opening ` ```python ` fence — never let the highlighter auto-detect on incomplete input.
- Test with a synthetic 500-line code response. If FPS drops in dev tools, the architecture is wrong.

**Warning signs:**
- Code block colors change as characters arrive.
- React DevTools profiler shows the whole message tree re-rendering per chunk.
- CPU pegs at 100% during streaming on a typical laptop.

**Phase to address:** U (chunked rendering + post-close highlighting).

---

### Pitfall 23: Auto-scroll fighting the user's intent

**What goes wrong:**
User scrolls up to read a previous turn while a new response streams in. Naïve auto-scroll snaps them back to the bottom on every chunk. They scroll up again, get snapped down again. The chat is unusable during a long response.

**Why it happens:**
- "Always scroll to bottom on new content" is the default chat behavior.
- The streaming delta rate hides the scroll fight from the developer who only tested short responses.

**How to avoid:**
- Phase U: maintain a `userIsAtBottom` flag (e.g., scroll position within 64px of bottom). Auto-scroll only when true. Show a "↓ new messages" affordance when not at bottom.
- Throttle scroll-into-view to ≤ 4 Hz; per-chunk scroll calls saturate the rendering pipeline.

**Warning signs:**
- During a long response, scroll position oscillates.
- User feedback "I can't read what it just said."

**Phase to address:** U (scroll-management on day 1 of streaming UI).

---

### Pitfall 24: Hydration mismatch on server-rendered streamed content

**What goes wrong:**
Next.js App Router server-renders thread pages; client hydrates them and resumes the SSE stream. If the server-rendered HTML contains a timestamp formatted with `toLocaleString()` (which uses the server timezone) and the client re-renders it with the user's timezone, React throws a hydration mismatch. Similar issues hit any "Just now"-style relative-time strings, message-ID-based React keys that differ between server and client, and Markdown rendering libraries whose output differs across versions/runtimes.

**Why it happens:**
- "Server render the thread + client resumes streaming" sounds clean and is the standard App Router pattern.
- Hydration mismatches are common enough that Next.js 16 lists five canonical causes ([Medium: Next.js 16 Listed 5 Hydration Error Causes](https://medium.com/@adi_leviim/next-js-16-listed-5-hydration-error-causes-mine-was-a-6th-2026-baeca8060c4d)).

**How to avoid:**
- Phase U: render timestamps as ISO strings on the server; format client-side after mount inside `useEffect`.
- Avoid relative-time displays that depend on `Date.now()` in the SSR output — render absolute time, replace with relative after hydration.
- Use deterministic React keys (message UUIDs from the DB, never `Math.random()` or array indices).
- Don't `fetch` with `cache: 'force-cache'` for thread message lists — chat data is dynamic.

**Warning signs:**
- Hydration warnings in the browser console.
- Time-ago strings flickering on first render.
- A `useEffect`-set state in a "Just now" badge causing layout shift.

**Phase to address:** U (SSR-safe rendering patterns).

---

### Pitfall 25: Heavy first-run dependencies break the "fresh clone" promise

**What goes wrong:**
A new user clones the repo, runs the quickstart, and:
- `sentence-transformers` first-import downloads ~90 MB of weights from Hugging Face (`CONCERNS.md` "Embedding model loaded per script invocation").
- `nltk.download("punkt_tab")` fires inside `_ensure_nltk_sentence_tokenizer()` and fails silently if offline (`CONCERNS.md` "Silent `nltk.download(...)` on import path").
- Trained model artifacts are committed to git (~7 MB) but the **CSV data they were trained on is in git-LFS pointers** — without `git lfs pull` they get 130-byte placeholder files that pandas reads as a 3-line junk CSV (`CONCERNS.md` "LFS-tracked CSVs are committed as unresolved pointers, HIGH"). And `git lfs` is not installed by default.
- If they want computer-use, that's a multi-GB Docker pull.

The "clone and run" promise is broken on day one. Every onboarding friction here is the user's first interaction with the open-source project.

**Why it happens:**
- Brownfield repo with research-grade deps and a missing requirements manifest.
- LFS-tracked CSVs assume `git-lfs` is universal; it isn't.
- Maintainer test environment "just has the cache warm."

**How to avoid:**
- Phase H: `make setup` script that runs `git lfs install && git lfs pull`, downloads `punkt_tab`, warms the sentence-transformer cache, and creates a `.env` from `.env.example`.
- Document the disk/bandwidth cost up front in README ("first setup downloads ~150 MB").
- Provide a `--no-embedding-router` mode that skips sentence-transformers entirely for the lightweight path.
- README **must work top-to-bottom on a fresh clone** — tested by a contributor who hasn't run the project before, not by the maintainer.
- Pin every dependency in `pyproject.toml` (CONCERNS.md "No dependency manifest, HIGH" must be closed before this milestone ships).

**Warning signs:**
- "Works on my machine" issue reports.
- `pd.read_csv(...)` fails with "Expected 1 fields, saw N" — that's the LFS pointer being parsed as CSV.
- First `python -m src.demo.demo_router` run hangs (NLTK download stalled).

**Phase to address:** H (setup script, pinned deps, README rewrite, fresh-clone test).

---

### Pitfall 26: Evaluation only measures task_type accuracy — ignores routing-as-decision quality

**What goes wrong:**
Current evaluation infrastructure (`evaluation/*.csv`, per-class F1 plots) tells you whether the classifier got `task_type` right. It does **not** tell you whether the *routing decision* was right. A correctly-classified `coding` prompt routed to a chat model when the user wanted Claude Code is a routing failure with a 100% task-classifier accuracy. The agentic-intent classifier is new and won't show up in old metrics. Evaluating routing quality requires labeling prompts with the *intended backend*, not the task type.

**Why it happens:**
- Existing metrics inherited from a single-model classification problem.
- "Decision-quality" labels don't exist in LLMRouterBench.
- Easy to keep optimizing what's measured.

**How to avoid:**
- Phase R: maintain a **routing decision eval set** separate from the task-type test split. Each row: `{prompt, expected_backend, expected_model_tier, notes}`. Hand-labeled, ~100 prompts to start. Re-evaluate every router change.
- Compute "backend accuracy" and "tier accuracy" alongside task accuracy.
- For agentic-intent classifier specifically: precision/recall on a binary eval set, with a chosen operating point (the false-positive cost of agentic→chat misroute is much lower than chat→agentic misroute, which spends money on Claude Code for a one-liner).

**Warning signs:**
- Router improvements show up in F1 but users don't notice the difference.
- F1 on `coding` is 0.9 but coding prompts still route to chat 30% of the time.
- No reviewer can answer "is this PR a routing-quality improvement?"

**Phase to address:** R (routing decision eval set + dedicated metrics).

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Skip the pinned dependency manifest (extend `CONCERNS.md` debt into the new milestone) | Faster iteration during integration phase | Joblib artifacts become unloadable on dep drift; "works on my machine" support burden | Never — the open-source distribution constraint makes this non-negotiable |
| Hardcoded if/else routing rules inside the FastAPI handler | Quick fix for a single bad case | Rule sprawl, untestable, drifts from trained model (Pitfall 4) | Only as a named, tested entry in the declarative rules table |
| Single global `Workspace` shared by all Claude Code threads | Skips per-thread workspace management | File collisions, lost user work (Pitfall 7) | Never |
| Computer-use enabled by default | "Works out of the box" demo | Security event waiting to happen (Pitfall 8) | Never |
| Print debugging API requests/responses | Fast troubleshooting | Key leak risk (Pitfall 10) | Local dev only with a redaction filter installed |
| Store screenshots inline as TEXT blobs in SQLite | Schema simplicity | DB bloat (Pitfall 15) | Only with a hard cap (e.g., < 10 retained per thread) and migration plan to blob-by-reference |
| Skip migrations, just `CREATE TABLE IF NOT EXISTS` | Faster schema iteration | Users on `git pull` get crashes (Pitfall 14) | Pre-v1 dev only — never after the first external user installs |
| Re-render whole markdown tree on every stream chunk | Easier to wire up streaming | UI flicker and CPU saturation (Pitfall 22) | Acceptable for the very first streaming spike; never in shipped UI |
| Phone-home telemetry for "product analytics" | Visibility into user behavior | Reputational killer in open source (Pitfall 10) | Never opt-out-default; opt-in local-file telemetry is the most that's defensible |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| `claude-agent-sdk` (Python) | Installing `claude-code-sdk` (deprecated package) or expecting Claude Code's default behavior post-rename | Install `claude-agent-sdk`, pass `claude_code` system-prompt preset explicitly (Pitfall 5) |
| Claude Agent SDK streaming | Treating it as a single HTTP call; no idle watchdog | Set `CLAUDE_ENABLE_STREAM_WATCHDOG=1` + finite `CLAUDE_STREAM_IDLE_TIMEOUT_MS`; use `query.interrupt()` for cancellation (Pitfall 6) |
| Anthropic computer-use | Shipping the reference Docker container as the default backend, enabled by default | Opt-in only; document threat model; cost+step cap; consider `anthropic-experimental/sandbox-runtime` (Pitfall 8) |
| OpenRouter streaming | Parsing `delta.content` as the only event type | Discriminated union of `text/tool_call/reasoning/usage/done`; reassemble partial JSON per `tool_call.id` (Pitfall 16) |
| OpenRouter model list | Hardcoding 16 slugs and trusting them forever | Validate against `/api/v1/models` on startup; use `models` parameter for per-request fallback chain (Pitfall 17) |
| OpenRouter BYOK | Forgetting `HTTP-Referer` / `X-Title`; not setting `provider.only` when BYOK is meant to be exclusive | Hardcode attribution headers in the wrapper; expose `provider.order` / `provider.only` in settings (Pitfall 18) |
| OpenRouter cancellation | Closing the browser tab and assuming the upstream stops | Forward client disconnect to `httpx.AsyncClient.aclose()` on the OpenRouter request so OpenRouter stops billing (Pitfall 9) |
| SQLite via FastAPI | Default `journal_mode=DELETE` + `busy_timeout=0` + shared connection across threads | `WAL` + `busy_timeout=5000` + per-thread connections; one long-lived writer connection (Pitfall 13) |
| Sentence-transformers + multiple Uvicorn workers | `--workers 4` default ⇒ 4× the embedding model in RAM | `--workers 1` default, lazy load, document expected RAM (Pitfall 11) |
| sklearn predict in FastAPI async handler | `async def` everywhere | Wrap in `run_in_threadpool` or use sync `def` handlers (Pitfall 12) |
| NLTK / Hugging Face downloads on import | First-time import hits the network; CI hangs offline | `make setup` pre-fetches; fail loudly when offline (Pitfall 25) |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Re-render markdown + re-highlight code on every SSE chunk | UI flicker, CPU spikes, browser fan kicks on | Render unclosed code as plain text; memoize per-message; highlight only on close (Pitfall 22) | Any response with > 50 lines of code |
| Multiple Uvicorn workers each holding sentence-transformer model | 1.5 GB+ RAM at idle, OOM on 8 GB laptops | `--workers 1`, lazy load embedding model, gate behind feature flag (Pitfall 11) | First multi-user dev box / first hosted deploy |
| Synchronous sklearn `predict` blocking async handler | p99 latency climbs with concurrency; event loop visibly stalled | `run_in_threadpool` wrapping convention (Pitfall 12) | > 5 concurrent in-flight requests |
| Inline screenshot/agent-trace storage in SQLite | DB > 500 MB; slow message-list rendering | Blob-by-reference; retention cap per thread (Pitfall 15) | A few sessions of computer-use |
| SSE without heartbeats during long agent runs | Idle proxy/browser disconnects mid-run | 15-second heartbeat events; visible elapsed indicator (Pitfall 6) | Any agent run > 60 s |
| Per-chunk DB writes for streaming messages | Write contention, "database is locked" | Buffer chunks, write once per N tokens or per second (combined with WAL + busy_timeout) | Concurrent streams in 2+ threads |
| Polling for new messages instead of subscribing | Battery drain on laptop; bandwidth waste | SSE-only update path; no polling fallback in v1 | Always |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Printing request headers (with `Authorization`) during integration debugging | API key leak into logs / issue reports | Logger redaction filter; ban `print(request)` patterns in code review (Pitfall 10) |
| Persisting BYOK keys in SQLite for "convenience" | Theft on disk-image dump or backup leak | Keys in `.env` and in-memory settings only; mask in UI; never persist to DB (Pitfall 10) |
| Trusting prompt content when invoking computer-use | Prompt injection from visited webpages → file exfiltration, shell exec | Computer-use disabled by default; opt-in flag; per-turn cost+step cap; document threat model (Pitfall 8) |
| Running Claude Code agents against the user's real `cwd` by default | Unintended edits to important files | Ephemeral per-thread workspace; opt-in to real cwd; serialize per-workspace (Pitfall 7) |
| `joblib.load` on artifacts of unknown provenance | Pickle deserialization → arbitrary code exec (`CONCERNS.md` flags this) | Only load committed artifacts in v1; if third-party, switch to `skops` or ONNX. Document trust model in README. |
| Outbound HTTP to a non-provider host | Phone-home perception → reputational damage | Allow-listed outbound hosts: OpenRouter, Anthropic, only. Tested as a runtime invariant (Pitfall 10) |
| `.env` not in `.gitignore` (repo currently has no root `.gitignore`, see CONCERNS.md) | Accidental key commit | Add `.env`, `*.key`, `*.pem`, `__pycache__/` to root `.gitignore` before adding any key handling code |
| CORS misconfiguration during local dev (Next.js on 3000, FastAPI on 8000) | Either too permissive (`*`) shipped to "prod," or too restrictive blocking the demo | Explicit `allow_origins=["http://localhost:3000"]`; environment-driven; never `["*"]` with `allow_credentials=True` |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Hidden routing rationale | User can't trust the auto-routing | Always-visible backend chip with 1-line rationale (Pitfall 20) |
| Over-explained routing rationale | Visual noise, scrolled past | Compact chip; expand on click (Pitfall 20) |
| No override when route is wrong | User abandons rather than corrects | Per-turn "switch backend, re-run" affordance + slash commands (Pitfall 21) |
| Visible model name shift between turns with no explanation | "Why did it just use a different model?" | Chip explains the routing change; user sees the rationale (Pitfall 19, 20) |
| Stop button doesn't stop | Lost trust, possible runaway cost | Cancellation wired to SDK `interrupt()` + upstream HTTP abort (Pitfall 6, 9) |
| Auto-scroll snapping while user reads back | Cannot read previous content during a stream | `userIsAtBottom` check; "↓ new messages" affordance (Pitfall 23) |
| Code blocks flickering during streaming | Looks broken | Plain-text until fence closes; highlight on completion (Pitfall 22) |
| Live cost not visible | $$ surprise on the provider dashboard | Per-turn running cost in the UI; per-turn cap enforced visibly (Pitfall 9) |
| Computer-use silent failures (sandbox not configured) | User thinks the app is broken | Surface "computer-use is disabled / not configured" with a link to setup (Pitfall 8) |
| Multiple Claude Code threads silently colliding | Lost edits, confused user | Workspace badge in thread settings; "agent busy in another thread" status (Pitfall 7) |

## "Looks Done But Isn't" Checklist

- [ ] **Live OpenRouter call:** Often missing `HTTP-Referer` / `X-Title` headers and a per-request fallback chain — verify by checking the OpenRouter dashboard attribution + force a 404 in dev to confirm fallback triggers.
- [ ] **SSE streaming endpoint:** Often missing heartbeat events and disconnect-cancels-upstream — verify by closing the browser tab mid-stream and checking that the OpenRouter request is aborted.
- [ ] **Claude Code SDK integration:** Often missing `query.interrupt()` wiring on the stop button — verify by clicking stop mid-run and observing the agent actually stops within 2 seconds.
- [ ] **Computer-use integration:** Often missing opt-in gating, per-turn cost cap, and step cap — verify by reading the threat-model section of the README and the cost-cap code path.
- [ ] **BYOK key handling:** Often missing the redaction logger filter and the masked-in-UI display — verify by triggering an exception during a request and inspecting logs.
- [ ] **SQLite setup:** Often missing `WAL` + `busy_timeout` pragmas — verify by `PRAGMA journal_mode;` after first connect.
- [ ] **Schema migrations:** Often missing a real migration tool — verify a v0→v1 schema change applies cleanly on an existing DB without data loss.
- [ ] **Calibrated router confidence:** Often missing — verify by inspecting the reliability diagram and the fallback-threshold tests in the eval pipeline.
- [ ] **Routing decision eval set:** Often missing — verify there is a `routing_decision_eval.csv` distinct from `classifier_training.csv`, evaluated on every router change.
- [ ] **Backend override UX:** Often missing — verify by clicking "switch to Claude Code" on a turn that routed elsewhere; the same prompt should re-run with the chosen backend.
- [ ] **Quickstart on fresh clone:** Often missing — verify by having a fresh contributor follow the README on a clean machine. Catch: LFS pull, NLTK download, deps install, demo prompts.
- [ ] **Cost cap enforcement:** Often missing — verify by setting a $0.01 cap and asking for a long response; the run must abort and the UI must show "cost cap hit."
- [ ] **Per-thread Claude Code workspace:** Often missing — verify by opening two threads simultaneously, running Claude Code in both, and checking that file edits don't cross over.
- [ ] **CORS configuration:** Often misconfigured — verify the Next.js dev server (port 3000) talks to FastAPI (port 8000) without `*` origin.
- [ ] **Hydration:** Often broken with timestamps — verify by opening a thread page with several old messages and checking the browser console for hydration warnings.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Production drift on benchmark router (Pitfall 1) | MEDIUM | Add OOD class + canary set, lower confidence threshold for fallback, retrain offline against augmented data; v2 may take live decision-logs as new training data once the no-live-retraining v1 constraint is relaxed |
| Hardcoded model 404 from OpenRouter (Pitfall 17) | LOW | Hot-update `config/model_mapping.json`; existing fallback chain already in code if Pitfall 17 was prevented; redeploy |
| API key leak in logs (Pitfall 10) | HIGH | Rotate all impacted keys immediately; install logger redaction; audit existing logs; post-mortem on whose machines had logs |
| Computer-use prompt-injection incident (Pitfall 8) | HIGH | Disable feature globally via env flag; review threat model; require explicit opt-in for next release; document affected users |
| Multi-thread Claude Code file collision (Pitfall 7) | MEDIUM | Restore from user backup if any; introduce per-thread workspace; lock per `cwd` |
| SQLite "database is locked" storm (Pitfall 13) | LOW | Apply `WAL` + `busy_timeout` pragmas + restart |
| DB schema mismatch after `git pull` (Pitfall 14) | MEDIUM | Ship a one-off migration; recommend backup-and-replay; introduce real migration tool |
| Cost runaway (Pitfall 9) | HIGH | Kill the running tab/process; clamp daily cap to 0; review missing per-turn caps; communicate with affected user |
| Hydration mismatch reports (Pitfall 24) | LOW | Switch offending render to client-only via `useEffect`; SSR ISO timestamps |
| UI flicker on code streaming (Pitfall 22) | LOW | Plain-text-until-close + per-message memoization |

## Pitfall-to-Phase Mapping

Phases referenced are the working hypothesis: **R** = Router-brain extension (agentic-intent classifier, decision layer, calibration, decision eval set), **B** = Backend integrations (OpenRouter, Claude Agent SDK, computer-use), **A** = FastAPI back-end (streaming, threading, lifecycle), **U** = Next.js chat UI, **P** = Persistence (SQLite, migrations), **H** = Hardening / open-source release readiness.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1 — Benchmark drift on real prompts | R | Canary set passes; OOD class fires on truncated/emoji prompts in regression run |
| 2 — Task type ≠ backend (scope blindness) | R | Decision eval set distinguishes "explain X" from "build X" with correct backend |
| 3 — Overconfident probabilities | R | Reliability diagram in eval; fallback fires below threshold in unit test |
| 4 — Rules drifting from ML | R | All rules in a single declarative table; per-rule test; decision-log shows rule firings |
| 5 — Wrong SDK package | B | `pyproject.toml` pins `claude-agent-sdk`; CI smoke test asserts import |
| 6 — Agent runs timing out / hanging | B + A + U | `CLAUDE_ENABLE_STREAM_WATCHDOG=1` set; heartbeat events emitted; stop button cancels within 2s |
| 7 — Concurrent Claude Code workspace collisions | B | Per-thread workspace by default; lock per cwd; test with two simultaneous agent threads |
| 8 — Computer-use unsafe defaults | B + H | Disabled-by-default; opt-in flag; cost+step cap; README threat model section present |
| 9 — Cost runaway | B + A + P + U | Per-turn USD cap unit test; daily-cap integration test; tab-close-cancels-upstream test; live-cost UI element |
| 10 — Key / prompt leakage | H + B (and present from B onward) | Logger redaction filter active globally; `.gitignore` covers `.env`; CI grep blocks `sk-`/`sk-ant-` patterns |
| 11 — Joblib × N workers RAM blowup | A | `--workers 1` default in startup docs; idle RAM measured in README; lazy load test |
| 12 — Blocking sklearn in async handler | A | p99 latency under N=20 concurrent streams stays inside budget |
| 13 — SQLite write contention | P | `PRAGMA journal_mode=WAL` verified on connect; concurrency test passes |
| 14 — Schema migration breakage | P | `yoyo`/`alembic` migrations from v1; v0→v1 upgrade test on a populated DB |
| 15 — Inline blob bloat | P | Screenshots go to blob-by-reference; DB size stays bounded in long-thread test |
| 16 — Mixed SSE event types | B + A + U | Discriminated-union parser; partial-JSON reassembly test; reasoning-block rendering test |
| 17 — Stale OpenRouter model slugs | B | Startup validation against `/api/v1/models`; fallback chain unit test |
| 18 — Missing OpenRouter attribution | B | Outbound request inspector confirms `HTTP-Referer` + `X-Title` present |
| 19 — Backend switching breaks context | A + U | Mid-thread backend switch test (chat → code → chat) with context preserved |
| 20 — Backend chip noise vs invisibility | U | Design review against canary prompts; 1-line default, expandable |
| 21 — No override when route is wrong | U + P | Per-turn override re-runs current turn; logged for v2 retraining signal |
| 22 — Code-block flicker | U | Render profiler shows zero re-highlight during stream of unclosed fence |
| 23 — Auto-scroll fighting user | U | Manual scroll-up during streaming is sticky; "↓ new messages" pill appears |
| 24 — Hydration mismatch | U | Zero hydration warnings on thread reload with 20+ messages |
| 25 — Heavy first-run dependencies | H | Fresh-clone walkthrough by a non-maintainer; `make setup` runs clean offline-after-first-cache |
| 26 — Evaluation blind to routing quality | R | `routing_decision_eval.csv` exists and is part of every router-PR regression run |

## Sources

- [Migrate to Claude Agent SDK — Anthropic docs](https://code.claude.com/docs/en/agent-sdk/migration-guide) — SDK rename, breaking `ClaudeCodeOptions → ClaudeAgentOptions`, default system-prompt change (Pitfall 5)
- [Claude Agent SDK for Python — PyPI](https://pypi.org/project/claude-agent-sdk/) — package status, deprecation of `claude-code-sdk` (Pitfall 5)
- [Agent SDK reference — TypeScript](https://code.claude.com/docs/en/agent-sdk/typescript) — `query.interrupt()` API for cancellation (Pitfall 6)
- [BUG: Claude Code hangs indefinitely on streaming stall](https://github.com/anthropics/claude-code/issues/25979) — `CLAUDE_ENABLE_STREAM_WATCHDOG` / `CLAUDE_STREAM_IDLE_TIMEOUT_MS` env vars (Pitfall 6)
- [Bedrock streaming stalls hang forever](https://github.com/anthropics/claude-code/issues/29344) — second confirmation of the stall pattern (Pitfall 6)
- [Streaming Text Deltas Pause for 3+ Minutes](https://github.com/anthropics/claude-agent-sdk-typescript/issues/44) — same class of stall in the new SDK (Pitfall 6)
- [OpenRouter API Streaming docs](https://openrouter.ai/docs/api/reference/streaming) — usage in last SSE event; cancellation behavior on supported providers (Pitfall 9, 16)
- [OpenRouter Usage Accounting](https://openrouter.ai/docs/use-cases/usage-accounting) — when usage is/isn't available (Pitfall 16)
- [OpenRouter Reasoning Tokens guide](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens) — `reasoning_details` in deltas (Pitfall 16)
- [Issue: Reasoning with OpenRouter not available while streaming (litellm)](https://github.com/BerriAI/litellm/issues/8631) — known reasoning-in-stream bug (Pitfall 16)
- [No Reasoning tokens (ai-sdk-provider)](https://github.com/OpenRouterTeam/ai-sdk-provider/issues/22) — second confirmation, ai-sdk side (Pitfall 16)
- [OpenRouter Provider Routing](https://openrouter.ai/docs/guides/routing/provider-selection) — `order`, `only`, fallback semantics (Pitfall 17, 18)
- [OpenRouter BYOK](https://openrouter.ai/docs/guides/overview/auth/byok) — BYOK fallback rules + `only` to lock provider (Pitfall 18)
- [OpenRouter App Attribution](https://openrouter.ai/docs/app-attribution) — `HTTP-Referer` + `X-Title` requirements (Pitfall 18)
- [Anthropic computer-use docs](https://docs.anthropic.com/en/docs/build-with-claude/computer-use) — current tool description, model versions (Pitfall 8)
- [anthropics/anthropic-quickstarts — computer-use-demo](https://github.com/anthropics/anthropic-quickstarts/blob/main/computer-use-demo/README.md) — reference Docker container (Pitfall 8)
- [anthropic-experimental/sandbox-runtime](https://github.com/anthropic-experimental/sandbox-runtime) — research-preview lightweight sandbox (Pitfall 8)
- [Anthropic Engineering: Claude Code sandboxing](https://www.anthropic.com/engineering/claude-code-sandboxing) — sandbox design (Pitfall 8)
- [Claude Computer Use: A Ticking Time Bomb (prompt.security)](https://prompt.security/blog/claude-computer-use-a-ticking-time-bomb) — prompt-injection threat surface (Pitfall 8)
- [How to Sandbox Claude Code (MintMCP)](https://www.mintmcp.com/blog/sandbox-claude-code) — Docker + Claude Code sandbox combination (Pitfall 8)
- [AI Agent Token Budget Management (MindStudio)](https://www.mindstudio.ai/blog/ai-agent-token-budget-management-claude-code) — automatic compaction + pre-execution budget checks (Pitfall 9)
- [I Spent $0.20 Reproducing the Multi-Agent Loop That Cost Someone $47K](https://medium.com/@mohamedmsatfi1/i-spent-0-20-reproducing-the-multi-agent-loop-that-cost-someone-47k-7f57c51f3c06) — canonical cost-runaway case study (Pitfall 9)
- [scikit-learn CalibratedClassifierCV](https://scikit-learn.org/stable/modules/generated/sklearn.calibration.CalibratedClassifierCV.html) — calibration API (Pitfall 3)
- [scikit-learn Probability Calibration](https://scikit-learn.org/stable/modules/calibration.html) — LogisticRegression calibration properties, when to wrap (Pitfall 3)
- [LLMRouterBench / RouterBench](https://www.emergentmind.com/topics/llmrouterbench) — training data scope and known generalization limits (Pitfall 1)
- [FastAPI Server Workers](https://fastapi.tiangolo.com/deployment/server-workers/) — per-worker memory linearity (Pitfall 11)
- [FastAPI Mistakes That Kill Your Performance (dev.to)](https://dev.to/igorbenav/fastapi-mistakes-that-kill-your-performance-2b8k) — blocking-in-async-handler pitfalls (Pitfall 12)
- [SQLite Concurrency: WAL Mode, Thread Safety (iifx.dev)](https://iifx.dev/en/articles/17373144) — WAL semantics for concurrent writers (Pitfall 13)
- [SQLite concurrent writes and "database is locked" errors](https://tenthousandmeters.com/blog/sqlite-concurrent-writes-and-database-is-locked-errors/) — `busy_timeout` impact (Pitfall 13)
- [Abusing SQLite to Handle Concurrency (SkyPilot)](https://blog.skypilot.co/abusing-sqlite-to-handle-concurrency/) — production patterns (Pitfall 13)
- [AI SDK 5 — Vercel](https://vercel.com/blog/ai-sdk-5) — `useChat` Transport, UIMessageChunk event types (Pitfall 16)
- [AI SDK UI: Stream Protocols](https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol) — SSE event protocol (Pitfall 16)
- [Next.js 16 Listed 5 Hydration Error Causes (Medium)](https://medium.com/@adi_leviim/next-js-16-listed-5-hydration-error-causes-mine-was-a-6th-2026-baeca8060c4d) — hydration mismatch patterns (Pitfall 24)
- [Next.js Caching docs](https://nextjs.org/docs/app/getting-started/caching) — fetch cache behavior in 2026 App Router (Pitfall 24)
- Local context: `/Users/michaelmarrero/GitHub/Prompt-Optimizer/.planning/PROJECT.md`, `.planning/codebase/CONCERNS.md`, `.planning/codebase/INTEGRATIONS.md`, `.planning/codebase/TESTING.md` — current state of the brownfield repo, known concerns this milestone must address rather than re-create.

---
*Pitfalls research for: auto-routing multi-backend AI chat on top of an existing offline scikit-learn routing pipeline*
*Researched: 2026-05-11*

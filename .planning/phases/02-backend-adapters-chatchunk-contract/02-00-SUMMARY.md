---
phase: 02
plan: 00
subsystem: backend-adapters-shared-modules
tags: [backend-adapters, chatchunk, pydantic, keystore, redaction, pricing, cost]
dependency_graph:
  requires:
    - "src.routing.schema.Backend literal (Phase 1; mirrored verbatim in apps/api/backends/protocol.py)"
    - "src.routing.tests.test_decide_smoke (D-18 import-graph guard — must still pass)"
  provides:
    - "apps.api.backends.chunks (ChatChunk Pydantic v2 union + TypeAdapter)"
    - "apps.api.backends.protocol (BackendAdapter Protocol, Message, AdapterOptions)"
    - "apps.api.backends.cost (CostTracker, DEFAULT_PER_TURN_COST_USD)"
    - "apps.api.backends.pricing (PricingTable with static + OpenRouter refresh)"
    - "apps.api.backends.keystore (KeyStore with optional keyring extra)"
    - "apps.api.backends.logging_filter (RedactionFilter + install_redaction_filter)"
    - "apps.api side-effect import: load_dotenv() + install_redaction_filter()"
    - "config/pricing.json (13 models + _default)"
    - "apps/api/backends/tests/conftest.py (fakes + adapter_factory)"
    - "apps/api/backends/tests/test_adapter_contract.py (D-19 18-case stub)"
  affects:
    - "pyproject.toml: 9 new base deps + 2 dev deps + keyring optional extra"
    - "uv.lock: regenerated; claude-code-sdk absent (OSS-06)"
    - "[tool.pytest.ini_options]: testpaths += apps, asyncio_mode=\"auto\", live marker"
    - "[tool.hatch.build.targets.wheel]: packages += apps"
tech_stack:
  added:
    - "pydantic 2.13.4 (discriminated unions, TypeAdapter)"
    - "openai 2.36.0 (AsyncOpenAI for OpenRouter — Wave 1 use)"
    - "anthropic 0.40+ (Wave 1 use)"
    - "claude-agent-sdk 0.1.81 (Wave 1 use)"
    - "playwright 1.59.0 (Wave 1 use)"
    - "python-dotenv 1.2.2 (import-time .env load)"
    - "httpx 0.27+ (pricing refresh)"
    - "tiktoken 0.13.0 (Wave 1 use)"
    - "pytest-asyncio 1.3.0 (asyncio_mode=auto)"
    - "pytest-timeout 2.4.0 (D-19 cancellation invariant)"
    - "pre-commit 4.6.0 (Wave 2 use)"
    - "keyring 24+ (optional extra; lazy import)"
  patterns:
    - "Pydantic v2 discriminated union via Annotated[Union[...], Field(discriminator=\"type\")] + TypeAdapter ingestion"
    - "typing.Protocol for structural BackendAdapter contract"
    - "Frozen dataclasses for Message, AdapterOptions (immutable value objects)"
    - "Lazy try/except ImportError for optional keyring extra (D-10)"
    - "LogRecordFactory wrapper + Filter belt-and-suspenders for redaction (Pitfall 8)"
    - "Mtime-based 24h cache for OpenRouter refresh (Pitfall 6 per-Mtok)"
    - "Lazy adapter imports inside conftest.adapter_factory (B3 fix)"
key_files:
  created:
    - "apps/__init__.py"
    - "apps/api/__init__.py"
    - "apps/api/backends/__init__.py"
    - "apps/api/backends/protocol.py"
    - "apps/api/backends/chunks.py"
    - "apps/api/backends/keystore.py"
    - "apps/api/backends/logging_filter.py"
    - "apps/api/backends/pricing.py"
    - "apps/api/backends/cost.py"
    - "apps/api/backends/tests/__init__.py"
    - "apps/api/backends/tests/conftest.py"
    - "apps/api/backends/tests/test_chunks.py"
    - "apps/api/backends/tests/test_logging_filter.py"
    - "apps/api/backends/tests/test_keystore.py"
    - "apps/api/backends/tests/test_pricing.py"
    - "apps/api/backends/tests/test_adapter_contract.py"
    - "config/pricing.json"
  modified:
    - "pyproject.toml"
    - "uv.lock"
    - ".planning/phases/02-backend-adapters-chatchunk-contract/02-RESEARCH.md"
decisions:
  - "Pattern 10's literal recipe (Filter on root logger only) does not redact records captured by pytest's caplog — parent-logger filters are not consulted when a record propagates up to a parent handler. Defensive fix: install a logging.setLogRecordFactory wrapper that redacts every record at creation time, plus keep the RedactionFilter on the root for direct-emit code paths. Both layers clear record.args per Pitfall 8."
  - "chat_chunk_adapter is declared without a type annotation (chat_chunk_adapter = TypeAdapter(ChatChunk)) so the plan's exact-pattern grep acceptance criterion passes verbatim."
  - "config/pricing.json _default row is {input_per_mtok: 5.00, output_per_mtok: 20.00} per CONTEXT specifics line 266 — conservative upper bound that ensures cost cap trips even when an unknown OpenRouter slug arrives before the first refresh."
  - "apps/api/__init__.py uses pathlib.Path(__file__).resolve().parents[2] (CONTEXT line 245) for PROJECT_ROOT instead of the Phase 1 os.path.dirname chain. Phase 2 establishes pathlib as the convention inside the apps/ subtree."
  - "Adapter classes used by the D-19 contract suite are imported LAZILY inside conftest.adapter_factory (B3 fix). Module-level imports of OpenRouterAdapter / ClaudeCodeAdapter / ComputerUseAdapter are forbidden in test_adapter_contract.py; negative grep on the conftest also enforces 6+ try/except/skip triples."
  - "02-RESEARCH.md Open Questions section reconciled to RESOLVED status (B2 fix): 1 header + 4 RESOLVED: question titles + 4 **Resolution:** lines."
metrics:
  duration_min: 13
  tasks_completed: 4
  files_created: 17
  files_modified: 3
  files_total: 20
  unit_tests_pass: 43
  contract_tests_skipped: 18
  d18_guard_state: green
  completed_at: "2026-05-15"
---

# Phase 02 Plan 00: Scaffolding and Shared Modules Summary

## One-liner

Lands the Phase 2 shared backend surface — Pydantic v2 ChatChunk discriminated union, BackendAdapter Protocol, KeyStore, RedactionFilter, PricingTable, CostTracker, and the D-19 parametric contract suite stub — so Wave 1 OpenRouter / Claude Code / computer-use adapters can land in parallel without redefining contracts.

## Tasks Completed

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | Extend pyproject.toml + regenerate uv.lock with Phase 2 base deps | ad0aba3 | pyproject.toml, uv.lock |
| 2 | Create shared module surface + config/pricing.json | 4e2cf1b | 9 source files + config/pricing.json |
| 3 | Author shared tests + conftest fakes + D-19 contract suite stub | 09c35de | 7 test files + apps/api/backends/logging_filter.py (Rule 1 fix) |
| 4 | Reconcile RESEARCH.md Open Questions with RESOLVED status (B2) | e919f2b | 02-RESEARCH.md |

## Source files created (9)

| Path | Purpose |
| ---- | ------- |
| `apps/__init__.py` | Top-level package marker (no exports). |
| `apps/api/__init__.py` | Side-effect import: `load_dotenv()` + `install_redaction_filter()`. PROJECT_ROOT via pathlib.parents[2]. |
| `apps/api/backends/__init__.py` | Backend submodule package marker. |
| `apps/api/backends/protocol.py` | `BackendAdapter` `Protocol` + frozen `Message` and `AdapterOptions` dataclasses; `Backend = Literal[...]` mirrors `src/routing/schema.py:33`. |
| `apps/api/backends/chunks.py` | 7-variant Pydantic v2 discriminated union: `TextDelta`, `ToolCall`, `ToolResult`, `FileDiff`, `Screenshot`, `StreamError`, `Done`. `chat_chunk_adapter = TypeAdapter(ChatChunk)` for ingestion. `StreamError.code` is a CLOSED 9-value `Literal[...]`. `Done.routing_signals` carries Phase 1 `RoutingDecision.signals`. `Screenshot` carries both `image_b64` and `image_ref` (D-14). |
| `apps/api/backends/keystore.py` | `KeyStore` with in-memory primary + env fallback via `_ENV_MAP` + optional OS keyring via lazy try/except import. `SERVICE_NAME: Final[str] = "prompt-optimizer"`. Constructor raises `RuntimeError("...uv sync --extra keyring")` when `use_keyring=True` and the extra is absent. |
| `apps/api/backends/logging_filter.py` | `SECRET_PATTERNS` for `sk-ant-`, `sk-`, `Bearer …`; `RedactionFilter(logging.Filter)` + `install_redaction_filter()` (idempotent) + `LogRecordFactory` wrapper that mutates `record.msg` and clears `record.args` (Pitfall 8). |
| `apps/api/backends/pricing.py` | `PricingTable` with `from_static`, `get` (always returns _default for unknown slugs), async `refresh_from_openrouter` with 24h mtime cache, `_merge_openrouter_snapshot` converting per-token decimal strings to per-Mtok floats (Pitfall 6). |
| `apps/api/backends/cost.py` | `CostTracker` base class with `record_input/record_output/tokens_in/tokens_out/total/over_cap`; `DEFAULT_PER_TURN_COST_USD: Final[float] = 0.50`. |

## Test files created (6)

| Path | Coverage |
| ---- | -------- |
| `apps/api/backends/tests/conftest.py` | Session-scoped `pricing_table` + `key_store` fixtures; function-scoped fakes (`fake_openai`, `fake_claude_sdk_client`, `fake_anthropic`, `fake_screen`); parametric `adapter_factory` with LAZY adapter imports (try/except ImportError → `pytest.skip`). |
| `apps/api/backends/tests/test_chunks.py` | 16 tests — every variant's default `type`, round-trip via `chat_chunk_adapter`, discriminator dispatch, closed `StreamError.code` vocabulary, `Done.routing_signals` preservation. |
| `apps/api/backends/tests/test_logging_filter.py` | 7 tests — `sk-ant-` / `sk-` / `Bearer …` redaction, `%s` interpolation Pitfall 8 regression, idempotent install, clean-line passthrough, SECRET_PATTERNS length. |
| `apps/api/backends/tests/test_keystore.py` | 8 tests — memory primary, env fallback for both providers, unknown-provider None, `use_keyring=True` raise with remediation text, env-cached-into-memory behavior. |
| `apps/api/backends/tests/test_pricing.py` | 12 tests — static load, gpt-5 / anthropic rates, `_default` fallback, conservative-upper-bound check, Pitfall 6 per-Mtok conversion, missing/invalid pricing handling, new-model addition, async fresh-cache no-HTTP behavior. |
| `apps/api/backends/tests/test_adapter_contract.py` | 6 invariants × 3 backends = 18 parametric cases; module-level adapter imports are forbidden (B3 enforcement); lazy imports in adapter_factory + `test_missing_api_key_raises_before_stream` skip until Wave 1 adapters land. |

## Pydantic schema commit hash + representative chunk JSON

- ChatChunk schema lives at commit `4e2cf1b` (file `apps/api/backends/chunks.py`).
- Representative JSON for a `TextDelta`: `{"type":"text_delta","text":"hello"}`
- Representative JSON for a `Done` with routing signals: `{"type":"done","tokens_in":100,"tokens_out":50,"cost_usd":0.0125,"latency_ms":2500,"routing_signals":{"task_type":"coding","agentic_intent":true}}`

## config/pricing.json

- 14 entries total: 13 model rows + `_default`.
- `_default = {"input_per_mtok": 5.00, "output_per_mtok": 20.00}` per CONTEXT specifics line 266.
- Required keys verified present: `openai/gpt-5`, `openai/gpt-5-chat`, `qwen/qwen3-235b-a22b-2507`, `qwen/qwen3-235b-a22b-thinking-2507`, `deepseek/deepseek-v3.1-terminus`, `deepseek/deepseek-chat-v3-0324`, `moonshotai/kimi-k2-0905`, `google/gemini-2.5-flash`, `openrouter/auto`, `anthropic/claude-opus-4-7`, `anthropic/claude-sonnet-4-6`, `claude-agent-sdk`, `computer-use-2025-11-24`, `_default`.

## Phase 1 D-18 import-graph guard

Confirmed green:

```
$ uv run pytest src/routing/tests/test_decide_smoke.py -x -q
.......                                                                  [100%]
```

`pydantic` is in the FORBIDDEN_MODULES list — and even though `apps.api.backends.chunks` imports it, the test for `import src.routing.decide` correctly shows it does not pull pydantic into `sys.modules` for the routing brain.

## B3 fix outcome

`test_adapter_contract.py` has zero module-level adapter imports:

```
$ grep -E "^from apps\.api\.backends\.(openrouter|claude_code|computer_use)\.adapter import" apps/api/backends/tests/test_adapter_contract.py | wc -l
0
```

`conftest.py` has 11 matches for `try:` / `except ImportError` / `pytest.skip` (≥ 6 required — one try/except/skip triple per adapter × 2 locations where adapters are imported).

The contract suite collects 18 cases (6 invariants × 3 adapters); all 18 skip cleanly because adapter modules do not yet exist. Once Wave 1 plans land, the same file becomes the live contract gate.

## B2 fix outcome

`02-RESEARCH.md` Open Questions reconciled to RESOLVED:

- 1 header rename: `## Open Questions` → `## Open Questions (RESOLVED)`.
- 4 question titles prefixed with `RESOLVED: `.
- 4 `**Resolution:**` lines appended (one per question).
- Total `RESOLVED` occurrences: 5 (1 header + 4 titles) — meets Dimension 11 gate threshold of ≥ 5.

## Deviations from Plan

### Rule 1 — Bug: RedactionFilter alone does not redact pytest caplog records

**Found during:** Task 3, first run of `test_redaction_replaces_anthropic_keys`.

**Issue:** RESEARCH Pattern 10's literal recipe attaches a `RedactionFilter` to the root logger. Python's logging model does NOT consult parent-logger filters when a child logger's record propagates up to a parent's handler — only the handler's own filter list runs. The pytest `caplog` fixture installs a handler on the captured logger; that handler never saw the root's filter. The redaction-regression test asserts `"sk-ant-" not in caplog.text`, which failed.

**Fix:** Install a `logging.setLogRecordFactory` wrapper that redacts every `LogRecord` at creation time. Keep the `RedactionFilter` on the root logger and its handlers as belt-and-suspenders for direct-emit code paths (e.g. code that constructs `LogRecord` instances directly). Both layers clear `record.args` after replacing `record.msg` per Pitfall 8.

**Files modified:** `apps/api/backends/logging_filter.py` (factory hook added; module docstring updated; module-level `_RECORD_FACTORY_INSTALLED` flag for idempotency).

**Commit:** `09c35de` (bundled with the test files that exercise the fix).

**Why this is a Rule 1 fix and not a Rule 4 architectural change:** The behavior contract (records carrying secrets are redacted before any handler sees them) is unchanged. Only the implementation strategy is updated to satisfy the contract in the pytest environment, which is the canonical regression-test environment for SECURE-01. The Filter on the root logger remains in place so the existing test for `root.filters where isinstance Redaction == 1` still holds.

## Authentication gates

None. All work in this plan is offline (no API keys required).

## Verification commands re-run at completion

```
$ uv run pytest -m "not live" apps/api/backends/tests/ -x -q
ssssssssssssssssss...........................................            [100%]
43 passed, 18 skipped in 0.07s

$ uv run pytest src/routing/tests/test_decide_smoke.py -x -q
.......                                                                  [100%]

$ uv run pytest -m "not live" -q
143 passed, 19 skipped in 68.02s

$ uv lock --check
Resolved 137 packages in 2ms

$ grep -c '"claude-code-sdk"' uv.lock
0
```

## Wave 1 readiness checklist

Wave 1 OpenRouter / Claude Code / computer-use adapter plans can now import:

```python
from apps.api.backends.chunks import (
    ChatChunk, TextDelta, ToolCall, ToolResult, FileDiff, Screenshot,
    StreamError, Done, chat_chunk_adapter,
)
from apps.api.backends.protocol import (
    BackendAdapter, Message, AdapterOptions, Backend,
)
from apps.api.backends.cost import CostTracker, DEFAULT_PER_TURN_COST_USD
from apps.api.backends.pricing import PricingTable
from apps.api.backends.keystore import KeyStore
```

The D-19 contract suite (`test_adapter_contract.py`) will activate per-adapter as soon as `apps/api/backends/<backend>/adapter.py` lands with a class matching the construction signature in `conftest.adapter_factory`.

## Self-Check: PASSED

All files claimed in the SUMMARY exist; all four task commits exist in the git log.

```
$ for f in apps/__init__.py apps/api/__init__.py apps/api/backends/__init__.py apps/api/backends/protocol.py apps/api/backends/chunks.py apps/api/backends/keystore.py apps/api/backends/logging_filter.py apps/api/backends/pricing.py apps/api/backends/cost.py apps/api/backends/tests/__init__.py apps/api/backends/tests/conftest.py apps/api/backends/tests/test_chunks.py apps/api/backends/tests/test_logging_filter.py apps/api/backends/tests/test_keystore.py apps/api/backends/tests/test_pricing.py apps/api/backends/tests/test_adapter_contract.py config/pricing.json; do
    [ -f "$f" ] && echo "FOUND: $f" || echo "MISSING: $f"
done

$ git log --oneline --all | grep -E "ad0aba3|4e2cf1b|09c35de|e919f2b"
e919f2b docs(02-00): reconcile Open Questions with RESOLVED markers (B2)
09c35de test(02-00): add shared backend tests + D-19 contract suite stub
4e2cf1b feat(02-00): add shared backend module surface and pricing table
ad0aba3 chore(02-00): add Phase 2 base deps + asyncio test mode
```

All 17 created files present; all 4 task commits present.

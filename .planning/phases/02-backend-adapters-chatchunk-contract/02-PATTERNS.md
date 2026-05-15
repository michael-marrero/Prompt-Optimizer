# Phase 2: Backend Adapters & ChatChunk Contract - Pattern Map

**Mapped:** 2026-05-14
**Files analyzed:** 49 new files + 4 existing files modified
**Analogs found:** 33 / 49 (16 are novel — no in-repo analog, use RESEARCH.md patterns)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `apps/api/__init__.py` | package-init | side-effect-on-import | `src/routing/config.py` (constants module) | partial |
| `apps/api/backends/__init__.py` | package-init | none | (no analog; empty package marker) | n/a |
| `apps/api/backends/protocol.py` | type-contract | structural-typing | `src/routing/schema.py` | role-match |
| `apps/api/backends/chunks.py` | type-contract | discriminated-union | `src/routing/schema.py` (frozen dataclass) | role-match (shape diverges — Pydantic vs dataclass) |
| `apps/api/backends/keystore.py` | utility (secrets) | in-memory + optional persist | (no analog) | none |
| `apps/api/backends/logging_filter.py` | utility (logging) | filter | (no analog) | none |
| `apps/api/backends/pricing.py` | config-loader + http-refresh | json-load + async-http | `src/demo/demo_router.py:load_json` + `src/routing/decide.py:_load_default_artifacts` | partial |
| `apps/api/backends/cost.py` | helper class | counter + cap-check | `src/routing/policy.py` | role-match |
| `apps/api/backends/tests/test_adapter_contract.py` | test (D-19 parametric) | async iteration | `src/routing/tests/test_decide_smoke.py` + `test_rule_cascade.py` | role-match |
| `apps/api/backends/tests/test_chunks.py` | test (schema) | sync | `src/routing/tests/test_schema.py` | exact |
| `apps/api/backends/tests/test_logging_filter.py` | test (filter) | sync | `src/routing/tests/test_uncertainty_fallback.py` (style) | partial |
| `apps/api/backends/tests/test_keystore.py` | test | sync | `src/routing/tests/test_schema.py` (style) | partial |
| `apps/api/backends/tests/test_pricing.py` | test | sync + async | `src/routing/tests/test_rule_cascade.py` (json fixture) | partial |
| `apps/api/backends/tests/conftest.py` | test-fixtures | session-scoped | `src/routing/tests/conftest.py` | exact |
| `apps/api/backends/openrouter/__init__.py` | package-init | re-export | `src/routing/__init__.py` (empty) | role-match |
| `apps/api/backends/openrouter/__main__.py` | CLI | argparse → asyncio → JSON-lines | `src/routing/__main__.py` + `src/routing/decide.py:main` | role-match (diverges: async + streaming JSON) |
| `apps/api/backends/openrouter/adapter.py` | adapter class | async streaming | `src/routing/decide.py` (entry function shape) | partial (function → class; sync → async) |
| `apps/api/backends/openrouter/cost.py` | CostTracker subclass | counter | `src/routing/policy.py` (composed helper) | role-match |
| `apps/api/backends/openrouter/errors.py` | error-mapping | transform | `src/data/build_classifier_dataset.py:42-48` (defensive fallback) | partial |
| `apps/api/backends/openrouter/tests/{conftest.py, fakes.py, test_adapter.py, test_live.py}` | tests + fakes | unit + opt-in live | `src/routing/tests/*` for style; no in-repo fake-class analog | partial |
| `apps/api/backends/claude_code/__init__.py` | package-init | side-effect (os.environ.setdefault) | `src/routing/__init__.py` (empty) | partial |
| `apps/api/backends/claude_code/__main__.py` | CLI | argparse → asyncio | `src/routing/__main__.py` | role-match |
| `apps/api/backends/claude_code/adapter.py` | adapter class | async streaming + subprocess | `src/routing/decide.py` | partial |
| `apps/api/backends/claude_code/cost.py` | CostTracker subclass | counter | `src/routing/policy.py` | role-match |
| `apps/api/backends/claude_code/errors.py` | error-mapping | transform | (no analog) | none |
| `apps/api/backends/claude_code/workspace.py` | helper (tmpdir) | filesystem | (no analog — novel) | none |
| `apps/api/backends/claude_code/step_counter.py` | helper (counter) | counter | `src/routing/policy.py` (small helper) | role-match |
| `apps/api/backends/claude_code/tests/*` | tests | unit + opt-in live | `src/routing/tests/*` | partial |
| `apps/api/backends/computer_use/__init__.py` | package-init | re-export | `src/routing/__init__.py` | role-match |
| `apps/api/backends/computer_use/__main__.py` | CLI | argparse → asyncio | `src/routing/__main__.py` | role-match |
| `apps/api/backends/computer_use/adapter.py` | adapter class | async streaming + agent loop | `src/routing/decide.py` (stage cascade) | partial |
| `apps/api/backends/computer_use/cost.py` | CostTracker subclass | counter | `src/routing/policy.py` | role-match |
| `apps/api/backends/computer_use/errors.py` | error-mapping | transform | (no analog) | none |
| `apps/api/backends/computer_use/screen.py` | helper (Playwright wrapper) | browser-control | (no analog — novel) | none |
| `apps/api/backends/computer_use/step_counter.py` | helper (counter) | counter | `src/routing/policy.py` | role-match |
| `apps/api/backends/computer_use/tests/*` | tests | unit + opt-in live | `src/routing/tests/*` | partial |
| `config/pricing.json` | config (data) | json | `config/model_mapping.json` | exact |
| `.pre-commit-config.yaml` | ops (hook config) | yaml | (no analog — novel) | none |
| `scripts/no-secrets.sh` | ops (shell) | bash | (no analog — novel) | none |
| `scripts/no-deprecated-sdk.sh` | ops (shell) | bash | (no analog — novel) | none |
| `.github/workflows/live-smoke.yml` | ops (CI) | yaml | `.github/workflows/ci.yml` | role-match |
| `pyproject.toml` (modify) | config | toml | `pyproject.toml` (extend in place) | exact |
| `.github/workflows/ci.yml` (modify) | ops (CI) | yaml | `.github/workflows/ci.yml` (extend in place) | exact |
| `uv.lock` (regen) | config (generated) | generated | (regen via `uv lock`) | n/a |
| `.planning/REQUIREMENTS.md` (modify) | docs | markdown | `.planning/REQUIREMENTS.md` (in place) | exact |

---

## Pattern Assignments

### Group A: Shared modules at `apps/api/backends/`

#### `apps/api/__init__.py` (package-init, side-effect-on-import)

**Analog:** `src/routing/config.py` (path-discovery + constant module) — partial only; this file is novel because it performs SIDE EFFECTS at import (`dotenv.load_dotenv()` + `install_redaction_filter()`). Use RESEARCH.md Pattern 10 + 11 for the side effects.

**Path discovery to copy** (from `src/routing/config.py:32-40`):
```python
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))

MODELS_DIR = os.path.join(PROJECT_ROOT, "models")
CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")
```

**What to copy:**
- `os.path.abspath(__file__)` path-discovery preamble — same depth pattern (`apps/api/__init__.py` is also at `<root>/<package>/__init__.py`, so use `..` once to get repo root).
- Module docstring style: opens with one-line summary, blank line, then a 2-3-paragraph "what does this module do and why" block (see `src/routing/config.py:1-26`).

**What to diverge from:**
- Phase 1's `config.py` is import-side-effect-FREE; this file MUST execute `load_dotenv()` and `install_redaction_filter()` at module load. Add an explicit docstring callout: "Side effects at import: ..."
- Use `pathlib.Path(__file__).resolve().parents[2]` per CONTEXT line 245 (NOT `os.path.dirname` chain). Phase 2 establishes the cleaner `pathlib` pattern in the new `apps/` tree.

**Anti-pattern to avoid:** Do NOT add `sys.path.append` here. CONTEXT line 244-245 explicitly forbids it; `apps/` is declared in `pyproject.toml [tool.hatch.build.targets.wheel] packages = ["src", "apps"]`.

---

#### `apps/api/backends/__init__.py` (package-init)

**Analog:** `src/routing/tests/__init__.py` (1-line empty package marker).

**Pattern:** Empty file (1 line, possibly a single triple-quoted module docstring). No re-exports. The downstream consumer imports `from apps.api.backends.chunks import ChatChunk` directly.

---

#### `apps/api/backends/protocol.py` (type-contract, structural-typing)

**Analog:** `src/routing/schema.py` (frozen-dataclass contract module).

**Imports + module docstring pattern** (from `src/routing/schema.py:1-30`):
```python
"""RoutingDecision dataclass — the public contract of `src.routing.decide`.

ROUTER-05 locks the return type of `decide(...)`. This module ONLY uses
stdlib (`dataclasses`, `typing`, `json`) — no third-party imports — so
it is safe for the D-18 import-graph guard.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Literal
```

**Frozen-dataclass pattern to reuse** (from `src/routing/schema.py:33-55`):
```python
Backend = Literal["openrouter", "claude_code", "computer_use"]


@dataclass(frozen=True)
class RoutingDecision:
    backend: Backend
    model_or_agent: str
    rationale: str
    confidence: float
    signals: dict[str, Any] = field(default_factory=dict)
```

**What to copy:**
- `from __future__ import annotations` first line
- `@dataclass(frozen=True)` for `Message` and `AdapterOptions` per RESEARCH Pattern 2 lines 441-455
- Stdlib-only imports policy — protocol.py imports only `typing`, `dataclasses`, and `apps.api.backends.chunks`. Mirrors the D-18 spirit (no provider SDK leak in the contract layer).
- `Backend = Literal[...]` style for any new literal type aliases

**What to diverge from:**
- Add `typing.Protocol` + `typing.AsyncIterator` (not in schema.py)
- Add `Message` and `AdapterOptions` frozen dataclasses alongside the Protocol (RESEARCH Pattern 2)
- No `to_json()` method — Pydantic models handle their own serialization; dataclasses here are just value objects

---

#### `apps/api/backends/chunks.py` (type-contract, Pydantic v2 discriminated union)

**Analog:** `src/routing/schema.py` — **role-match only.** Phase 1 used a frozen dataclass; Phase 2 D-01 mandates Pydantic v2. Use RESEARCH Pattern 1 (lines 330-417) as the canonical shape.

**Module docstring style to copy** (from `src/routing/schema.py:1-23`):
- Opening one-liner, the requirement ID it satisfies (BACKEND-01 here), enumerate every field with semantic meaning.
- Add a list of all 7 discriminator literal values: `text_delta | tool_call | tool_result | file_diff | screenshot | stream_error | done`.

**What to diverge from `src/routing/schema.py`:**
- Use `pydantic.BaseModel` not `@dataclass`. Each variant is its own `BaseModel`.
- Use `Annotated[Union[...], Field(discriminator="type")]` per RESEARCH Pattern 1 line 408-411.
- Use `TypeAdapter(ChatChunk)` for runtime JSON ingestion (Phase 3 SSE) per RESEARCH line 413-416.
- Field convention: `tokens_in: int | None = None` (lowercase PEP 604 union; matches `src/demo/demo_router.py:96` `extra_values: dict | None = None`).

**Closed `code` vocabulary for `StreamError`** (CONTEXT D-06):
```python
code: Literal[
    "cost_cap_exceeded", "step_cap_exceeded", "cancelled", "rate_limited",
    "auth_failed", "provider_unavailable", "timeout", "validation_error",
    "internal_error",
]
```

**Screenshot variant must carry both fields** (CONTEXT D-14):
- `image_b64: str | None = None` (Phase 2 sets this always)
- `image_ref: str | None = None` (Phase 3 conditionally swaps in for ≥256 KB)
- `image_format: Literal["png", "jpeg"] = "png"`
- `step: int`

**Done variant must carry `routing_signals`** (CONTEXT specifics line 267 + D-19 fixture):
- `routing_signals: dict[str, Any] | None = None`

---

#### `apps/api/backends/keystore.py` (utility — secrets)

**No analog in repo.** Novel module. Use RESEARCH Pattern 12 (lines 1623-1681) as the canonical shape.

**Module style to copy from existing repo files:**
- Module docstring opener style from `src/routing/config.py:1-26` (purpose, what it touches, what it does NOT touch — here: never persists to SQLite, never logs).
- `Final[str]` constant pattern from RESEARCH line 1634 (`SERVICE_NAME: Final[str] = "prompt-optimizer"`).
- Try/except optional-import idiom (CONTEXT D-10):
  ```python
  try:
      import keyring as _keyring
      _HAS_KEYRING = True
  except ImportError:
      _HAS_KEYRING = False
  ```

**Constructor raise-early pattern to copy** (from `src/routing/decide.py:122-127`):
```python
if not os.path.exists(path):
    raise FileNotFoundError(
        f"{artifact_name} not found at:\n{path}\n\n"
        f"Train/save {artifact_name} first (...).
    )
```
Apply here as: when `use_keyring=True` but `_HAS_KEYRING` is False, raise `RuntimeError` with `"Run: uv sync --extra keyring"` remediation text.

---

#### `apps/api/backends/logging_filter.py` (utility — logging)

**No analog in repo.** Novel module. Use RESEARCH Pattern 10 (lines 1472-1525).

**What to copy from RESEARCH:**
- `SECRET_PATTERNS` list of `(re.compile(...), replacement_str)` tuples — three patterns: `sk-ant-`, `sk-`, `Bearer …`.
- `RedactionFilter(logging.Filter)` subclass with `filter(self, record)` that mutates `record.msg = msg` AND `record.args = ()` per Pitfall 8.
- `install_redaction_filter()` idempotent function — checks `root.filters` for existing `RedactionFilter` instance before attaching.

**Module-level logger pattern to mirror** (from `src/routing/decide.py:77`):
```python
logger = logging.getLogger(__name__)
```

---

#### `apps/api/backends/pricing.py` (config-loader + http-refresh)

**Analogs (partial):**
- `src/demo/demo_router.py:74-85` `load_json()` — json-load-with-FileNotFoundError pattern.
- `src/routing/decide.py:135-175` `_load_default_artifacts()` — multi-file load with remediation hints.

**JSON-load pattern to copy** (from `src/demo/demo_router.py:74-85`):
```python
def load_json(path: str, name: str):
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{name} not found at:\n{path}"
        )
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)
```

**FileNotFoundError remediation-hint pattern** (from `src/routing/decide.py:122-127`):
```python
if not os.path.exists(path):
    raise FileNotFoundError(
        f"{artifact_name} not found at:\n{path}\n\n"
        f"Train/save {artifact_name} first (...).
    )
```

**Async http-refresh shape** — no analog in repo. Use RESEARCH Pattern 6 lines 1281-1330 verbatim. Key choices to preserve:
- `httpx.AsyncClient(timeout=10.0)` context manager
- 24h mtime-based cache invalidation (one `stat()` call, no extra dep)
- `_merge_openrouter_snapshot` converts the per-token decimal strings to per-Mtok floats (Pitfall 6)
- On HTTPError: `logger.warning("OpenRouter pricing refresh failed: %s — using static table.", exc)` — non-fatal, fall back to static

---

#### `apps/api/backends/cost.py` (base class)

**Analog:** `src/routing/policy.py` — pure helper module imported by the orchestrator. Same pattern: stdlib-only, no I/O, composed by `decide()` / adapter respectively.

**Module-level `Final` constant pattern to copy** (from `src/routing/config.py:50-60`):
```python
# Module-level scalar default with type annotation + explanatory comment
DEFAULT_TASK_TYPE_TAU: float = 0.35
DEFAULT_AGENTIC_INTENT_TAU: float = 0.55
DEFAULT_MODEL_ROUTER_TAU: float = 0.20
```

Mirror as (per CONTEXT specifics line 260):
```python
DEFAULT_PER_TURN_COST_USD: Final[float] = 0.50
```

**Module docstring opener pattern** (from `src/routing/policy.py:1-46`):
- Open with one-line purpose, blank, then enumerate every public function with a brief sig + role description. Apply to `CostTracker` methods.

**Class shape to use** — RESEARCH Pattern 6 lines 1226-1259. Key methods:
- `record_input(n: int)`, `record_output(n: int)`, `tokens_in()`, `tokens_out()`, `total() -> float`, `over_cap() -> bool`.
- `_final_cost_override: float | None` for provider-authoritative cost (Claude Code's `result.total_cost_usd`).
- Composed by adapter, not inherited from a Protocol.

---

#### `apps/api/backends/tests/test_adapter_contract.py` (D-19 parametric)

**Analog:** `src/routing/tests/test_decide_smoke.py` (shape + style) + `src/routing/tests/test_rule_cascade.py` (parametrization style).

**Imports + style to copy** (from `src/routing/tests/test_decide_smoke.py:1-20`):
```python
# Plan 06 Task 3 — D-18 forbidden-import guard + ROUTER-05 smoke test.
#
# Two tests:
#   test_no_forbidden_modules_imported_after_decide()
#       ...
#
#   test_decide_returns_routing_decision()
#       ...

from __future__ import annotations

import os
import sys

import pytest
```

**Note:** Phase 1 tests use comment-block module docstrings (`# Plan 06 Task 3 — ...` rather than `"""..."""`). Follow the same style here: open with a comment block enumerating the test contracts (the 6 D-19 invariants).

**Fixture + parametrize pattern to copy** (from `src/routing/tests/test_rule_cascade.py:18-26`):
```python
@pytest.fixture(scope="module")
def model_mapping() -> dict:
    with open(MODEL_MAPPING_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)
```

**D-19 parametric shape** — RESEARCH lines 2088-2232 is the canonical full text. Six tests parametrized across three adapters:
1. `test_happy_path_terminates_with_done`
2. `test_cost_cap_aborts`
3. `test_step_cap_aborts` (skip openrouter — single round-trip)
4. `test_cancellation_within_2_seconds` (with `@pytest.mark.timeout(2)`)
5. `test_done_always_lands`
6. `test_missing_api_key_raises_before_stream`

**What to copy from `src/routing/tests/test_decide_smoke.py:42-56` for the forbidden-modules style assertion:**
```python
leaked = {
    name.split(".")[0]
    for name in sys.modules
} & FORBIDDEN_MODULES

assert not leaked, (
    f"src.routing.decide leaked forbidden imports into sys.modules: "
    f"{sorted(leaked)}. Forbidden set (D-18): {sorted(FORBIDDEN_MODULES)}."
)
```
Apply analogously: `import src.routing.decide` MUST still NOT pull in `openai`, `anthropic`, etc. after Phase 2 adds them at the apps/api layer. Keep that test passing.

---

#### `apps/api/backends/tests/test_chunks.py` (BACKEND-01 schema test)

**Analog:** `src/routing/tests/test_schema.py` — exact role match.

**Test-function structure to copy** (from `src/routing/tests/test_schema.py:22-45`):
```python
def test_routing_decision_to_json_exposes_five_keys() -> None:
    from src.routing.schema import RoutingDecision

    decision = RoutingDecision(
        backend="openrouter",
        model_or_agent="openai/gpt-5",
        rationale="picked gpt-5",
        confidence=0.85,
    )
    payload = decision.to_json()
    assert isinstance(payload, str)
    parsed = json.loads(payload)
    assert set(parsed.keys()) == {
        "backend", "model_or_agent", "rationale", "confidence", "signals",
    }
```

**What to copy:**
- Inline import inside the test function (avoids module-level pollution; consistent with `src/routing/tests/`).
- `assert isinstance(...)` for type checks
- `assert set(parsed.keys()) == {...}` for exact key sets
- Type-annotated `def test_X() -> None:` signatures

**What to diverge from:**
- Use Pydantic `.model_dump_json()` and `.model_validate_json()` round-trip, not `.to_json()` + `json.loads()`.
- Test the discriminator field — `TypeAdapter(ChatChunk).validate_python({"type": "text_delta", "text": "hi"})` returns a `TextDelta` instance per RESEARCH line 415.
- Phase 1's `FrozenInstanceError` test (`src/routing/tests/test_schema.py:48-58`) has a Pydantic equivalent: `ValidationError` on mutation of a `model_config = ConfigDict(frozen=True)` model. Use the same test name pattern: `test_chatchunk_variant_is_frozen`.

---

#### `apps/api/backends/tests/test_logging_filter.py` / `test_keystore.py` / `test_pricing.py`

**Style analog:** `src/routing/tests/test_schema.py` (small focused tests, inline imports, type-annotated returns).

**Async test annotation pattern to use** (RESEARCH line 2065 `asyncio_mode = "auto"`):
```python
@pytest.mark.asyncio
async def test_refresh_from_openrouter_uses_cache_when_fresh(tmp_path):
    ...
```

**test_logging_filter.py specific** — RESEARCH lines 1536-1551 gives the canonical `caplog`-based test pattern. Two minimum assertions:
- `assert "sk-ant-" not in caplog.text`
- `assert "***REDACTED-ANTHROPIC***" in caplog.text`

**test_keystore.py specific** — RESEARCH Pattern 12. Cover:
- env-var fallback when memory + keyring miss
- `use_keyring=True` raises when `_HAS_KEYRING` is False
- `set()` populates memory; `get()` returns it without keyring call

**test_pricing.py specific** — copy the `model_mapping` fixture pattern from `src/routing/tests/test_rule_cascade.py:22-26`, adapted to load `config/pricing.json`. Test:
- `PricingTable.from_static(path)` loads the file
- `.get("openai/gpt-5")` returns expected rates
- `.get("unknown-model")` falls back to `_default`
- `_merge_openrouter_snapshot` converts per-token decimal strings to per-Mtok floats (Pitfall 6)

---

#### `apps/api/backends/tests/conftest.py` (shared fixtures)

**Analog:** `src/routing/tests/conftest.py` — exact match. Session-scoped fixtures with `pytest.importorskip` for optional deps.

**Pattern to copy** (from `src/routing/tests/conftest.py:23-45`):
```python
def _load_joblib_or_skip(path: str, label: str):
    joblib = pytest.importorskip("joblib")
    if not os.path.exists(path):
        pytest.skip(f"{label} not found at {path} — produced by a later plan")
    return joblib.load(path)


@pytest.fixture(scope="session")
def task_artifacts():
    return _load_joblib_or_skip(TASK_CLASSIFIER_PATH, "task_type_classifier.joblib")
```

**What to copy:**
- `scope="session"` for expensive-to-construct fixtures (e.g., `pricing_table`, `key_store`)
- `pytest.importorskip` for any optional dependency (e.g., `keyring`)
- `_load_X_or_skip` helper pattern — skip rather than fail when artifact is missing

**What to diverge from:**
- Add fake-injection fixtures (`fake_openai`, `fake_claude_sdk_client`, `fake_anthropic`, `fake_screen`) referenced by `test_adapter_contract.py`. These are NEW — no in-repo analog. Use RESEARCH Pattern 14 + Common Operation 3 (lines 1916-1979) for shape.
- Add `monkeypatch` usage for `COMPUTER_USE_OPT_IN` env var setup (RESEARCH line 2125).

---

### Group B: OpenRouter adapter at `apps/api/backends/openrouter/`

#### `apps/api/backends/openrouter/__init__.py`

**Analog:** `src/routing/__init__.py` — currently empty 1-liner.

**Pattern:** Single-line or empty package marker. Optionally re-export `OpenRouterAdapter` for ergonomic `from apps.api.backends.openrouter import OpenRouterAdapter`. Compare to RESEARCH line 1467:
```python
from apps.api.backends.openrouter.adapter import OpenRouterAdapter

__all__ = ["OpenRouterAdapter"]
```

---

#### `apps/api/backends/openrouter/__main__.py` (CLI)

**Analog:** `src/routing/__main__.py` (3-liner) + `src/routing/decide.py:main()` (the actual CLI logic, called by both `__main__.py` and `decide.py`).

**`__main__.py` aliasing pattern to copy** (from `src/routing/__main__.py:16-26`):
```python
"""Package-level entry point so `python -m src.routing` runs the CLI."""

from src.routing.decide import main


def _entrypoint() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    _entrypoint()
```

**What to copy:**
- The indirection function pattern (`_entrypoint`) so `import apps.api.backends.openrouter.__main__` doesn't `SystemExit` the calling process. The Phase 1 module docstring explains this WR-07 fix at line 8-13.
- Lazy import: `from apps.api.backends.openrouter.adapter import OpenRouterAdapter` happens inside the function body, not at module top, so the CLI startup is fast even when adapter import has SDK side-effects.

**What to diverge from:**
- Make `main()` async (`async def _main()`) and dispatch via `asyncio.run(_main())` per RESEARCH Common Operation 2 lines 1873-1914.
- argparse flags per CONTEXT line 146: `--prompt`, `--max-cost-usd`, `--model`. Print each `ChatChunk` as one JSON line to stdout (`chunk.model_dump_json()`).

**argparse skeleton to copy** (from `src/routing/decide.py:535-544`):
```python
parser = argparse.ArgumentParser(
    description="Route a single prompt and print RoutingDecision as JSON.",
)
parser.add_argument("prompt", help="The prompt text to route.")
args = parser.parse_args(argv)

decision = decide(prompt=args.prompt)
print(decision.to_json())
return 0
```

Adapt to: `--prompt` is positional or required flag, plus optional `--max-cost-usd: float = 0.50` (default from `DEFAULT_PER_TURN_COST_USD`) and `--model: str`. Iterate the async generator and `print(chunk.model_dump_json())` per chunk.

---

#### `apps/api/backends/openrouter/adapter.py` (adapter class)

**Analog:** `src/routing/decide.py` — same role (entry function with clean signature), but Phase 2 diverges from function-style to class-style. Use RESEARCH Pattern 3 (lines 472-660) as canonical shape.

**Module docstring + import style to copy** (from `src/routing/decide.py:1-77`):
```python
"""Routing brain entry point — `decide(prompt, ...) -> RoutingDecision`.

Public surface (ROUTER-05 + D-17):

    decide(prompt, history=None, artifacts=None, settings=None) -> RoutingDecision
    main() -> int   # CLI: `python -m src.routing.decide '<prompt>'`

Pipeline (6 stages, all inside one top-level try/except for V7 robustness):
    ...
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Any, Optional
```

Apply as:
```python
"""OpenRouter adapter — async streaming via OpenAI SDK v1.40+.

Public surface (BACKEND-02 + BACKEND-03):

    class OpenRouterAdapter:
        async def stream(prompt, history, options) -> AsyncIterator[ChatChunk]

Pipeline:
    1. Pre-flight: tiktoken input estimate, cost tracker init.
    2. client.chat.completions.create(..., stream=True, stream_options={"include_usage": True})
    3. Per chunk: emit TextDelta, accumulate tool_call deltas by index, check over_cap()
    4. On finish_reason == "tool_calls": flush accumulated ToolCall chunks
    5. On final usage chunk: override tracker with provider truth
    6. Terminal: Done chunk with cost / latency / tokens / routing_signals
"""
```

**Module-level logger pattern to copy** (from `src/routing/decide.py:73-77`):
```python
logger = logging.getLogger(__name__)
```

This is mandatory — SECURE-01 redaction filter only intercepts `logging.LogRecord`. Adapter `print()` is forbidden per RESEARCH anti-patterns line 1721.

**Constants pattern to copy** (from `src/routing/config.py:36-40`):
- Module-level `SCREAMING_SNAKE_CASE` constants for `OPENROUTER_BASE_URL`, `HTTP_REFERER`, `X_TITLE` per CONTEXT line 141.

**Class shape** — RESEARCH lines 505-660 verbatim. Key elements:
- `__init__(self, api_key, *, max_cost_usd, client_factory=None)` with keyword-only flags per CONVENTIONS (CLAUDE.md "Keyword-only arguments").
- Constructor raises if `api_key` is falsy (D-19 invariant #6: typed exception BEFORE `stream()`).
- `_default_client_factory(api_key) -> AsyncOpenAI` static method enables fake injection per RESEARCH Common Operation 3.

**Cancellation handling** — copy RESEARCH Pattern 7 (lines 1381-1410):
```python
async def stream(self, ...) -> AsyncIterator[ChatChunk]:
    try:
        ...
        yield Done(...)
    except asyncio.CancelledError:
        yield StreamError(code="cancelled", message="...", retriable=True)
        yield Done(...)
        raise   # Required in 3.11+
    except OtherException:
        yield StreamError(...)
        yield Done(...)
        # Don't re-raise
```

**V7-style try/except wrapping** — the spiritual parent is `src/routing/decide.py:501-522`:
```python
except Exception as exc:  # noqa: BLE001 — V7 robustness wrapper
    logger.exception(
        "decide() fell back to openrouter/auto due to error"
    )
    return _build_fallback_decision(...)
```

Apply analogously: never let an unhandled exception propagate out of `stream()`. Instead emit `StreamError(code="internal_error", retriable=False) + Done` and let the async generator close normally.

---

#### `apps/api/backends/openrouter/cost.py` (CostTracker subclass)

**Analog:** `src/routing/policy.py` (small helper class composed by the orchestrator).

**`policy.py` module style to copy** (from `src/routing/policy.py:1-46`):
- Module docstring enumerates every public function with brief sig + role
- `from __future__ import annotations` first line
- Stdlib-only imports + the package's own `config` module
- No `__all__` (CONVENTIONS: "Public surface is implicit — anything not prefixed with `_` is considered public")

**Class shape** — RESEARCH Pattern 6 lines 1361-1377:
```python
class OpenRouterCostTracker(CostTracker):
    _ENCODING = tiktoken.encoding_for_model("gpt-4")

    def record_input_estimate(self, prompt: str, history: list) -> None:
        joined = prompt + "\n".join(m.content for m in history)
        self.record_input(len(self._ENCODING.encode(joined)))

    def record_output_delta(self, text: str) -> None:
        self.record_output(len(self._ENCODING.encode(text)))

    def record_final_usage(self, prompt_tokens, completion_tokens) -> None:
        self._tokens_in = prompt_tokens
        self._tokens_out = completion_tokens
```

---

#### `apps/api/backends/openrouter/errors.py` (provider error → StreamError)

**Loose analog:** `src/data/build_classifier_dataset.py:42-48` (`_raise_csv_field_limit` — defensive fallback pattern with descending retry).

**Mapping table pattern to invent (no exact analog):**
```python
# Map openai.* exception classes to StreamError code + retriable flag
PROVIDER_ERROR_MAP: dict[type[Exception], tuple[str, bool]] = {
    openai.AuthenticationError: ("auth_failed", False),
    openai.RateLimitError: ("rate_limited", True),
    openai.APITimeoutError: ("timeout", True),
    openai.APIStatusError: ("provider_unavailable", True),
}


def map_provider_error(exc: Exception) -> tuple[str, str, bool]:
    """Return (code, message, retriable) for any openai exception."""
    for exc_class, (code, retriable) in PROVIDER_ERROR_MAP.items():
        if isinstance(exc, exc_class):
            return code, str(exc), retriable
    return "internal_error", str(exc), False
```

**Closed code vocabulary** comes from CONTEXT D-06 (apps/api/backends/chunks.py StreamError `code` Literal). The mapping table must only use codes from that closed set.

---

#### `apps/api/backends/openrouter/tests/{conftest.py, fakes.py, test_adapter.py, test_live.py}`

**Style analog:** `src/routing/tests/*` — small focused tests, inline imports, type-annotated returns.

**Live-test gate pattern (no in-repo analog; novel):** Use `@pytest.mark.live` + `@pytest.mark.skipif(not os.getenv("OPENROUTER_API_KEY"))`.

**conftest.py local fixtures pattern to copy** (from `src/routing/tests/test_rule_cascade.py:18-26`):
```python
REPO_ROOT = os.path.abspath(os.path.join(__file__, "..", "..", "..", ".."))
MODEL_MAPPING_PATH = os.path.join(REPO_ROOT, "config", "model_mapping.json")


@pytest.fixture(scope="module")
def model_mapping() -> dict:
    with open(MODEL_MAPPING_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)
```

Adapt path depth: `apps/api/backends/openrouter/tests/conftest.py` is 4 directories deep — `os.path.join(__file__, "..", "..", "..", "..", "..")` gets to repo root (one more `..` than `src/routing/tests/`).

**fakes.py shape (no analog):** Use RESEARCH Common Operation 3 lines 1916-1979. Fake exposes the same methods as the real SDK client; constructor takes the canned event sequence; adapter doesn't know it's fake.

---

### Group C: Claude Code adapter at `apps/api/backends/claude_code/`

#### `apps/api/backends/claude_code/__init__.py` (side-effect: env var)

**Analog:** `src/routing/__init__.py` — empty. But this file has a side effect (set `CLAUDE_ENABLE_STREAM_WATCHDOG=1`).

**Pattern to use** — RESEARCH Pattern 9 (lines 1456-1470):
```python
"""Claude Code adapter package.

Side effects at import:
  - Sets `CLAUDE_ENABLE_STREAM_WATCHDOG=1` via `os.environ.setdefault(...)`.
    The Claude Code subprocess inherits the env var (BACKEND-09).
"""
import os
os.environ.setdefault("CLAUDE_ENABLE_STREAM_WATCHDOG", "1")

from apps.api.backends.claude_code.adapter import ClaudeCodeAdapter

__all__ = ["ClaudeCodeAdapter"]
```

`setdefault` (not assignment) — don't overwrite if operator already set it.

---

#### `apps/api/backends/claude_code/__main__.py`

Same shape as `apps/api/backends/openrouter/__main__.py`. Single point of divergence: `--cwd` flag for the opt-in user-repo workspace (BACKEND-08); default is None → adapter uses `tempfile.mkdtemp` (CONTEXT specifics line 264).

---

#### `apps/api/backends/claude_code/adapter.py`

**Analog:** `src/routing/decide.py` — same shape, async + class.

**Pipeline pattern to copy** (from `src/routing/decide.py:296-499`): step-numbered comment-banner sections, each enclosed in `# ---` ASCII underlines, plus a top-level try/except wrapper.

**Class shape** — RESEARCH Pattern 4 (lines 664-868). Key requirements:
- Use `ClaudeSDKClient` (NOT standalone `query()`) per Pitfall 2 — `interrupt()` is the BACKEND-07 cancellation hook.
- Per-message `usage` block feeds the cost tracker; final `ResultMessage.total_cost_usd` is authoritative.
- Each `assistant` message = one step (D-15); emit `StreamError(step_cap_exceeded)` + `Done` if step counter exceeds `max_steps`.
- Emit `FileDiff` for `Edit`/`Write` tool calls, `ToolResult` for all others (CONTEXT D-02).

**Allowed-tools lock** (CONTEXT discretion line 142):
```python
ALLOWED_TOOLS: Final[list[str]] = ["Read", "Edit", "Write", "Bash", "Glob", "Grep"]
```

---

#### `apps/api/backends/claude_code/workspace.py` (helper — tmpdir lifecycle)

**No analog.** Novel module. Use RESEARCH Pattern 8 (lines 1430-1454).

**Pattern:**
```python
@contextlib.asynccontextmanager
async def ephemeral_workspace(cwd: str | None) -> AsyncIterator[tuple[str, bool]]:
    """Yield (workspace_path, must_cleanup). If cwd is None, mkdtemp + cleanup."""
    if cwd is None:
        workspace = tempfile.mkdtemp(prefix="pomu-cc-")
        cleanup = True
    else:
        workspace = cwd
        cleanup = False
    try:
        yield workspace, cleanup
    finally:
        if cleanup:
            shutil.rmtree(workspace, ignore_errors=True)
```

---

#### `apps/api/backends/claude_code/step_counter.py`

**Analog:** `src/routing/policy.py` (small helper class).

**Pattern:**
```python
# Per CONTEXT specifics line 261:
DEFAULT_STEP_CAP: Final[int] = 25


class StepCounter:
    def __init__(self, cap: int = DEFAULT_STEP_CAP):
        self._cap = cap
        self._value = 0

    def increment(self) -> int:
        self._value += 1
        return self._value

    def exceeded(self) -> bool:
        return self._value >= self._cap

    @property
    def value(self) -> int:
        return self._value
```

---

#### `apps/api/backends/claude_code/cost.py`, `errors.py`, `tests/*`

Same pattern as the OpenRouter analogues. Diverges in:
- `cost.py`: Anthropic doesn't have a public tokenizer, so char-count / 4 estimator (RESEARCH line 1379) — NOT tiktoken.
- `errors.py`: `claude_agent_sdk` exception classes (need to import from SDK; check actual class names at adapter-implementation time).
- `tests/test_workspace.py`: Tests mkdtemp + cleanup invariant (BACKEND-08).
- `tests/test_watchdog_env.py`: One-line test: `assert os.environ["CLAUDE_ENABLE_STREAM_WATCHDOG"] == "1"` after `import apps.api.backends.claude_code`.

---

### Group D: Computer-use adapter at `apps/api/backends/computer_use/`

Same shape as the other two adapters. Key divergences:

#### `apps/api/backends/computer_use/__init__.py`

**Analog:** `src/routing/__init__.py` (empty). No env-var side effect here (the `COMPUTER_USE_OPT_IN` check happens at `ComputerUseAdapter.__init__`, NOT at import — CONTEXT specifics line 263).

#### `apps/api/backends/computer_use/adapter.py`

**Class shape** — RESEARCH Pattern 5 (lines 870-1210). The adapter OWNS the full agent loop (CONTEXT D-12):
- Screenshot → model → action → screenshot → repeat
- Per-iteration step counter (15 cap; CONTEXT D-15)
- `computer_20251124` tool + `computer-use-2025-11-24` beta header
- Constructor raises if `os.getenv("COMPUTER_USE_OPT_IN") != "1"` per CONTEXT specifics line 263 (raise BEFORE any provider client constructed)

**Anti-pattern guard** (RESEARCH line 1727): `headless=True` is the Playwright default; never expose a debug toggle that defaults to headed.

#### `apps/api/backends/computer_use/screen.py`

**No analog.** Novel module. Use RESEARCH Pattern 5 + CONTEXT D-13 verbatim.

#### `apps/api/backends/computer_use/tests/test_optin.py`

Specific test:
```python
def test_constructor_raises_without_opt_in(monkeypatch):
    monkeypatch.delenv("COMPUTER_USE_OPT_IN", raising=False)
    with pytest.raises(RuntimeError, match="COMPUTER_USE_OPT_IN"):
        ComputerUseAdapter(api_key="fake")
```

Style copies `src/routing/tests/test_schema.py:48-58` (`with pytest.raises(...)` + inline import + type-annotated `-> None`).

---

### Group E: Config + Ops files

#### `config/pricing.json`

**Analog:** `config/model_mapping.json` — exact match. Flat JSON dict keyed by slug, loaded once at startup. Both live in `config/` and are consumed by single-source loaders.

**Schema to use** (per CONTEXT D-17 + RESEARCH lines 1336-1351):
```json
{
  "openai/gpt-5": {"input_per_mtok": 2.50, "output_per_mtok": 10.00},
  ...
  "_default": {"input_per_mtok": 5.00, "output_per_mtok": 20.00}
}
```

**What to copy from `config/model_mapping.json`:**
- Top-level structure: flat dict keyed by model id
- Reserved sentinel key (`OTHER` in model_mapping → `_default` in pricing)
- Stable, deterministic key ordering grouped by provider

**What to diverge from:**
- Value shape: `model_mapping` carries 6 fields per entry; `pricing` carries only 2 (`input_per_mtok`, `output_per_mtok`).
- No `notes` or `display_name` — pricing is pure numeric.

---

#### `.pre-commit-config.yaml`

**No analog.** Novel ops file. Use RESEARCH Pattern 11 lines 1564-1581 verbatim.

#### `scripts/no-secrets.sh`, `scripts/no-deprecated-sdk.sh`

**No analog.** Novel ops files. Use RESEARCH Pattern 11 lines 1583-1619 verbatim.

#### `.github/workflows/live-smoke.yml`

**Analog:** `.github/workflows/ci.yml` — partial. Same YAML shape but trigger is `workflow_dispatch` + scheduled cron (CONTEXT D-20 line 132), not push.

**Structure to copy** (from `.github/workflows/ci.yml:1-44`):
- `name:` opener
- `on:` triggers
- `jobs.<name>.runs-on: ubuntu-latest`
- `steps:` block with `uses: actions/checkout@v4` + `uses: astral-sh/setup-uv@v3`

**Diverge:** Add `if: ${{ secrets.OPENROUTER_API_KEY != '' }}` gate so the workflow no-ops on forks without the secret. Use `--live-budget=$0.10` (CONTEXT D-20) and `continue-on-error: true` (failures are informational, not push-blocking).

---

### Group F: Existing files modified

#### `pyproject.toml` (extend in place)

**Current state** (from `pyproject.toml:1-42`):
```toml
[project]
name = "prompt-optimizer"
version = "0.1.0"
description = "Quality-first prompt router with calibrated classifiers"
readme = "ReadMe.md"
requires-python = ">=3.10"
license = { text = "MIT" }
dependencies = [
    "scikit-learn>=1.7,<2.0",
    "pandas>=2.0,<3.0",
    "numpy>=1.26,<3.0",
    "scipy>=1.11,<2.0",
    "joblib>=1.4,<2.0",
    "matplotlib>=3.8,<4.0",
    "nltk>=3.9,<4.0",
    "sentence-transformers>=3.0,<4.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=9.0,<10.0",
    "pytest-cov>=5.0,<7.0",
]

[project.scripts]
route-decide = "src.routing.decide:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src"]

[tool.pytest.ini_options]
testpaths = ["src"]
python_files = ["test_*.py"]
addopts = "-x -q --import-mode=importlib"
```

**Modifications required (CONTEXT line 195 + RESEARCH line 2260):**
- **`[project.dependencies]` adds (base deps, locked-decision pins):**
  - `"pydantic>=2.6,<3.0"` (CONTEXT D-01)
  - `"openai>=1.40,<3.0"` (CONTEXT line 182)
  - `"anthropic>=0.40,<1.0"` (CONTEXT line 184)
  - `"claude-agent-sdk>=0.1.80,<0.2"` (CONTEXT line 183; OSS-06: NOT `claude-code-sdk`)
  - `"playwright>=1.45,<2.0"` (CONTEXT D-13)
  - `"python-dotenv>=1.0,<2.0"` (CONTEXT D-11)
  - `"httpx>=0.27,<1.0"` (transitive but explicit for pricing.py)
  - `"tiktoken>=0.7,<1.0"` (RESEARCH Pattern 6 line 1364)
- **`[project.optional-dependencies] dev` adds:**
  - `"pytest-asyncio>=0.23,<1.0"`
  - `"pytest-timeout>=2.3,<3.0"`
  - `"pre-commit>=3.5,<5.0"`
- **NEW `[project.optional-dependencies] keyring`:**
  ```toml
  keyring = ["keyring>=24,<26"]
  ```
- **Extend `[tool.hatch.build.targets.wheel]`:**
  ```toml
  packages = ["src", "apps"]
  ```
- **Extend `[tool.pytest.ini_options]`:**
  ```toml
  testpaths = ["src", "apps"]
  markers = ["live: hits real provider APIs (BYOK required)"]
  asyncio_mode = "auto"
  ```

**What to copy:** Preserve every existing line. Modifications are additive only.

---

#### `.github/workflows/ci.yml` (extend in place)

**Current state** (from `.github/workflows/ci.yml:1-44`):
```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout (with LFS for data_processed/*.csv)
        uses: actions/checkout@v4
        with:
          lfs: true

      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true

      - name: Install Python 3.11
        run: uv python install 3.11

      - name: Sync dependencies (locked)
        run: uv sync --locked --all-extras --dev

      - name: Pre-fetch NLTK data (Pitfall 5 mitigation)
        run: |
          uv run python -c "import nltk; nltk.download('punkt_tab', quiet=True); nltk.download('punkt', quiet=True)"

      - name: Run full pytest suite
        run: uv run pytest -x -q

      # Phase 1 close-out: --check currently exits 1 because...
      - name: Routing canary eval (advisory — see ci.yml comment above)
        if: ${{ hashFiles('data_processed/routing_decision_eval.csv') != '' }}
        continue-on-error: true
        run: uv run python -m src.evaluation.evaluate_routing --check
```

**Modifications required (CONTEXT D-20 lines 120-132):**

Insert AFTER `Sync dependencies (locked)`:
```yaml
      - name: Sync with keyring extra (SECURE-04)
        run: uv sync --locked --extra keyring

      - name: Run pre-commit hooks (SECURE-02 + OSS-06)
        run: uv run pre-commit run --all-files

      - name: OSS-06 — claude_agent_sdk import smoke
        run: uv run python -c "from claude_agent_sdk import ClaudeAgentOptions"

      - name: OSS-06 — ensure deprecated claude-code-sdk absent
        run: |
          ! uv run python -c "import claude_code_sdk" 2>/dev/null
          ! grep -q '"claude-code-sdk"' uv.lock
```

Then split the `Run full pytest suite` step into:
```yaml
      - name: Phase 1 — src/ tests (D-18 import-graph guard stays green)
        run: uv run pytest -x -q src/

      - name: Phase 2 — apps/api/backends unit tests (no live)
        run: uv run pytest -x -q -m 'not live' apps/api/backends
```

The advisory `Routing canary eval` step stays as-is (commit `64a07d2` resolved its `continue-on-error: true` state, per CONTEXT line 240).

**What to copy:** The full existing structure (`actions/checkout@v4` with `lfs: true`, `astral-sh/setup-uv@v3`, `uv python install 3.11`, etc.). Phase 2 only adds steps.

---

#### `uv.lock` (regen via `uv lock`)

No excerpt. Planner records the regen step: `uv lock` after `pyproject.toml` edits. The pre-commit hook `scripts/no-deprecated-sdk.sh` also greps this file (RESEARCH line 1614).

---

#### `.planning/REQUIREMENTS.md` (modify two lines)

**Current BACKEND-01 wording** (from `.planning/REQUIREMENTS.md:22`):
```markdown
- [ ] **BACKEND-01**: `ChatChunk` discriminated union (`TextDelta | ToolCall | Screenshot | FileDiff | StreamError | Done`) is the single contract between adapters, storage, and UI
```

**New BACKEND-01 wording (per CONTEXT D-02):**
```markdown
- [ ] **BACKEND-01**: `ChatChunk` discriminated union (`TextDelta | ToolCall | ToolResult | FileDiff | Screenshot | StreamError | Done`) is the single contract between adapters, storage, and UI
```

(Adds `ToolResult` between `ToolCall` and `FileDiff`.)

**Current BACKEND-06 wording** (from `.planning/REQUIREMENTS.md:27`):
```markdown
- [ ] **BACKEND-06**: Each adapter enforces a hard per-turn USD cap (default $0.50) and per-iteration step cap (25 for Claude Code, 15 for computer-use) at the adapter boundary
```

**Phase 1 of CONTEXT (line 95) says this is already the correct wording** ("per-iteration step cap (25 for Claude Code, 15 for computer-use)"). On re-read, the file already matches. The CONTEXT note says "Update REQUIREMENTS.md BACKEND-06 wording in this phase" — this means **verify and (only if drift exists) re-assert** the line at planning time. The current file at line 27 matches the locked wording. Plan a no-op verification step.

---

## Shared Patterns

### Module docstring style

**Source:** `src/routing/decide.py:1-40`, `src/routing/policy.py:1-46`, `src/routing/schema.py:1-23`, `src/routing/config.py:1-26`.

**Apply to:** Every new `.py` file in `apps/api/backends/`.

**Shape:**
```python
"""<One-line purpose>.

Public surface (<REQ-IDs>):
    <signatures>

<2-3 paragraphs of "what does this module do, what does it NOT do, what's the
contract with the rest of the codebase">

<Cross-references to RESEARCH.md patterns, CONTEXT decisions, or anti-patterns.>
"""
```

### `from __future__ import annotations`

**Source:** Every Phase 1 module (`src/routing/decide.py:42`, `src/routing/policy.py:47`, `src/routing/schema.py:26`, `src/routing/config.py:28`).

**Apply to:** Every new Python file in `apps/api/backends/`.

**Rationale:** Enables PEP 604 union syntax (`X | Y` instead of `Optional[X]`) under Python 3.10+. Phase 1 uses this consistently.

### Path discovery

**Source:** `src/routing/config.py:32-40` (legacy `os.path` chain) — but CONTEXT line 245 explicitly says to use the cleaner `pathlib` form in `apps/api/` per the new-tree opportunity.

**Apply to:** Any `apps/api/backends/*.py` file that needs to reference the project root.

**Pattern:**
```python
from pathlib import Path

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]   # apps/api/backends/X.py → repo root
CONFIG_DIR: Path = PROJECT_ROOT / "config"
```

(Parent count depends on file depth — adapter modules at `apps/api/backends/<backend>/X.py` use `parents[3]`.)

**Do NOT** add `sys.path.append` for cross-package imports — CONTEXT line 244 forbids it. Use `from apps.api.backends.chunks import TextDelta` directly (the package is installed via `uv sync`).

### Module-level logger

**Source:** `src/routing/decide.py:77`.

**Apply to:** Every adapter module, every helper that emits log output.

**Pattern:**
```python
import logging

logger = logging.getLogger(__name__)
```

**Critical:** Adapter MUST use `logger.info/warning/error/exception`, NEVER `print()`. SECURE-01 redaction filter only intercepts `logging.LogRecord` (RESEARCH anti-patterns line 1721).

### Constructor argument style

**Source:** `src/feature_extraction/build_features.py` (uses `from __future__ import annotations`); `src/model_router/train_embedding_router.py` (uses keyword-only `*,`); CONVENTIONS "Keyword-only arguments" rule.

**Apply to:** Every adapter `__init__` and helper function with multiple boolean flags.

**Pattern:**
```python
def __init__(
    self,
    api_key: str,
    *,
    max_cost_usd: float = DEFAULT_PER_TURN_COST_USD,
    client_factory: Callable | None = None,
) -> None: ...
```

The `*,` separator forces every subsequent argument to be keyword-only. Matches the existing `save_embedding_router_artifacts(*, prepend_dataset_to_query, prepend_prompt_stub, classifier_type, output_path=...)` convention.

### `FileNotFoundError` with remediation text

**Source:** `src/routing/decide.py:122-127`, `src/demo/demo_router.py:51-55`.

**Apply to:** Every loader (`PricingTable.from_static`, `KeyStore` constructor when `use_keyring=True` and keyring missing).

**Pattern:**
```python
if not os.path.exists(path):
    raise FileNotFoundError(
        f"{name} not found at:\n{path}\n\n"
        f"<one-line remediation hint, e.g. 'Run: uv sync --extra keyring'>"
    )
```

### Test-file conventions

**Source:** `src/routing/tests/test_decide_smoke.py`, `test_schema.py`, `test_rule_cascade.py`, `test_uncertainty_fallback.py`.

**Apply to:** Every test file in `apps/api/backends/`.

**Conventions:**
- Open with a `# <Plan Task> — <one-line purpose>.` comment block (NOT a triple-quoted docstring). Enumerate every test contract.
- `from __future__ import annotations` after the comment block.
- Inline imports inside test functions (`from apps.api.backends.chunks import TextDelta`) — avoids module-level state.
- Type-annotated `def test_X() -> None:` signatures.
- For parametric tests, copy the `@pytest.fixture(scope="module")` JSON-load pattern from `src/routing/tests/test_rule_cascade.py:22-26`.
- For async tests, use `@pytest.mark.asyncio` (RESEARCH line 2065 sets `asyncio_mode = "auto"` so the marker is technically optional, but explicit is preferred).
- For cancellation/timing tests, use `@pytest.mark.timeout(2)` (RESEARCH line 2178).

### CLI entry point shape

**Source:** `src/routing/__main__.py:16-26` + `src/routing/decide.py:530-548`.

**Apply to:** Every `apps/api/backends/<backend>/__main__.py`.

**Pattern (sync wrapper around async main):**
```python
# __main__.py
"""Package-level CLI: `python -m apps.api.backends.<backend>`."""

import asyncio

from apps.api.backends.<backend>.adapter import <Backend>Adapter


async def _amain(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(...)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--max-cost-usd", type=float, default=0.50)
    parser.add_argument("--model", default=None)
    args = parser.parse_args(argv)

    adapter = <Backend>Adapter(api_key=os.environ["..."], max_cost_usd=args.max_cost_usd)
    async for chunk in adapter.stream(prompt=args.prompt, history=[], options=AdapterOptions(model=args.model)):
        print(chunk.model_dump_json())
    return 0


def _entrypoint() -> None:
    raise SystemExit(asyncio.run(_amain()))


if __name__ == "__main__":
    _entrypoint()
```

### Frozen-dataclass value-object pattern

**Source:** `src/routing/schema.py:36-55`.

**Apply to:** `apps/api/backends/protocol.py` `Message` and `AdapterOptions`.

**Pattern:** `@dataclass(frozen=True)` with `default_factory=dict` for any mutable defaults.

### asyncio.CancelledError handling

**Source:** No in-repo analog (Phase 1 is sync). Use RESEARCH Pattern 7 (lines 1381-1410) verbatim.

**Apply to:** Every adapter `stream()` method.

**Pattern:** Emit `StreamError(code="cancelled", retriable=True) + Done` inside the `except asyncio.CancelledError:` block, then `raise` (Python 3.11+ asyncio integrity).

### Top-level try/except wrapping ("V7 robustness")

**Source:** `src/routing/decide.py:501-522`.

**Apply to:** Every adapter `stream()` method.

**Pattern:**
```python
async def stream(self, ...) -> AsyncIterator[ChatChunk]:
    try:
        # Happy path
        async for ... in self._client...:
            yield ...
        yield Done(...)

    except asyncio.CancelledError:
        yield StreamError(code="cancelled", ...)
        yield Done(...)
        raise

    except Exception as exc:  # noqa: BLE001
        logger.exception("<adapter> fell back to StreamError due to error")
        code, msg, retriable = map_provider_error(exc)
        yield StreamError(code=code, message=msg, retriable=retriable)
        yield Done(...)
        # Do NOT re-raise — terminate generator via StopAsyncIteration after Done
```

---

## No Analog Found

Files with no close in-repo match (planner should use RESEARCH.md patterns):

| File | Role | Data Flow | RESEARCH Pattern |
|------|------|-----------|------------------|
| `apps/api/backends/chunks.py` (Pydantic union) | type-contract | discriminated-union | Pattern 1 (lines 330-417) |
| `apps/api/backends/keystore.py` | utility (secrets) | memory + optional persist | Pattern 12 (lines 1623-1681) |
| `apps/api/backends/logging_filter.py` | utility (logging) | filter | Pattern 10 (lines 1472-1525) |
| `apps/api/backends/pricing.py` (async refresh) | config + async-http | async-http + cache | Pattern 6 (lines 1281-1330) |
| `apps/api/backends/openrouter/adapter.py` | adapter class | async streaming | Pattern 3 (lines 472-660) |
| `apps/api/backends/openrouter/errors.py` | error-mapping | transform | (table-driven, novel) |
| `apps/api/backends/openrouter/tests/fakes.py` | test-fakes | mock SDK client | Common Operation 3 (lines 1916-1979) |
| `apps/api/backends/claude_code/adapter.py` | adapter class | async streaming + subprocess | Pattern 4 (lines 664-868) |
| `apps/api/backends/claude_code/workspace.py` | helper (tmpdir) | filesystem | Pattern 8 (lines 1430-1454) |
| `apps/api/backends/claude_code/errors.py` | error-mapping | transform | (table-driven, novel) |
| `apps/api/backends/claude_code/tests/fakes.py` | test-fakes | mock SDK | Common Operation 3 |
| `apps/api/backends/computer_use/adapter.py` | adapter class | async + agent loop | Pattern 5 (lines 870-1210) |
| `apps/api/backends/computer_use/screen.py` | helper (Playwright) | browser-control | Pattern 5 (Playwright sub-block) |
| `apps/api/backends/computer_use/errors.py` | error-mapping | transform | (novel) |
| `apps/api/backends/computer_use/tests/fakes.py` | test-fakes | mock screen + SDK | Common Operation 3 |
| `.pre-commit-config.yaml`, `scripts/no-secrets.sh`, `scripts/no-deprecated-sdk.sh` | ops | yaml + bash | Pattern 11 (lines 1559-1619) |

---

## Metadata

**Analog search scope:**
- `/Users/michaelmarrero/GitHub/Prompt-Optimizer/src/routing/` (Phase 1 source — 5 modules + 5 test files)
- `/Users/michaelmarrero/GitHub/Prompt-Optimizer/src/demo/demo_router.py` (lifted patterns: `load_json`, `load_joblib_artifacts`, `choose_final_route`)
- `/Users/michaelmarrero/GitHub/Prompt-Optimizer/src/data/build_classifier_dataset.py:42-48` (defensive-fallback shape — loose analog for `errors.py`)
- `/Users/michaelmarrero/GitHub/Prompt-Optimizer/.github/workflows/ci.yml` (existing CI workflow — extension target)
- `/Users/michaelmarrero/GitHub/Prompt-Optimizer/pyproject.toml` (existing package config — extension target)
- `/Users/michaelmarrero/GitHub/Prompt-Optimizer/config/model_mapping.json` (existing JSON config — sibling-file template for `pricing.json`)

**Files scanned (read):**
- `src/routing/__init__.py`, `src/routing/__main__.py`, `src/routing/decide.py`, `src/routing/schema.py`, `src/routing/policy.py`, `src/routing/config.py`
- `src/routing/tests/__init__.py`, `src/routing/tests/conftest.py`, `src/routing/tests/test_decide_smoke.py`, `src/routing/tests/test_schema.py`, `src/routing/tests/test_uncertainty_fallback.py`, `src/routing/tests/test_rule_cascade.py`
- `src/demo/demo_router.py` (lines 1-120)
- `.github/workflows/ci.yml`
- `config/model_mapping.json`
- `pyproject.toml`
- `.planning/phases/02-backend-adapters-chatchunk-contract/02-CONTEXT.md`
- `.planning/phases/02-backend-adapters-chatchunk-contract/02-RESEARCH.md` (targeted reads: lines 330-660 Patterns 1-3, lines 1211-1525 Patterns 6-10, lines 1559-1750 Patterns 11-14, lines 2056-2261 Validation Architecture)
- `.planning/phases/01-router-brain-foundation/01-CONTEXT.md`
- `.planning/REQUIREMENTS.md`

**Pattern extraction date:** 2026-05-14

"""Pure-data pydantic-v2 schemas for the Layer-0 eval harness.

These models are the typed substrate every downstream eval plan (suites,
solvers, scorers, CI gate) imports. The module is intentionally import-light:
it pulls only `pydantic` (already a core dependency, line 17 of pyproject.toml)
and NOTHING from `inspect_ai`, so Layer-0 tests can read it key-free and the
D-18 one-way import arrow (eval/ -> src/routing, never the reverse) stays clean.

Conventions mirror `apps/api/backends/chunks.py`:
    - `from __future__ import annotations`
    - `BaseModel` subclasses with `Literal[...]` closed vocabularies
    - optional fields default to `None`
    - cross-referencing docstrings

CRITICAL label correction:
    The AI-SPEC (§4b lines 476-490) wrote the OpenRouter backend label with a
    "_chat" suffix. That value is WRONG. The AUTHORITATIVE backend labels are
    defined in `src/routing/schema.py:33` (CONTEXT D-04) as the three sentinels
    the adapters consume directly:

        Backend = Literal["openrouter", "claude_code", "computer_use"]

    The field SHAPES from the AI-SPEC are correct; only the literal value was
    wrong. We copy the corrected triple verbatim so gold labels and predicted
    labels share one closed vocabulary with `decide()`.

Cross-refs:
    - src/routing/schema.py:33 (authoritative Backend literal)
    - apps/api/backends/chunks.py (pydantic-v2 module conventions)
    - 10-AI-SPEC.md §4b lines 476-490 (field shapes; label value corrected here)
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# CONTEXT D-04 / src/routing/schema.py:33 — the three backend sentinels.
# Corrected from the AI-SPEC's wrong "_chat"-suffixed OpenRouter value.
Backend = Literal["openrouter", "claude_code", "computer_use"]


class RoutingScoreRecord(BaseModel):
    """One scored routing prediction in the routing suite.

    `predicted_backend` comes from `src.routing.decide.decide(...)`; `gold_backend`
    is the hand-labeled canary truth. `correct` is the backend-exact-match outcome
    the EVAL-01 routing-accuracy band is computed over.

    - prompt_id: stable identifier of the canary prompt being scored
    - predicted_backend: backend `decide()` chose (closed Backend vocabulary)
    - gold_backend: hand-labeled correct backend (closed Backend vocabulary)
    - correct: True iff predicted_backend == gold_backend
    - rationale: optional one-line `decide()` rationale, for debugging
    """

    prompt_id: str
    predicted_backend: Backend
    gold_backend: Backend
    correct: bool
    rationale: str | None = None


class JudgeVerdict(BaseModel):
    """Structured verdict emitted by the model-graded judge (agentic suite).

    Returned by the pinned judge model (`anthropic/claude-sonnet-4-6`) under a
    `response_schema` so the scorer parses a validated object rather than free
    text. Field shapes follow AI-SPEC §4b lines 476-490.

    - verdict: "pass" or "fail" — the binary grading outcome
    - confidence: judge self-reported confidence in [0.0, 1.0]
    - reasoning: judge explanation, capped at 2000 chars to bound token cost
    - failing_criterion: which rubric criterion failed (None when verdict == "pass")
    """

    verdict: Literal["pass", "fail"]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(max_length=2000)
    failing_criterion: str | None = None

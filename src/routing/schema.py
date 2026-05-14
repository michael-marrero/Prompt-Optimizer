"""RoutingDecision dataclass — the public contract of `src.routing.decide`.

ROUTER-05 locks the return type of `decide(prompt, history, artifacts, settings)`.
This module ONLY uses stdlib (`dataclasses`, `typing`, `json`) — no third-party
imports — so it is safe for the D-18 import-graph guard.

The shape mirrors RESEARCH §Pattern 4 lines 569-608 and CONTEXT D-03 + D-04:

    backend         (Backend Literal)  which of the three backends owns the call
    model_or_agent  (str)              concrete provider-ready identifier
                                       ("openai/gpt-5", "claude-agent-sdk",
                                       "computer-use-2025-11-24", or
                                       "openrouter/auto" for the fallback)
    rationale       (str)              one-line human reason; fallback decisions
                                       MUST end with FALLBACK_RATIONALE_SUFFIX
                                       from src.routing.config
    confidence      (float)            min of the per-stage max-probabilities;
                                       in [0.0, 1.0]
    signals         (dict[str, Any])   structured per-stage telemetry —
                                       task_type, agentic_intent, rule_fired,
                                       top-K predictions, threshold check
                                       results, etc.; persistable to a
                                       routing_decisions SQLite row in STORE-02.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

# CONTEXT D-04: three backend sentinels. Adapters consume these directly.
Backend = Literal["openrouter", "claude_code", "computer_use"]


@dataclass(frozen=True)
class RoutingDecision:
    """Immutable routing decision returned by `src.routing.decide.decide`.

    Constructed in five places inside `decide()`:
    - the four cascade branches that emit a "happy path" decision
      (openrouter / claude_code / computer_use), plus
    - the fallback decision builder for the low-confidence path.

    `frozen=True` is load-bearing: downstream consumers (Phase 2 adapters,
    Phase 3 FastAPI, Phase 4 UI) treat the decision as a value object that
    flows through the request lifecycle without being mutated. Tests assert
    the frozen contract.
    """

    backend: Backend
    model_or_agent: str
    rationale: str
    confidence: float
    signals: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        """Serialize as a one-line JSON object for the CLI (D-17).

        `ensure_ascii=False` preserves the U+2014 em-dash in the fallback
        rationale so the stdout output is byte-faithful to the rationale
        string a consumer would read from `RoutingDecision.rationale`.
        """
        return json.dumps(asdict(self), ensure_ascii=False)

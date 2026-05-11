# Phase 1: Router Brain Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `01-CONTEXT.md` — this log preserves the alternatives considered.

**Date:** 2026-05-11
**Phase:** 1-router-brain-foundation
**Mode:** --batch (grouped numbered batches per area)
**Areas discussed:** Backend decision policy, Agentic-intent training data, Low-confidence fallback & OOD policy, Canary eval composition

---

## Backend decision policy

### Q1 — How should the three signals (task_type, agentic_intent, model_router) compose into a backend pick?

| Option | Description | Selected |
|--------|-------------|----------|
| Hard-coded rule cascade | if agentic_intent==True AND (task_type in {coding, instruction-following} OR keyword 'build/write/edit/refactor') → Claude Code; elif agentic_intent==True AND keyword 'open/browse/url/click' → computer-use; else → OpenRouter. Debuggable; every branch shows up in the rationale. | ✓ |
| Two-step gate + lookup | Step 1 agentic_intent decides chat vs. agent; step 2 picks model (chat) or branches via keyword lookup (agent). Simpler than rules, less expressive. | |
| Score blend with weights | scores = w1*task + w2*agentic + w3*model_router; argmax with cost tiebreaker. Tunable but magic weights, harder rationale. | |

**User's choice:** Hard-coded rule cascade.
**Notes:** Recommended option; aligns with PROJECT.md "Core Value" (transparent rationale) and gives every backend a deterministic, inspectable branch.

### Q2 — Inside the OpenRouter branch, what does the rule cascade use for `model_or_agent`?

| Option | Description | Selected |
|--------|-------------|----------|
| Existing `model_router` → `config/model_mapping.json` | Reuse model_router.joblib prediction; resolve via mapping; unverified slugs → OTHER → openrouter/auto. Preserves all training work. | ✓ |
| Use tier_router + hand-curated default per tier | Predict tier only; one canonical model per tier. Smaller label space, but discards 16-class training and the mapping. | |
| Hybrid (model_router first, tier_router on sub-threshold) | Two attempts; resilient to OOD. More moving parts. | |

**User's choice:** Existing `model_router` → `config/model_mapping.json` (Recommended).
**Notes:** Smallest scope; preserves the 16-entry mapping and the existing 16-class artifact.

### Q3 — Rationale string format

| Option | Description | Selected |
|--------|-------------|----------|
| Short human sentence | Easy display, hard to inspect programmatically. | |
| Structured key=value pairs | Machine-parsable, less pretty. | |
| Both | `rationale` (str) for the chip; `signals` (dict) for SQLite/CI inspection. | ✓ |

**User's choice:** Both.
**Notes:** Keeps the Phase 4/5 chip UX simple while still giving the persistence layer (STORE-02 `routing_decisions` row) a structured payload to store.

### Q4 — `model_or_agent` form

| Option | Description | Selected |
|--------|-------------|----------|
| Concrete provider-ready strings | OpenRouter: resolved api_model; Claude Code/computer-use: fixed sentinels. Adapters consume directly. | ✓ |
| Benchmark slug | Adapters resolve to api_model themselves. Keeps decide() decoupled. | |
| Always a structured object | Form-tagged dict; most flexible, heavier schema. | |

**User's choice:** Concrete provider-ready strings.
**Notes:** Adapters in Phase 2 don't need to know about `config/model_mapping.json` — the brain hands them a ready-to-call identifier.

---

## Agentic-intent training data

### Q1 — Where do positive (agentic) examples come from?

| Option | Description | Selected |
|--------|-------------|----------|
| Hand-write 200–400 from scratch | High SNR, slow. | |
| Mine LLMRouterBench tool-use / coding subsets | Fast, large N, noisy proxy. | |
| LLM-synthesize from ~30 seeds | Cheap, high volume, biased toward LLM's view of "agentic". | ✓ |
| Mix (seeds + LLM + mined rows) | Robust, most work. | |

**User's choice:** LLM-synthesize from a small seed.
**Notes:** ~30 hand-written seeds anchored to README golden-path examples; LLM expands to ~500.

### Q2 — Where do negative (conversational) examples come from?

| Option | Description | Selected |
|--------|-------------|----------|
| LLMRouterBench non-tool-use rows | Abundant; already in pipeline. | ✓ |
| Hand-written + LLM-synthesized | Distributional symmetry with positives. | |
| Both (LLMRouterBench + hand-written tricky negatives) | Belt-and-suspenders. | |

**User's choice:** LLMRouterBench non-tool-use rows.
**Notes:** No new ingest path; reuses the existing offline pipeline; planner picks the exact filter (math + factual QA + writing + affective + instruction-following without imperatives).

### Q3 — Target sample size?

| Option | Description | Selected |
|--------|-------------|----------|
| ~200 (100/100) | Minimum viable; hand-inspectable. | |
| ~1,000 (500/500) | Room for CalibratedClassifierCV to actually calibrate. | ✓ |
| ~5,000+ | Risks training on noisy labels. | |

**User's choice:** ~1,000 total, balanced 500/500.
**Notes:** Big enough for `CalibratedClassifierCV`'s default 5-fold CV; small enough that the researcher can sample-audit.

### Q4 — Feature stack for the agentic-intent head?

| Option | Description | Selected |
|--------|-------------|----------|
| Same TF-IDF + handcrafted as existing classifiers | Consistent, reuses PromptFeatureExtractor. | |
| Embeddings + LogisticRegression | Better small-N generalization; new dep path. | |
| Existing stack + 3–5 new agentic-specific handcrafted features | imperative-verb count, URL presence, file-path presence, code-block markers. | ✓ |

**User's choice:** Existing stack + new agentic-specific handcrafted features.
**Notes:** Extends PromptFeatureExtractor (so all three heads benefit from the new features); preserves the canonical saved-artifact dict shape.

---

## Low-confidence fallback & OOD policy

### Q1 — OOD sentinel mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| Literal `unknown` class in label encoder | Clean; predict() can return "unknown". | |
| Probability threshold only | Smaller training change; couples OOD to threshold. | |
| Both | Belt-and-suspenders; two failure modes. | ✓ |

**User's choice:** Both.
**Notes:** Train the `unknown` class on rows that fail every keyword group in `build_question_type.py`; ALSO apply a per-stage probability threshold at inference time.

### Q2 — Where does the confidence threshold live?

| Option | Description | Selected |
|--------|-------------|----------|
| Per-stage thresholds in `settings` | Independently tunable; defaults in code. | ✓ |
| Single global threshold | Simpler, less correct. | |
| Per-stage thresholds derived from canary ECE/PR curves | Reproducible, more work. | |

**User's choice:** Per-stage thresholds in `settings`.
**Notes:** Defaults: `task_type_tau=0.35`, `agentic_intent_tau=0.55`, `model_router_tau=0.20`. The model-router threshold is intentionally lower because its 16-class softmax has a lower natural max-prob floor.

### Q3 — Fallback target

| Option | Description | Selected |
|--------|-------------|----------|
| `openrouter/auto` | OpenRouter's meta-router; already mapped; verified. | ✓ |
| Hand-picked single model (gpt-5-chat or sonnet) | Predictable, vendor-locked. | |
| Tier-aware fallback (call tier_router on sub-threshold) | Keeps tier_router useful. | |

**User's choice:** `openrouter/auto`.
**Notes:** Already present in `config/model_mapping.json` as the `openrouter` slug, `tier="medium"`, `openrouter_verified=true`. No new mapping entry required.

### Q4 — Backend on fallback, and rationale phrase

| Option | Description | Selected |
|--------|-------------|----------|
| Always OpenRouter on fallback; rationale ends "low confidence — fallback" | Safest; matches success criterion #4. | ✓ |
| Backend depends on which stage triggered fallback | More expressive, more failure modes. | |
| `backend="fallback"` separate enum value | Cleanest separation, expands enum surface. | |

**User's choice:** Always OpenRouter on fallback.
**Notes:** Exact rationale phrase `"low confidence — fallback"` is asserted by the unit test in `src/routing/tests/` per Phase 1 success criterion #4.

---

## Canary eval composition

### Q1 — Distribution across backends

| Option | Description | Selected |
|--------|-------------|----------|
| Balanced thirds + fallback bucket (~12/12/12 + 6) | Parity across backends; fallback gets first-class coverage. | ✓ |
| Weighted to expected real traffic (~25/10/5 + 5) | Realistic chat distribution. | |
| Balanced thirds with NO fallback bucket | Implicit fallback coverage. | |

**User's choice:** Balanced thirds + dedicated fallback bucket. Target ~42 prompts.

### Q2 — Where do canary prompts come from?

| Option | Description | Selected |
|--------|-------------|----------|
| All hand-written, anchored to README golden-path examples | Highest authenticity, slowest. | |
| Hand-written + slice of real chats | Captures real-world drift. | |
| Hand-written + license-checked adversarial slice from public sets | HumanEval/MMLU/WebArena-style; diverse. | ✓ |

**User's choice:** Hand-written + small license-checked adversarial slice from public sets.
**Notes:** Every public-set row MUST be cited and license-checked before commit; redistributable rows kept verbatim, non-redistributable rows paraphrased.

### Q3 — Guaranteed edge-case slots

| Option | Description | Selected |
|--------|-------------|----------|
| All four categories (haiku-vs-code, explain-vs-build, informational-URL, low-confidence trap) — ~8 slots | Comprehensive coverage of known confusables. | ✓ |
| A subset (haiku-vs-code + explain-vs-build only) | Smaller, still covers main confusables. | |
| None as guaranteed slots | Natural distribution. | |

**User's choice:** All four edge-case categories.
**Notes:** Each category contributes at least one prompt pair; the four categories together occupy ~8 of the ~42 slots (~19%).

### Q4 — Evaluator output

| Option | Description | Selected |
|--------|-------------|----------|
| Required only (accuracy + per-classifier ECE) | Smallest scope; matches success criterion exactly. | |
| Required + per-backend P/R | +1 table; useful for debugging route bias. | |
| Required + per-backend P/R + confusion matrix + low_confidence_rate | Most informative; biggest scope. | ✓ |

**User's choice:** Full metric stack.
**Notes:** Eval is offline; cost is acceptable. CSVs land under `evaluation/routing/`.

---

## Claude's Discretion

The following implementation choices were intentionally NOT pinned in CONTEXT.md and are deferred to the researcher / planner:

- Calibration method (`sigmoid` vs `isotonic`) and CV k-fold count
- `src/routing/` internal module layout (single file vs split into `decide.py` + `policy.py` + `schema.py` + `config.py`)
- `RoutingDecision` runtime form (`@dataclass` recommended; `TypedDict` or `pydantic.BaseModel` acceptable if justified)
- Whether to centralize path constants in `src/paths.py` opportunistically
- The exact list of agentic / browse keywords for the rule cascade — anchored to the seed prompts but expandable
- Whether to script the `models/uncalibrated/` one-time backup or do it manually
- Pre-commit / pytest scaffolding choices (no test framework exists today; planner picks)

## Deferred Ideas

(These also live in CONTEXT.md's `<deferred>` section.)

- File renames flagged as anti-patterns in ARCHITECTURE.md (`Feature_extractor.py`, `build_top_model_datatset.py`)
- Cost-aware classifier integration as a tiebreaker mechanism — preserved as a baseline only per PROJECT.md
- Logging redaction filter, pre-commit hook for `sk-` prefixes — Phase 2 deliverables
- `make setup` / NLTK + SentenceTransformer pre-fetch — Phase 6 deliverable
- v2 router items (per-stage confidence UI panel, model fallback chain, cross-backend handoff, live retraining loop)

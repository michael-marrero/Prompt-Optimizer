"""Routing brain entry point — `decide(prompt, ...) -> RoutingDecision`.

Public surface (ROUTER-05 + D-17):

    decide(prompt, history=None, artifacts=None, settings=None) -> RoutingDecision
    main() -> int   # CLI: `python -m src.routing.decide '<prompt>'`

Pipeline (6 stages, all inside one top-level try/except for V7 robustness):

    1. Stage 1 — task-type classifier predict_proba over the
       PromptFeatureExtractor + TF-IDF + handcrafted stack. Argmax
       label + max-prob.
       Gate: if max_prob < tau_task OR predicted == "unknown" -> fallback.

    2. Stage 2 — agentic-intent binary classifier predict_proba.
       Gate: if max_prob < tau_agentic -> fallback.

    3. Stage 3 — D-01 rule cascade (policy.decide_backend).
       Returns ("claude_code" | "computer_use" | "openrouter", ...).
       For non-OpenRouter backends, emit RoutingDecision with the
       sentinel as model_or_agent and exit.

    4. Stage 4 — model_router predict_proba (only for OpenRouter
       branch). Stage-2 text input is built via
       src.feature_extraction.text_inputs.build_router_text_input_single
       so the format string isn't duplicated.
       Gate: if max_prob < tau_router -> fallback.

    5. Stage 5 — quality_first_pick on top-K + choose_final_route to
       resolve the picked slug into an api_model.

    6. Stage 6 — emit the final RoutingDecision with min-of-confidences
       and a rationale string concatenating each stage's signal.

This module imports ONLY stdlib + sklearn/scipy/joblib/pandas/numpy +
local `src.routing.*` and `src.feature_extraction.*`. NO HTTP libraries,
NO LLM SDKs, NO web framework (D-18). The smoke test in
src/routing/tests/test_decide_smoke.py asserts this at runtime by
walking sys.modules after `import src.routing.decide`.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Any, Optional

import joblib
import pandas as pd
from scipy.sparse import csr_matrix, hstack

from src.feature_extraction.text_inputs import build_router_text_input_single
from src.routing.config import (
    CONFIG_DIR,
    DEFAULT_AGENTIC_INTENT_TAU,
    DEFAULT_ARTIFACT_PATHS,
    DEFAULT_EPSILON,
    DEFAULT_MODEL_MAPPING_PATH,
    DEFAULT_MODEL_ROUTER_TAU,
    DEFAULT_TASK_TYPE_TAU,
    FALLBACK_BACKEND,
    FALLBACK_MODEL_OR_AGENT,
    FALLBACK_RATIONALE_SUFFIX,
    MODELS_DIR,
    PROJECT_ROOT,
)
from src.routing.policy import choose_final_route, decide_backend, quality_first_pick
from src.routing.schema import RoutingDecision

# Module-level logger so the V7 catch surfaces internal errors to operators
# (WR-02 from 01-REVIEW.md). Without this the brain would silently route
# every prompt to openrouter/auto when, e.g., a joblib went corrupt or a
# feature_columns mismatch developed — no operator-visible signal.
logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# sys.path injection so `from Feature_extractor import PromptFeatureExtractor`
# resolves. This is the documented anti-pattern from CLAUDE.md but kept
# here per CONTEXT <code_context> line 151 — broad migration is deferred.
# The D-18 smoke test verifies that even with this sys.path manipulation,
# no FORBIDDEN modules leak in.
# ----------------------------------------------------------------------

_SRC_FEATURE_EXTRACTION_DIR = os.path.join(PROJECT_ROOT, "src", "feature_extraction")
if _SRC_FEATURE_EXTRACTION_DIR not in sys.path:
    sys.path.append(_SRC_FEATURE_EXTRACTION_DIR)

from Feature_extractor import PromptFeatureExtractor  # noqa: E402


# ----------------------------------------------------------------------
# Internal cache for PromptFeatureExtractor (cheap to construct but
# constructor walks NLTK download guard; module-level singleton avoids
# repeated guard checks across batch decide() calls in tests).
# ----------------------------------------------------------------------

_EXTRACTOR_SINGLETON: Optional[PromptFeatureExtractor] = None


def _get_extractor() -> PromptFeatureExtractor:
    global _EXTRACTOR_SINGLETON
    if _EXTRACTOR_SINGLETON is None:
        _EXTRACTOR_SINGLETON = PromptFeatureExtractor()
    return _EXTRACTOR_SINGLETON


# ----------------------------------------------------------------------
# Artifact loader (canonical 5/6-key joblib dict shape; same validator
# semantics as src.demo.demo_router.load_joblib_artifacts but lifted
# here so the routing brain doesn't import from src.demo).
# ----------------------------------------------------------------------


_REQUIRED_KEYS = ("model", "vectorizer", "scaler", "label_encoder", "feature_columns")


def _load_one_artifact(path: str, artifact_name: str) -> dict:
    """Load a single joblib artifact dict with the canonical 5-key shape."""
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{artifact_name} not found at:\n{path}\n\n"
            f"Train/save {artifact_name} first (see src/task_classifier/ or "
            f"src/model_router/ training scripts)."
        )
    artifacts = joblib.load(path)
    for key in _REQUIRED_KEYS:
        if key not in artifacts:
            raise KeyError(f"{artifact_name} is missing required key: {key}")
    return artifacts


def _load_default_artifacts() -> dict:
    """Load the three joblib heads + model_mapping.json from disk.

    Used by `decide()` when the caller passes `artifacts=None`. Each
    file load raises FileNotFoundError with a remediation hint so a
    fresh checkout sees a clear "run X first" message instead of a
    cryptic stack trace.

    Returns:
      dict with keys:
        - task_type_classifier (dict)
        - agentic_intent_classifier (dict)
        - model_router (dict)
        - model_mapping (dict)
    """
    task_artifacts = _load_one_artifact(
        DEFAULT_ARTIFACT_PATHS["task_type_classifier"],
        "task_type_classifier.joblib",
    )
    agentic_artifacts = _load_one_artifact(
        DEFAULT_ARTIFACT_PATHS["agentic_intent_classifier"],
        "agentic_intent_classifier.joblib",
    )
    router_artifacts = _load_one_artifact(
        DEFAULT_ARTIFACT_PATHS["model_router"],
        "model_router.joblib",
    )

    if not os.path.exists(DEFAULT_MODEL_MAPPING_PATH):
        raise FileNotFoundError(
            f"model_mapping.json not found at:\n{DEFAULT_MODEL_MAPPING_PATH}"
        )
    with open(DEFAULT_MODEL_MAPPING_PATH, "r", encoding="utf-8") as fh:
        model_mapping = json.load(fh)

    return {
        "task_type_classifier": task_artifacts,
        "agentic_intent_classifier": agentic_artifacts,
        "model_router": router_artifacts,
        "model_mapping": model_mapping,
    }


# ----------------------------------------------------------------------
# Feature helpers — lifted from src/demo/demo_router.py:81-107
# ----------------------------------------------------------------------


def _build_numeric_features(
    prompt: str,
    feature_columns: list,
    extractor: PromptFeatureExtractor,
    extra_values: Optional[dict] = None,
) -> pd.DataFrame:
    """Build a 1-row DataFrame matching the artifact's feature_columns.

    Extra columns from extractor.extract() are silently dropped because
    `feature_df[feature_columns]` trims to whatever the saved artifact
    was trained on. Missing columns are filled with 0 (defensive).
    """
    extracted_features = extractor.extract(prompt)

    row: dict = {}
    row.update(extracted_features)
    if extra_values:
        row.update(extra_values)

    feature_df = pd.DataFrame([row])

    for col in feature_columns:
        if col not in feature_df.columns:
            feature_df[col] = 0

    feature_df = feature_df[feature_columns].fillna(0)
    return feature_df


def _predict_with_calibrated(
    prompt: str,
    raw_text_series: pd.Series,
    artifact: dict,
    extractor: PromptFeatureExtractor,
    extra_values: Optional[dict] = None,
) -> tuple[str, float, list[tuple[str, float]]]:
    """Call predict_proba on a calibrated joblib artifact dict.

    Returns (top_label, top_confidence, full_confidence_table).

    The confidence_table is a list of (label, probability) tuples
    sorted by probability descending — same shape that
    src.demo.demo_router.predict_task_type and predict_best_model
    return, so existing consumers can plug in unmodified.
    """
    model = artifact["model"]
    vectorizer = artifact["vectorizer"]
    scaler = artifact["scaler"]
    label_encoder = artifact["label_encoder"]
    feature_columns = artifact["feature_columns"]

    text_features = vectorizer.transform(raw_text_series)
    numeric_df = _build_numeric_features(prompt, feature_columns, extractor, extra_values)
    numeric_scaled = scaler.transform(numeric_df)
    numeric_sparse = csr_matrix(numeric_scaled)

    combined = hstack([text_features, numeric_sparse])

    probabilities = model.predict_proba(combined)[0]

    confidence_table = [
        (str(label), float(prob))
        for label, prob in zip(label_encoder.classes_, probabilities)
    ]
    confidence_table.sort(key=lambda kv: kv[1], reverse=True)

    top_label, top_prob = confidence_table[0]
    return top_label, top_prob, confidence_table


# ----------------------------------------------------------------------
# Fallback decision builder (D-11 + D-12 + Success Criterion #4)
# ----------------------------------------------------------------------


def _build_fallback_decision(
    rationale_prefix: str,
    signals: dict,
    confidence: float,
) -> RoutingDecision:
    """Construct a RoutingDecision whose rationale ENDS with the locked
    FALLBACK_RATIONALE_SUFFIX. Caller passes a short prefix describing
    which stage tripped the threshold.
    """
    # Join with " - " so the substring "low confidence — fallback"
    # remains at the literal end of the string regardless of prefix.
    prefix = rationale_prefix.rstrip()
    if prefix:
        rationale = f"{prefix} - {FALLBACK_RATIONALE_SUFFIX}"
    else:
        rationale = FALLBACK_RATIONALE_SUFFIX

    # Defensive: assert the substring contract at construction time.
    # Acts as belt-and-suspenders for the unit tests in
    # test_uncertainty_fallback.py.
    assert rationale.endswith(FALLBACK_RATIONALE_SUFFIX), (
        f"Fallback rationale did not end with locked suffix: {rationale!r}"
    )

    return RoutingDecision(
        backend=FALLBACK_BACKEND,
        model_or_agent=FALLBACK_MODEL_OR_AGENT,
        rationale=rationale,
        confidence=float(confidence),
        signals=dict(signals),
    )


# ----------------------------------------------------------------------
# Public entry point — decide()
# ----------------------------------------------------------------------


def decide(
    prompt: str,
    history: Optional[list] = None,
    artifacts: Optional[dict] = None,
    settings: Optional[dict] = None,
) -> RoutingDecision:
    """Route a prompt to a backend via the calibrated 3-head cascade.

    Args:
      prompt: The user's prompt text. Empty / None / very-long inputs
        are tolerated — _agentic_features bounds input to 50,000 chars
        upstream, and decide() wraps the whole pipeline in
        try/except for V7 robustness.
      history: Conversation history. Reserved for v2; ignored in v1.
      artifacts: Pre-loaded artifact dict (4 keys: task_type_classifier,
        agentic_intent_classifier, model_router, model_mapping). Pass
        this in test contexts to avoid re-loading the joblibs.
        If None, _load_default_artifacts() is called.
      settings: Per-call overrides. Recognized keys:
        - task_type_tau (float)
        - agentic_intent_tau (float)
        - model_router_tau (float)
        - epsilon (float)
        Any key not provided falls back to its module-level default.

    Returns:
      RoutingDecision (frozen @dataclass).
    """
    try:
        # ----------------------------------------------------------
        # Normalize inputs (V5 input validation)
        # ----------------------------------------------------------
        if not isinstance(prompt, str):
            prompt = "" if prompt is None else str(prompt)

        if artifacts is None:
            artifacts = _load_default_artifacts()
        if settings is None:
            settings = {}

        tau_task = float(settings.get("task_type_tau", DEFAULT_TASK_TYPE_TAU))
        tau_agentic = float(settings.get("agentic_intent_tau", DEFAULT_AGENTIC_INTENT_TAU))
        tau_router = float(settings.get("model_router_tau", DEFAULT_MODEL_ROUTER_TAU))
        epsilon = float(settings.get("epsilon", DEFAULT_EPSILON))

        # Empty / whitespace-only prompts have no semantic content; the
        # calibrated heads might still produce a "confident" prediction
        # by sheer prior, but routing a blank prompt to any specific
        # backend is wrong. Treat as OOD and short-circuit to fallback.
        # This satisfies Plan 06 behavior Test 3 (empty -> fallback) and
        # V5 input validation from the threat model.
        if not prompt or not prompt.strip():
            return _build_fallback_decision(
                rationale_prefix="empty prompt",
                signals={"task_confidence": 0.0, "task_type": "unknown"},
                confidence=0.0,
            )

        extractor = _get_extractor()

        signals: dict[str, Any] = {}

        # ----------------------------------------------------------
        # Stage 1 — task-type classifier (no gate yet)
        # ----------------------------------------------------------
        raw_text = pd.Series([prompt])
        task_label, task_conf, task_table = _predict_with_calibrated(
            prompt, raw_text, artifacts["task_type_classifier"], extractor
        )
        signals["task_type"] = task_label
        signals["task_confidence"] = float(task_conf)
        signals["task_top3"] = task_table[:3]

        # ----------------------------------------------------------
        # Stage 2 — agentic-intent classifier
        # ----------------------------------------------------------
        agentic_label, agentic_conf, agentic_table = _predict_with_calibrated(
            prompt, raw_text, artifacts["agentic_intent_classifier"], extractor
        )
        is_agentic = (agentic_label == "agentic")
        signals["agentic_intent"] = agentic_label
        signals["agentic_confidence"] = float(agentic_conf)

        if agentic_conf < tau_agentic:
            prefix = f"agentic-intent confidence {agentic_conf:.2f} below {tau_agentic:.2f}"
            return _build_fallback_decision(prefix, signals, agentic_conf)

        # ----------------------------------------------------------
        # Stage 3 — D-01 rule cascade
        #
        # The cascade has two high-precision paths that depend ONLY on
        # the agentic flag + a keyword match (build/browse). When one
        # of those paths fires, we have strong enough evidence to skip
        # the task_type tau gate — the keyword is the high-precision
        # signal for "this is an action-taking prompt". This matches
        # D-01's literal text:
        #
        #   agentic AND (task in {coding, ...} OR keyword in BUILD)
        #     -> claude_code
        #   agentic AND keyword in BROWSE -> computer_use
        #
        # i.e. the keyword path is independent of task_type.
        #
        # Stage 1's task_type tau gate only applies on the conversational
        # / non-keyword path below, where the task_type classifier IS
        # the only signal between "good route to OpenRouter" and
        # "fallback to openrouter/auto on uncertainty."
        # ----------------------------------------------------------
        backend, sentinel_or_none, rule_reason = decide_backend(
            agentic_intent=is_agentic,
            agentic_confidence=agentic_conf,
            task_type=task_label,
            prompt=prompt,
        )
        signals["rule_fired"] = rule_reason

        if backend in {"claude_code", "computer_use"}:
            # High-precision keyword/coding path fired — emit decision.
            # Confidence is the min of per-stage max-probs (task + agentic).
            confidence = min(task_conf, agentic_conf)
            rationale = (
                f"task={task_label} | agentic={agentic_label} | {rule_reason}"
            )
            return RoutingDecision(
                backend=backend,
                model_or_agent=sentinel_or_none or "",  # mypy: non-Optional
                rationale=rationale,
                confidence=float(confidence),
                signals=signals,
            )

        # ----------------------------------------------------------
        # Stage 3b — OpenRouter path needs the task_type tau gate.
        #
        # D-09 dual signal: argmax == "unknown" OR max_prob below tau.
        # This is the OOD detection. If task_type is genuinely uncertain
        # AND no keyword path fired, we don't trust the cascade enough
        # to commit to a specific OpenRouter model — fall back to
        # openrouter/auto.
        # ----------------------------------------------------------
        if task_label == "unknown" or task_conf < tau_task:
            prefix = (
                f"task confidence {task_conf:.2f} below {tau_task:.2f}"
                if task_label != "unknown"
                else f"task predicted 'unknown' (confidence {task_conf:.2f})"
            )
            return _build_fallback_decision(prefix, signals, task_conf)

        # ----------------------------------------------------------
        # Stage 4 — OpenRouter branch: model_router prediction
        # ----------------------------------------------------------
        router_text = build_router_text_input_single(
            prompt=prompt,
            question_type=task_label,
            keyword_question_type="unknown",
        )
        router_label, router_conf, router_table = _predict_with_calibrated(
            prompt,
            router_text,
            artifacts["model_router"],
            extractor,
            extra_values={"question_type_confidence": float(task_conf)},
        )
        signals["predicted_model"] = router_label
        signals["model_router_confidence"] = float(router_conf)
        signals["model_router_top3"] = router_table[:3]

        if router_conf < tau_router:
            prefix = f"model-router confidence {router_conf:.2f} below {tau_router:.2f}"
            return _build_fallback_decision(prefix, signals, router_conf)

        # ----------------------------------------------------------
        # Stage 5 — quality-first cost tiebreaker (ROUTER-06) + resolve
        # to api_model via choose_final_route (D-02).
        # ----------------------------------------------------------
        model_mapping = artifacts["model_mapping"]
        chosen_slug = quality_first_pick(
            router_table[:3], model_mapping, epsilon=epsilon
        )
        signals["chosen_slug"] = chosen_slug
        signals["tier_tiebreaker_fired"] = (chosen_slug != router_table[0][0])

        route_info = choose_final_route(chosen_slug, model_mapping)
        resolved_model = route_info.get("api_model") or FALLBACK_MODEL_OR_AGENT
        signals["openrouter_verified"] = bool(route_info.get("openrouter_verified", False))
        signals["route_source"] = route_info.get("source", "unmapped_prediction")
        signals["route_tier"] = route_info.get("tier", "unknown")

        # ----------------------------------------------------------
        # Stage 6 — emit RoutingDecision
        # ----------------------------------------------------------
        confidence = min(task_conf, agentic_conf, router_conf)
        rationale = (
            f"task={task_label} | agentic={agentic_label} "
            f"| model_router={router_label} | chosen={chosen_slug} "
            f"| {rule_reason}"
        )
        return RoutingDecision(
            backend="openrouter",
            model_or_agent=resolved_model,
            rationale=rationale,
            confidence=float(confidence),
            signals=signals,
        )

    except Exception as exc:  # noqa: BLE001 — V7 robustness wrapper
        # Never propagate exceptions. Emit a fallback decision so the
        # caller always gets a RoutingDecision (CONTEXT §threat_model
        # T-01-RB-V7).
        #
        # WR-02 fix: log the exception with traceback so operators see
        # the failure (corrupt joblib, feature_columns mismatch, etc.).
        # Without this, every prompt silently routes to openrouter/auto
        # with no indication that the calibrated heads are broken.
        # logger.exception emits ERROR-level + the full traceback to
        # whichever handler the host process has configured.
        logger.exception(
            "decide() fell back to openrouter/auto due to error"
        )
        return _build_fallback_decision(
            rationale_prefix=f"internal error: {type(exc).__name__}",
            signals={
                "error_type": type(exc).__name__,
                "error_msg": str(exc)[:500],  # bound the error string
            },
            confidence=0.0,
        )


# ----------------------------------------------------------------------
# CLI entry point (D-17)
# ----------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    """`python -m src.routing.decide '<prompt>'` — print decision as JSON.

    One-line JSON output so downstream tools (Plan 07's eval runner,
    Phase 2's adapter shims) can pipe / parse it deterministically.
    """
    parser = argparse.ArgumentParser(
        description="Route a single prompt and print RoutingDecision as JSON.",
    )
    parser.add_argument("prompt", help="The prompt text to route.")
    args = parser.parse_args(argv)

    decision = decide(prompt=args.prompt)
    print(decision.to_json())
    return 0


if __name__ == "__main__":
    sys.exit(main())

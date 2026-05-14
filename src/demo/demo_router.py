import os
import sys
import json
import joblib
import pandas as pd

from scipy.sparse import hstack, csr_matrix


# ------------------------------------------------------------
# Path setup
# ------------------------------------------------------------

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))

SRC_DIR = os.path.join(PROJECT_ROOT, "src", "feature_extraction")
MODELS_DIR = os.path.join(PROJECT_ROOT, "models")
CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")

TASK_CLASSIFIER_PATH = os.path.join(MODELS_DIR, "task_type_classifier.joblib")
MODEL_ROUTER_PATH = os.path.join(MODELS_DIR, "model_router.joblib")
AGENTIC_INTENT_PATH = os.path.join(MODELS_DIR, "agentic_intent_classifier.joblib")
MODEL_MAPPING_PATH = os.path.join(CONFIG_DIR, "model_mapping.json")

if SRC_DIR not in sys.path:
    sys.path.append(SRC_DIR)

from Feature_extractor import PromptFeatureExtractor
from src.feature_extraction.text_inputs import build_router_text_input_single

# ROUTER-07: route_prompt now delegates to the framework-free routing brain
# rather than running its own two-stage pipeline. The REPL surface
# (input loop + print_route_result) is preserved verbatim for backward
# compatibility; internally the brain emits a RoutingDecision that we
# adapt back into the legacy dict shape print_route_result consumes.
from src.routing.config import FALLBACK_MODEL_OR_AGENT
from src.routing.decide import decide
from src.routing.schema import RoutingDecision


# ------------------------------------------------------------
# Load helpers
# ------------------------------------------------------------

def load_joblib_artifacts(path: str, artifact_name: str):
    """
    Load a saved joblib artifact dictionary.
    """

    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{artifact_name} not found at:\n{path}\n\n"
            f"Train/save {artifact_name} first."
        )

    artifacts = joblib.load(path)

    required_keys = [
        "model",
        "vectorizer",
        "scaler",
        "label_encoder",
        "feature_columns",
    ]

    for key in required_keys:
        if key not in artifacts:
            raise KeyError(f"{artifact_name} is missing required key: {key}")

    return artifacts


def load_json(path: str, name: str):
    """
    Load a JSON config file.
    """

    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{name} not found at:\n{path}"
        )

    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


# ------------------------------------------------------------
# Feature preparation
# ------------------------------------------------------------

def build_numeric_features(
    prompt: str,
    feature_columns: list,
    extractor: PromptFeatureExtractor,
    extra_values: dict | None = None
) -> pd.DataFrame:
    """
    Build numeric feature DataFrame matching the saved model's expected columns.
    """

    extracted_features = extractor.extract(prompt)

    row = {}
    row.update(extracted_features)

    if extra_values:
        row.update(extra_values)

    feature_df = pd.DataFrame([row])

    for col in feature_columns:
        if col not in feature_df.columns:
            feature_df[col] = 0

    feature_df = feature_df[feature_columns].fillna(0)

    return feature_df


# ------------------------------------------------------------
# Stage 1: Task classifier (kept for legacy callers / tests)
# ------------------------------------------------------------

def predict_task_type(
    prompt: str,
    task_artifacts: dict,
    extractor: PromptFeatureExtractor
):
    """
    Predict the task/question type for a prompt.

    NOTE: Plan 08 / ROUTER-07 moved the live demo pipeline to
    `src.routing.decide`. This function is preserved unchanged for any
    legacy callers (e.g. import-time smoke tests) that depend on its
    return shape, but `route_prompt` no longer calls it.
    """

    model = task_artifacts["model"]
    vectorizer = task_artifacts["vectorizer"]
    scaler = task_artifacts["scaler"]
    label_encoder = task_artifacts["label_encoder"]
    feature_columns = task_artifacts["feature_columns"]

    text_series = pd.Series([prompt])
    text_features = vectorizer.transform(text_series)

    numeric_df = build_numeric_features(
        prompt=prompt,
        feature_columns=feature_columns,
        extractor=extractor
    )

    numeric_scaled = scaler.transform(numeric_df)
    numeric_sparse = csr_matrix(numeric_scaled)

    combined_features = hstack([text_features, numeric_sparse])

    prediction_encoded = model.predict(combined_features)[0]
    prediction_label = label_encoder.inverse_transform([prediction_encoded])[0]

    probabilities = model.predict_proba(combined_features)[0]

    confidence_table = []

    for label, probability in zip(label_encoder.classes_, probabilities):
        confidence_table.append((label, probability))

    confidence_table.sort(key=lambda item: item[1], reverse=True)

    confidence = confidence_table[0][1]

    return prediction_label, confidence, confidence_table


# ------------------------------------------------------------
# Stage 2: Exact/top model router (kept for legacy callers / tests)
# ------------------------------------------------------------

def predict_best_model(
    prompt: str,
    question_type: str,
    question_type_confidence: float,
    model_router_artifacts: dict,
    extractor: PromptFeatureExtractor
):
    """
    Predict the best model class using the trained model router.

    NOTE: Plan 08 / ROUTER-07 moved the live demo pipeline to
    `src.routing.decide`. This function is preserved unchanged for any
    legacy callers; `route_prompt` no longer calls it.
    """

    model = model_router_artifacts["model"]
    vectorizer = model_router_artifacts["vectorizer"]
    scaler = model_router_artifacts["scaler"]
    label_encoder = model_router_artifacts["label_encoder"]
    feature_columns = model_router_artifacts["feature_columns"]

    text_features = vectorizer.transform(
        build_router_text_input_single(
            prompt=prompt,
            question_type=question_type
        )
    )

    numeric_df = build_numeric_features(
        prompt=prompt,
        feature_columns=feature_columns,
        extractor=extractor,
        extra_values={
            "question_type_confidence": question_type_confidence
        }
    )

    numeric_scaled = scaler.transform(numeric_df)
    numeric_sparse = csr_matrix(numeric_scaled)

    combined_features = hstack([text_features, numeric_sparse])

    prediction_encoded = model.predict(combined_features)[0]
    prediction_label = label_encoder.inverse_transform([prediction_encoded])[0]

    probabilities = model.predict_proba(combined_features)[0]

    confidence_table = []

    for label, probability in zip(label_encoder.classes_, probabilities):
        confidence_table.append((label, probability))

    confidence_table.sort(key=lambda item: item[1], reverse=True)

    confidence = confidence_table[0][1]

    return prediction_label, confidence, confidence_table


# ------------------------------------------------------------
# Mapping / final route logic
# ------------------------------------------------------------

def choose_final_route(predicted_model: str, model_mapping: dict):
    """
    Convert the predicted model class into route metadata.

    If the model is unknown or OTHER, use the OTHER mapping.
    """

    if predicted_model in model_mapping:
        model_info = model_mapping[predicted_model].copy()
        model_info["source"] = "model_router"
        return model_info

    if "OTHER" in model_mapping:
        model_info = model_mapping["OTHER"].copy()
        model_info["source"] = "fallback_other"
        model_info["original_prediction"] = predicted_model
        return model_info

    return {
        "display_name": predicted_model,
        "provider": "simulated",
        "tier": "unknown",
        "api_model": None,
        "openrouter_verified": False,
        "source": "unmapped_prediction",
        "notes": "Predicted model was not found in model_mapping.json."
    }


def get_api_model_for_real_call(final_model_info: dict):
    """
    Return the API model if verified.

    For simulated/unverified models, return None.
    """

    if final_model_info.get("openrouter_verified") and final_model_info.get("api_model"):
        return final_model_info["api_model"]

    return None


# ------------------------------------------------------------
# RoutingDecision -> legacy dict adapter (ROUTER-07)
# ------------------------------------------------------------

def _decision_to_legacy_dict(
    decision: RoutingDecision,
    prompt: str,
    artifacts: dict,
) -> dict:
    """
    Adapt a RoutingDecision (produced by `src.routing.decide.decide`) into
    the legacy dict shape consumed by `print_route_result` below.

    The brain's `signals` carry per-stage telemetry; we project them back
    onto the original demo keys so the existing print path keeps working.
    For non-OpenRouter branches (claude_code / computer_use / fallback)
    the brain's `model_or_agent` is the canonical identifier and there
    is no model_router prediction — we synthesize sensible defaults so
    `print_route_result` never crashes on a missing key.

    WR-06 fix: take the full `artifacts` dict (4-key shape: task,
    agentic, model_router, model_mapping) instead of a parallel
    `model_mapping` argument. This guarantees the demo adapter resolves
    route metadata against the SAME mapping the brain used inside
    decide() — eliminates the fragile assumption that the demo's view of
    model_mapping matches the brain's view.

    Output keys (matches the original route_prompt return shape):
      prompt
      question_type, question_type_confidence, task_predictions
      predicted_model, model_confidence, model_predictions
      final_model_info, api_model_for_real_call
      routing_decision  # NEW — the structured decision for future UI surfaces
    """

    # Source the mapping from the same artifacts dict the brain consumed
    # (WR-06). KeyError if absent — fail loud rather than fall back to {}.
    model_mapping = artifacts["model_mapping"]

    signals = decision.signals or {}

    # --- Stage 1: task type (always populated by the brain) -----------
    question_type = signals.get("task_type", "unknown")
    question_type_confidence = float(signals.get("task_confidence", 0.0))
    task_predictions = list(signals.get("task_top3", []))

    # --- Stage 2: model-or-agent + confidence + route metadata --------
    # For the OpenRouter branch the brain populates "predicted_model"
    # and "model_router_top3". For Claude Code / computer-use the
    # `model_or_agent` is the canonical sentinel.
    if decision.backend == "openrouter":
        predicted_model = signals.get("predicted_model") or decision.model_or_agent
        model_confidence = float(signals.get("model_router_confidence", decision.confidence))
        model_predictions = list(signals.get("model_router_top3", []))

        # Resolve route metadata via the legacy choose_final_route helper
        # so the demo display keeps reading `display_name`, `provider`,
        # `tier`, `api_model`, `openrouter_verified`, and `source` in
        # exactly the shape it always has.
        chosen_slug = signals.get("chosen_slug") or predicted_model
        final_model_info = choose_final_route(chosen_slug, model_mapping)

        # Override api_model with whatever the brain actually picked.
        # For fallback (low-confidence + unverified-slug branches) this
        # reflects the brain's decision rather than the raw slug's
        # api_model from model_mapping.json (which may be null).
        #
        # WR-01 fix: When the brain substitutes the slug's api_model (e.g.,
        # because choose_final_route returned a null api_model for an
        # unverified-but-mapped slug like internlm3-8b-instruct, and
        # decide() fell through to FALLBACK_MODEL_OR_AGENT), the legacy
        # display would still show the slug's stale openrouter_verified=False
        # and source="model_router". Re-derive both fields from the
        # openrouter/auto mapping entry so the displayed route metadata
        # is consistent with the api_model the brain actually picked.
        final_model_info = dict(final_model_info)
        if (
            final_model_info.get("api_model") != decision.model_or_agent
            and decision.model_or_agent == FALLBACK_MODEL_OR_AGENT
        ):
            auto_entry = model_mapping.get("openrouter", {})
            final_model_info["openrouter_verified"] = bool(
                auto_entry.get("openrouter_verified", False)
            )
            final_model_info["source"] = "unverified_slug_fallback_to_auto"
        final_model_info["api_model"] = decision.model_or_agent

    else:
        # claude_code / computer_use — the brain's model_or_agent is the
        # canonical sentinel; there is no model_router top-3 to display.
        predicted_model = decision.model_or_agent
        model_confidence = float(decision.confidence)
        model_predictions = []

        # Synthesize a route-info dict for the non-OpenRouter sentinels
        # so print_route_result has a stable shape to render. None of
        # these go through OpenRouter's verified slug list.
        final_model_info = {
            "display_name": decision.model_or_agent,
            "provider": "claude_code" if decision.backend == "claude_code" else "computer_use",
            "tier": "strong",
            "api_model": decision.model_or_agent,
            "openrouter_verified": False,
            "source": decision.backend,
        }

    api_model_for_real_call = get_api_model_for_real_call(final_model_info)

    return {
        "prompt": prompt,

        "question_type": question_type,
        "question_type_confidence": question_type_confidence,
        "task_predictions": task_predictions,

        "predicted_model": predicted_model,
        "model_confidence": model_confidence,
        "model_predictions": model_predictions,

        "final_model_info": final_model_info,
        "api_model_for_real_call": api_model_for_real_call,

        # NEW (Plan 08): expose the full structured decision so the
        # future FastAPI / UI layers (Phase 3 / Phase 4) can render the
        # rationale chip without re-running the brain.
        "routing_decision": decision,
    }


# ------------------------------------------------------------
# Full route pipeline (now delegates to src.routing.decide)
# ------------------------------------------------------------

def route_prompt(
    prompt: str,
    task_artifacts: dict,
    model_router_artifacts: dict,
    model_mapping: dict,
    extractor: PromptFeatureExtractor,
    agentic_intent_artifacts: dict | None = None,
):
    """
    Route a single prompt via the framework-free routing brain.

    Plan 08 / ROUTER-07: instead of running the legacy two-stage
    pipeline (predict_task_type -> predict_best_model -> choose_final_route)
    in this function, we delegate to `src.routing.decide.decide()` which
    composes the three calibrated heads (task_type + agentic_intent +
    model_router) plus the D-01 rule cascade. The result is adapted
    back into the legacy dict shape `print_route_result` consumes so
    the REPL UX is unchanged.

    The `extractor` arg is preserved for backwards compatibility — the
    brain manages its own PromptFeatureExtractor singleton so we don't
    need to pass ours in. The `task_artifacts`, `model_router_artifacts`,
    and `agentic_intent_artifacts` are forwarded so the brain doesn't
    re-load the joblibs on every REPL turn (perf optimization for
    interactive use).

    Args:
      prompt: the user prompt text from the REPL.
      task_artifacts: dict loaded from models/task_type_classifier.joblib.
      model_router_artifacts: dict loaded from models/model_router.joblib.
      model_mapping: dict loaded from config/model_mapping.json.
      extractor: PromptFeatureExtractor (preserved for backwards-compat;
                 unused internally because the brain owns its own).
      agentic_intent_artifacts: dict loaded from
                 models/agentic_intent_classifier.joblib. If None, the
                 brain will load it from disk on the first call.
    """

    # Lazy-load the agentic-intent artifact if the caller didn't pre-load it
    # (preserves the existing route_prompt signature for any test that
    # constructs the call with only the legacy four arguments).
    if agentic_intent_artifacts is None:
        agentic_intent_artifacts = load_joblib_artifacts(
            AGENTIC_INTENT_PATH,
            "agentic_intent_classifier.joblib",
        )

    artifacts = {
        "task_type_classifier": task_artifacts,
        "model_router": model_router_artifacts,
        "agentic_intent_classifier": agentic_intent_artifacts,
        "model_mapping": model_mapping,
    }

    decision = decide(prompt=prompt, artifacts=artifacts)

    # WR-06 fix: pass the same artifacts dict the brain consumed so the
    # adapter resolves route metadata against the same model_mapping.
    return _decision_to_legacy_dict(decision, prompt, artifacts)


# ------------------------------------------------------------
# Display helpers
# ------------------------------------------------------------

def print_top_predictions(title: str, confidence_table: list, top_n: int = 5):
    """
    Print top prediction probabilities.
    """

    print(f"\n{title}")

    for label, probability in confidence_table[:top_n]:
        print(f"- {label}: {probability:.4f}")


def print_route_result(result: dict):
    """
    Pretty terminal output for one route.
    """

    final_model = result["final_model_info"]

    print("\n" + "=" * 70)
    print("PROMPT ROUTING RESULT")
    print("=" * 70)

    print("\nPrompt:")
    print(result["prompt"])

    print("\nStage 1: Task Classifier")
    print(f"Predicted question type: {result['question_type']}")
    print(f"Confidence: {result['question_type_confidence']:.4f}")

    print("\nStage 2: Model Router")
    print(f"Predicted model class: {result['predicted_model']}")
    print(f"Confidence: {result['model_confidence']:.4f}")

    print("\nFinal Simulated Route")
    print(f"Display name: {final_model.get('display_name')}")
    print(f"Provider: {final_model.get('provider')}")
    print(f"Tier: {final_model.get('tier')}")
    print(f"API model: {final_model.get('api_model')}")
    print(f"OpenRouter verified: {final_model.get('openrouter_verified')}")
    print(f"Route source: {final_model.get('source')}")

    api_model = result["api_model_for_real_call"]

    if api_model:
        print(f"Real API model available: {api_model}")
    else:
        print("Real API model available: None, simulated/unverified route")

    original_prediction = final_model.get("original_prediction")
    if original_prediction:
        print(f"Original unmapped prediction: {original_prediction}")

    notes = final_model.get("notes")
    if notes:
        print(f"Notes: {notes}")

    if result.get("task_predictions"):
        print_top_predictions(
            title="Top task type predictions:",
            confidence_table=result["task_predictions"]
        )

    if result.get("model_predictions"):
        print_top_predictions(
            title="Top model predictions:",
            confidence_table=result["model_predictions"]
        )

    # Plan 08 enhancement: surface the structured rationale + confidence
    # produced by the routing brain so the user can see why a prompt
    # routed where it did. Graceful degradation when an older caller
    # doesn't pass routing_decision through.
    decision = result.get("routing_decision")
    if decision is not None:
        print(f"\nRationale: {decision.rationale}")
        print(f"Confidence: {decision.confidence:.3f}")

    print("\n" + "=" * 70)


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

def main():
    print("\nPrompt Optimizer Demo Router")
    print("----------------------------")
    print("Pipeline: src.routing.decide -> calibrated 3-head cascade")
    print("Loading saved models and route mappings...")

    task_artifacts = load_joblib_artifacts(
        TASK_CLASSIFIER_PATH,
        "task_type_classifier.joblib"
    )

    model_router_artifacts = load_joblib_artifacts(
        MODEL_ROUTER_PATH,
        "model_router.joblib"
    )

    agentic_intent_artifacts = load_joblib_artifacts(
        AGENTIC_INTENT_PATH,
        "agentic_intent_classifier.joblib"
    )

    model_mapping = load_json(
        MODEL_MAPPING_PATH,
        "model_mapping.json"
    )

    extractor = PromptFeatureExtractor()

    print("\nLoaded successfully.")
    print("Type a prompt to route.")
    print("Type 'quit' to stop.")

    while True:
        prompt = input("\nPrompt: ").strip()

        if prompt.lower() in ["quit", "exit", "q"]:
            print("Goodbye.")
            break

        if not prompt:
            print("Please enter a prompt.")
            continue

        try:
            result = route_prompt(
                prompt=prompt,
                task_artifacts=task_artifacts,
                model_router_artifacts=model_router_artifacts,
                model_mapping=model_mapping,
                extractor=extractor,
                agentic_intent_artifacts=agentic_intent_artifacts,
            )

            print_route_result(result)

        except Exception as error:
            print("\nRouting failed.")
            print(f"Error: {error}")


if __name__ == "__main__":
    main()

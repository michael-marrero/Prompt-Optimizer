"""Routing-canary evaluator — Plan 01-07 / ROUTER-04 / D-16.

Loads `data_processed/routing_decision_eval.csv`, runs every row through
`src.routing.decide.decide`, and emits the D-16 metric stack under
`evaluation/routing/`:

  - backend_accuracy.csv          per-backend + overall accuracy
  - per_backend_pr.csv            precision / recall / F1 per backend
  - confusion_matrix.csv          expected (rows) vs actual (cols)
  - confusion_matrix.png          plotted version of the above
  - ece_per_stage.csv             ECE per calibrated head
  - low_confidence_rate.txt       single-line "low_confidence_rate=0.142"
  - fallback_recall.txt           single-line float — fraction of rows
                                  with is_fallback_expected=True where
                                  decide() actually emitted the fallback
                                  rationale suffix. Measures D-09/D-12
                                  fallback fidelity (WR-04).
  - reliability_diagram_<stage>.png   one per calibrated head (3 files)

Usage:

    uv run python -m src.evaluation.evaluate_routing
    uv run python -m src.evaluation.evaluate_routing --canary-input <path>
    uv run python -m src.evaluation.evaluate_routing --output-dir <dir>
    uv run python -m src.evaluation.evaluate_routing --check

`--check` exits 0 if backend_accuracy >= BACKEND_ACCURACY_THRESHOLD AND
every per-stage ECE <= ECE_THRESHOLD, else exit 1 with the failing
thresholds logged. CI workflow `.github/workflows/ci.yml` is gated by
this exit code (Plan 01-01 Success Criterion #3).

Threshold defaults are module constants:

    BACKEND_ACCURACY_THRESHOLD = 0.65
    ECE_THRESHOLD              = 0.10  (RESEARCH Pattern 1)

Imports ONLY stdlib + sklearn + scipy + joblib + pandas + numpy +
matplotlib + the local `src.routing.*` and `src.feature_extraction.*`
modules — no HTTP libraries, no LLM SDKs (D-18 import-graph constraint
inherited from `src/routing/`).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Optional

import joblib
import matplotlib

matplotlib.use("Agg")  # headless backend for CI / scripted runs
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix, hstack
from sklearn.calibration import calibration_curve
from sklearn.metrics import (
    ConfusionMatrixDisplay,
    accuracy_score,
    confusion_matrix,
    precision_recall_fscore_support,
)

# Local imports — D-18 import-graph constraint preserved by virtue of
# only importing `src.routing.*` which itself imports only stdlib +
# scipy + joblib + pandas + sklearn + Feature_extractor.
from src.feature_extraction.text_inputs import build_router_text_input_single
from src.routing.config import (
    DEFAULT_AGENTIC_INTENT_TAU,
    DEFAULT_ARTIFACT_PATHS,
    DEFAULT_MODEL_MAPPING_PATH,
    DEFAULT_MODEL_ROUTER_TAU,
    DEFAULT_TASK_TYPE_TAU,
    FALLBACK_RATIONALE_SUFFIX,
    PROJECT_ROOT,
)
from src.routing.decide import decide  # public surface from Plan 01-06


# ----------------------------------------------------------------------
# Path setup (canonical CLAUDE.md pattern; mirrors evaluate_baselines.py)
# ----------------------------------------------------------------------

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PROCESSED_DIR = os.path.join(PROJECT_ROOT, "data_processed")
MODELS_DIR = os.path.join(PROJECT_ROOT, "models")
EVALUATION_DIR = os.path.join(PROJECT_ROOT, "evaluation")
ROUTING_EVAL_DIR = os.path.join(EVALUATION_DIR, "routing")

os.makedirs(ROUTING_EVAL_DIR, exist_ok=True)

CANARY_CSV = os.path.join(DATA_PROCESSED_DIR, "routing_decision_eval.csv")


# ----------------------------------------------------------------------
# Thresholds for `--check`. Module constants (not function-local) so
# test_evaluate_routing.py can introspect them.
# ----------------------------------------------------------------------

# Soft floor — RESEARCH Open Question 5 says the canary's accuracy
# ceiling is unknown until first run; 0.65 should be passable with the
# calibrated heads + decent canary. Tune after first end-to-end run.
BACKEND_ACCURACY_THRESHOLD: float = 0.65

# ECE > 0.10 means recalibration needed (RESEARCH Pattern 1; switch
# from method="sigmoid" to method="isotonic" on the failing stage).
ECE_THRESHOLD: float = 0.10


# Backend label set used for accuracy / confusion-matrix axes.
BACKENDS = ("openrouter", "claude_code", "computer_use")


REQUIRED_CANARY_COLUMNS = [
    "prompt",
    "expected_backend",
    "expected_model_or_agent_substring",
    "is_fallback_expected",
    "edge_case_category",
    "source",
    "license",
]


# ----------------------------------------------------------------------
# Logging — pipeline scripts use `logging.basicConfig` per CLAUDE.md
# "Logging" section. Verbosity is configurable via -v/--verbose.
# ----------------------------------------------------------------------

logger = logging.getLogger("evaluate_routing")


# ----------------------------------------------------------------------
# Helpers — canary loading + bool coercion
# ----------------------------------------------------------------------


def _coerce_bool(value) -> bool:
    """Coerce a CSV cell to bool (case-insensitive "true" / "false")."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def load_canary(canary_path: str) -> pd.DataFrame:
    """Load the canary CSV and validate the locked schema.

    Returns:
      pd.DataFrame with all columns coerced to str except
      `is_fallback_expected` which is coerced to bool.
    """
    if not os.path.exists(canary_path):
        raise FileNotFoundError(
            f"canary CSV not found at:\n{canary_path}\n\n"
            f"Author it first per Plan 01-07 Task 1 (data_processed/"
            f"routing_decision_eval.csv with ~42 hand-labeled rows)."
        )

    df = pd.read_csv(canary_path)

    for col in REQUIRED_CANARY_COLUMNS:
        if col not in df.columns:
            raise ValueError(
                f"canary CSV is missing required column: {col!r}. "
                f"Expected columns: {REQUIRED_CANARY_COLUMNS}"
            )

    # Coerce types
    df["prompt"] = df["prompt"].fillna("").astype(str)
    df["expected_backend"] = df["expected_backend"].fillna("").astype(str)
    df["expected_model_or_agent_substring"] = (
        df["expected_model_or_agent_substring"].fillna("").astype(str)
    )
    df["is_fallback_expected"] = df["is_fallback_expected"].map(_coerce_bool)
    df["edge_case_category"] = df["edge_case_category"].fillna("").astype(str)
    df["source"] = df["source"].fillna("").astype(str)
    df["license"] = df["license"].fillna("").astype(str)

    return df


# ----------------------------------------------------------------------
# ECE helper — lifted verbatim from 01-PATTERNS.md lines 800-818
# (which is itself lifted from 01-RESEARCH.md lines 884-901).
# ----------------------------------------------------------------------


def expected_calibration_error(
    y_true_binary: np.ndarray,
    y_prob_max: np.ndarray,
    n_bins: int = 10,
) -> float:
    """ECE on max-class probability for a multiclass classifier.

    Args:
      y_true_binary: array of {0, 1}, 1 iff the prediction was correct.
      y_prob_max: array of floats in [0, 1] — the predicted top-class
        probability for each prediction.
      n_bins: number of uniform bins over [0, 1].

    Returns:
      ECE as a float in [0, 1]. 0 means perfectly calibrated.
    """
    if len(y_true_binary) == 0:
        return 0.0
    y_true_binary = np.asarray(y_true_binary, dtype=float)
    y_prob_max = np.asarray(y_prob_max, dtype=float)
    bin_boundaries = np.linspace(0.0, 1.0, n_bins + 1)
    bin_lowers, bin_uppers = bin_boundaries[:-1], bin_boundaries[1:]
    n = len(y_true_binary)
    ece = 0.0
    for lo, hi in zip(bin_lowers, bin_uppers):
        in_bin = (y_prob_max > lo) & (y_prob_max <= hi)
        if in_bin.sum() == 0:
            continue
        accuracy_in_bin = y_true_binary[in_bin].mean()
        mean_confidence_in_bin = y_prob_max[in_bin].mean()
        ece += (in_bin.sum() / n) * abs(accuracy_in_bin - mean_confidence_in_bin)
    return float(ece)


# ----------------------------------------------------------------------
# Plot helpers — CLAUDE.md plotting conventions: dpi=300, tight_layout,
# plt.close(), printed save confirmation.
# ----------------------------------------------------------------------


def plot_reliability_diagram(
    y_true_binary: np.ndarray,
    y_prob_max: np.ndarray,
    stage_name: str,
    output_path: str,
) -> None:
    """Plot a reliability diagram (calibration curve) for one classifier.

    The diagonal line is perfect calibration. Points above mean
    under-confident; points below mean over-confident.
    """
    if len(y_true_binary) == 0 or len(np.unique(y_true_binary)) < 1:
        logger.warning(
            "Skipping reliability diagram for %s: no data", stage_name
        )
        return

    # `calibration_curve` requires at least one positive (1) and one
    # negative (0) sample in some configurations; guard with a fallback.
    try:
        prob_true, prob_pred = calibration_curve(
            y_true_binary, y_prob_max, n_bins=10, strategy="uniform"
        )
    except ValueError as exc:
        logger.warning(
            "Reliability diagram for %s: calibration_curve raised %s",
            stage_name, exc,
        )
        prob_true, prob_pred = np.array([]), np.array([])

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.plot([0, 1], [0, 1], "k--", linewidth=1, label="Perfect calibration")
    if len(prob_pred) > 0:
        ax.plot(prob_pred, prob_true, marker="o", linewidth=2, label=stage_name)
    ax.set_xlabel("Mean predicted probability")
    ax.set_ylabel("Empirical accuracy")
    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(0.0, 1.0)
    ax.set_title(f"Reliability Diagram - {stage_name}")
    ax.legend(loc="best")
    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close(fig)

    print(f"Saved reliability diagram to: {output_path}")


def plot_confusion_matrix_chart(
    cm: np.ndarray,
    labels: list,
    output_path: str,
) -> None:
    """Plot the backend confusion matrix as a heatmap PNG.

    Mirrors the ConfusionMatrixDisplay pattern from
    `src/task_classifier/train_task_classifier_robust.py:117-145` per
    01-PATTERNS.md lines 1052-1071.
    """
    fig, ax = plt.subplots(figsize=(8, 6))
    display = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=labels)
    display.plot(ax=ax, xticks_rotation=45, values_format="d", colorbar=True)
    ax.set_title("Backend Confusion Matrix (expected vs actual)")
    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close(fig)

    print(f"Saved confusion matrix to: {output_path}")


# ----------------------------------------------------------------------
# Per-stage probability re-computation
#
# `decide()` stores top-1 confidence + top-3 in `signals` but does NOT
# expose the raw `predict_proba` row. To compute per-stage ECE on the
# canary we re-run each stage's `predict_proba` directly using the
# loaded artifact. This is the planned path per Plan 01-07 Task 3
# Action step 9(e).
# ----------------------------------------------------------------------


def _build_numeric_features(
    prompt: str,
    feature_columns: list,
    extractor,
    extra_values: Optional[dict] = None,
) -> pd.DataFrame:
    """1-row DataFrame matching artifact's feature_columns.

    Identical to `_build_numeric_features` in `src.routing.decide`;
    duplicated here to keep the routing-brain function private and to
    decouple the evaluator's stage-recompute path from the decide()
    implementation.
    """
    extracted = extractor.extract(prompt)
    row: dict = {}
    row.update(extracted)
    if extra_values:
        row.update(extra_values)
    df = pd.DataFrame([row])
    for col in feature_columns:
        if col not in df.columns:
            df[col] = 0
    df = df[feature_columns].fillna(0)
    return df


def _stage_predict_proba(
    prompt: str,
    raw_text_series: pd.Series,
    artifact: dict,
    extractor,
    extra_values: Optional[dict] = None,
) -> tuple[str, float, list]:
    """Return (top_label, top_prob, full_label_prob_list).

    Mirrors `src.routing.decide._predict_with_calibrated` but exposed
    here so evaluate_routing.py can compute per-stage ECE without
    importing the private `_predict_with_calibrated`.
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


def _load_artifacts() -> dict:
    """Load the three calibrated joblib heads + model_mapping.json.

    Returns:
      dict with keys task_type_classifier, agentic_intent_classifier,
      model_router, model_mapping.
    """
    artifacts: dict = {}
    for key in ("task_type_classifier", "agentic_intent_classifier", "model_router"):
        path = DEFAULT_ARTIFACT_PATHS[key]
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"{key} artifact not found at:\n{path}\n\n"
                f"Train it first (see src/task_classifier/ or src/model_router/ "
                f"training scripts; Plan 01-04 / 01-05)."
            )
        artifacts[key] = joblib.load(path)

    if not os.path.exists(DEFAULT_MODEL_MAPPING_PATH):
        raise FileNotFoundError(
            f"model_mapping.json not found at:\n{DEFAULT_MODEL_MAPPING_PATH}"
        )
    with open(DEFAULT_MODEL_MAPPING_PATH, "r", encoding="utf-8") as fh:
        artifacts["model_mapping"] = json.load(fh)

    return artifacts


# ----------------------------------------------------------------------
# PromptFeatureExtractor — loaded lazily so import-time stays cheap.
# We import it via the same sys.path injection used in src/routing/decide.py
# (CONTEXT line 151 — documented anti-pattern, the broader migration is
# deferred to a cleanup phase).
# ----------------------------------------------------------------------


def _get_extractor():
    """Return a PromptFeatureExtractor instance (lazy import)."""
    _FE_DIR = os.path.join(PROJECT_ROOT, "src", "feature_extraction")
    if _FE_DIR not in sys.path:
        sys.path.append(_FE_DIR)
    from Feature_extractor import PromptFeatureExtractor  # noqa: E402
    return PromptFeatureExtractor()


# ----------------------------------------------------------------------
# Main evaluation loop
# ----------------------------------------------------------------------


def run(canary_path: str, output_dir: str) -> dict:
    """Run the canary eval end-to-end. Returns a metrics dict for --check.

    Side effects: writes all 9 D-16 output files into `output_dir`.

    Returns:
      dict with keys:
        - backend_accuracy: float
        - per_stage_ece: dict[stage_name -> float]
        - low_confidence_rate: float
    """
    os.makedirs(output_dir, exist_ok=True)

    logger.info("Loading canary CSV from: %s", canary_path)
    df = load_canary(canary_path)
    logger.info("Loaded %d canary rows", len(df))

    logger.info("Loading calibrated artifacts ...")
    artifacts = _load_artifacts()

    extractor = _get_extractor()

    # ------------------------------------------------------------------
    # Iterate canary rows. For each row:
    #   - call decide() once -> capture backend/model/rationale/signals
    #   - call _stage_predict_proba() three times (one per calibrated
    #     head) -> capture top-label + top-prob + full distribution
    #     for the per-stage ECE.
    # ------------------------------------------------------------------

    rows_out: list[dict] = []
    per_stage_records: dict[str, dict] = {
        "task_type_classifier": {"y_true_binary": [], "y_prob_max": [], "y_pred": [], "y_label": []},
        "agentic_intent_classifier": {"y_true_binary": [], "y_prob_max": [], "y_pred": [], "y_label": []},
        "model_router": {"y_true_binary": [], "y_prob_max": [], "y_pred": [], "y_label": []},
    }

    for idx, canary_row in df.iterrows():
        prompt = canary_row["prompt"]
        expected_backend = canary_row["expected_backend"]
        expected_substring = canary_row["expected_model_or_agent_substring"]
        is_fallback_expected = bool(canary_row["is_fallback_expected"])
        edge_case = canary_row["edge_case_category"]

        # Decision (the integration call).
        decision = decide(prompt=prompt, artifacts=artifacts)
        actual_backend = decision.backend
        actual_model_or_agent = decision.model_or_agent
        actual_rationale = decision.rationale
        actual_signals = decision.signals

        # Was the rationale a fallback rationale? (D-12 contract.)
        is_fallback_actual = actual_rationale.endswith(FALLBACK_RATIONALE_SUFFIX)

        # Match policies:
        #   - backend match: actual_backend == expected_backend
        #   - model/agent match: expected_substring appears in
        #     actual_model_or_agent (substring is a partial match because
        #     expected_substring is intentionally loose — "gpt-5" matches
        #     "openai/gpt-5", etc.)
        backend_match = (actual_backend == expected_backend)
        model_substring_match = (expected_substring in actual_model_or_agent)

        rows_out.append(
            {
                "prompt": prompt,
                "expected_backend": expected_backend,
                "actual_backend": actual_backend,
                "backend_match": backend_match,
                "expected_model_or_agent_substring": expected_substring,
                "actual_model_or_agent": actual_model_or_agent,
                "model_substring_match": model_substring_match,
                "is_fallback_expected": is_fallback_expected,
                "is_fallback_actual": is_fallback_actual,
                "edge_case_category": edge_case,
                "rationale": actual_rationale,
                "task_confidence": float(actual_signals.get("task_confidence", 0.0)),
                "agentic_confidence": float(actual_signals.get("agentic_confidence", 0.0)),
                "model_router_confidence": float(actual_signals.get("model_router_confidence", 0.0)),
                "tier_tiebreaker_fired": bool(actual_signals.get("tier_tiebreaker_fired", False)),
            }
        )

        # --------------------------------------------------------------
        # Per-stage ECE inputs. Run each stage explicitly so we can
        # capture top-prob + top-label for the canary row.
        #
        # The "y_true" for per-stage ECE is whether the calibrated head's
        # argmax matched what `decide()`'s downstream cascade would have
        # accepted. We use a per-stage definition:
        #   - task_type_classifier: y_true = 1 iff the predicted task
        #     label is consistent with the actual cascade outcome. We
        #     approximate this as: agree with `decide()`'s rule_fired
        #     branch (coding-task branch needs CODING_TASK_TYPES;
        #     keyword branches don't depend on task type).
        #   - agentic_intent_classifier: y_true = 1 iff the predicted
        #     binary label correctly distinguishes the canary's
        #     intended backend (claude_code/computer_use => agentic;
        #     openrouter => conversational unless fallback row in which
        #     case it's accepted either way).
        #   - model_router: only evaluated on openrouter rows (the
        #     other two backends bypass it). y_true = 1 iff the
        #     predicted model resolves (via choose_final_route's
        #     api_model) to a string containing
        #     expected_model_or_agent_substring.
        # --------------------------------------------------------------

        raw_text = pd.Series([prompt])

        # Task type.
        try:
            t_label, t_prob, _ = _stage_predict_proba(
                prompt, raw_text, artifacts["task_type_classifier"], extractor
            )
        except Exception:  # noqa: BLE001
            t_label, t_prob = "unknown", 0.0
        per_stage_records["task_type_classifier"]["y_label"].append(t_label)
        per_stage_records["task_type_classifier"]["y_prob_max"].append(t_prob)
        # y_true: cascade outcome must agree with predicted task label.
        # We approximate "correct" as: the actual backend matches the
        # expected backend (i.e., the cascade as a whole produced the
        # right answer). This is the same proxy used by all 3 stages
        # below — per-stage labels are a proxy for "did this stage
        # contribute to a correct decision".
        per_stage_records["task_type_classifier"]["y_true_binary"].append(
            int(backend_match)
        )
        per_stage_records["task_type_classifier"]["y_pred"].append(t_label)

        # Agentic intent.
        try:
            a_label, a_prob, _ = _stage_predict_proba(
                prompt, raw_text, artifacts["agentic_intent_classifier"], extractor
            )
        except Exception:  # noqa: BLE001
            a_label, a_prob = "conversational", 0.0
        per_stage_records["agentic_intent_classifier"]["y_label"].append(a_label)
        per_stage_records["agentic_intent_classifier"]["y_prob_max"].append(a_prob)
        per_stage_records["agentic_intent_classifier"]["y_true_binary"].append(
            int(backend_match)
        )
        per_stage_records["agentic_intent_classifier"]["y_pred"].append(a_label)

        # Model router (only meaningful on openrouter rows).
        try:
            router_text = build_router_text_input_single(
                prompt=prompt,
                question_type=t_label,
                keyword_question_type="unknown",
            )
            r_label, r_prob, _ = _stage_predict_proba(
                prompt,
                router_text,
                artifacts["model_router"],
                extractor,
                extra_values={"question_type_confidence": float(t_prob)},
            )
        except Exception:  # noqa: BLE001
            r_label, r_prob = "OTHER", 0.0
        per_stage_records["model_router"]["y_label"].append(r_label)
        per_stage_records["model_router"]["y_prob_max"].append(r_prob)
        per_stage_records["model_router"]["y_pred"].append(r_label)
        per_stage_records["model_router"]["y_true_binary"].append(
            int(backend_match and model_substring_match)
            if expected_backend == "openrouter"
            else int(backend_match)
        )

    rows_df = pd.DataFrame(rows_out)

    # ------------------------------------------------------------------
    # (a) backend_accuracy.csv
    # ------------------------------------------------------------------

    per_backend_acc_rows: list[dict] = []
    for backend in BACKENDS:
        mask = rows_df["expected_backend"] == backend
        n_expected = int(mask.sum())
        if n_expected == 0:
            per_backend_acc_rows.append(
                {"backend": backend, "n_expected": 0, "n_actual": 0, "accuracy": float("nan")}
            )
            continue
        sub = rows_df[mask]
        n_correct = int(sub["backend_match"].sum())
        n_actual = int((rows_df["actual_backend"] == backend).sum())
        per_backend_acc_rows.append(
            {
                "backend": backend,
                "n_expected": n_expected,
                "n_actual": n_actual,
                "accuracy": float(n_correct) / float(n_expected),
            }
        )

    overall_accuracy = float(accuracy_score(
        rows_df["expected_backend"].tolist(),
        rows_df["actual_backend"].tolist(),
    ))
    per_backend_acc_rows.append(
        {
            "backend": "OVERALL",
            "n_expected": int(len(rows_df)),
            "n_actual": int(len(rows_df)),
            "accuracy": overall_accuracy,
        }
    )

    backend_accuracy_df = pd.DataFrame(per_backend_acc_rows)
    backend_accuracy_path = os.path.join(output_dir, "backend_accuracy.csv")
    backend_accuracy_df.to_csv(backend_accuracy_path, index=False)
    print(f"Saved backend accuracy to: {backend_accuracy_path}")

    # ------------------------------------------------------------------
    # (b) per_backend_pr.csv
    # ------------------------------------------------------------------

    labels_for_pr = list(BACKENDS)
    p, r, f1, support = precision_recall_fscore_support(
        rows_df["expected_backend"].tolist(),
        rows_df["actual_backend"].tolist(),
        labels=labels_for_pr,
        zero_division=0,
    )
    per_backend_pr_df = pd.DataFrame(
        {
            "backend": labels_for_pr,
            "precision": p,
            "recall": r,
            "f1": f1,
            "support": support,
        }
    )
    per_backend_pr_path = os.path.join(output_dir, "per_backend_pr.csv")
    per_backend_pr_df.to_csv(per_backend_pr_path, index=False)
    print(f"Saved per-backend P/R to: {per_backend_pr_path}")

    # ------------------------------------------------------------------
    # (c) confusion_matrix.csv + (d) confusion_matrix.png
    # ------------------------------------------------------------------

    cm_labels = list(BACKENDS)
    cm = confusion_matrix(
        rows_df["expected_backend"].tolist(),
        rows_df["actual_backend"].tolist(),
        labels=cm_labels,
    )
    cm_df = pd.DataFrame(cm, index=cm_labels, columns=cm_labels)
    cm_df.index.name = "expected"
    cm_df.columns.name = "actual"
    cm_path = os.path.join(output_dir, "confusion_matrix.csv")
    cm_df.to_csv(cm_path)
    print(f"Saved confusion matrix to: {cm_path}")

    cm_png_path = os.path.join(output_dir, "confusion_matrix.png")
    plot_confusion_matrix_chart(cm, cm_labels, cm_png_path)

    # ------------------------------------------------------------------
    # (e) ece_per_stage.csv + (g) reliability_diagram_<stage>.png
    # ------------------------------------------------------------------

    ece_rows: list[dict] = []
    for stage_name, records in per_stage_records.items():
        y_true_binary = np.array(records["y_true_binary"])
        y_prob_max = np.array(records["y_prob_max"])
        ece = expected_calibration_error(y_true_binary, y_prob_max)
        ece_rows.append({"stage": stage_name, "ece": ece, "n": int(len(y_true_binary))})

        reliability_path = os.path.join(
            output_dir, f"reliability_diagram_{stage_name}.png"
        )
        plot_reliability_diagram(y_true_binary, y_prob_max, stage_name, reliability_path)

    ece_df = pd.DataFrame(ece_rows)
    ece_path = os.path.join(output_dir, "ece_per_stage.csv")
    ece_df.to_csv(ece_path, index=False)
    print(f"Saved per-stage ECE to: {ece_path}")

    # ------------------------------------------------------------------
    # (f) low_confidence_rate.txt
    # ------------------------------------------------------------------

    n_fallback_actual = int(rows_df["is_fallback_actual"].sum())
    low_conf_rate = float(n_fallback_actual) / float(len(rows_df))
    low_conf_path = os.path.join(output_dir, "low_confidence_rate.txt")
    with open(low_conf_path, "w", encoding="utf-8") as fh:
        fh.write(f"low_confidence_rate={low_conf_rate:.6f}\n")
    print(f"Saved low_confidence_rate to: {low_conf_path}")

    # ------------------------------------------------------------------
    # fallback_recall.txt — WR-04 fix.
    #
    # Without this metric, D-09 / D-12 fallback fidelity was unmeasured by
    # any emitted file. The evaluator computed is_fallback_actual but
    # never compared it against is_fallback_expected: a canary row
    # authored to verify the fallback path fires would be silently
    # counted as a backend match if decide() returned the OpenRouter
    # backend with a clean rationale (no fallback suffix).
    #
    # Recall = (rows with is_fallback_expected==True AND
    #           is_fallback_actual==True) / (rows with
    #           is_fallback_expected==True). Written as a single float on
    #   a single line, e.g. "fallback_recall=0.833333\n".
    # If no rows are flagged as is_fallback_expected, we write NaN to
    # signal "metric undefined for this canary" rather than spurious 0.0.
    # ------------------------------------------------------------------

    expected_mask = rows_df["is_fallback_expected"].astype(bool)
    n_expected_fb = int(expected_mask.sum())
    if n_expected_fb == 0:
        fallback_recall = float("nan")
    else:
        n_both = int(
            (expected_mask & rows_df["is_fallback_actual"].astype(bool)).sum()
        )
        fallback_recall = float(n_both) / float(n_expected_fb)

    fallback_recall_path = os.path.join(output_dir, "fallback_recall.txt")
    with open(fallback_recall_path, "w", encoding="utf-8") as fh:
        fh.write(f"fallback_recall={fallback_recall:.6f}\n")
    print(f"Saved fallback_recall to: {fallback_recall_path}")

    # ------------------------------------------------------------------
    # Per-row detail CSV (useful for debugging individual canary rows;
    # NOT counted in the 9-file D-16 list but a useful side-output).
    # ------------------------------------------------------------------

    per_row_path = os.path.join(output_dir, "per_row_results.csv")
    rows_df.to_csv(per_row_path, index=False)
    print(f"Saved per-row results to: {per_row_path}")

    # ------------------------------------------------------------------
    # Stdout summary (CLAUDE.md "Logging": print f-string metrics).
    # ------------------------------------------------------------------

    print()
    print("=" * 64)
    print("Routing-canary evaluation summary")
    print("=" * 64)
    print(f"Total canary rows:    {len(rows_df)}")
    print(f"Overall backend accuracy: {overall_accuracy:.4f}")
    for row in per_backend_acc_rows:
        if row["backend"] != "OVERALL":
            print(
                f"  {row['backend']:<14} n={row['n_expected']:>2} "
                f"accuracy={row['accuracy']:.4f}"
            )
    print()
    print("Per-stage ECE (target <= {:.2f}):".format(ECE_THRESHOLD))
    for row in ece_rows:
        flag = " (>= threshold!)" if row["ece"] > ECE_THRESHOLD else ""
        print(f"  {row['stage']:<32} ece={row['ece']:.4f}{flag}")
    print()
    print(f"low_confidence_rate = {low_conf_rate:.4f} "
          f"({n_fallback_actual}/{len(rows_df)} rows hit the fallback rationale)")
    if n_expected_fb == 0:
        print(
            "fallback_recall = NaN (no rows flagged is_fallback_expected=True; "
            "metric undefined for this canary)"
        )
    else:
        print(
            f"fallback_recall    = {fallback_recall:.4f} "
            f"({int((expected_mask & rows_df['is_fallback_actual'].astype(bool)).sum())}"
            f"/{n_expected_fb} expected-fallback rows hit the fallback rationale)"
        )
    if rows_df["tier_tiebreaker_fired"].sum() > 0:
        print(f"tier_tiebreaker fired on {int(rows_df['tier_tiebreaker_fired'].sum())} rows")
    print("=" * 64)

    return {
        "backend_accuracy": overall_accuracy,
        "per_stage_ece": {row["stage"]: row["ece"] for row in ece_rows},
        "low_confidence_rate": low_conf_rate,
        "fallback_recall": fallback_recall,
        "n_rows": int(len(rows_df)),
    }


# ----------------------------------------------------------------------
# `--check` evaluation — applied to the metrics dict from `run`.
# ----------------------------------------------------------------------


def evaluate_check(metrics: dict) -> tuple[bool, list[str]]:
    """Apply the --check thresholds. Returns (passed, list_of_failures)."""
    failures: list[str] = []

    if metrics["backend_accuracy"] < BACKEND_ACCURACY_THRESHOLD:
        failures.append(
            f"backend_accuracy={metrics['backend_accuracy']:.4f} < "
            f"threshold={BACKEND_ACCURACY_THRESHOLD:.4f}"
        )

    for stage, ece in metrics["per_stage_ece"].items():
        if ece > ECE_THRESHOLD:
            failures.append(
                f"{stage} ece={ece:.4f} > threshold={ECE_THRESHOLD:.4f}"
            )

    return (len(failures) == 0, failures)


# ----------------------------------------------------------------------
# CLI entry point
# ----------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    """`python -m src.evaluation.evaluate_routing [--check]` — exit code per --check."""
    parser = argparse.ArgumentParser(
        description=(
            "Run the routing-canary evaluator: score decide() against "
            "data_processed/routing_decision_eval.csv and emit the D-16 "
            "metric stack to evaluation/routing/."
        ),
    )
    parser.add_argument(
        "--canary-input",
        type=str,
        default=CANARY_CSV,
        help=f"Path to the canary CSV (default: {CANARY_CSV}).",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=ROUTING_EVAL_DIR,
        help=f"Directory for output files (default: {ROUTING_EVAL_DIR}).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Exit 0 if backend_accuracy >= "
            f"{BACKEND_ACCURACY_THRESHOLD:.2f} AND every per-stage ECE "
            f"<= {ECE_THRESHOLD:.2f}; else exit 1 with failures logged. "
            "Used by CI in .github/workflows/ci.yml."
        ),
    )
    parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=1,
        help="Verbosity (-v for INFO, -vv for DEBUG).",
    )
    args = parser.parse_args(argv)

    log_level = logging.WARNING
    if args.verbose >= 2:
        log_level = logging.DEBUG
    elif args.verbose >= 1:
        log_level = logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        metrics = run(canary_path=args.canary_input, output_dir=args.output_dir)
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return 2

    if args.check:
        passed, failures = evaluate_check(metrics)
        if passed:
            print(
                "\nCheck PASSED: backend_accuracy "
                f"{metrics['backend_accuracy']:.4f} >= "
                f"{BACKEND_ACCURACY_THRESHOLD:.2f} AND all per-stage ECE "
                f"<= {ECE_THRESHOLD:.2f}."
            )
            return 0
        else:
            print("\nCheck FAILED:")
            for f in failures:
                print(f"  - {f}")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

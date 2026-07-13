"""
STEP 4.1 - Evidence slice: is the general/knowledge/factual label overlap the
real routing weakness? (Epic 4, evidence-gated — NO retrain, NO label merge.)

Runs the saved task_type_classifier over a held-out slice, isolates the
`general`/`knowledge`/`factual` trio, and reports:
  - a trio confusion matrix (trio x trio+"other") + per-class precision/recall/F1,
  - a single `trio_confusion_rate` (share of true-trio rows the classifier assigns
    to a *different* trio label) — THE HEADLINE NUMBER,
  - a misroute-contribution estimate (how often swapping the true task_type token
    for the predicted one flips the model_router top-1 pick — the AD-9 lever),
  - a go/no-go signal vs a *provisional* --threshold.

Report-first by design: the point of this story is to PRODUCE the confusion
number so a human sets the go/no-go threshold from evidence, not a hunch. The
default threshold is provisional. A no-go halts Epic 4 (no AD-9 retrain tax paid).

Caveat baked into the report: the task-type labels are *weak* (dataset-derived,
`build_question_type.py`), so this measures "does the classifier reproduce the
weak labels", not "are these labels the semantically wrong cut". Treat the
number as strong-suggestive, not proof.

Run from the repo root:

    python -m src.evaluation.evaluate_task_type_confusion_slice \
        --input data_processed/classifier_training_with_types.csv \
        --threshold 0.15 --check
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")  # no display — offline eval (D-16 convention)
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.sparse import csr_matrix, hstack  # noqa: E402
from sklearn.metrics import precision_recall_fscore_support  # noqa: E402
from sklearn.model_selection import train_test_split  # noqa: E402

from src.feature_extraction.text_inputs import build_router_text_input_single  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = PROJECT_ROOT / "data_processed" / "classifier_training_with_types.csv"
DEFAULT_CLASSIFIER = PROJECT_ROOT / "models" / "task_type_classifier.joblib"
DEFAULT_MODEL_ROUTER = PROJECT_ROOT / "models" / "model_router.joblib"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "evaluation" / "task_type_slice"

TRIO = ("factual", "general", "knowledge")  # the overlapping labels under investigation
OTHER = "other"
DEFAULT_THRESHOLD = 0.15  # PROVISIONAL — set the real go/no-go cutoff from the measured rate
MIN_TRIO_SUPPORT = 20     # below this many true-trio rows, the rate is too noisy to decide on
LABEL_COLUMN = "question_type"
TEXT_COLUMN = "origin_query"
NA_LABEL = "general"      # training fills NaN question_type with this before splitting — mirror it

# Exit codes: the go/no-go decision is encoded so Epic 4.2 can gate on it.
EXIT_GO = 0            # merge justified — confusion >= threshold
EXIT_NOGO = 1          # merge NOT justified — halt the epic, no retrain
EXIT_UNAVAILABLE = 2   # evidence could not be produced (missing/LFS-stub data)

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Pure metric functions (data-independent, unit-testable)
# ----------------------------------------------------------------------
def trio_confusion_rate(y_true, y_pred, trio: tuple[str, ...] = TRIO) -> float:
    """Share of true-trio rows the classifier assigns to a *different* trio label.

    Only trio->trio mislabels count (the mutual overlap the merge would fix);
    a trio row escaping to a non-trio label is reported in the matrix but is not
    'trio confusion'. Returns 0.0 when there are no true-trio rows.
    """
    y_true = np.asarray(y_true, dtype=object)
    y_pred = np.asarray(y_pred, dtype=object)
    trio_set = set(trio)
    true_trio = np.array([t in trio_set for t in y_true])
    n = int(true_trio.sum())
    if n == 0:
        return 0.0
    confused = np.array([
        (yp in trio_set and yp != yt)
        for yt, yp in zip(y_true[true_trio], y_pred[true_trio])
    ])
    return float(confused.sum()) / n


def trio_escape_rate(y_true, y_pred, trio: tuple[str, ...] = TRIO) -> float:
    """Share of true-trio rows the classifier sends OUT of the trio (to a non-trio
    label). Reported alongside trio_confusion_rate so a low confusion rate can't be
    misread as 'trio is fine' when the trio is actually escaping to `other`. Merging
    the trio labels does NOT fix escapes — that's why this is a separate signal."""
    y_true = np.asarray(y_true, dtype=object)
    y_pred = np.asarray(y_pred, dtype=object)
    trio_set = set(trio)
    true_trio = np.array([t in trio_set for t in y_true])
    n = int(true_trio.sum())
    if n == 0:
        return 0.0
    escaped = np.array([yp not in trio_set for yp in y_pred[true_trio]])
    return float(escaped.sum()) / n


def trio_support(y_true, trio: tuple[str, ...] = TRIO) -> int:
    trio_set = set(trio)
    return int(sum(1 for t in np.asarray(y_true, dtype=object) if t in trio_set))


def trio_confusion_matrix(y_true, y_pred, trio: tuple[str, ...] = TRIO) -> pd.DataFrame:
    """Rows = true trio labels, cols = trio labels + 'other' (escaped). Counts."""
    y_true = np.asarray(y_true, dtype=object)
    y_pred = np.asarray(y_pred, dtype=object)
    trio_set = set(trio)
    cols = list(trio) + [OTHER]
    mat = pd.DataFrame(0, index=list(trio), columns=cols, dtype=int)
    for yt, yp in zip(y_true, y_pred):
        if yt in trio_set:
            bucket = yp if yp in trio_set else OTHER
            mat.loc[yt, bucket] += 1
    return mat


def per_class_metrics(y_true, y_pred, trio: tuple[str, ...] = TRIO) -> pd.DataFrame:
    """precision/recall/F1/support for each trio label over the whole slice."""
    p, r, f1, support = precision_recall_fscore_support(
        y_true, y_pred, labels=list(trio), zero_division=0,
    )
    return pd.DataFrame({
        "label": list(trio), "precision": p, "recall": r, "f1": f1, "support": support,
    })


def go_no_go(rate: float, threshold: float) -> bool:
    """GO (merge justified) iff the measured trio confusion *exceeds* the threshold (AC #3)."""
    return rate > threshold


def _is_lfs_pointer(path: Path) -> bool:
    """A git-LFS pointer stub begins with the spec version line."""
    try:
        with open(path, "rb") as fh:
            return fh.read(64).startswith(b"version https://git-lfs.github.com/spec/")
    except OSError:
        return False


# ----------------------------------------------------------------------
# Prediction (reads the precomputed numeric columns inline in the CSV — no
# PromptFeatureExtractor/NLTK needed; each bundle carries its own feature_columns)
# ----------------------------------------------------------------------
def _feature_matrix(bundle: dict, texts: pd.Series, df: pd.DataFrame):
    text_x = bundle["vectorizer"].transform(texts)
    numeric = df.reindex(columns=bundle["feature_columns"], fill_value=0).fillna(0)
    numeric_x = csr_matrix(bundle["scaler"].transform(numeric))
    return hstack([text_x, numeric_x])


def predict_labels(bundle: dict, df: pd.DataFrame) -> np.ndarray:
    """Predict task-type label strings for each row using the saved classifier."""
    texts = df[TEXT_COLUMN].fillna("").astype(str)
    pred = bundle["model"].predict(_feature_matrix(bundle, texts, df))
    return bundle["label_encoder"].inverse_transform(pred)


def _heldout_slice(df: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    """Return (slice, held_out). `held_out=True` is the 20% the saved classifier did
    NOT fit — reproduced with the same seed AND the same NaN handling the training
    script uses (`fillna("general")`, train_task_classifier_robust.py:409) so the
    partition matches. `held_out=False` means the data was too thin to stratify and we
    fell back to scoring the FULL frame (resubstitution — confusion is understated).
    """
    y = df[LABEL_COLUMN].fillna(NA_LABEL).astype(str)
    try:
        _, test_df = train_test_split(df, test_size=0.2, random_state=42, stratify=y)
        return test_df, True
    except ValueError:
        logger.warning(
            "RESUBSTITUTION: too few rows per label to stratify a held-out split — scoring the "
            "FULL training set. Confusion is understated; do not treat this as held-out evidence."
        )
        return df, False


def misroute_flips(model_router_bundle, test_df, y_true, y_pred,
                   trio: tuple[str, ...] = TRIO) -> dict | None:
    """For each misclassified true-trio row, does swapping the true task_type token
    for the predicted one flip the model_router top-1 pick? Returns counts, or None
    when no model_router is available (confusion rate alone drives the decision)."""
    if model_router_bundle is None:
        return None
    trio_set = set(trio)
    y_true = np.asarray(y_true, dtype=object)
    y_pred = np.asarray(y_pred, dtype=object)
    rows, true_labels, pred_labels = [], [], []
    for (_, row), yt, yp in zip(test_df.iterrows(), y_true, y_pred):
        if yt in trio_set and yp != yt:
            rows.append(row)
            true_labels.append(yt)
            pred_labels.append(yp)
    n = len(rows)
    if n == 0:
        return {"misroute_flip_count": 0, "misroute_flip_rate": 0.0, "n_misclassified_trio": 0}

    sub = pd.DataFrame(rows)
    prompts = sub[TEXT_COLUMN].fillna("").astype(str).tolist()

    def _router_top1(labels: list[str]) -> np.ndarray:
        texts = pd.Series([
            build_router_text_input_single(p, q).iloc[0] for p, q in zip(prompts, labels)
        ])
        return model_router_bundle["model"].predict(_feature_matrix(model_router_bundle, texts, sub))

    flips = int((_router_top1(true_labels) != _router_top1(pred_labels)).sum())
    return {"misroute_flip_count": flips, "misroute_flip_rate": flips / n, "n_misclassified_trio": n}


# ----------------------------------------------------------------------
# Orchestration
# ----------------------------------------------------------------------
_WEAK_LABEL_CAVEAT = (
    "CAVEAT: task-type labels are weak (dataset-derived via build_question_type.py). "
    "This measures whether the classifier reproduces the weak labels, not whether the "
    "labels are the semantically wrong cut. Strong-suggestive, not proof."
)


def run(df: pd.DataFrame, classifier_bundle: dict, *, threshold: float,
        trio: tuple[str, ...] = TRIO, model_router_bundle=None,
        output_dir: Path | None = None, date: str = "") -> dict:
    """Score the held-out slice, compute the trio evidence, emit a go/no-go dict.
    Writes the evidence report when output_dir is given."""
    test_df, held_out = _heldout_slice(df)
    test_df = test_df.reset_index(drop=True)
    y_true = test_df[LABEL_COLUMN].fillna(NA_LABEL).astype(str).to_numpy()
    y_pred = predict_labels(classifier_bundle, test_df)

    rate = trio_confusion_rate(y_true, y_pred, trio)
    escape = trio_escape_rate(y_true, y_pred, trio)
    support = trio_support(y_true, trio)
    matrix = trio_confusion_matrix(y_true, y_pred, trio)
    metrics = per_class_metrics(y_true, y_pred, trio)
    flips = misroute_flips(model_router_bundle, test_df, y_true, y_pred, trio)
    go = go_no_go(rate, threshold)

    if support < MIN_TRIO_SUPPORT:
        logger.warning("Only %d true-trio rows (< %d) — the confusion rate is noisy; treat the "
                       "decision as low-confidence.", support, MIN_TRIO_SUPPORT)

    result = {
        "trio_confusion_rate": rate,
        "trio_escape_rate": escape,
        "trio_support": support,
        "sufficient_support": support >= MIN_TRIO_SUPPORT,
        "held_out": held_out,
        "threshold": threshold,
        "go": go,
        "decision": "GO" if go else "NO-GO",
        "n_test": int(len(test_df)),
        "misroute_flip_rate": None if flips is None else flips["misroute_flip_rate"],
        "misroute_flip_count": None if flips is None else flips["misroute_flip_count"],
        "per_class": metrics.to_dict(orient="records"),
    }

    if output_dir is not None:
        _write_report(output_dir, matrix, metrics, result, date)
    return result


def _write_report(output_dir: Path, matrix: pd.DataFrame, metrics: pd.DataFrame,
                  result: dict, date: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    matrix.to_csv(output_dir / "confusion_matrix.csv")
    metrics.to_csv(output_dir / "metrics_per_class.csv", index=False)

    fig, ax = plt.subplots(figsize=(6, 5))
    im = ax.imshow(matrix.to_numpy(), cmap="Blues")
    ax.set_xticks(range(len(matrix.columns)), labels=matrix.columns, rotation=45, ha="right")
    ax.set_yticks(range(len(matrix.index)), labels=matrix.index)
    ax.set_xlabel("predicted"); ax.set_ylabel("true (trio)")
    ax.set_title("general/knowledge/factual confusion")
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            ax.text(j, i, int(matrix.iat[i, j]), ha="center", va="center", fontsize=9)
    fig.colorbar(im, ax=ax)
    fig.tight_layout()
    fig.savefig(output_dir / "confusion_matrix.png", dpi=300)
    plt.close(fig)

    flip = ("n/a (model_router unavailable)" if result["misroute_flip_rate"] is None
            else f"{result['misroute_flip_rate']:.3f} ({result['misroute_flip_count']} flips)")
    scored = "held-out 20%" if result["held_out"] else "RESUBSTITUTION (full training set — confusion understated)"
    support_note = "" if result["sufficient_support"] else (
        f"  ⚠ LOW SUPPORT: only {result['trio_support']} true-trio rows (< {MIN_TRIO_SUPPORT}) — low-confidence decision.")
    per_class_lines = [
        f"  - {row['label']}: precision={row['precision']:.3f} recall={row['recall']:.3f} "
        f"f1={row['f1']:.3f} support={int(row['support'])}"
        for row in metrics.to_dict(orient="records")
    ]
    lines = [
        f"# Story 4.1 evidence — general/knowledge/factual confusion ({date})".rstrip(),
        "",
        f"**Decision: {result['decision']}**  (trio_confusion_rate="
        f"{result['trio_confusion_rate']:.4f} vs threshold={result['threshold']:.4f}, PROVISIONAL){support_note}",
        "",
        f"- trio confusion rate (headline, trio->trio only): **{result['trio_confusion_rate']:.4f}**",
        f"- trio escape rate (trio->other; NOT fixed by merging): {result['trio_escape_rate']:.4f}",
        f"- true-trio rows / scored on: {result['trio_support']} / {result['n_test']} ({scored})",
        f"- misroute-flip rate (AD-9 token swap): {flip}",
        "",
        "## per-class (trio)",
        *per_class_lines,
        "",
        "GO = merge justified (Epic 4.2 may proceed). NO-GO = halt Epic 4, keep the labels, no AD-9 retrain.",
        "",
        "NOTE (misroute-flip): a *directional* token-sensitivity proxy — the model_router's "
        "router-native numerics (question_type_confidence, best_model_tier) are absent from this CSV "
        "and zero-filled, so the absolute flip rate is not calibrated; it isolates the task_type token only.",
        "",
        _WEAK_LABEL_CAVEAT,
    ]
    (output_dir / "go_no_go_decision.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def _setup_logging(verbosity: int) -> None:
    level = logging.WARNING
    if verbosity >= 2:
        level = logging.DEBUG
    elif verbosity >= 1:
        level = logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%H:%M:%S")


def _unavailable(output_dir: Path, reason: str) -> int:
    logger.error("Evidence unavailable: %s", reason)
    logger.error("Materialize the data first: `git lfs pull` (or pass --input to a real CSV).")
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "go_no_go_decision.md").write_text(
            f"# Story 4.1 evidence\n\nEvidence unavailable — no decision.\n\n{reason}\n\n"
            f"Run `git lfs pull` to materialize the labelled dataset, then re-run.\n",
            encoding="utf-8",
        )
    except OSError:
        pass
    return EXIT_UNAVAILABLE


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", "-i", type=Path, default=DEFAULT_INPUT,
                        help=f"Labelled CSV (question_type + origin_query + numerics). Default: {DEFAULT_INPUT}.")
    parser.add_argument("--classifier", type=Path, default=DEFAULT_CLASSIFIER,
                        help=f"task_type_classifier bundle. Default: {DEFAULT_CLASSIFIER}.")
    parser.add_argument("--model-router", type=Path, default=DEFAULT_MODEL_ROUTER,
                        help="model_router bundle for the misroute-flip estimate (optional).")
    parser.add_argument("--output-dir", "-o", type=Path, default=DEFAULT_OUTPUT_DIR,
                        help=f"Evidence report dir. Default: {DEFAULT_OUTPUT_DIR}.")
    parser.add_argument("--threshold", "-t", type=float, default=DEFAULT_THRESHOLD,
                        help=f"PROVISIONAL go/no-go cutoff on trio_confusion_rate. Default: {DEFAULT_THRESHOLD}.")
    parser.add_argument("--date", type=str, default="", help="Stamp for the report (repo scripts inject the date).")
    parser.add_argument("--check", action="store_true", help="Exit 0=GO / 1=NO-GO for gating; else always 0.")
    parser.add_argument("-v", "--verbose", action="count", default=1, help="-v info, -vv debug.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    _setup_logging(args.verbose)

    # AC #4 — evidence unavailable (missing or git-LFS stub) is a clean exit-2, not a crash.
    if not args.input.exists() or _is_lfs_pointer(args.input):
        return _unavailable(args.output_dir, f"labelled dataset not materialized: {args.input}")
    if not args.classifier.exists() or _is_lfs_pointer(args.classifier):
        return _unavailable(args.output_dir, f"classifier bundle missing: {args.classifier}")

    try:  # a non-stub but empty/truncated CSV must be a clean exit-2, not a traceback
        df = pd.read_csv(args.input)
    except (pd.errors.EmptyDataError, pd.errors.ParserError, OSError, UnicodeDecodeError) as exc:
        return _unavailable(args.output_dir, f"input CSV unreadable ({type(exc).__name__}): {args.input}")
    missing = [c for c in (TEXT_COLUMN, LABEL_COLUMN) if c not in df.columns]
    if missing:
        return _unavailable(args.output_dir, f"input CSV missing required column(s): {', '.join(missing)}")

    try:
        classifier_bundle = joblib.load(args.classifier)
    except Exception as exc:  # corrupt/truncated bundle
        return _unavailable(args.output_dir, f"classifier bundle unloadable: {args.classifier} ({exc})")

    # Guard: the CSV must carry the numeric columns the classifier trained on, else
    # they silently zero-fill and predictions are bogus (no error otherwise).
    missing_feats = [c for c in classifier_bundle.get("feature_columns", []) if c not in df.columns]
    if missing_feats:
        return _unavailable(
            args.output_dir,
            f"input CSV missing {len(missing_feats)} classifier feature column(s), "
            f"e.g. {missing_feats[:5]} — wrong CSV? Predictions would be silently wrong.",
        )

    model_router_bundle = None
    if args.model_router.exists() and not _is_lfs_pointer(args.model_router):
        try:
            model_router_bundle = joblib.load(args.model_router)
        except Exception as exc:
            logger.warning("model_router present but unloadable (%s) — skipping misroute-flip estimate.", exc)
    else:
        logger.info("model_router not available — reporting confusion rate without the misroute-flip estimate.")

    result = run(df, classifier_bundle, threshold=args.threshold,
                 model_router_bundle=model_router_bundle, output_dir=args.output_dir, date=args.date)

    # Report-first: the measured rate + decision are the headline.
    scored = "held-out" if result["held_out"] else "RESUBSTITUTION (understated)"
    print(f"\nTRIO CONFUSION RATE: {result['trio_confusion_rate']:.4f}  "
          f"-> {result['decision']} (threshold={result['threshold']:.4f}, PROVISIONAL)")
    print(f"  escape-to-other: {result['trio_escape_rate']:.4f}  |  trio rows: {result['trio_support']} "
          f"({scored})  |  misroute-flip rate: {result['misroute_flip_rate']}")
    if not result["sufficient_support"]:
        print(f"  ⚠ LOW SUPPORT (< {MIN_TRIO_SUPPORT} trio rows) — low-confidence decision.")
    print(f"  {_WEAK_LABEL_CAVEAT}")
    print(f"  evidence written to: {args.output_dir}")

    if args.check:
        return EXIT_GO if result["go"] else EXIT_NOGO
    return EXIT_GO


if __name__ == "__main__":
    sys.exit(main())

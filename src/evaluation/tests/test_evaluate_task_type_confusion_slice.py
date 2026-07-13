"""Story 4.1 — task-type confusion-slice tests (data-independent).

Pure metric functions over synthetic arrays + end-to-end main() with a tiny
fitted classifier bundle in tmp_path. No live models/, no benchmark CSV, no LFS.
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix, hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion
from sklearn.preprocessing import LabelEncoder, StandardScaler

from src.evaluation import evaluate_task_type_confusion_slice as slice_mod

FEATURE_COLS = ["char_count", "word_count"]


def _synthetic_df() -> pd.DataFrame:
    rows = []
    labels = ["factual", "general", "knowledge", "coding", "math"]
    for i in range(20):
        label = labels[i % len(labels)]
        text = f"{label} sample question number {i} about various topics"
        rows.append({"origin_query": text, "question_type": label,
                     "char_count": len(text), "word_count": len(text.split())})
    return pd.DataFrame(rows)


def _confused_df() -> pd.DataFrame:
    """Trio labels share identical text+numerics so the classifier CANNOT separate them
    -> genuine trio->trio confusion. A singleton non-trio class forces the held-out split
    to fall back to full-frame scoring, making the measured rate deterministic."""
    rows = []
    for i in range(18):  # 6 each of factual/general/knowledge, identical features
        label = slice_mod.TRIO[i % 3]
        rows.append({"origin_query": "ambiguous overlapping trivia knowledge fact query",
                     "question_type": label, "char_count": 45, "word_count": 6})
    rows.append({"origin_query": "write a poem about the sea", "question_type": "writing",
                 "char_count": 26, "word_count": 6})  # singleton -> stratify fails -> resubstitution
    return pd.DataFrame(rows)


def _ample_df() -> pd.DataFrame:
    """Enough rows per class that the held-out split actually stratifies (held_out=True)."""
    rows = []
    labels = ["factual", "general", "knowledge", "coding", "math"]
    for i in range(50):
        label = labels[i % len(labels)]
        text = f"{label} distinct sample text number {i} discussing its topic clearly"
        rows.append({"origin_query": text, "question_type": label,
                     "char_count": len(text), "word_count": len(text.split())})
    return pd.DataFrame(rows)


def _make_bundle(df: pd.DataFrame, y_col: str) -> dict:
    """Fit a tiny classifier bundle with the exact production pipeline shape."""
    vectorizer = FeatureUnion([
        ("word", TfidfVectorizer(ngram_range=(1, 2), min_df=1)),
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 4), min_df=1)),
    ])
    text_x = vectorizer.fit_transform(df["origin_query"])
    scaler = StandardScaler()
    num_x = csr_matrix(scaler.fit_transform(df[FEATURE_COLS]))
    X = hstack([text_x, num_x])
    le = LabelEncoder()
    y = le.fit_transform(df[y_col].astype(str))
    model = LogisticRegression(max_iter=1000).fit(X, y)
    return {"model": model, "vectorizer": vectorizer, "scaler": scaler,
            "label_encoder": le, "feature_columns": FEATURE_COLS}


# ----------------------------------------------------------------------
# Pure metric functions
# ----------------------------------------------------------------------
def test_trio_confusion_rate_counts_only_trio_to_trio_mislabels() -> None:
    y_true = ["factual", "factual", "knowledge", "general", "coding"]
    y_pred = ["knowledge", "factual", "factual", "general", "coding"]
    # true-trio rows = 4 (coding excluded); confused trio->trio = row0, row2 = 2/4
    assert slice_mod.trio_confusion_rate(y_true, y_pred) == 0.5


def test_trio_confusion_rate_zero_when_no_trio_rows() -> None:
    assert slice_mod.trio_confusion_rate(["coding", "math"], ["coding", "writing"]) == 0.0


def test_trio_confusion_matrix_buckets_escapes_to_other() -> None:
    y_true = ["factual", "factual", "knowledge"]
    y_pred = ["knowledge", "coding", "knowledge"]  # coding -> 'other'
    m = slice_mod.trio_confusion_matrix(y_true, y_pred)
    assert m.loc["factual", "knowledge"] == 1
    assert m.loc["factual", slice_mod.OTHER] == 1
    assert m.loc["knowledge", "knowledge"] == 1


def test_go_no_go_threshold() -> None:
    assert slice_mod.go_no_go(0.50, 0.15) is True
    assert slice_mod.go_no_go(0.10, 0.15) is False
    assert slice_mod.go_no_go(0.15, 0.15) is False  # boundary: strictly "exceeds" (>)


def test_trio_escape_rate() -> None:
    # true trio: factual, factual, knowledge; preds: coding(escape), factual(ok), general(trio)
    assert slice_mod.trio_escape_rate(["factual", "factual", "knowledge"],
                                      ["coding", "factual", "general"]) == 1 / 3


def test_is_lfs_pointer(tmp_path: Path) -> None:
    stub = tmp_path / "stub.csv"
    stub.write_text("version https://git-lfs.github.com/spec/v1\noid sha256:abc\n")
    real = tmp_path / "real.csv"
    real.write_text("origin_query,question_type\nhi,factual\n")
    assert slice_mod._is_lfs_pointer(stub) is True
    assert slice_mod._is_lfs_pointer(real) is False


def test_misroute_flips_none_without_router() -> None:
    assert slice_mod.misroute_flips(None, pd.DataFrame(), [], []) is None


# ----------------------------------------------------------------------
# run() + main()
# ----------------------------------------------------------------------
def test_run_returns_evidence_dict(tmp_path: Path) -> None:
    df = _synthetic_df()
    bundle = _make_bundle(df, "question_type")
    result = slice_mod.run(df, bundle, threshold=0.15, output_dir=tmp_path / "out", date="2026-07-13")
    assert set(result) >= {"trio_confusion_rate", "trio_escape_rate", "trio_support",
                           "held_out", "go", "decision", "n_test", "per_class"}
    assert 0.0 <= result["trio_confusion_rate"] <= 1.0
    md = (tmp_path / "out" / "go_no_go_decision.md").read_text()
    assert (tmp_path / "out" / "confusion_matrix.csv").exists()
    assert "CAVEAT" in md and "escape rate" in md and "per-class" in md  # honesty signals in the report


def test_run_measured_confusion_is_go_and_flags_resubstitution(tmp_path: Path) -> None:
    df = _confused_df()
    bundle = _make_bundle(df, "question_type")
    result = slice_mod.run(df, bundle, threshold=0.15)
    assert result["trio_confusion_rate"] > 0.15 and result["go"] is True  # measured, not threshold-forced
    assert result["held_out"] is False  # thin data -> resubstitution, honestly flagged


def test_run_clean_data_is_nogo(tmp_path: Path) -> None:
    df = _synthetic_df()
    result = slice_mod.run(df, _make_bundle(df, "question_type"), threshold=0.15)
    assert result["trio_confusion_rate"] <= 0.15 and result["go"] is False


def test_run_heldout_true_on_ample_data() -> None:
    df = _ample_df()
    result = slice_mod.run(df, _make_bundle(df, "question_type"), threshold=0.15)
    assert result["held_out"] is True  # enough rows per class to stratify a real held-out split


def _write_inputs(tmp_path: Path, df: pd.DataFrame):
    csv = tmp_path / "labelled.csv"
    df.to_csv(csv, index=False)
    clf = tmp_path / "task_type_classifier.joblib"
    joblib.dump(_make_bundle(df, "question_type"), clf)
    return csv, clf


def test_main_check_go_exit0(tmp_path: Path, capsys) -> None:
    csv, clf = _write_inputs(tmp_path, _confused_df())
    rc = slice_mod.main(["--input", str(csv), "--classifier", str(clf),
                         "--model-router", str(tmp_path / "none.joblib"),
                         "--output-dir", str(tmp_path / "out"), "--threshold", "0.15", "--check"])
    assert rc == slice_mod.EXIT_GO  # measured confusion clears 0.15
    assert "TRIO CONFUSION RATE" in capsys.readouterr().out


def test_main_check_nogo_exit1(tmp_path: Path) -> None:
    csv, clf = _write_inputs(tmp_path, _synthetic_df())
    rc = slice_mod.main(["--input", str(csv), "--classifier", str(clf),
                         "--model-router", str(tmp_path / "none.joblib"),
                         "--output-dir", str(tmp_path / "out"), "--threshold", "0.15", "--check"])
    assert rc == slice_mod.EXIT_NOGO  # clean data -> low confusion -> NO-GO


def test_main_lfs_stub_input_exit2(tmp_path: Path) -> None:
    stub = tmp_path / "labelled.csv"
    stub.write_text("version https://git-lfs.github.com/spec/v1\noid sha256:deadbeef\n")
    clf = tmp_path / "clf.joblib"
    joblib.dump(_make_bundle(_synthetic_df(), "question_type"), clf)
    rc = slice_mod.main(["--input", str(stub), "--classifier", str(clf),
                         "--output-dir", str(tmp_path / "out")])
    assert rc == slice_mod.EXIT_UNAVAILABLE
    assert "unavailable" in (tmp_path / "out" / "go_no_go_decision.md").read_text().lower()


def test_main_missing_column_exit2(tmp_path: Path) -> None:
    csv = tmp_path / "bad.csv"
    pd.DataFrame({"origin_query": ["hi"], "char_count": [2], "word_count": [1]}).to_csv(csv, index=False)
    clf = tmp_path / "clf.joblib"
    joblib.dump(_make_bundle(_synthetic_df(), "question_type"), clf)
    rc = slice_mod.main(["--input", str(csv), "--classifier", str(clf), "--output-dir", str(tmp_path / "out")])
    assert rc == slice_mod.EXIT_UNAVAILABLE  # no question_type column


def test_main_missing_feature_columns_exit2(tmp_path: Path) -> None:
    """CSV missing the classifier's numeric feature columns -> clean exit-2, not silent
    zero-fill + bogus predictions."""
    csv = tmp_path / "nofeat.csv"
    pd.DataFrame({"origin_query": ["a", "b"], "question_type": ["factual", "general"]}).to_csv(csv, index=False)
    clf = tmp_path / "clf.joblib"
    joblib.dump(_make_bundle(_synthetic_df(), "question_type"), clf)  # feature_columns = char_count, word_count
    rc = slice_mod.main(["--input", str(csv), "--classifier", str(clf), "--output-dir", str(tmp_path / "out")])
    assert rc == slice_mod.EXIT_UNAVAILABLE


def test_main_empty_csv_exit2(tmp_path: Path) -> None:
    csv = tmp_path / "empty.csv"
    csv.write_text("")  # 0-byte, non-stub -> pd.read_csv EmptyDataError must be caught
    clf = tmp_path / "clf.joblib"
    joblib.dump(_make_bundle(_synthetic_df(), "question_type"), clf)
    rc = slice_mod.main(["--input", str(csv), "--classifier", str(clf), "--output-dir", str(tmp_path / "out")])
    assert rc == slice_mod.EXIT_UNAVAILABLE


def test_main_missing_classifier_exit2(tmp_path: Path) -> None:
    csv, _ = _write_inputs(tmp_path, _synthetic_df())
    rc = slice_mod.main(["--input", str(csv), "--classifier", str(tmp_path / "nope.joblib"),
                         "--output-dir", str(tmp_path / "out")])
    assert rc == slice_mod.EXIT_UNAVAILABLE


def test_misroute_flips_with_router_reports_counts(tmp_path: Path) -> None:
    df = _synthetic_df().reset_index(drop=True)
    router = _make_bundle(df, "question_type")  # any label space; we only need top-1 predictions
    y_true = df["question_type"].to_numpy()
    # force some trio rows to be "misclassified" so the flip analysis has rows to consider
    y_pred = np.array(["knowledge" if t == "factual" else t for t in y_true], dtype=object)
    out = slice_mod.misroute_flips(router, df, y_true, y_pred)
    assert out is not None
    assert out["n_misclassified_trio"] >= 1
    assert 0.0 <= out["misroute_flip_rate"] <= 1.0

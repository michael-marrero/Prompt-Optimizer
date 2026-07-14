"""
Quality-regret baseline eval — the metric the exact-model-match table was missing.

Exact-model accuracy grades a router against `best_model` = the *cheapest* model that
scored top, so it conflates quality with a cost tiebreak (see evaluation_summary.md §5).
For a quality-first product the real question is: how much answer QUALITY does a strategy
give up versus the best available model, and at what cost?

This computes, per strategy, mean quality-regret = mean(best_score - chosen_score) and
mean cost, from per-(model, question) scores in flat_records.csv.

Key baseline it resolves: the best *fixed* model (min mean regret over all always-<model>
strategies). If one fixed model has ~0 regret, "always route there" wins on quality and a
learned router is justified by COST only — not quality. That is the number that decides
whether this product should be a smart router or "default to strong, downgrade when sure".

Run from repo root:
    python src/evaluation/evaluate_quality_regret.py            # reads data_processed/flat_records.csv
    python src/evaluation/evaluate_quality_regret.py --input path/to/flat_records.csv
    python src/evaluation/evaluate_quality_regret.py --selftest # synthetic assert-based check

Exit codes: 0 ok / 2 evidence-unavailable (missing/stub/empty input) — never crashes on the
git-LFS / uncommitted-data_raw reality (flat_records.csv regenerates from data_raw/).
"""

import os
import sys
import argparse

import pandas as pd

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
DATA_PROCESSED_DIR = os.path.join(PROJECT_ROOT, "data_processed")
EVALUATION_DIR = os.path.join(PROJECT_ROOT, "evaluation")
FLAT_RECORDS_CSV = os.path.join(DATA_PROCESSED_DIR, "flat_records.csv")
OUTPUT_CSV = os.path.join(EVALUATION_DIR, "quality_regret_metrics.csv")

EXIT_OK = 0
EXIT_UNAVAILABLE = 2

# Minimum share of questions a fixed model must cover to be a deployable "always-<model>"
# candidate — a model evaluated on 3% of prompts can show fake-low regret on its easy slice.
_MIN_COVERAGE = 0.60


def _is_lfs_pointer(path: str) -> bool:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            return handle.readline().startswith("version https://git-lfs")
    except OSError:
        return True


def per_model_regret(df: pd.DataFrame) -> pd.DataFrame:
    """
    df needs columns: question_id, model_name, score, cost.
    best_score per question = max score across all models present on that question.
    Returns one row per model: coverage, mean_regret (over answered questions), mean_cost.
    """
    df = df[["question_id", "model_name", "score", "cost"]].copy()
    df["score"] = pd.to_numeric(df["score"], errors="coerce").fillna(0.0)
    df["cost"] = pd.to_numeric(df["cost"], errors="coerce").fillna(0.0)
    # Collapse duplicate (question, model) rows to one score (max) so a model isn't double-counted.
    df = df.groupby(["question_id", "model_name"], as_index=False).agg(
        score=("score", "max"), cost=("cost", "mean")
    )

    best = df.groupby("question_id")["score"].max().rename("best_score")
    df = df.join(best, on="question_id")
    df["regret"] = df["best_score"] - df["score"]

    n_questions = df["question_id"].nunique()
    rows = []
    for model, g in df.groupby("model_name"):
        rows.append(
            {
                "strategy": f"always:{model}",
                "coverage": len(g) / n_questions,
                "mean_regret": g["regret"].mean(),
                "mean_cost": g["cost"].mean(),
                "n_answered": len(g),
            }
        )
    out = pd.DataFrame(rows).sort_values(["mean_regret", "mean_cost"]).reset_index(drop=True)
    return out, n_questions


def summarize(regret_df: pd.DataFrame, n_questions: int) -> str:
    deployable = regret_df[regret_df["coverage"] >= _MIN_COVERAGE]
    lines = [
        "Quality-Regret Baselines",
        "------------------------",
        f"questions: {n_questions}   models: {len(regret_df)}",
        f"Oracle (best available per question): mean_regret=0.0000  (upper bound)",
        "",
        f"Best FIXED model with coverage >= {_MIN_COVERAGE:.0%} "
        "(the 'always route to one strong model' baseline):",
    ]
    if deployable.empty:
        lines.append(f"  NONE — no model is evaluated on >= {_MIN_COVERAGE:.0%} of questions.")
        lines.append("  (Regret across models is not comparable at low coverage; see per-model CSV.)")
    else:
        b = deployable.iloc[0]
        lines.append(
            f"  {b['strategy']}: mean_regret={b['mean_regret']:.4f}  "
            f"mean_cost={b['mean_cost']:.5f}  coverage={b['coverage']:.1%}"
        )
        lines.append("")
        lines.append(
            "  Interpretation: mean_regret near 0 => 'always route here' loses ~no quality; "
            "a learned router is then justified by COST only, not quality."
        )
    lines.append("")
    lines.append("Top 8 fixed models by lowest regret (any coverage):")
    for _, r in regret_df.head(8).iterrows():
        lines.append(
            f"  regret={r['mean_regret']:.4f}  cost={r['mean_cost']:.5f}  "
            f"cov={r['coverage']:.1%}  {r['strategy']}"
        )
    return "\n".join(lines)


def run(input_csv: str = FLAT_RECORDS_CSV) -> int:
    if not os.path.exists(input_csv) or _is_lfs_pointer(input_csv):
        print(
            f"\nEvidence unavailable: {input_csv}\n"
            "flat_records.csv is regenerated from the uncommitted data_raw/ tree.\n"
            "Materialize data_raw/, then: python -m src.data.flatten_raw_jsons\n"
        )
        return EXIT_UNAVAILABLE
    try:
        df = pd.read_csv(input_csv)
    except (pd.errors.EmptyDataError, pd.errors.ParserError) as error:
        print(f"\nEvidence unavailable: {input_csv} is empty/corrupt ({error}).")
        return EXIT_UNAVAILABLE

    required = {"question_id", "model_name", "score"}
    missing = required - set(df.columns)
    if missing:
        print(f"\nEvidence unavailable: {input_csv} missing columns: {sorted(missing)}")
        return EXIT_UNAVAILABLE
    if "cost" not in df.columns:
        df["cost"] = 0.0

    regret_df, n_questions = per_model_regret(df)
    os.makedirs(EVALUATION_DIR, exist_ok=True)
    regret_df.to_csv(OUTPUT_CSV, index=False)
    print(summarize(regret_df, n_questions))
    print(f"\nSaved per-model regret to: {OUTPUT_CSV}")
    return EXIT_OK


def _selftest() -> None:
    # 3 questions. modelA solves all (regret 0, full coverage); modelB misses q3;
    # modelC only appears on the one question it wins (fake-perfect, low coverage).
    df = pd.DataFrame(
        [
            {"question_id": "q1", "model_name": "A", "score": 1.0, "cost": 0.10},
            {"question_id": "q2", "model_name": "A", "score": 1.0, "cost": 0.10},
            {"question_id": "q3", "model_name": "A", "score": 1.0, "cost": 0.10},
            {"question_id": "q1", "model_name": "B", "score": 1.0, "cost": 0.00},
            {"question_id": "q2", "model_name": "B", "score": 1.0, "cost": 0.00},
            {"question_id": "q3", "model_name": "B", "score": 0.0, "cost": 0.00},
            {"question_id": "q1", "model_name": "C", "score": 1.0, "cost": 0.00},
        ]
    )
    out, n = per_model_regret(df)
    assert n == 3
    row = {r["strategy"]: r for _, r in out.iterrows()}
    assert abs(row["always:A"]["mean_regret"] - 0.0) < 1e-9, "A solves all -> 0 regret"
    assert abs(row["always:A"]["coverage"] - 1.0) < 1e-9
    assert abs(row["always:B"]["mean_regret"] - (1.0 / 3)) < 1e-9, "B misses 1 of 3"
    assert abs(row["always:C"]["mean_regret"] - 0.0) < 1e-9, "C fake-perfect on its 1 q"
    assert abs(row["always:C"]["coverage"] - (1.0 / 3)) < 1e-9, "but low coverage flags it"
    # deployable filter (>=0.60) must exclude C and rank A first (0 regret, higher cost ok).
    deployable = out[out["coverage"] >= _MIN_COVERAGE]
    assert list(deployable["strategy"]) and deployable.iloc[0]["strategy"] == "always:A"
    assert "always:C" not in set(deployable["strategy"])
    print("selftest OK")


def main() -> int:
    parser = argparse.ArgumentParser(description="Quality-regret baseline eval.")
    parser.add_argument("--input", default=FLAT_RECORDS_CSV, help="flat_records.csv path")
    parser.add_argument("--selftest", action="store_true", help="run synthetic assert check")
    args = parser.parse_args()
    if args.selftest:
        _selftest()
        return EXIT_OK
    return run(args.input)


if __name__ == "__main__":
    sys.exit(main())

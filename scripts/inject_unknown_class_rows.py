"""
Inject synthetic OOD (out-of-distribution) prompts as the D-09 `unknown` class.

The LLMRouterBench benchmark slugs all match one of the keyword groups in
`build_question_type.map_dataset_to_question_type`, so the natural unknown
distribution is 0 rows. This script materializes 50 synthetic OOD prompts —
spanning emoji-only, gibberish, single-token, multi-language, and mixed-noise
patterns — and appends them to `classifier_training_with_types.csv` with the
literal label `question_type = "unknown"`.

The 50 rows are embedded verbatim below so the dataset is deterministic and
reproducible. Each row's numeric features are computed live via
`PromptFeatureExtractor.extract(...)` (Plan 01-02 — 53 keys including the 5
agentic features). The output CSV preserves the original column order and
schema so Plan 05's training script reads it unchanged.

Run from the repo root:

    uv run python scripts/inject_unknown_class_rows.py

The script is idempotent: it strips any pre-existing rows whose dataset slug
starts with "synthetic_ood_" before appending the canonical 50, so re-running
never accumulates duplicates.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data_processed"
INPUT_CSV = DATA_DIR / "classifier_training_with_types.csv"
OUTPUT_CSV = INPUT_CSV  # in-place

SRC_FEATURE_EXTRACTION = PROJECT_ROOT / "src" / "feature_extraction"
if str(SRC_FEATURE_EXTRACTION) not in sys.path:
    sys.path.insert(0, str(SRC_FEATURE_EXTRACTION))

from Feature_extractor import PromptFeatureExtractor  # noqa: E402


# ============================================================
# 50 synthetic OOD prompts, grouped by archetype.
#
# Choices follow RESEARCH §Pitfall 2 step 3 — "emoji-only, gibberish,
# single-token" — extended with a small multi-language slice so the
# unknown class has distributional breadth, not just trivial inputs.
#
# Every prompt is intentionally distinct from every other (no near-dupes)
# so PromptFeatureExtractor.extract() produces visibly different numeric
# feature vectors across the bucket. Sentence-tokenizer-stable (NLTK
# punkt_tab handles each one without crashing).
# ============================================================

EMOJI_ONLY = [
    "🚀🚀🚀",
    "❓❓❓❓",
    "🤔",
    "😀😃😄😁",
    "💀💀💀💀💀",
    "🌍🌎🌏",
    "🎉🎊✨",
    "⭐⭐⭐⭐⭐",
    "🔥🔥🔥",
    "👀",
]

SINGLE_TOKEN_OR_PUNCT = [
    "???",
    "...",
    "!!!",
    "k",
    "ok",
    "lol",
    "huh",
    "ayy",
    "xyzzy",
    "foobar",
]

GIBBERISH = [
    "asdfgh qwerty zxcvbn poiuyt",
    "asdjkl;ghqwertyuiop",
    "blarg blorg blurg",
    "qzqzqzqzqzqz",
    "flibbertigibbet snickerdoodle",
    "wxyzwxyzwxyz wxyzwxyz",
    "jklasdjklasdjklasd",
    "kekw kekw kekw",
    "haha haha haha haha haha",
    "no no no no no no no no no",
]

MULTI_LANGUAGE_SHORT = [
    "你好世界",  # Chinese: "hello world"
    "こんにちは",  # Japanese: "hello"
    "안녕",  # Korean: "hi"
    "مرحبا",  # Arabic: "hello"
    "Здравствуйте",  # Russian: "hello (formal)"
    "γειά",  # Greek: "hi"
    "नमस्ते",  # Hindi: "namaste"
    "שלום",  # Hebrew: "hello/peace"
    "สวัสดี",  # Thai: "hello"
    "வணக்கம்",  # Tamil: "hello"
]

MIXED_NOISE_OR_AMBIGUOUS = [
    "qqq 123 ###",
    "//// ///",
    "[][][]",
    "{{{{}}}}",
    "++++++=====",
    "ZZZZZZZZZZZZZ",
    "...........................",
    "????????????????????",
    "🤖🤖🤖 lol idk",
    "hjkl hjkl hjkl",
]

SYNTHETIC_OOD_PROMPTS: list[str] = (
    EMOJI_ONLY
    + SINGLE_TOKEN_OR_PUNCT
    + GIBBERISH
    + MULTI_LANGUAGE_SHORT
    + MIXED_NOISE_OR_AMBIGUOUS
)

assert len(SYNTHETIC_OOD_PROMPTS) == 50, len(SYNTHETIC_OOD_PROMPTS)


def main() -> int:
    if not INPUT_CSV.exists():
        print(f"ERROR: input CSV not found: {INPUT_CSV}", file=sys.stderr)
        print(
            "Run `uv run python -m src.task_classifier.build_question_type` first.",
            file=sys.stderr,
        )
        return 2

    print(f"Loading {INPUT_CSV}...")
    df = pd.read_csv(INPUT_CSV)
    original_rows = len(df)
    print(f"  rows={original_rows}, cols={len(df.columns)}")

    # Idempotency: strip any pre-existing synthetic OOD rows so a re-run
    # doesn't accumulate duplicates.
    if "dataset" in df.columns:
        synth_mask = df["dataset"].astype(str).str.startswith("synthetic_ood_")
        n_stripped = int(synth_mask.sum())
        if n_stripped > 0:
            print(f"  stripping {n_stripped} existing synthetic_ood_ rows for re-run idempotency")
            df = df[~synth_mask].reset_index(drop=True)

    # Compute Plan 01-02 numeric features for each OOD row.
    extractor = PromptFeatureExtractor()

    feature_rows = []
    for text in SYNTHETIC_OOD_PROMPTS:
        feature_rows.append(extractor.extract(text))
    feats_df = pd.DataFrame(feature_rows)

    # Build the metadata columns. Match the LLMRouterBench schema so the
    # downstream training script reads the OOD rows like every other row.
    n = len(SYNTHETIC_OOD_PROMPTS)

    meta = pd.DataFrame({
        "question_id": [f"synthetic_ood::idx-{i}" for i in range(n)],
        "dataset": [
            *(["synthetic_ood_emoji"] * len(EMOJI_ONLY)),
            *(["synthetic_ood_single_token"] * len(SINGLE_TOKEN_OR_PUNCT)),
            *(["synthetic_ood_gibberish"] * len(GIBBERISH)),
            *(["synthetic_ood_multilang"] * len(MULTI_LANGUAGE_SHORT)),
            *(["synthetic_ood_mixed_noise"] * len(MIXED_NOISE_OR_AMBIGUOUS)),
        ],
        "split": ["synthetic"] * n,
        "origin_query": SYNTHETIC_OOD_PROMPTS,
        "prompt": SYNTHETIC_OOD_PROMPTS,
        "best_model": ["OTHER"] * n,
        "best_score": [0.0] * n,
        "best_cost": [0.0] * n,
        "n_models_compared": [0] * n,
        "models_evaluated": [""] * n,
    })

    ood_df = pd.concat([meta, feats_df], axis=1)
    ood_df["question_type"] = "unknown"

    # Align column order to match the existing CSV. Any extra cols added by
    # `extract()` that weren't in the original schema land after the metadata.
    existing_cols = list(df.columns)
    for col in existing_cols:
        if col not in ood_df.columns:
            ood_df[col] = 0
    ood_df = ood_df[existing_cols]

    out = pd.concat([df, ood_df], axis=0).reset_index(drop=True)
    out.to_csv(OUTPUT_CSV, index=False)

    print(f"\nAppended {n} synthetic OOD rows.")
    print(f"  new total rows: {len(out)} (was {original_rows})")

    # Verification report (matches plan's Task 3 acceptance criteria).
    qts = out["question_type"].value_counts()
    print("\nPer-class row counts (after injection):")
    for k, v in qts.items():
        pct = v / len(out) * 100.0
        print(f"  {k}: {v} ({pct:.2f}%)")

    unknown_n = int(qts.get("unknown", 0))
    print(f"\nUnknown rows: {unknown_n}")
    print(f"  Pitfall 2 floor: 15  -> {'OK' if unknown_n >= 15 else 'FAIL'}")
    cap = 0.15
    pct_unknown = unknown_n / len(out)
    print(f"  Pitfall 2 cap:   <{int(cap*100)}% -> {pct_unknown:.4%}  {'OK' if pct_unknown < cap else 'FAIL'}")

    print(f"\nWrote: {OUTPUT_CSV}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

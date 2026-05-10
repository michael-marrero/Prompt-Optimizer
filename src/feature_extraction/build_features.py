"""
Build feature columns for every CSV in ``data_processed/`` that has ``origin_query``.

Skips ``flat_records.csv`` (many duplicate queries per row) and files named ``*_features.csv``.
Writes ``<stem>_features.csv`` next to each source CSV.

Run from the repo root:

    python -m src.feature_extraction.build_features
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from Feature_extractor import PromptFeatureExtractor


_TEXT_COLUMN = "origin_query"
_SKIP_INPUT_NAMES = frozenset({"flat_records.csv"})


def _data_dir() -> Path:
    for parent in Path(__file__).resolve().parents:
        d = parent / "data_processed"
        if d.is_dir():
            return d
    raise FileNotFoundError(
        'Could not find a "data_processed" directory upward from '
        f"{Path(__file__).resolve()}"
    )


def _build_paths(data_dir: Path) -> list[Path]:
    out: list[Path] = []
    for path in sorted(data_dir.glob("*.csv")):
        if path.name in _SKIP_INPUT_NAMES:
            continue
        stem = path.stem
        if stem.endswith("_features"):
            continue
        out.append(path)
    return out


def main() -> None:
    data_dir = _data_dir()
    inputs = _build_paths(data_dir)
    if not inputs:
        raise SystemExit(f"No CSV inputs under {data_dir} (after skips).")

    extractor = PromptFeatureExtractor()
    for csv_path in inputs:
        df = pd.read_csv(csv_path)
        if _TEXT_COLUMN not in df.columns:
            print(f"skip (no {_TEXT_COLUMN!r} column): {csv_path.name}")
            continue

        features = [extractor.extract(q) for q in df[_TEXT_COLUMN]]
        feats_df = pd.DataFrame(features)
        out = pd.concat([df.reset_index(drop=True), feats_df], axis=1)

        out_path = csv_path.with_name(f"{csv_path.stem}_features.csv")
        out.to_csv(out_path, index=False)
        print(f"wrote {out_path.relative_to(data_dir.parent)}  ({len(out)} rows × {len(out.columns)} cols)")


if __name__ == "__main__":
    main()

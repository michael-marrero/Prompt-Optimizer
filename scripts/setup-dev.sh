#!/usr/bin/env bash
# OSS-02 / D-03 — clean-clone provisioning (retraining / training path). Superset of
# scripts/setup.sh: adds the LFS pull (training-only data_processed/*.csv) and the
# ~90 MB SentenceTransformer prefetch (used by retraining / the embedding router but
# NOT by the chat path), then delegates to setup.sh for the run-the-app provisioning.
# set -euo pipefail per D-04.
set -euo pipefail

# Anchor at the repo root so the script runs correctly from any working directory.
cd "$(dirname "$0")/.."

echo "==> git lfs install && git lfs pull (D-03: setup-dev is the SOLE LFS-pull owner)"
git lfs install && git lfs pull

echo "==> Prefetch SentenceTransformer all-MiniLM-L6-v2 into local HF cache"
# Model name is EMBEDDING_MODEL_NAME (src/model_router/train_embedding_router.py:54).
# Retraining / the embedding router needs it; the chat path (decide()) does not.
uv run python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

echo "==> Delegating to scripts/setup.sh for run-the-app provisioning (superset)"
exec ./scripts/setup.sh

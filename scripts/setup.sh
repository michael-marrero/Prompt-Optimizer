#!/usr/bin/env bash
# OSS-02 — clean-clone provisioning (run-the-app path). set -euo pipefail per D-04.
# Provisions BOTH Python (uv sync, NLTK prefetch, .env copy) AND web (pnpm install,
# playwright chromium) so a first-time contributor reaches a runnable app in one
# command. Fail-fast on any step (set -euo pipefail) and idempotent (skips an
# existing .env, relies on uv/pnpm/NLTK caching for cheap re-runs).
#
# DELIBERATE DEVIATION (D-03): this script runs `git lfs install` but NOT
# `git lfs pull`. The runtime loads only models/*.joblib (regular git objects, not
# LFS); the LFS-tracked data_processed/*.csv is training-only. `scripts/setup-dev.sh`
# is the SOLE owner of `git lfs pull`.
#
# DELIBERATE DEVIATION (Pitfall 3 / Open Question 1): the ~90 MB SentenceTransformer
# all-MiniLM-L6-v2 HF prefetch lives in scripts/setup-dev.sh (the training path),
# NOT here. decide() (the chat path) never loads it — only retraining / the embedding
# router does. Keeping it out of the run-the-app path shaves the single biggest item
# off the OSS-08 <10-min budget, mirroring the D-03 LFS split.
set -euo pipefail

# Anchor at the repo root so the script runs correctly from any working directory.
cd "$(dirname "$0")/.."

echo "==> git lfs install (idempotent; NOT pull — D-03; CSVs are training-only)"
git lfs install

echo "==> uv sync --locked (Python env)"                  # ci.yml:25-26
uv sync --locked

echo "==> Prefetch NLTK punkt_tab + punkt"                 # ci.yml:48-50 (verbatim)
uv run python -c "import nltk; nltk.download('punkt_tab', quiet=True); nltk.download('punkt', quiet=True)"

echo "==> pnpm install (web)"                              # web-test.yml:45-46
pnpm --dir apps/web install

echo "==> playwright install chromium"                     # web-test.yml:48-49
pnpm --dir apps/web exec playwright install chromium

echo "==> Copy .env.example -> .env if absent (idempotent; D-04 'if absent')"
[ -f .env ] || cp .env.example .env
[ -f apps/web/.env ] || cp apps/web/.env.example apps/web/.env

echo "==> setup complete. Next: paste your OpenRouter key into .env, then run 'make dev'."

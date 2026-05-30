#!/usr/bin/env bash
# OSS-02 / D-01 — launch FastAPI + Next together. Dependency-light two-process
# launcher (bash & + trap, no foreman/honcho/concurrently). Ctrl-C stops both.
# set -euo pipefail per D-04.
set -euo pipefail

# Anchor at the repo root so the script runs correctly from any working directory.
cd "$(dirname "$0")/.."

# FastAPI on :8000 (reads .env via apps.api side-effect import).
uv run uvicorn apps.api.main:app --port 8000 &
API_PID=$!

# Next dev on :3000. FASTAPI_URL pinned to the literal IPv4 127.0.0.1 (mirrors
# playwright.config.ts): Node resolves "localhost" to ::1 first via dns.lookup but
# uvicorn binds 127.0.0.1 only — without the pin the Next proxy's upstream fetch
# silently fails the IPv6 connect and returns an empty body.
( cd apps/web && FASTAPI_URL=http://127.0.0.1:8000 pnpm dev --port 3000 ) &
WEB_PID=$!

cleanup() { kill "$API_PID" "$WEB_PID" 2>/dev/null || true; }
trap cleanup INT TERM EXIT
wait

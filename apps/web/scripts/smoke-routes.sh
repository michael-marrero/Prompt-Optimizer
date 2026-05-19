#!/usr/bin/env bash
# Wave-2 end-to-end smoke check for the five route handlers landed in
# Plan 04-03. Boots the canned mock-FastAPI from Wave 0 + a Next dev
# server on port 3000, then curls the proxy and asserts the AI SDK v6
# UI Message Stream chunk substrings appear in the SSE body and the
# x-vercel-ai-ui-message-stream:v1 response header is set.
#
# This is a DEVELOPER-facing tool — NOT run from CI (CI uses the
# Playwright suite at apps/web/playwright/). Run once after Task 1+2
# to prove the proxy + translator + AI SDK v6 header all work end-to-end
# against the mock upstream that does not need a real OpenRouter key.
#
# Usage:
#   bash apps/web/scripts/smoke-routes.sh
#
# Exit codes:
#   0 — all assertions passed; the SSE pipe is wired correctly.
#   non-zero — one of the curl probes failed; the script prints the
#              failure context to stderr and tears down cleanly.

set -uo pipefail

# Resolve paths relative to the script's own location so the script can
# be run from any cwd inside the repo.
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
WEB_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"
REPO_ROOT="$( cd "$WEB_DIR/../.." && pwd )"

MOCK_PORT=8001
WEB_PORT=3000
# Use 127.0.0.1 (NOT "localhost") for both URLs. Node 18+ resolves
# `localhost` to ::1 (IPv6) first; the mock-fastapi.py default binds
# to 127.0.0.1 only and the Next route handler's fetch silently fails
# the IPv6 connect attempt before returning an empty stream. Pinning
# the IPv4 literal avoids the family-mismatch trap. (Critical: FASTAPI_URL
# passed to Next dev below MUST also use 127.0.0.1 for the same reason.)
MOCK_URL="http://127.0.0.1:$MOCK_PORT"
WEB_URL="http://127.0.0.1:$WEB_PORT"

MOCK_PID=""
WEB_PID=""

# Ensure background processes are killed on any exit (success, error,
# or SIGINT). The trap fires even if the script aborts via `set -e`
# (we are using `set -u` not `set -e` so we can catch curl failures
# individually with non-fatal exit codes).
cleanup() {
  local exit_code=$?
  if [ -n "$MOCK_PID" ]; then
    kill "$MOCK_PID" 2>/dev/null || true
  fi
  if [ -n "$WEB_PID" ]; then
    kill "$WEB_PID" 2>/dev/null || true
  fi
  # Belt-and-suspenders: kill anything still bound to our ports.
  lsof -t -iTCP:$MOCK_PORT -sTCP:LISTEN 2>/dev/null | xargs -r kill 2>/dev/null || true
  lsof -t -iTCP:$WEB_PORT  -sTCP:LISTEN 2>/dev/null | xargs -r kill 2>/dev/null || true
  exit "$exit_code"
}
trap cleanup EXIT INT TERM

# --------------------------------------------------------------------
# 1. Start the mock FastAPI on port 8001 (Wave 0 canned-SSE server)
# --------------------------------------------------------------------
# Prefer the repo's .venv Python (has sse_starlette + fastapi installed);
# fall back to system python3 / python in that order so the script also
# works in CI containers that uv-installs into a different prefix.
PY=""
if [ -x "$REPO_ROOT/.venv/bin/python" ]; then
  PY="$REPO_ROOT/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PY="python3"
elif command -v python >/dev/null 2>&1; then
  PY="python"
else
  echo "[smoke][FAIL] no python interpreter found" >&2
  exit 1
fi
echo "[smoke] using python: $PY" >&2
echo "[smoke] starting mock-fastapi on :$MOCK_PORT" >&2
"$PY" "$WEB_DIR/playwright/mock-fastapi.py" --port "$MOCK_PORT" >/dev/null 2>&1 &
MOCK_PID=$!

# --------------------------------------------------------------------
# 2. Start `next dev` on port 3000 with FASTAPI_URL pointing at mock
# --------------------------------------------------------------------
echo "[smoke] starting next dev on :$WEB_PORT (FASTAPI_URL=$MOCK_URL)" >&2
(
  cd "$WEB_DIR"
  FASTAPI_URL="$MOCK_URL" pnpm dev --port "$WEB_PORT" >/dev/null 2>&1
) &
WEB_PID=$!

# --------------------------------------------------------------------
# 3. Wait up to 30s for both servers to become reachable
# --------------------------------------------------------------------
wait_for_url() {
  local url=$1
  local label=$2
  local i
  for i in $(seq 1 30); do
    if curl -sf -o /dev/null "$url" 2>/dev/null; then
      echo "[smoke] $label up after ${i}s" >&2
      return 0
    fi
    sleep 1
  done
  echo "[smoke][FAIL] $label did not become reachable within 30s" >&2
  return 1
}

wait_for_url "$MOCK_URL/api/v1/healthz" "mock-fastapi"   || exit 2
wait_for_url "$WEB_URL/api/health"      "next dev /api/health proxy" || exit 2

# --------------------------------------------------------------------
# 3a. Warm up the /api/chat route. Next 16's dev server compiles route
# handlers on demand on the FIRST request; the second request hits the
# cached compile and streams in real time. Without this warm-up the
# subsequent POST sees a long delay or premature timeout while the
# Turbopack compile of the route handler completes.
# --------------------------------------------------------------------
echo "[smoke] warming up /api/chat route (JIT compile)" >&2
curl -sS --max-time 60 -o /dev/null \
  -X POST \
  -H "Content-Type: application/json" \
  --data '{"messages":[{"role":"user","parts":[{"type":"text","text":"warmup"}]}],"threadId":"warmup-thread"}' \
  "$WEB_URL/api/chat" || true
echo "[smoke] warm-up complete" >&2

# --------------------------------------------------------------------
# 4. Curl POST /api/chat — assert AI SDK v6 chunk substrings + header
# --------------------------------------------------------------------
echo "[smoke] POST $WEB_URL/api/chat" >&2

CHAT_BODY='{"messages":[{"role":"user","parts":[{"type":"text","text":"hello"}]}],"threadId":"test-thread"}'
HEADERS_FILE=$(mktemp)
BODY_FILE=$(mktemp)

# -N disables curl's output buffering so the SSE chunks land in real
# time. --max-time 10 caps the request so a stuck stream cannot hang
# the script.
HTTP_CODE=$(
  curl -sS -N \
    --max-time 30 \
    -X POST \
    -H "Content-Type: application/json" \
    -D "$HEADERS_FILE" \
    -o "$BODY_FILE" \
    -w "%{http_code}" \
    --data "$CHAT_BODY" \
    "$WEB_URL/api/chat" || echo "000"
)

if [ "$HTTP_CODE" != "200" ]; then
  echo "[smoke][FAIL] /api/chat returned $HTTP_CODE (expected 200)" >&2
  echo "  headers:" >&2
  cat "$HEADERS_FILE" >&2
  echo "  body:" >&2
  cat "$BODY_FILE" >&2
  exit 3
fi

# Header check — case-insensitive grep for the AI SDK v6 protocol header
if ! grep -i -q '^x-vercel-ai-ui-message-stream: v1' "$HEADERS_FILE"; then
  echo "[smoke][FAIL] /api/chat response missing x-vercel-ai-ui-message-stream:v1 header (Pitfall 7)" >&2
  echo "  headers received:" >&2
  cat "$HEADERS_FILE" >&2
  exit 4
fi
echo "[smoke] response header x-vercel-ai-ui-message-stream: v1 present" >&2

# Body chunk substring checks — one per AI SDK v6 chunk type the
# translator emits from the mock-fastapi canned 4-event sequence.
declare -a EXPECTED=(
  '"type":"start"'
  '"type":"data-routing"'
  '"type":"text-delta"'
  '"type":"data-metrics"'
  '"type":"finish"'
  'data: [DONE]'
)

CHAT_BODY_CONTENT=$(cat "$BODY_FILE")
echo "[smoke] body length: $(echo -n "$CHAT_BODY_CONTENT" | wc -c) bytes" >&2

for sub in "${EXPECTED[@]}"; do
  if ! grep -F -q "$sub" "$BODY_FILE"; then
    echo "[smoke][FAIL] /api/chat body missing substring: $sub" >&2
    echo "  body received (last 400 chars):" >&2
    tail -c 400 "$BODY_FILE" >&2
    exit 5
  fi
done
echo "[smoke] all AI SDK v6 chunk substrings present" >&2

# --------------------------------------------------------------------
# 5. Curl GET /api/health — assert adapters payload flows through
# --------------------------------------------------------------------
echo "[smoke] GET $WEB_URL/api/health" >&2
HEALTH_BODY=$(curl -sS --max-time 5 "$WEB_URL/api/health" || echo "")

if ! echo "$HEALTH_BODY" | grep -F -q '"adapters"'; then
  echo "[smoke][FAIL] /api/health body missing \"adapters\" key" >&2
  echo "  body: $HEALTH_BODY" >&2
  exit 6
fi
if ! echo "$HEALTH_BODY" | grep -F -q '"openrouter"'; then
  echo "[smoke][FAIL] /api/health body missing \"openrouter\" key" >&2
  echo "  body: $HEALTH_BODY" >&2
  exit 7
fi
echo "[smoke] /api/health adapters payload present" >&2

# --------------------------------------------------------------------
# 6. Done — cleanup() runs from the EXIT trap
# --------------------------------------------------------------------
rm -f "$HEADERS_FILE" "$BODY_FILE"
echo "[smoke] PASS" >&2
exit 0

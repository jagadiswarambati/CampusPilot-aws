#!/usr/bin/env bash
# UI flow test: starts the local dev server (real Lambda code + mocked DynamoDB), drives every page of the app
# in jsdom, then stops the server. Needs Node 18+ and the dev requirements (see README).
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"
export PORT="${PORT:-8787}"

command -v node > /dev/null || { echo "ERROR: Node.js 18+ is required for the UI flow test." >&2; exit 1; }
[ -d tests/e2e/node_modules ] || (cd tests/e2e && npm install --silent)

LOG="$(mktemp)"
"$PY" backend/dev_server.py > "$LOG" 2>&1 &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2> /dev/null || true; rm -f "$LOG"' EXIT

for _ in $(seq 1 40); do
  curl -sf "http://127.0.0.1:$PORT/health" > /dev/null 2>&1 && break
  sleep 0.3
done
curl -sf "http://127.0.0.1:$PORT/health" > /dev/null 2>&1 || { echo "ERROR: dev server did not start:" >&2; cat "$LOG" >&2; exit 1; }

(cd tests/e2e && BASE="http://127.0.0.1:$PORT" node ui_flow.mjs 2>&1) | grep -E "^(PASS|FAIL|All UI|[0-9]+ check)"

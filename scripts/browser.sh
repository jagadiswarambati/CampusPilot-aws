#!/usr/bin/env bash
# Real-browser tools (optional). Starts the local dev server, then runs one of:
#   ./scripts/browser.sh test     Playwright flow test: plan, book, check in, print, order, layout checks
#   ./scripts/browser.sh shots    regenerate docs/screenshots/*.png
# Needs: pip install playwright && playwright install chromium
set -euo pipefail
cd "$(dirname "$0")/.."
MODE="${1:-test}"
PY="${PYTHON:-python3}"                 # runs the dev server (needs moto)
BPY="${BROWSER_PYTHON:-$PY}"            # runs Playwright (defaults to the same Python)
PORT="${PORT:-8787}"
export PORT
BASE="http://127.0.0.1:${PORT}"
export BASE

"$BPY" -c "import playwright" 2> /dev/null || { echo "ERROR: Playwright is not installed. Run: pip install playwright && playwright install chromium" >&2; exit 1; }
LOG="$(mktemp)"
"$PY" backend/dev_server.py > "$LOG" 2>&1 &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2> /dev/null || true; rm -f "$LOG"' EXIT
for _ in $(seq 1 40); do curl -sf "$BASE/health" > /dev/null 2>&1 && break; sleep 0.3; done
curl -sf "$BASE/health" > /dev/null 2>&1 || { echo "ERROR: dev server did not start:" >&2; cat "$LOG" >&2; exit 1; }

case "$MODE" in
  test) "$BPY" tests/e2e/browser_flows.py ;;
  shots) "$BPY" scripts/screenshots.py ;;
  *) echo "Usage: $0 test|shots" >&2; exit 2 ;;
esac

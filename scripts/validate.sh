#!/usr/bin/env bash
# Runs every local check: backend tests, template lint, script and JS syntax, and the UI flow test.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"

echo "== Backend tests";   (cd backend && "$PY" -m pytest -q)
echo "== Template lint";   if command -v cfn-lint > /dev/null; then cfn-lint template.yaml && echo "ok"; else echo "skipped (pip install cfn-lint)"; fi
echo "== Shell syntax";    for s in scripts/*.sh; do bash -n "$s"; done && echo "ok"
echo "== JavaScript syntax"; if command -v node > /dev/null; then for f in frontend/js/*.js; do node --check "$f"; done && echo "ok"; else echo "skipped (Node not installed)"; fi
echo "== UI flow test"
if command -v node > /dev/null && "$PY" -c "import moto" 2> /dev/null; then PYTHON="$PY" ./scripts/e2e.sh | tail -3; else echo "skipped (needs Node and moto: pip install -r backend/requirements-dev.txt)"; fi
echo; echo "All local checks passed."

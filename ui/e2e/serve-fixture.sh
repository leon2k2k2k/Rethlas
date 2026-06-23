#!/usr/bin/env bash
# Boot the workbench against a fresh synthetic fixture tree (for Playwright).
set -euo pipefail
cd "$(dirname "$0")/.."
FIXTURE=/tmp/rethlas-e2e-fixture
rm -rf "$FIXTURE"
python3 tests/make_fixture.py "$FIXTURE"
export RETHLAS_ROOTS="{\"main\": \"$FIXTURE\"}"
export RETHLAS_SESSIONS_DIR="$FIXTURE/sessions"
export RETHLAS_DATA_DIR="$FIXTURE/uidata"
export RETHLAS_STUB_JOBS=1
exec python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8099

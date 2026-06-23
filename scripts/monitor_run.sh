#!/usr/bin/env bash
# Print a compact status view for one retry-run problem_id.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GENERATION_DIR="$REPO_ROOT/agents/generation"
PROBLEM_ID="${1:-}"

if [[ -z "$PROBLEM_ID" ]]; then
  echo "Usage: scripts/monitor_run.sh <problem_id>" >&2
  exit 2
fi

echo "=== Processes ==="
ps -eo pid,ppid,etime,stat,pcpu,pmem,cmd \
  | rg "codex exec|uvicorn api.server|${PROBLEM_ID}|code-server" || true

echo
echo "=== Files ==="
find \
  "$GENERATION_DIR/logs/$PROBLEM_ID" \
  "$GENERATION_DIR/memory/$PROBLEM_ID" \
  "$GENERATION_DIR/results/$PROBLEM_ID" \
  -maxdepth 1 -type f \
  -printf '%TY-%Tm-%Td %TH:%TM:%TS %s %p\n' 2>/dev/null \
  | sort || true

echo
echo "=== Manager Log ==="
tail -n 40 "$GENERATION_DIR/logs/$PROBLEM_ID/retry_manager.log" 2>/dev/null || true

echo
echo "=== Latest Attempt Log ==="
latest="$(find "$GENERATION_DIR/logs/$PROBLEM_ID" -maxdepth 1 -type f -name 'attempt_*.md' 2>/dev/null | sort | tail -n 1 || true)"
if [[ -n "$latest" ]]; then
  echo "$latest"
  tail -n 80 "$latest"
fi

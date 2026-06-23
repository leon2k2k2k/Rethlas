#!/usr/bin/env bash
# Print a compact status view for one discovery batch id.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GENERATION_DIR="$REPO_ROOT/agents/generation"
BATCH_ID="${1:-}"

if [[ -z "$BATCH_ID" ]]; then
  echo "Usage: scripts/monitor_discovery_batch.sh <batch_id>" >&2
  exit 2
fi

RESULT_DIR="$GENERATION_DIR/results/$BATCH_ID"
LOG_DIR="$GENERATION_DIR/logs/$BATCH_ID"
MEMORY_DIR="$GENERATION_DIR/memory/$BATCH_ID"

echo "=== Batch ==="
echo "batch_id: $BATCH_ID"
echo "results: $RESULT_DIR"
echo "logs: $LOG_DIR"
echo "memory: $MEMORY_DIR"

echo
echo "=== Processes ==="
ps -eo pid,ppid,etime,stat,pcpu,pmem,cmd \
  | rg "run_discovery_batch|run_discovery_pipeline|codex exec|${BATCH_ID}|uvicorn api.server" || true

echo
echo "=== Manifest ==="
jq . "$RESULT_DIR/batch_manifest.json" 2>/dev/null || true

echo
echo "=== Sample Status ==="
find "$RESULT_DIR" -mindepth 2 -maxdepth 2 -name status.json -print 2>/dev/null \
  | sort \
  | while IFS= read -r status; do
      rel="${status#"$RESULT_DIR/"}"
      jq -r --arg rel "$rel" \
        '"\($rel): \(.status) - \(.detail) @ \(.updated_at)"' \
        "$status" 2>/dev/null || echo "$rel: unreadable"
    done

echo
echo "=== Route Cards ==="
total_cards="$(find "$RESULT_DIR" -mindepth 2 -maxdepth 2 -name route_card.json -print 2>/dev/null | wc -l | tr -d ' ')"
valid_cards="$(find "$RESULT_DIR" -mindepth 2 -maxdepth 2 -name route_card_validation.json -print 2>/dev/null \
  | xargs -r jq -r 'select(.valid == true) | .valid' 2>/dev/null \
  | wc -l | tr -d ' ')"
echo "route_card.json: $total_cards"
echo "valid route cards: $valid_cards"

echo
echo "=== Stage Counts ==="
jq . "$RESULT_DIR/stage_counts.json" 2>/dev/null || true

echo
echo "=== Promotion Decision ==="
jq . "$RESULT_DIR/promotion_decision.json" 2>/dev/null || true

echo
echo "=== Recent Files ==="
find "$RESULT_DIR" "$LOG_DIR" "$MEMORY_DIR" -type f \
  -printf '%TY-%Tm-%Td %TH:%TM:%TS %s %p\n' 2>/dev/null \
  | sort \
  | tail -n 40 || true

echo
echo "=== Latest Logs ==="
find "$LOG_DIR" -mindepth 2 -maxdepth 2 -name discovery.log -print 2>/dev/null \
  | sort \
  | tail -n 2 \
  | while IFS= read -r log; do
      echo "--- $log"
      tail -n 40 "$log"
    done

#!/usr/bin/env bash
# Run the Rethlas discovery pipeline (discover -> triage -> promote).
# Domain-agnostic: defaults are neutral; point PROBLEM_FILE/DISCOVERY_PROFILE
# at any domain (Erdos by default in the example campaigns).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PROBLEM_FILE="${PROBLEM_FILE:-data/example.md}"
BATCH_ID="${BATCH_ID:-discovery/run_$(date -u +%Y%m%dT%H%M%SZ)}"
SAMPLES="${SAMPLES:-10}"
PARALLEL="${PARALLEL:-2}"
MIN_VALID_CARDS="${MIN_VALID_CARDS:-1}"
MODEL="${MODEL:-gpt-5.5}"
REASONING_EFFORT="${REASONING_EFFORT:-xhigh}"
DISCOVERY_PROFILE="${DISCOVERY_PROFILE:-low_hint}"
DISCOVERY_FOCUS="${DISCOVERY_FOCUS:-}"
ALLOW_SOURCE_TEMPLATES="${ALLOW_SOURCE_TEMPLATES:-}"
SOURCE_TEMPLATE_FILES="${SOURCE_TEMPLATE_FILES:-}"
MAX_PROMOTION_ATTEMPTS="${MAX_PROMOTION_ATTEMPTS:-3}"
MAX_OBSTRUCTION_ATTEMPTS="${MAX_OBSTRUCTION_ATTEMPTS:-3}"
AUTO_PROMOTE_DEPTH="${AUTO_PROMOTE_DEPTH:-1}"
AUTO_LAUNCH_PROMOTION="${AUTO_LAUNCH_PROMOTION:-0}"
AUTO_PROMOTE_OBSTRUCTION="${AUTO_PROMOTE_OBSTRUCTION:-0}"
AUTO_LAUNCH_OBSTRUCTION="${AUTO_LAUNCH_OBSTRUCTION:-0}"
AUTO_CONTINUE_CONDITIONAL="${AUTO_CONTINUE_CONDITIONAL:-1}"
CODEX_SILENT_TIMEOUT_SECONDS="${CODEX_SILENT_TIMEOUT_SECONDS:-900}"
CODEX_POLL_SECONDS="${CODEX_POLL_SECONDS:-30}"

usage() {
  cat <<'EOF'
Usage:
  SAMPLES=10 PARALLEL=2 BATCH_ID=discovery/run_001 \
    scripts/run_discovery_pipeline.sh

Environment:
  PROBLEM_FILE              Initial benchmark problem file.
  BATCH_ID                  Discovery batch id.
  SAMPLES                   Independent discovery samples. Default: 10.
  PARALLEL                  Parallel discovery jobs. Default: 2.
  MIN_VALID_CARDS           Minimum valid route cards required. Default: 1.
  MODEL                     Codex model. Default: gpt-5.5.
  REASONING_EFFORT          Codex reasoning effort. Default: xhigh.
  DISCOVERY_PROFILE         Discovery hint profile. Default:
                            unit_distance_transition.
  DISCOVERY_FOCUS           Optional route-card focus override.
  ALLOW_SOURCE_TEMPLATES    Optional profile source-template override.
  SOURCE_TEMPLATE_FILES     Optional profile template-list override.
  MAX_PROMOTION_ATTEMPTS    Attempts for generated repair run. Default: 3.
  MAX_OBSTRUCTION_ATTEMPTS  Attempts for generated obstruction run. Default: 3.
  AUTO_PROMOTE_DEPTH        Max obstruction-promotion stages after a failed
                            launched promotion. Default: 1.
  AUTO_LAUNCH_PROMOTION     1 to run generated repair command. Default: 0.
  AUTO_PROMOTE_OBSTRUCTION  1 to convert failed promoted blueprint into a
                            focused obstruction/source-lemma problem.
  AUTO_LAUNCH_OBSTRUCTION   1 to run the generated obstruction/source-lemma
                            problem after promotion. Requires
                            AUTO_PROMOTE_OBSTRUCTION=1.
  AUTO_CONTINUE_CONDITIONAL  1 to continue autoloop when a launched stage is
                            verifier-correct but still names a next missing
                            theorem. Default: 1.
  CODEX_SILENT_TIMEOUT_SECONDS
                            Silence timeout for each Codex attempt.
  CODEX_POLL_SECONDS        Heartbeat/staleness poll interval.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

cd "$REPO_ROOT"

PROBLEM_FILE="$PROBLEM_FILE" \
BATCH_ID="$BATCH_ID" \
SAMPLES="$SAMPLES" \
PARALLEL="$PARALLEL" \
MIN_VALID_CARDS="$MIN_VALID_CARDS" \
MODEL="$MODEL" \
REASONING_EFFORT="$REASONING_EFFORT" \
DISCOVERY_PROFILE="$DISCOVERY_PROFILE" \
DISCOVERY_FOCUS="$DISCOVERY_FOCUS" \
ALLOW_SOURCE_TEMPLATES="$ALLOW_SOURCE_TEMPLATES" \
SOURCE_TEMPLATE_FILES="$SOURCE_TEMPLATE_FILES" \
CODEX_SILENT_TIMEOUT_SECONDS="$CODEX_SILENT_TIMEOUT_SECONDS" \
CODEX_POLL_SECONDS="$CODEX_POLL_SECONDS" \
scripts/run_discovery_batch.sh

BATCH_RESULT_DIR="agents/generation/results/$BATCH_ID"
scripts/triage_route_cards.py "$BATCH_RESULT_DIR" --fail-on-invalid

promotion_args=(
  "$BATCH_RESULT_DIR"
  --max-attempts "$MAX_PROMOTION_ATTEMPTS"
  --model "$MODEL"
  --reasoning-effort "$REASONING_EFFORT"
  --codex-silent-timeout-seconds "$CODEX_SILENT_TIMEOUT_SECONDS"
  --codex-poll-seconds "$CODEX_POLL_SECONDS"
)

if [[ "$AUTO_LAUNCH_PROMOTION" == "1" ]]; then
  promotion_args+=(--launch)
fi

if [[ "$AUTO_LAUNCH_PROMOTION" == "1" && "$AUTO_PROMOTE_OBSTRUCTION" == "1" ]]; then
  set +e
  scripts/apply_promotion_decision.py "${promotion_args[@]}"
  promotion_code=$?
  set -e

  PROMOTION_MANIFEST="$BATCH_RESULT_DIR/promotion_manifest.json"
  if [[ ! -s "$PROMOTION_MANIFEST" ]]; then
    echo "Promotion failed and no promotion_manifest.json was written: $PROMOTION_MANIFEST" >&2
    exit "$promotion_code"
  fi

  PROMOTED_PROBLEM_ID="$(jq -r '.generated_problem_id // empty' "$PROMOTION_MANIFEST")"
  if [[ -z "$PROMOTED_PROBLEM_ID" ]]; then
    echo "Promotion failed and promotion_manifest.json has no generated_problem_id" >&2
    exit "$promotion_code"
  fi

  PROMOTED_RESULT_DIR="agents/generation/results/$PROMOTED_PROBLEM_ID"

  if [[ "$promotion_code" -eq 0 ]]; then
    if [[ "$AUTO_CONTINUE_CONDITIONAL" != "1" || ! -s "$PROMOTED_RESULT_DIR/blueprint_verified.md" ]]; then
      exit 0
    fi
    scripts/classify_blueprint_status.py "$PROMOTED_RESULT_DIR" \
      --output "$PROMOTED_RESULT_DIR/blueprint_status.json" >/dev/null
    PROMOTED_STATUS="$(jq -r '.status // empty' "$PROMOTED_RESULT_DIR/blueprint_status.json")"
    if [[ "$PROMOTED_STATUS" != "verified_conditioning" ]]; then
      exit 0
    fi
  fi

  if [[ ! -s "$PROMOTED_RESULT_DIR/blueprint.md" ]]; then
    echo "Promotion failed without a blueprint obstruction at $PROMOTED_RESULT_DIR/blueprint.md" >&2
    exit "$promotion_code"
  fi

  CURRENT_RESULT_DIR="$PROMOTED_RESULT_DIR"
  CURRENT_EXIT_CODE="$promotion_code"
  CURRENT_PROBLEM_ID="$PROMOTED_PROBLEM_ID"

  for depth in $(seq 1 "$AUTO_PROMOTE_DEPTH"); do
    if [[ ! -s "$CURRENT_RESULT_DIR/blueprint.md" ]]; then
      echo "Autoloop depth $depth has no blueprint at $CURRENT_RESULT_DIR/blueprint.md" >&2
      exit "$CURRENT_EXIT_CODE"
    fi

    obstruction_args=(
      "$CURRENT_RESULT_DIR"
      --max-attempts "$MAX_OBSTRUCTION_ATTEMPTS"
      --model "$MODEL"
      --reasoning-effort "$REASONING_EFFORT"
      --codex-silent-timeout-seconds "$CODEX_SILENT_TIMEOUT_SECONDS"
      --codex-poll-seconds "$CODEX_POLL_SECONDS"
    )

    if [[ "$AUTO_LAUNCH_OBSTRUCTION" == "1" ]]; then
      obstruction_args+=(--launch)
    fi

    set +e
    scripts/promote_blueprint_obstruction.py "${obstruction_args[@]}"
    obstruction_code=$?
    set -e

    SOURCE_OBSTRUCTION_MANIFEST="$CURRENT_RESULT_DIR/source_obstruction_promotion_manifest.json"
    SOURCE_PROBLEM_ID=""
    SOURCE_ACTION=""
    if [[ -s "$SOURCE_OBSTRUCTION_MANIFEST" ]]; then
      SOURCE_PROBLEM_ID="$(jq -r '.generated_problem_id // empty' "$SOURCE_OBSTRUCTION_MANIFEST")"
      SOURCE_ACTION="$(jq -r '.action // empty' "$SOURCE_OBSTRUCTION_MANIFEST")"
    fi
    SOURCE_RESULT_DIR=""
    if [[ -n "$SOURCE_PROBLEM_ID" ]]; then
      SOURCE_RESULT_DIR="agents/generation/results/$SOURCE_PROBLEM_ID"
    fi

    SOURCE_STATUS=""
    SOURCE_SHOULD_CONTINUE="false"
    if [[ -n "$SOURCE_RESULT_DIR" && -s "$SOURCE_RESULT_DIR/blueprint_verified.md" ]]; then
      scripts/classify_blueprint_status.py "$SOURCE_RESULT_DIR" \
        --output "$SOURCE_RESULT_DIR/blueprint_status.json" >/dev/null
      SOURCE_STATUS="$(jq -r '.status // empty' "$SOURCE_RESULT_DIR/blueprint_status.json")"
      SOURCE_SHOULD_CONTINUE="$(jq -r '.should_continue // false' "$SOURCE_RESULT_DIR/blueprint_status.json")"
    fi

    state_json="$(jq -c -n \
      --arg action "obstruction_promoted" \
      --arg batch_id "$BATCH_ID" \
      --argjson depth "$depth" \
      --argjson input_exit_code "$CURRENT_EXIT_CODE" \
      --argjson obstruction_exit_code "$obstruction_code" \
      --arg input_problem_id "$CURRENT_PROBLEM_ID" \
      --arg input_result_dir "$CURRENT_RESULT_DIR" \
      --arg source_action "$SOURCE_ACTION" \
      --arg source_problem_id "$SOURCE_PROBLEM_ID" \
      --arg source_result_dir "$SOURCE_RESULT_DIR" \
      --arg source_obstruction_manifest "$SOURCE_OBSTRUCTION_MANIFEST" \
      --arg source_status "$SOURCE_STATUS" \
      --arg source_should_continue "$SOURCE_SHOULD_CONTINUE" \
      --arg auto_launch_obstruction "$AUTO_LAUNCH_OBSTRUCTION" \
      --arg auto_continue_conditional "$AUTO_CONTINUE_CONDITIONAL" \
      '{
        action: $action,
        batch_id: $batch_id,
        depth: $depth,
        input_exit_code: $input_exit_code,
        obstruction_exit_code: $obstruction_exit_code,
        input_problem_id: $input_problem_id,
        input_result_dir: $input_result_dir,
        source_action: $source_action,
        source_problem_id: $source_problem_id,
        source_result_dir: $source_result_dir,
        source_obstruction_manifest: $source_obstruction_manifest,
        source_status: $source_status,
        source_should_continue: ($source_should_continue == "true"),
        auto_launch_obstruction: ($auto_launch_obstruction == "1"),
        auto_continue_conditional: ($auto_continue_conditional == "1")
      }')"
    printf '%s\n' "$state_json" >> "$BATCH_RESULT_DIR/autoloop_events.jsonl"
    printf '%s\n' "$state_json" | jq '.' > "$BATCH_RESULT_DIR/autoloop_state.json"

    if [[ "$obstruction_code" -eq 0 ]]; then
      if [[ "$AUTO_CONTINUE_CONDITIONAL" == "1" && "$AUTO_LAUNCH_OBSTRUCTION" == "1" && "$SOURCE_SHOULD_CONTINUE" == "true" ]]; then
        CURRENT_RESULT_DIR="$SOURCE_RESULT_DIR"
        CURRENT_PROBLEM_ID="$SOURCE_PROBLEM_ID"
        CURRENT_EXIT_CODE="$obstruction_code"
        continue
      fi
      exit 0
    fi

    if [[ "$AUTO_LAUNCH_OBSTRUCTION" != "1" || -z "$SOURCE_RESULT_DIR" ]]; then
      exit "$obstruction_code"
    fi

    CURRENT_RESULT_DIR="$SOURCE_RESULT_DIR"
    CURRENT_PROBLEM_ID="$SOURCE_PROBLEM_ID"
    CURRENT_EXIT_CODE="$obstruction_code"
  done

  exit "$CURRENT_EXIT_CODE"
else
  scripts/apply_promotion_decision.py "${promotion_args[@]}"
fi

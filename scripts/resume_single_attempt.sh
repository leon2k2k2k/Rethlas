#!/usr/bin/env bash
# Resume one specific Rethlas attempt with the same prompt shape as the retry runner.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GENERATION_DIR="$REPO_ROOT/agents/generation"

PROBLEM_FILE="${PROBLEM_FILE:-}"
PROBLEM_ID="${PROBLEM_ID:-}"
ATTEMPT_NUMBER="${ATTEMPT_NUMBER:-}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-5}"
MODEL="${MODEL:-gpt-5.5}"
REASONING_EFFORT="${REASONING_EFFORT:-xhigh}"
VERIFY_ENDPOINT="${VERIFY_ENDPOINT:-http://127.0.0.1:8091/verify}"
BLIND_RUN="${BLIND_RUN:-1}"
PROVIDER="${PROVIDER:-}"
source "$REPO_ROOT/scripts/codex_provider_flags.sh"

usage() {
  cat <<'EOF'
Usage:
  PROBLEM_FILE=data/path/problem.md PROBLEM_ID=run/id ATTEMPT_NUMBER=5 scripts/resume_single_attempt.sh
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ -z "$PROBLEM_FILE" || -z "$PROBLEM_ID" || -z "$ATTEMPT_NUMBER" ]]; then
  usage >&2
  exit 2
fi

ABS_PROBLEM_FILE="$GENERATION_DIR/$PROBLEM_FILE"
RESULT_DIR="$GENERATION_DIR/results/$PROBLEM_ID"
MEMORY_DIR="$GENERATION_DIR/memory/$PROBLEM_ID"
LOG_DIR="$GENERATION_DIR/logs/$PROBLEM_ID"
BLUEPRINT="$RESULT_DIR/blueprint.md"
MANAGER_LOG="$LOG_DIR/retry_manager.log"
ATTEMPT_LOG="$LOG_DIR/attempt_${ATTEMPT_NUMBER}.md"

mkdir -p "$RESULT_DIR" "$MEMORY_DIR" "$LOG_DIR"

log() {
  local msg="$1"
  printf '[%s] %s\n' "$(date -Iseconds)" "$msg" | tee -a "$MANAGER_LOG"
}

append_memory_json() {
  local channel="$1"
  local json_file="$2"
  local target="$MEMORY_DIR/${channel}.jsonl"
  jq -c \
    --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg channel "$channel" \
    --arg source "resume_single_attempt" \
    '. as $record | {timestamp_utc: $ts, channel: $channel, record: ($record + {source: $source})}' \
    "$json_file" >> "$target"
}

verify_blueprint() {
  local verify_json="$RESULT_DIR/verification_attempt_${ATTEMPT_NUMBER}.json"
  local verify_tmp="${verify_json}.tmp"

  if [[ ! -s "$BLUEPRINT" ]]; then
    log "Attempt ${ATTEMPT_NUMBER}: no blueprint.md to verify"
    return 1
  fi

  log "Attempt ${ATTEMPT_NUMBER}: blueprint exists; calling verifier"
  if jq -n --rawfile statement "$ABS_PROBLEM_FILE" --rawfile proof "$BLUEPRINT" \
      '{statement: $statement, proof: $proof}' \
      | curl -sS -X POST "$VERIFY_ENDPOINT" \
          -H "Content-Type: application/json" \
          --data-binary @- \
          > "$verify_tmp"; then
    mv "$verify_tmp" "$verify_json"
  else
    rm -f "$verify_tmp"
    log "Attempt ${ATTEMPT_NUMBER}: verifier HTTP call failed"
    return 1
  fi

  append_memory_json "verification_reports" "$verify_json"
  log "Attempt ${ATTEMPT_NUMBER}: verifier verdict=$(jq -r '.verdict // "missing"' "$verify_json")"
}

build_prompt() {
  local blind_clause=""
  if [[ "$BLIND_RUN" == "1" ]]; then
    blind_clause="The problem is a blind benchmark; obey its blindness rules exactly."
  else
    blind_clause="Use the retrieval policy in AGENTS.md and in the problem statement."
  fi

  cat <<EOF
Attempt ${ATTEMPT_NUMBER}/${MAX_ATTEMPTS} for ${PROBLEM_FILE}. Use problem_id=${PROBLEM_ID}.

Continue from the existing memory and results for this problem. The previous attempt did not produce an acceptable verified proof.

Before choosing the next route, read and use these files if they exist:
- memory/${PROBLEM_ID}/failed_paths.jsonl
- memory/${PROBLEM_ID}/subgoals.jsonl
- memory/${PROBLEM_ID}/proof_steps.jsonl
- memory/${PROBLEM_ID}/branch_states.jsonl
- memory/${PROBLEM_ID}/verification_reports.jsonl
- results/${PROBLEM_ID}/blueprint.md

Do not repeat failed strategies. If the previous blueprint is promising, audit and repair it. If the previous direction is invalid, branch away and record exactly why. ${blind_clause}
EOF
}

prompt="$(build_prompt)"

log "Attempt ${ATTEMPT_NUMBER}/${MAX_ATTEMPTS}: resuming Codex; log=$ATTEMPT_LOG"
{
  printf 'resumed_at: %s\n' "$(date -Iseconds)"
  printf 'problem_id: %s\n' "$PROBLEM_ID"
  printf 'problem_file: %s\n' "$PROBLEM_FILE"
  printf 'model: %s\n' "$MODEL"
  printf 'reasoning_effort: %s\n\n' "$REASONING_EFFORT"
} >> "$ATTEMPT_LOG"

set +e
(
  cd "$GENERATION_DIR"
  printf '%s\n' "$prompt" \
    | RETHLAS_BLIND_RUN="$BLIND_RUN" codex exec \
        -C "$GENERATION_DIR" \
        -m "$MODEL" \
        --config "model_reasoning_effort=\"${REASONING_EFFORT}\"" \
        ${PROVIDER_FLAGS[@]+"${PROVIDER_FLAGS[@]}"} \
          --config 'mcp_servers.reasoning_agent.command="python3"' \
          --config 'mcp_servers.reasoning_agent.args=["./mcp/server.py"]' \
          --config "mcp_servers.reasoning_agent.cwd=\"$GENERATION_DIR\"" \
        --dangerously-bypass-approvals-and-sandbox
) >> "$ATTEMPT_LOG" 2>&1
code=$?
set -e

log "Attempt ${ATTEMPT_NUMBER}/${MAX_ATTEMPTS}: Codex exited with code ${code}"

if [[ -f "$BLUEPRINT" ]]; then
  cp "$BLUEPRINT" "$RESULT_DIR/blueprint_attempt_${ATTEMPT_NUMBER}.md"
fi

verify_blueprint || true

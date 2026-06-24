#!/usr/bin/env bash
# Launch independent Rethlas discovery samples that emit route cards.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GENERATION_DIR="$REPO_ROOT/agents/generation"

PROBLEM_FILE="${PROBLEM_FILE:-data/example.md}"
BATCH_ID="${BATCH_ID:-discovery_$(date -u +%Y%m%dT%H%M%SZ)}"
SAMPLES="${SAMPLES:-5}"
PARALLEL="${PARALLEL:-2}"
MIN_VALID_CARDS="${MIN_VALID_CARDS:-1}"
MODEL="${MODEL:-gpt-5.5}"
REASONING_EFFORT="${REASONING_EFFORT:-xhigh}"
PROVIDER="${PROVIDER:-}"
source "$REPO_ROOT/scripts/codex_provider_flags.sh"
DISCOVERY_PROFILE="${DISCOVERY_PROFILE:-low_hint}"
DISCOVERY_FOCUS="${DISCOVERY_FOCUS:-${DISCOVERY_MODE:-}}"
ALLOW_SOURCE_TEMPLATES="${ALLOW_SOURCE_TEMPLATES:-}"
SOURCE_TEMPLATE_FILES="${SOURCE_TEMPLATE_FILES:-}"
CODEX_SILENT_TIMEOUT_SECONDS="${CODEX_SILENT_TIMEOUT_SECONDS:-900}"
CODEX_POLL_SECONDS="${CODEX_POLL_SECONDS:-30}"
DRY_RUN="${DRY_RUN:-0}"

case "$DISCOVERY_PROFILE" in
  bare)
    DISCOVERY_FOCUS="${DISCOVERY_FOCUS:-general}"
    ALLOW_SOURCE_TEMPLATES="${ALLOW_SOURCE_TEMPLATES:-0}"
    SOURCE_TEMPLATE_FILES="${SOURCE_TEMPLATE_FILES:-}"
    ;;
  low_hint)
    DISCOVERY_FOCUS="${DISCOVERY_FOCUS:-general}"
    ALLOW_SOURCE_TEMPLATES="${ALLOW_SOURCE_TEMPLATES:-1}"
    SOURCE_TEMPLATE_FILES="${SOURCE_TEMPLATE_FILES:-escape_operators.md hidden_coordinate_bridge.md}"
    ;;
  source_family)
    DISCOVERY_FOCUS="${DISCOVERY_FOCUS:-source_family}"
    ALLOW_SOURCE_TEMPLATES="${ALLOW_SOURCE_TEMPLATES:-1}"
    SOURCE_TEMPLATE_FILES="${SOURCE_TEMPLATE_FILES:-escape_operators.md hidden_coordinate_bridge.md source_family_discovery.md}"
    ;;
  unit_distance_transition|number_theory_transition|nt_transition)
    DISCOVERY_FOCUS="${DISCOVERY_FOCUS:-unit_distance_transition}"
    ALLOW_SOURCE_TEMPLATES="${ALLOW_SOURCE_TEMPLATES:-1}"
    SOURCE_TEMPLATE_FILES="${SOURCE_TEMPLATE_FILES:-escape_operators.md hidden_coordinate_bridge.md source_family_discovery.md unit_distance_number_theory_transition.md}"
    ;;
  arithmetic_hint|number_field_focus)
    DISCOVERY_FOCUS="${DISCOVERY_FOCUS:-number_field_focus}"
    ALLOW_SOURCE_TEMPLATES="${ALLOW_SOURCE_TEMPLATES:-1}"
    SOURCE_TEMPLATE_FILES="${SOURCE_TEMPLATE_FILES:-escape_operators.md hidden_coordinate_bridge.md source_family_discovery.md unit_distance_number_theory_transition.md number_field_source_menu.md}"
    ;;
  *)
    echo "Unknown DISCOVERY_PROFILE: $DISCOVERY_PROFILE" >&2
    echo "Allowed profiles: bare, low_hint, source_family, unit_distance_transition, arithmetic_hint, number_field_focus" >&2
    exit 2
    ;;
esac

usage() {
  cat <<'EOF'
Usage:
  PROBLEM_FILE=data/discrete_geometry/unit_distance_disproof.md \
  BATCH_ID=discrete_geometry/unit_distance_discovery_test \
  SAMPLES=10 PARALLEL=2 scripts/run_discovery_batch.sh

Environment:
  PROBLEM_FILE             Relative path under agents/generation/data/.
  BATCH_ID                 Batch id under results/, logs/, and memory/.
  SAMPLES                  Number of independent samples. Default: 5.
  PARALLEL                 Concurrent Codex processes. Default: 2.
  MIN_VALID_CARDS          Minimum valid route cards required. Default: 1.
  MODEL                    Codex model. Default: gpt-5.5.
  REASONING_EFFORT         Codex reasoning effort. Default: xhigh.
  DISCOVERY_PROFILE        Hint profile. Default: low_hint.
                           bare: no source templates, focus=general.
                           low_hint: generic escape/bridge templates only.
                           source_family: adds generic source-family menu.
                           unit_distance_transition: asks for the planar-to-
                           arithmetic transition evidence without the full
                           number-field menu.
                           arithmetic_hint / number_field_focus: adds
                           unit-distance transition and number-field menus.
  DISCOVERY_FOCUS          Route-card focus label. Defaults from profile.
  DISCOVERY_MODE           Deprecated alias for DISCOVERY_FOCUS.
  ALLOW_SOURCE_TEMPLATES   Override profile source-template policy.
  SOURCE_TEMPLATE_FILES    Override profile source template basenames.
  CODEX_SILENT_TIMEOUT_SECONDS
                           Kill a sample if its log mtime is stale this long.
                           Default: 900. Set 0 to disable.
  CODEX_POLL_SECONDS       Heartbeat/staleness poll interval. Default: 30.
  DRY_RUN                  1 writes prompts/status without launching Codex.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ "$PROBLEM_FILE" = /* || "$PROBLEM_FILE" == *".."* || "$PROBLEM_FILE" != data/*.md ]]; then
  echo "PROBLEM_FILE must be a relative markdown path under agents/generation/data/: $PROBLEM_FILE" >&2
  exit 2
fi

if [[ ! "$SAMPLES" =~ ^[1-9][0-9]*$ ]]; then
  echo "SAMPLES must be a positive integer: $SAMPLES" >&2
  exit 2
fi

if [[ ! "$PARALLEL" =~ ^[1-9][0-9]*$ ]]; then
  echo "PARALLEL must be a positive integer: $PARALLEL" >&2
  exit 2
fi

if [[ ! "$MIN_VALID_CARDS" =~ ^[0-9]+$ ]]; then
  echo "MIN_VALID_CARDS must be a nonnegative integer: $MIN_VALID_CARDS" >&2
  exit 2
fi

if [[ ! "$CODEX_SILENT_TIMEOUT_SECONDS" =~ ^[0-9]+$ ]]; then
  echo "CODEX_SILENT_TIMEOUT_SECONDS must be a nonnegative integer: $CODEX_SILENT_TIMEOUT_SECONDS" >&2
  exit 2
fi

if [[ ! "$CODEX_POLL_SECONDS" =~ ^[1-9][0-9]*$ ]]; then
  echo "CODEX_POLL_SECONDS must be a positive integer: $CODEX_POLL_SECONDS" >&2
  exit 2
fi

ABS_PROBLEM_FILE="$GENERATION_DIR/$PROBLEM_FILE"
if [[ ! -f "$ABS_PROBLEM_FILE" ]]; then
  echo "Problem file not found: $ABS_PROBLEM_FILE" >&2
  exit 2
fi

BATCH_RESULT_DIR="$GENERATION_DIR/results/$BATCH_ID"
BATCH_LOG_DIR="$GENERATION_DIR/logs/$BATCH_ID"
BATCH_MEMORY_DIR="$GENERATION_DIR/memory/$BATCH_ID"
MANIFEST="$BATCH_RESULT_DIR/batch_manifest.json"

mkdir -p "$BATCH_RESULT_DIR" "$BATCH_LOG_DIR" "$BATCH_MEMORY_DIR"

for template in $SOURCE_TEMPLATE_FILES; do
  if [[ "$template" = /* || "$template" == *".."* || "$template" == */* ]]; then
    echo "SOURCE_TEMPLATE_FILES entries must be basenames under source_templates/: $template" >&2
    exit 2
  fi
  if [[ "$ALLOW_SOURCE_TEMPLATES" == "1" && ! -f "$GENERATION_DIR/source_templates/$template" ]]; then
    echo "Source template not found: source_templates/$template" >&2
    exit 2
  fi
done

write_status() {
  local status_file="$1"
  local sample_id="$2"
  local status="$3"
  local detail="$4"
  jq -n \
    --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg sample_id "$sample_id" \
    --arg status "$status" \
    --arg detail "$detail" \
    '{updated_at: $ts, sample_id: $sample_id, status: $status, detail: $detail}' \
    > "$status_file"
}

build_prompt() {
  local sample_id="$1"
  local sample_problem_id="$2"
  local templates_clause="No source templates are allowed in this sample."
  local promotion_clause
  local focus_clause
  local evidence_clause=""

  if [[ "$ALLOW_SOURCE_TEMPLATES" == "1" ]]; then
    templates_clause="SOURCE_TEMPLATE_FILES=${SOURCE_TEMPLATE_FILES}. Read only these files under source_templates/ as generic background templates."
  fi

  promotion_clause="- focus on whether the route should promote from direct planar attempts to a representation change, an exact same-length source search, a source-entropy/cost bottleneck, a growing-rank or growing-degree search, or parameter assembly;"
  focus_clause="- compare at most three broad route families without assuming which family wins."

  if [[ "$DISCOVERY_FOCUS" == "number_field_focus" ]]; then
    promotion_clause="- focus on whether the route should promote from planar attempts to hidden coordinates, source entropy, growing-degree arithmetic, or number-field source construction;"
    focus_clause="- compare broad arithmetic and number-field source families as possible suppliers of many exact same-length or unit-modulus displacements, but do not assume any particular family wins."
    evidence_clause='- include transition_signal, unit_distance_signals, and stage_evidence fields when they clarify the promotion evidence;'
  elif [[ "$DISCOVERY_FOCUS" == "unit_distance_transition" ]]; then
    promotion_clause="- audit the Erdos lattice baseline, identify the exact same-length or denominator bottleneck, and decide whether the next stage should be hidden coordinates, source-family discovery, growing-degree arithmetic, or number-field source construction;"
    focus_clause="- compare at most three broad families and promote toward number theory only if the route card explains the planar/fixed-rank failure and the entropy-vs-cost ledger."
    evidence_clause='- include transition_signal, unit_distance_signals, and stage_evidence fields; set booleans honestly, especially planar_baseline_audited, equal_length_bottleneck, fixed_degree_or_rank_failed, growing_degree_move, number_field_candidate, and quantitative_slots_filled;'
  elif [[ "$DISCOVERY_FOCUS" == "source_family" ]]; then
    promotion_clause="- focus on whether the route should promote from a representation-change bottleneck to a source-family search, growing-rank/growing-degree search, or parameter assembly;"
    focus_clause="- compare broad source families as possible suppliers of many exact same-length or unit-modulus displacements, but do not assume any particular family wins."
  fi

  cat <<EOF
Use AGENTS.md exactly. DISCOVERY_MODE=route_card. DISCOVERY_FOCUS=${DISCOVERY_FOCUS}. Use problem_id=${sample_problem_id}. Read problem file ${PROBLEM_FILE}.

This is independent discovery sample ${sample_id} in batch ${BATCH_ID}.

Do not read memory/ or results/ for any sibling sample, previous run, or other problem_id. Do not run the verifier unless you have a complete proof candidate and have already written the route card. Do not search the web or arXiv. Do not read target-proof notes, OpenAI chain-of-thought material, recent announcements, or unlisted local notes.

Do not read .agents/skills/*.md or launch recursive/subgoal agents in this discovery sample. Do not enter the normal long proof-and-repair loop. Read the problem and listed source templates, compare at most three route families, then write the required route_card.json and brief_blueprint.md artifacts.

${templates_clause}

Discovery objective:
- produce results/${sample_problem_id}/route_card.json matching schemas/route_card.schema.json;
- produce results/${sample_problem_id}/brief_blueprint.md;
- set route_card.json field "discovery_mode" to "${DISCOVERY_FOCUS}";
${promotion_clause}
${focus_clause}
${evidence_clause}

The route card must be honest. If no proof is found, record the exact missing object and failed cost comparison.
EOF
}

jq -n \
  --arg created_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg problem_file "$PROBLEM_FILE" \
  --arg batch_id "$BATCH_ID" \
  --arg model "$MODEL" \
  --arg effort "$REASONING_EFFORT" \
  --arg discovery_profile "$DISCOVERY_PROFILE" \
  --arg discovery_focus "$DISCOVERY_FOCUS" \
  --argjson samples "$SAMPLES" \
  --argjson parallel "$PARALLEL" \
  --argjson min_valid_cards "$MIN_VALID_CARDS" \
  --argjson codex_silent_timeout_seconds "$CODEX_SILENT_TIMEOUT_SECONDS" \
  --argjson codex_poll_seconds "$CODEX_POLL_SECONDS" \
  --arg allow_source_templates "$ALLOW_SOURCE_TEMPLATES" \
  --arg source_template_files "$SOURCE_TEMPLATE_FILES" \
  '{created_at: $created_at, problem_file: $problem_file, batch_id: $batch_id,
    model: $model, reasoning_effort: $effort,
    discovery_profile: $discovery_profile,
    discovery_focus: $discovery_focus,
    samples: $samples, parallel: $parallel,
    min_valid_cards: $min_valid_cards,
    codex_silent_timeout_seconds: $codex_silent_timeout_seconds,
    codex_poll_seconds: $codex_poll_seconds,
    allow_source_templates: ($allow_source_templates == "1"),
    source_template_files: (if $source_template_files == "" then [] else ($source_template_files | split(" ")) end)}' \
  > "$MANIFEST"

kill_tree() {
  local pid="$1"
  local signal="$2"
  local child
  while IFS= read -r child; do
    [[ -n "$child" ]] || continue
    kill_tree "$child" "$signal"
  done < <(pgrep -P "$pid" 2>/dev/null || true)
  kill "-$signal" "$pid" 2>/dev/null || true
}

run_sample() {
  local n="$1"
  local sample_id
  sample_id="$(printf 'sample_%03d' "$n")"
  local sample_problem_id="$BATCH_ID/$sample_id"
  local result_dir="$GENERATION_DIR/results/$sample_problem_id"
  local memory_dir="$GENERATION_DIR/memory/$sample_problem_id"
  local log_dir="$GENERATION_DIR/logs/$sample_problem_id"
  local prompt_file="$log_dir/prompt.md"
  local log_file="$log_dir/discovery.log"
  local status_file="$result_dir/status.json"
  local heartbeat_file="$result_dir/heartbeat.txt"
  local route_card="$result_dir/route_card.json"
  local route_card_validation="$result_dir/route_card_validation.json"

  mkdir -p "$result_dir" "$memory_dir" "$log_dir"
  build_prompt "$sample_id" "$sample_problem_id" > "$prompt_file"
  write_status "$status_file" "$sample_id" "planned" "prompt written"

  if [[ "$DRY_RUN" == "1" ]]; then
    write_status "$status_file" "$sample_id" "dry_run" "DRY_RUN=1; Codex not launched"
    return 0
  fi

  write_status "$status_file" "$sample_id" "running" "Codex launched"
  date -u +%Y-%m-%dT%H:%M:%SZ > "$heartbeat_file"

  {
    printf 'started_at: %s\n' "$(date -Iseconds)"
    printf 'batch_id: %s\n' "$BATCH_ID"
    printf 'sample_id: %s\n' "$sample_id"
    printf 'problem_id: %s\n' "$sample_problem_id"
    printf 'problem_file: %s\n' "$PROBLEM_FILE"
    printf 'model: %s\n' "$MODEL"
    printf 'reasoning_effort: %s\n\n' "$REASONING_EFFORT"
  } > "$log_file"

  set +e
  (
    cd "$GENERATION_DIR"
    codex exec \
      -C "$GENERATION_DIR" \
      -m "$MODEL" \
      --config "model_reasoning_effort=\"${REASONING_EFFORT}\"" \
      ${PROVIDER_FLAGS[@]+"${PROVIDER_FLAGS[@]}"} \
          --config 'mcp_servers.reasoning_agent.command="python3"' \
          --config 'mcp_servers.reasoning_agent.args=["./mcp/server.py"]' \
          --config "mcp_servers.reasoning_agent.cwd=\"$GENERATION_DIR\"" \
      --dangerously-bypass-approvals-and-sandbox \
      "$(cat "$prompt_file")"
  ) >> "$log_file" 2>&1 &
  local codex_pid=$!
  local timed_out=0
  local mtime now stale
  while kill -0 "$codex_pid" 2>/dev/null; do
    sleep "$CODEX_POLL_SECONDS"
    date -u +%Y-%m-%dT%H:%M:%SZ > "$heartbeat_file"
    if [[ "$CODEX_SILENT_TIMEOUT_SECONDS" -gt 0 ]]; then
      mtime="$(stat -c %Y "$log_file" 2>/dev/null || date +%s)"
      now="$(date +%s)"
      stale=$((now - mtime))
      if [[ "$stale" -ge "$CODEX_SILENT_TIMEOUT_SECONDS" ]]; then
        printf '[%s] sample %s: log silent for %ss; terminating Codex pid %s\n' \
          "$(date -Iseconds)" "$sample_id" "$stale" "$codex_pid" >> "$log_file"
        write_status "$status_file" "$sample_id" "silent_timeout" \
          "Codex log silent for ${stale}s; timeout=${CODEX_SILENT_TIMEOUT_SECONDS}s"
        kill_tree "$codex_pid" TERM
        sleep 5
        kill_tree "$codex_pid" KILL
        timed_out=1
        break
      fi
    fi
  done
  wait "$codex_pid"
  local code=$?
  if [[ "$timed_out" -eq 1 ]]; then
    code=124
  fi
  set -e

  date -u +%Y-%m-%dT%H:%M:%SZ > "$heartbeat_file"

  if [[ $code -ne 0 ]]; then
    if [[ "$timed_out" -ne 1 ]]; then
      write_status "$status_file" "$sample_id" "codex_failed" "Codex exited with code $code"
    fi
    return "$code"
  fi

  if [[ ! -s "$route_card" ]]; then
    write_status "$status_file" "$sample_id" "missing_route_card" "Codex exited but route_card.json is missing"
    return 1
  fi

  if ! "$REPO_ROOT/scripts/validate_route_card.py" "$route_card" --write-report "$route_card_validation" >> "$log_file" 2>&1; then
    write_status "$status_file" "$sample_id" "invalid_route_card" "route_card.json failed schema validation"
    return 1
  fi

  write_status "$status_file" "$sample_id" "completed" "route_card.json written"
}

pids=()
failures=0

for n in $(seq 1 "$SAMPLES"); do
  run_sample "$n" &
  pids+=("$!")

  while [[ "${#pids[@]}" -ge "$PARALLEL" ]]; do
    if ! wait -n; then
      failures=$((failures + 1))
    fi
    live=()
    for pid in "${pids[@]}"; do
      if kill -0 "$pid" 2>/dev/null; then
        live+=("$pid")
      fi
    done
    pids=("${live[@]}")
  done
done

for pid in "${pids[@]}"; do
  if ! wait "$pid"; then
    failures=$((failures + 1))
  fi
done

echo "Discovery batch complete: $BATCH_ID"
echo "Results: $BATCH_RESULT_DIR"
echo "Logs: $BATCH_LOG_DIR"
echo "Failures: $failures"

valid_cards=0
while IFS= read -r -d '' validation; do
  if jq -e '.valid == true' "$validation" >/dev/null 2>&1; then
    valid_cards=$((valid_cards + 1))
  fi
done < <(find "$BATCH_RESULT_DIR" -name route_card_validation.json -print0)

echo "Valid route cards: $valid_cards"

if [[ "$DRY_RUN" == "1" ]]; then
  echo "DRY_RUN=1; skipping MIN_VALID_CARDS gate"
  exit 0
fi

if [[ "$valid_cards" -lt "$MIN_VALID_CARDS" ]]; then
  echo "Only $valid_cards valid route cards; MIN_VALID_CARDS=$MIN_VALID_CARDS" >&2
  exit 1
fi

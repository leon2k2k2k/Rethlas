#!/usr/bin/env bash
# Run a Rethlas generation problem with fresh-process retries.
#
# Each retry starts a new Codex process but keeps the problem's memory/results
# directory, so later attempts can use failed paths and verifier feedback.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GENERATION_DIR="$REPO_ROOT/agents/generation"

PROBLEM_FILE="${PROBLEM_FILE:-data/discrete_geometry/unit_distance_disproof.md}"
PROBLEM_ID="${PROBLEM_ID:-}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-5}"
MODEL="${MODEL:-gpt-5.5}"
REASONING_EFFORT="${REASONING_EFFORT:-xhigh}"
PROVIDER="${PROVIDER:-}"
source "$REPO_ROOT/scripts/codex_provider_flags.sh"
CONTINUE_ROUNDS="${CONTINUE_ROUNDS:-0}"
TOKEN_BUDGET="${TOKEN_BUDGET:-0}"
# Literature cutoff: when set (YYYY-MM-DD), the run may search arXiv/web but
# only the world frozen at that date. Enforced by the noegress egress block +
# the frozen_literature MCP tools backed by scripts/frozen_proxy.py.
LITERATURE_CUTOFF="${RETHLAS_LITERATURE_CUTOFF:-}"
PROXY_PORT="${RETHLAS_PROXY_PORT:-38450}"
NOEGRESS_SO="$REPO_ROOT/scripts/net/noegress.so"
LIT_FLAGS=()
CODEX_PRELOAD=""
NET_ALLOW=""
VERIFY_ENDPOINT="${VERIFY_ENDPOINT:-http://127.0.0.1:8091/verify}"
BLIND_RUN="${BLIND_RUN:-1}"
CODEX_SILENT_TIMEOUT_SECONDS="${CODEX_SILENT_TIMEOUT_SECONDS:-900}"
CODEX_POLL_SECONDS="${CODEX_POLL_SECONDS:-30}"

usage() {
  cat <<'EOF'
Usage:
  PROBLEM_FILE=data/path/problem.md PROBLEM_ID=run/id MAX_ATTEMPTS=5 scripts/run_with_retries.sh

Environment:
  PROBLEM_FILE       Path relative to agents/generation, under data/.
  PROBLEM_ID         Output id for memory/results/logs. Defaults to PROBLEM_FILE without data/.md.
  MAX_ATTEMPTS       Number of fresh Codex attempts. Default: 5.
  MODEL              Codex model. Default: gpt-5.5 (deepseek-v4-pro if PROVIDER=deepseek).
  REASONING_EFFORT   Codex reasoning effort. Default: xhigh.
  PROVIDER           Empty (default, gpt) or "deepseek" (DeepSeek V4 via local bridge).
  CONTINUE_ROUNDS    Max same-session resume rounds per attempt when no verified
                     proof yet. Default: 0 (single round, legacy behavior).
  TOKEN_BUDGET       Target output-token budget per attempt. Stated to the model
                     as policy and enforced: continuation rounds stop once the
                     attempt log shows this many tokens used. 0 = no budget talk.
  VERIFY_ENDPOINT    Verification API endpoint. Default: http://127.0.0.1:8091/verify.
  BLIND_RUN          Set RETHLAS_BLIND_RUN for child processes. Default: 1.
  CODEX_SILENT_TIMEOUT_SECONDS
                     Kill an attempt if its log mtime is stale this long.
                     Default: 900. Set 0 to disable.
  CODEX_POLL_SECONDS Heartbeat/staleness poll interval. Default: 30.
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

if [[ ! "$MAX_ATTEMPTS" =~ ^[1-9][0-9]*$ ]]; then
  echo "MAX_ATTEMPTS must be a positive integer: $MAX_ATTEMPTS" >&2
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

if [[ ! "$CONTINUE_ROUNDS" =~ ^[0-9]+$ || ! "$TOKEN_BUDGET" =~ ^[0-9]+$ ]]; then
  echo "CONTINUE_ROUNDS and TOKEN_BUDGET must be nonnegative integers" >&2
  exit 2
fi

if [[ -z "$PROBLEM_ID" ]]; then
  PROBLEM_ID="${PROBLEM_FILE#data/}"
  PROBLEM_ID="${PROBLEM_ID%.md}"
fi

ABS_PROBLEM_FILE="$GENERATION_DIR/$PROBLEM_FILE"
if [[ ! -f "$ABS_PROBLEM_FILE" ]]; then
  echo "Problem file not found: $ABS_PROBLEM_FILE" >&2
  exit 2
fi

RESULT_DIR="$GENERATION_DIR/results/$PROBLEM_ID"
MEMORY_DIR="$GENERATION_DIR/memory/$PROBLEM_ID"
LOG_DIR="$GENERATION_DIR/logs/$PROBLEM_ID"
BLUEPRINT="$RESULT_DIR/blueprint.md"
VERIFIED="$RESULT_DIR/blueprint_verified.md"
MANAGER_LOG="$LOG_DIR/retry_manager.log"
HEARTBEAT="$RESULT_DIR/heartbeat.txt"

mkdir -p "$RESULT_DIR" "$MEMORY_DIR" "$LOG_DIR"

log() {
  local msg="$1"
  printf '[%s] %s\n' "$(date -Iseconds)" "$msg" | tee -a "$MANAGER_LOG"
}

# When a literature cutoff is set, ensure the frozen proxy is up and prepare
# the per-codex flags: LD_PRELOAD egress block + frozen_literature MCP mount.
setup_literature_cutoff() {
  [[ -z "$LITERATURE_CUTOFF" ]] && return 0
  if [[ ! -f "$NOEGRESS_SO" ]]; then
    log "FATAL: literature cutoff set but $NOEGRESS_SO missing (run scripts/net/build.sh)"
    exit 2
  fi
  if ! curl -sS -m3 "http://127.0.0.1:${PROXY_PORT}/health" >/dev/null 2>&1; then
    log "Starting frozen proxy on :${PROXY_PORT} (cutoff=${LITERATURE_CUTOFF})"
    RETHLAS_LITERATURE_CUTOFF="$LITERATURE_CUTOFF" RETHLAS_PROXY_PORT="$PROXY_PORT" \
      RETHLAS_PROXY_LOG="$RESULT_DIR/retrieval_manifest.jsonl" \
      nohup python3 "$REPO_ROOT/scripts/frozen_proxy.py" \
      > "$LOG_DIR/frozen_proxy.log" 2>&1 &
    sleep 2
  fi
  CODEX_PRELOAD="$NOEGRESS_SO"
  # The egress block must still let the model reach its own inference endpoint
  # (we sandbox retrieval, not the model). gpt -> OpenAI/ChatGPT hosts; deepseek
  # goes through the localhost bridge (always allowed) so needs nothing extra.
  if [[ -z "${RETHLAS_NET_ALLOW:-}" ]]; then
    if [[ -z "$PROVIDER" ]]; then
      NET_ALLOW="openai.com,chatgpt.com"
    else
      NET_ALLOW=""
    fi
  else
    NET_ALLOW="$RETHLAS_NET_ALLOW"
  fi
  # The frozen_literature MCP server inherits RETHLAS_PROXY_PORT / cutoff from
  # codex's environment (exported in run_codex_round), so no env config flag.
  # web_search="disabled" is CRITICAL: codex's native web_search tool runs
  # server-side (ChatGPT backend / bridge), outside the egress block, and would
  # otherwise fetch the live post-cutoff proof. This is the only knob that
  # removes it; without it the cutoff leaks.
  LIT_FLAGS=(
    --config 'web_search="disabled"'
    --config 'mcp_servers.frozen_lit.command="python3"'
    --config "mcp_servers.frozen_lit.args=[\"$GENERATION_DIR/mcp/frozen_literature.py\"]"
  )
  log "Literature cutoff active: ${LITERATURE_CUTOFF}; egress allowlist='${NET_ALLOW}'; literature via frozen proxy only"
}

append_memory_json() {
  local channel="$1"
  local json_file="$2"
  local target="$MEMORY_DIR/${channel}.jsonl"
  mkdir -p "$MEMORY_DIR"
  jq -c \
    --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg channel "$channel" \
    --arg source "retry_runner" \
    '. as $record | {timestamp_utc: $ts, channel: $channel, record: ($record + {source: $source})}' \
    "$json_file" >> "$target"
}

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

# Run one codex round (fresh session, or resume when a session id is given),
# streaming to the attempt log under the silent-timeout watchdog.
# Sets ROUND_EXIT (124 on watchdog kill).
run_codex_round() {
  local prompt="$1"
  local attempt_log="$2"
  local resume_sid="$3"
  local -a codex_cmd
  if [[ -n "$resume_sid" ]]; then
    # `codex exec resume` does not accept -C; the session keeps its cwd.
    codex_cmd=(codex exec resume "$resume_sid")
  else
    codex_cmd=(codex exec -C "$GENERATION_DIR")
  fi
  set +e
  (
    cd "$GENERATION_DIR"
    if [[ -n "$CODEX_PRELOAD" ]]; then
      export LD_PRELOAD="$CODEX_PRELOAD"
      export RETHLAS_NET_ALLOW="$NET_ALLOW"
      export RETHLAS_PROXY_PORT="$PROXY_PORT"
      export RETHLAS_LITERATURE_CUTOFF="$LITERATURE_CUTOFF"
    fi
    printf '%s\n' "$prompt" \
      | RETHLAS_BLIND_RUN="$BLIND_RUN" "${codex_cmd[@]}" \
          -m "$MODEL" \
          --config "model_reasoning_effort=\"${REASONING_EFFORT}\"" \
          ${PROVIDER_FLAGS[@]+"${PROVIDER_FLAGS[@]}"} \
          ${LIT_FLAGS[@]+"${LIT_FLAGS[@]}"} \
          --config 'mcp_servers.reasoning_agent.command="python3"' \
          --config 'mcp_servers.reasoning_agent.args=["./mcp/server.py"]' \
          --config "mcp_servers.reasoning_agent.cwd=\"$GENERATION_DIR\"" \
          --dangerously-bypass-approvals-and-sandbox \
          -
  ) >> "$attempt_log" 2>&1 &
  local codex_pid=$!
  local timed_out=0
  local mtime now stale
  while kill -0 "$codex_pid" 2>/dev/null; do
    sleep "$CODEX_POLL_SECONDS"
    date -u +%Y-%m-%dT%H:%M:%SZ > "$HEARTBEAT"
    if [[ "$CODEX_SILENT_TIMEOUT_SECONDS" -gt 0 ]]; then
      mtime="$(stat -c %Y "$attempt_log" 2>/dev/null || date +%s)"
      now="$(date +%s)"
      stale=$((now - mtime))
      if [[ "$stale" -ge "$CODEX_SILENT_TIMEOUT_SECONDS" ]]; then
        printf '[%s] log silent for %ss; terminating Codex pid %s\n' \
          "$(date -Iseconds)" "$stale" "$codex_pid" >> "$attempt_log"
        log "Codex log silent for ${stale}s; timeout=${CODEX_SILENT_TIMEOUT_SECONDS}s"
        kill_tree "$codex_pid" TERM
        sleep 5
        kill_tree "$codex_pid" KILL
        timed_out=1
        break
      fi
    fi
  done
  wait "$codex_pid"
  ROUND_EXIT=$?
  if [[ "$timed_out" -eq 1 ]]; then
    ROUND_EXIT=124
  fi
  set -e
}

# Set to 1 only when THIS controller promoted the blueprint after a real
# verifier verdict. Agent-written blueprint_verified.md files are not trusted.
PROMOTED=0

# If the agent wrote blueprint_verified.md itself (no controller promotion),
# quarantine it and fall back to verifying its content as a normal blueprint.
vet_agent_verified() {
  local attempt="$1"
  if [[ -f "$VERIFIED" && "$PROMOTED" -ne 1 ]]; then
    log "Attempt ${attempt}: agent wrote blueprint_verified.md without controller verification; quarantining"
    if [[ ! -s "$BLUEPRINT" ]]; then
      cp "$VERIFIED" "$BLUEPRINT"
    fi
    mv "$VERIFIED" "$RESULT_DIR/blueprint_selfpromoted_attempt_${attempt}.md"
  fi
}

verify_blueprint() {
  local attempt="$1"
  local verify_json="$RESULT_DIR/verification_attempt_${attempt}.json"
  local verify_tmp="${verify_json}.tmp"

  if [[ ! -s "$BLUEPRINT" ]]; then
    return 1
  fi

  log "Attempt ${attempt}: blueprint exists; calling verifier"
  local statement
  statement="$(python3 "$REPO_ROOT/scripts/extract_target_statement.py" "$ABS_PROBLEM_FILE")"
  if jq -n --arg statement "$statement" --rawfile proof "$BLUEPRINT" \
      '{statement: $statement, proof: $proof}' \
      | curl -sS -X POST "$VERIFY_ENDPOINT" \
          -H "Content-Type: application/json" \
          --data-binary @- \
          > "$verify_tmp"; then
    mv "$verify_tmp" "$verify_json"
  else
    rm -f "$verify_tmp"
    log "Attempt ${attempt}: verifier HTTP call failed"
    jq -n --arg attempt "$attempt" \
      '{attempt: ($attempt | tonumber), verdict: "verifier_call_failed", repair_hints: "Verifier HTTP call failed."}' \
      > "$verify_json"
  fi

  append_memory_json "verification_reports" "$verify_json"

  local verdict
  verdict="$(jq -r '.verdict // "missing"' "$verify_json" 2>/dev/null || echo "invalid")"
  log "Attempt ${attempt}: verifier verdict=${verdict}"

  if [[ "$verdict" == "correct" ]]; then
    cp "$BLUEPRINT" "$VERIFIED"
    PROMOTED=1
    log "Attempt ${attempt}: promoted blueprint.md to blueprint_verified.md"
    return 0
  fi

  return 1
}

audit_blind_sources() {
  local attempt="$1"
  local attempt_log="$2"
  local audit_json="$RESULT_DIR/blind_source_audit_attempt_${attempt}.json"
  local verify_json="$RESULT_DIR/verification_attempt_${attempt}.json"

  if [[ "$BLIND_RUN" != "1" ]]; then
    return 0
  fi

  if "$REPO_ROOT/scripts/audit_blind_run.py" \
      --problem-file "$ABS_PROBLEM_FILE" \
      --problem-id "$PROBLEM_ID" \
      --log "$attempt_log" \
      --output "$audit_json"; then
    log "Attempt ${attempt}: blind source audit passed"
    return 0
  fi

  log "Attempt ${attempt}: blind source audit failed"
  jq -n \
    --arg attempt "$attempt" \
    --slurpfile audit "$audit_json" \
    '{
      attempt: ($attempt | tonumber),
      verdict: "blind_source_violation",
      repair_hints: "The attempt violated the blind source policy. Do not read .agents/skills/*.md, scan source_templates directories, or mention unlisted source template files; use only the exact files listed by the problem.",
      audit: $audit[0]
    }' > "$verify_json"
  append_memory_json "verification_reports" "$verify_json"
  return 1
}

budget_clause() {
  if [[ "$TOKEN_BUDGET" -gt 0 ]]; then
    printf '%s' "Run budget policy: this attempt has a total budget of roughly ${TOKEN_BUDGET} output tokens, and the controller will keep resuming this session until that budget is spent. Spend the full budget on mathematics. Do not write a final proof-attempt or obstruction report while budget remains: a wrap-up submitted early counts as a failed attempt. When one branch is exhausted, record it in failed_paths and attack the next strongest branch at full depth instead of summarizing."
  fi
}

rigor_clause() {
  cat <<'EOF'
Rigor policy (hard rules):
(1) Compute before you trust. You have shell access; for every load-bearing lemma that admits finite or numerical testing, write a short script and try to falsify it on small cases BEFORE building on it. A surviving lemma earns your proof effort; a falsified one saves the whole budget — record the counterexample in counterexamples and branch immediately. Record what you tested in toy_examples.
(2) Prove or retrieve, never just cite. A load-bearing claim must be either proven in the blueprint, or retrieved and quoted through the literature tools with an exact source the referee can check. A citation you cannot retrieve is an unproven lemma: prove it from scratch or treat the route as blocked. Do not paper over the hard step with a plausible-sounding reference.
(3) Be honest about being stuck. Never write blueprint_verified.md yourself; only the controller promotes. If a specific obstacle blocks you, write a precise statement of the missing lemma and what you tried into subgoals (mark it stuck=true) instead of submitting a proof that glosses over it — a localized honest gap is repairable, a hidden one is not.
(4) Attack gaps in THIS session. If a non-trivial lemma, computation, or reduction appears necessary, attempt to prove the lemma, run the computation, or carry out the reduction now, before listing it as a gap. Do not stop at "this remains to be proved" while you still have a plausible route to attack it.
(5) If the problem statement is ambiguous, inconsistent, or likely contains a typo, open the blueprint with a short section "Problem statement and interpretation" stating the cleanest faithful reading and your assumptions; do not silently solve a different problem.
(6) If essential gaps remain when you write the blueprint, end it with a section "Remaining open issues" listing, for each gap: (a) what it is mathematically, (b) where in the blueprint it appears, (c) what you tried, (d) what would close it (a specific computation, an alternative approach, a missing reference). This section is a work order for the next round, not an excuse to stop.
EOF
}

build_continue_prompt() {
  local round="$1"
  local hints="$2"
  local hints_clause=""
  if [[ -n "$hints" ]]; then
    hints_clause="Your latest blueprint was verified WRONG by the referee. Repair hints: ${hints} Address each complaint point by point, in place, like a paper revision: either repair the proof or record the route in failed_paths and branch to a different architecture. If the referee doubts a specific estimate or lemma, run a numerical/finite spot-check on it before reworking the proof around it."
  fi
  cat <<EOF
Continuation round ${round} for problem_id=${PROBLEM_ID} (same session; your earlier work is above). Budget remains, and the run policy is to spend the full token budget on mathematics. Do not stop at a proof-attempt or obstruction report. ${hints_clause} Re-read your branch_states and failed_paths, then either push your strongest open branch to explicit formulas and a complete construction, or open a genuinely different architecture that is not already in failed_paths. Update memory channels as you work and rewrite results/${PROBLEM_ID}/blueprint.md whenever it improves. $(rigor_clause) $(budget_clause)
EOF
}

tokens_spent() {
  # pipefail-safe: a log with no "tokens used" lines must yield 0, not kill
  # the script under set -e.
  { grep -A1 '^tokens used$' "$1" 2>/dev/null || true; } \
    | { grep -oE '^[0-9,]+$' || true; } | tr -d ',' | awk '{s+=$1} END {print s+0}'
}

build_prompt() {
  local attempt="$1"
  local blind_clause=""
  local startup_clause=""
  if [[ "$BLIND_RUN" == "1" ]]; then
    blind_clause="The problem is a blind benchmark; obey its blindness rules exactly. If the problem lists allowed source_templates, that list is the complete local background allowlist. Do not read .agents/skills/*.md, sibling memory/results, target-proof notes, local notes, web pages, or arXiv unless the problem explicitly names those exact sources. Do not run find/ls/rg/grep over source_templates; open only exact listed files by path if needed."
    startup_clause="If MCP memory tools are unavailable, create the local fallback memory files once and then immediately begin theorem work. Do not spend multiple iterations inspecting skill docs or printing initialization diffs. Do not read .agents/skills/*.md at any time during this blind run unless the problem file explicitly lists that exact skill file. Do not launch recursive/subgoal agents. Do not read memory/ or results/ for any other problem_id; only use memory/${PROBLEM_ID}, results/${PROBLEM_ID}, and the current problem file unless a later attempt prompt explicitly asks you to audit your own prior artifacts. Before any further setup, write at least one mathematical branch choice to branch_states and one real plan/proof record to subgoals or proof_steps. If the prompt asks for asymptotic formulas, explicit inequalities, or parameter comparisons, then that first proof_steps record must already contain at least one concrete displayed formula or inequality, not just a heuristic summary."
  else
    blind_clause="Use the retrieval policy in AGENTS.md and in the problem statement."
    startup_clause="If MCP memory tools are unavailable, create the local fallback memory files once and then immediately begin theorem work. Do not spend multiple iterations inspecting skill docs or printing initialization diffs. Do not read .agents/skills/*.md before the first branch choice unless blocked on a missing contract detail. Do not read memory/ or results/ for any other problem_id; only use memory/${PROBLEM_ID}, results/${PROBLEM_ID}, and the current problem file unless a later attempt prompt explicitly asks you to audit your own prior artifacts. Before any further setup, write at least one mathematical branch choice to branch_states and one real plan/proof record to subgoals or proof_steps. If the prompt asks for asymptotic formulas, explicit inequalities, or parameter comparisons, then that first proof_steps record must already contain at least one concrete displayed formula or inequality, not just a heuristic summary."
  fi

  if [[ "$attempt" -eq 1 ]]; then
    cat <<EOF
Use AGENTS.md exactly to solve the math problem in ${PROBLEM_FILE}. Use problem_id=${PROBLEM_ID}. ${blind_clause} ${startup_clause} $(rigor_clause) $(budget_clause)
EOF
    return
  fi

  cat <<EOF
Attempt ${attempt}/${MAX_ATTEMPTS} for ${PROBLEM_FILE}. Use problem_id=${PROBLEM_ID}.

Continue from the existing memory and results for this problem. The previous attempt did not produce an acceptable verified proof.

Before choosing the next route, read and use these files if they exist:
- memory/${PROBLEM_ID}/failed_paths.jsonl
- memory/${PROBLEM_ID}/subgoals.jsonl
- memory/${PROBLEM_ID}/proof_steps.jsonl
- memory/${PROBLEM_ID}/branch_states.jsonl
- memory/${PROBLEM_ID}/verification_reports.jsonl
- results/${PROBLEM_ID}/blueprint.md

Do not repeat failed strategies. If the previous blueprint is promising, audit and repair it. If the previous direction is invalid, branch away and record exactly why. If the same lemma has failed verification more than once, your FIRST action this attempt is a computational spot-check of that lemma on small cases: falsified means abandon the route now; surviving means concentrate the entire budget on proving exactly that lemma. ${blind_clause} ${startup_clause} $(rigor_clause) $(budget_clause)
EOF
}

setup_literature_cutoff

log "Starting retry run: problem_id=${PROBLEM_ID}, problem_file=${PROBLEM_FILE}, attempts=${MAX_ATTEMPTS}, model=${MODEL}, effort=${REASONING_EFFORT}, blind=${BLIND_RUN}, silent_timeout=${CODEX_SILENT_TIMEOUT_SECONDS}, poll=${CODEX_POLL_SECONDS}, cutoff=${LITERATURE_CUTOFF:-none}"

for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
  vet_agent_verified "$attempt"
  if [[ -f "$VERIFIED" ]]; then
    log "Verified artifact already exists: $VERIFIED"
    exit 0
  fi

  attempt_log="$LOG_DIR/attempt_${attempt}.md"
  prompt="$(build_prompt "$attempt")"

  log "Attempt ${attempt}/${MAX_ATTEMPTS}: launching Codex; log=$attempt_log"
  {
    printf 'started_at: %s\n' "$(date -Iseconds)"
    printf 'problem_id: %s\n' "$PROBLEM_ID"
    printf 'problem_file: %s\n' "$PROBLEM_FILE"
    printf 'model: %s\n' "$MODEL"
    [[ -n "$PROVIDER" ]] && printf 'provider: %s\n' "$PROVIDER"
    printf 'reasoning_effort: %s\n\n' "$REASONING_EFFORT"
  } > "$attempt_log"

  run_codex_round "$prompt" "$attempt_log" ""
  code=$ROUND_EXIT

  log "Attempt ${attempt}/${MAX_ATTEMPTS}: Codex exited with code ${code}"

  last_verified_mtime=0
  for cont in $(seq 1 "$CONTINUE_ROUNDS"); do
    vet_agent_verified "$attempt"
    [[ "$PROMOTED" -eq 1 ]] && break
    hints=""
    if [[ -s "$BLUEPRINT" ]]; then
      bp_mtime="$(stat -c %Y "$BLUEPRINT")"
      if [[ "$bp_mtime" -ne "$last_verified_mtime" ]]; then
        last_verified_mtime=$bp_mtime
        if verify_blueprint "$attempt"; then
          exit 0
        fi
        hints="$(jq -r '.repair_hints // empty' \
          "$RESULT_DIR/verification_attempt_${attempt}.json" 2>/dev/null | head -c 1500)"
      fi
    fi
    spent="$(tokens_spent "$attempt_log")"
    if [[ "$TOKEN_BUDGET" -gt 0 && "$spent" -ge "$TOKEN_BUDGET" ]]; then
      log "Attempt ${attempt}: token budget spent (${spent}/${TOKEN_BUDGET}); ending continuation"
      break
    fi
    session_id="$( { grep -m1 'session id:' "$attempt_log" || true; } \
      | { grep -oE '[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}' || true; } )"
    if [[ -z "$session_id" ]]; then
      log "Attempt ${attempt}: no session id in log; cannot resume"
      break
    fi
    log "Attempt ${attempt}: continuation round ${cont}/${CONTINUE_ROUNDS} (tokens so far: ${spent}); resuming session ${session_id}"
    printf '\n[continuation round %s at %s]\n' "$cont" "$(date -Iseconds)" >> "$attempt_log"
    run_codex_round "$(build_continue_prompt "$cont" "$hints")" "$attempt_log" "$session_id"
    log "Attempt ${attempt}: continuation round ${cont} exited with code ${ROUND_EXIT}"
  done

  if ! audit_blind_sources "$attempt" "$attempt_log"; then
    if [[ "$attempt" -lt "$MAX_ATTEMPTS" ]]; then
      log "Attempt ${attempt}/${MAX_ATTEMPTS}: source audit failed; retrying after short pause"
      sleep 5
      continue
    fi
    continue
  fi

  if [[ -f "$BLUEPRINT" ]]; then
    cp "$BLUEPRINT" "$RESULT_DIR/blueprint_attempt_${attempt}.md"
  fi

  vet_agent_verified "$attempt"
  if [[ -f "$VERIFIED" ]]; then
    log "Attempt ${attempt}/${MAX_ATTEMPTS}: controller-verified artifact present"
    exit 0
  fi

  if [[ -s "$BLUEPRINT" && "$(stat -c %Y "$BLUEPRINT")" -ne "$last_verified_mtime" ]]; then
    if verify_blueprint "$attempt"; then
      exit 0
    fi
  fi

  if [[ "$attempt" -lt "$MAX_ATTEMPTS" ]]; then
    log "Attempt ${attempt}/${MAX_ATTEMPTS}: no verified proof; retrying after short pause"
    sleep 5
  fi
done

log "Exhausted ${MAX_ATTEMPTS} attempts without blueprint_verified.md"
exit 1

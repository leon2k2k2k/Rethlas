"""Shared synthetic-repo builder for pytest and Playwright e2e."""
import hashlib
import json
import os
import time
from pathlib import Path

SESSION_A = "01900000-0000-7000-8000-00000000000a"
SESSION_B = "01900000-0000-7000-8000-00000000000b"
SESSION_REF = "01900000-0000-7000-8000-00000000000f"

PROBLEM_MD = """# Fixture problem: toy theorem

## Background

Some context with math \\(x^2\\).

## Target Statement

For every integer \\(n\\), \\(n + 0 = n\\).

## Required analysis

Do things.
"""

TARGET_STATEMENT = "For every integer \\(n\\), \\(n + 0 = n\\)."


def _attempt_log(problem_id, session_id):
    return (
        f"started_at: 2026-06-09T01:00:00+08:00\n"
        f"problem_id: {problem_id}\n"
        f"problem_file: data/{problem_id}.md\n"
        f"model: gpt-5.5\n"
        f"reasoning_effort: xhigh\n\n"
        f"OpenAI Codex v0.137.0\n--------\n"
        f"workdir: /x\nmodel: gpt-5.5\n"
        f"session id: {session_id}\n--------\n"
        f"user\nSolve it.\ncodex\nDone, see blueprint.\n"
    )


def _rollout_lines(session_id):
    recs = [
        {"timestamp": "t", "type": "session_meta",
         "payload": {"id": session_id, "cwd": "/x", "model_provider": "openai",
                     "cli_version": "0.137.0", "timestamp": "2026-06-09T01:00:00Z"}},
        {"type": "response_item", "payload": {"type": "message", "role": "user",
                                              "content": [{"type": "input_text", "text": "Solve \\(x\\)."}]}},
        {"type": "response_item", "payload": {"type": "reasoning",
                                              "summary": [{"type": "summary_text", "text": "**Thinking** about \\(x\\)"}]}},
        # parallel batch: two calls then two outputs
        {"type": "response_item", "payload": {"type": "function_call", "name": "exec_command",
                                              "call_id": "call_1", "arguments": "{\"cmd\":\"ls\"}"}},
        {"type": "response_item", "payload": {"type": "function_call", "name": "exec_command",
                                              "call_id": "call_2", "arguments": "{\"cmd\":\"pwd\"}"}},
        {"type": "response_item", "payload": {"type": "function_call_output",
                                              "call_id": "call_1", "output": "a b c"}},
        {"type": "response_item", "payload": {"type": "function_call_output",
                                              "call_id": "call_2", "output": "/x"}},
        {"type": "event_msg", "payload": {"type": "context_compacted"}},
        {"type": "response_item", "payload": {"type": "message", "role": "assistant",
                                              "content": [{"type": "output_text", "text": "Proof: \\(n+0=n\\)."}]}},
    ]
    return "".join(json.dumps(r) + "\n" for r in recs)


def build_repo(root: Path):
    gen = root / "agents" / "generation"
    ver = root / "agents" / "verification"

    # --- verified run with full artifacts
    pid = "alg/fix_verified"
    (gen / "logs" / "alg" / "fix_verified").mkdir(parents=True)
    (gen / "logs" / "alg" / "fix_verified" / "attempt_1.md").write_text(_attempt_log(pid, SESSION_A))
    rdir = gen / "results" / "alg" / "fix_verified"
    rdir.mkdir(parents=True)
    (rdir / "blueprint.md").write_text("# theorem\n\\(n+0=n\\)\n")
    (rdir / "blueprint_verified.md").write_text("# theorem\n\\(n+0=n\\)\n")
    (rdir / "verification_attempt_1.json").write_text(json.dumps({
        "verification_report": {"summary": "The proof is correct.", "critical_errors": []},
        "verdict": "correct", "repair_hints": None}))
    (gen / "data" / "alg").mkdir(parents=True)
    (gen / "data" / "alg" / "fix_verified.md").write_text(PROBLEM_MD)
    mdir = gen / "memory" / "alg" / "fix_verified"
    mdir.mkdir(parents=True)
    (mdir / "branch_states.jsonl").write_text(
        json.dumps({"timestamp_utc": "2026-06-09T01:00:00+00:00", "channel": "branch_states",
                    "record": {"branch_id": "root", "state": {"status": "active"}}}) + "\n")

    # --- running run (fresh heartbeat)
    pid2 = "alg/fix_running"
    (gen / "logs" / "alg" / "fix_running").mkdir(parents=True)
    (gen / "logs" / "alg" / "fix_running" / "attempt_1.md").write_text(_attempt_log(pid2, SESSION_B))
    rdir2 = gen / "results" / "alg" / "fix_running"
    rdir2.mkdir(parents=True)
    (rdir2 / "heartbeat.txt").write_text("now")
    # heartbeat mtime = now → running

    # --- dead run (watchdog kill marker, old mtimes)
    pid3 = "alg/fix_dead"
    d3 = gen / "logs" / "alg" / "fix_dead"
    d3.mkdir(parents=True)
    log3 = d3 / "attempt_1.md"
    log3.write_text(_attempt_log(pid3, SESSION_B) +
                    "\n[2026-06-09] attempt 1: log silent for 1800s; terminating Codex pid 123\n")
    old = time.time() - 3600
    os.utime(log3, (old, old))
    rdir3 = gen / "results" / "alg" / "fix_dead"
    rdir3.mkdir(parents=True)
    (rdir3 / "blueprint.md").write_text("# partial\n")

    # --- results-only run
    (gen / "results" / "alg" / "fix_resultsonly").mkdir(parents=True)
    (gen / "results" / "alg" / "fix_resultsonly" / "blueprint.md").write_text("x")

    # --- iter-style run (clone format)
    d5 = gen / "logs" / "geo" / "fix_iter" / "iter"
    d5.mkdir(parents=True)
    for i in range(3):
        (d5 / f"fix_iter_iter_{i}.md").write_text(
            f"Reading additional input from stdin...\nOpenAI Codex v0.138.0\n--------\n"
            f"model: gpt-5.5\nsession id: {SESSION_B}\n--------\nuser\ngo\n")
    (gen / "data" / "geo").mkdir(parents=True)
    (gen / "data" / "geo" / "fix_iter.md").write_text(PROBLEM_MD)

    # --- discovery batch with route cards (results-only)
    bdir = gen / "results" / "geo" / "fix_batch"
    (bdir / "sample_001").mkdir(parents=True)
    (bdir / "batch_manifest.json").write_text(json.dumps({"batch_id": "geo/fix_batch"}))
    (bdir / "sample_001" / "route_card.json").write_text(json.dumps({
        "problem_id": "geo/fix_batch", "stage": "number_field_source_identified",
        "construction_family": "fixture family", "confidence": 0.8}))

    # --- editable configs
    (gen / "AGENTS.md").write_text("# Math Reasoning Agent\n\nFixture instructions.\n")
    (gen / ".codex").mkdir(exist_ok=True)
    (gen / ".codex" / "config.toml").write_text('model = "gpt-5.5"\n')

    # --- rollouts
    sess = root / "sessions" / "2026" / "06" / "09"
    sess.mkdir(parents=True)
    (sess / f"rollout-2026-06-09T01-00-00-{SESSION_A}.jsonl").write_text(_rollout_lines(SESSION_A))
    (sess / f"rollout-2026-06-09T01-05-00-{SESSION_B}.jsonl").write_text(_rollout_lines(SESSION_B))

    # --- verification agent with hash-named referee run
    h = hashlib.sha256(TARGET_STATEMENT.encode()).hexdigest()[:12]
    vdir = ver / "results" / f"20260609T010203Z_{h}"
    vdir.mkdir(parents=True)
    (vdir / "log.md").write_text(
        "started_at_utc: 2026-06-09T01:02:03+00:00\n"
        "command: codex exec ... 'Run_id: x. Statement: ... Proof: ...'\n"
        "OpenAI Codex v0.137.0\n--------\nmodel: gpt-5.5\n"
        f"session id: {SESSION_REF}\n--------\n"
        "user\nverify\ncodex\nChecked \\(n+0=n\\): holds.\n")
    (vdir / "verification.json").write_text(json.dumps({
        "verification_report": {"summary": "Fixture verified."}, "verdict": "correct"}))

    # age everything (fresh mtimes read as "running"), then refresh the one
    # run that should be live
    old = time.time() - 3600
    for p in root.rglob("*"):
        os.utime(p, (old, old))
    hb = gen / "results" / "alg" / "fix_running" / "heartbeat.txt"
    now = time.time()
    os.utime(hb, (now, now))
    return root



#!/usr/bin/env python3
"""Rethlas pipeline: one coherent entrypoint over every stage.

A thin, legible driver on top of the existing stage scripts in scripts/. It
replaces the scattered 28-env-var invocations and the old pool-sweep shell
(rethlas-run-manager.sh) with one config file per campaign and one unified
state file you can read at a glance.

Subcommands (run `pipeline.py <cmd> -h` for each):
  pool      Sweep a queue of problems: N concurrent attack->verify->repair runs,
            auto-advancing through the queue, harvested into one scoreboard.
  discover  Discovery -> triage -> promotion chain (the research/exploration track).
  triage    Score the route cards in a discovery batch dir.
  promote   Turn triaged route cards into new problem files + launch scripts.
  status    Print the scoreboard for a campaign from its state file.

Campaign configs live in campaigns/<name>.yaml. State lands in
pipeline_runs/<name>/ (state.json + harvest.md).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent
GEN_DIR = REPO_ROOT / "agents" / "generation"
SCRIPTS = REPO_ROOT / "scripts"
RUNS_DIR = REPO_ROOT / "pipeline_runs"

# How classify_blueprint_status.py's statuses roll up for the scoreboard.
STATUS_GROUPS = {
    "verified_final": "verified",
    "verified_unpromoted": "verified",
    "verified_conditioning": "partial",
    "unverified_blueprint": "attempted",
    "blueprint_no_verdict": "attempted",
    "no_blueprint": "failed",
    "already_verified": "verified",
    "dry_run": "dry_run",
    "error": "error",
}
SCOREBOARD_ORDER = ("verified", "partial", "attempted", "failed", "dry_run", "error", "other")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_config(path: Path) -> dict:
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cfg.setdefault("name", path.stem)
    cfg.setdefault("mode", "pool")
    return cfg


def problem_id_for(problem_file: str) -> str:
    pid = problem_file
    if pid.startswith("data/"):
        pid = pid[len("data/"):]
    if pid.endswith(".md"):
        pid = pid[: -len(".md")]
    return pid


def classify(result_dir: Path) -> dict:
    """Run classify_blueprint_status.py; it is the source of truth for outcome."""
    if not result_dir.is_dir():
        return {"status": "no_blueprint", "verification_verdict": ""}
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "classify_blueprint_status.py"), str(result_dir)],
        capture_output=True, text=True,
    )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"status": "error", "stderr": proc.stderr.strip()[:500]}


def write_state(name: str, state: dict) -> Path:
    run_dir = RUNS_DIR / name
    run_dir.mkdir(parents=True, exist_ok=True)
    out = run_dir / "state.json"
    out.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


def read_state(name: str) -> dict | None:
    out = RUNS_DIR / name / "state.json"
    return json.loads(out.read_text(encoding="utf-8")) if out.is_file() else None


# --------------------------------------------------------------------------- #
# pool  — the queue sweep (N concurrent attack->verify->repair, auto-advance)
# --------------------------------------------------------------------------- #
def solve_env(cfg: dict, problem_file: str) -> dict:
    env = os.environ.copy()
    env["PROBLEM_FILE"] = problem_file
    env["MAX_ATTEMPTS"] = str(cfg.get("max_attempts", 5))
    env["MODEL"] = str(cfg.get("model", "gpt-5.5"))
    env["REASONING_EFFORT"] = str(cfg.get("reasoning_effort", "xhigh"))
    env["PROVIDER"] = str(cfg.get("provider", ""))
    env["VERIFY_ENDPOINT"] = str(cfg.get("verify_endpoint", "http://127.0.0.1:8091/verify"))
    env["BLIND_RUN"] = str(cfg.get("blind_run", 1))
    env["CODEX_SILENT_TIMEOUT_SECONDS"] = str(cfg.get("codex_silent_timeout_seconds", 900))
    if cfg.get("literature_cutoff"):
        env["RETHLAS_LITERATURE_CUTOFF"] = str(cfg["literature_cutoff"])
    return env


def load_queue(cfg: dict) -> list[str]:
    """Problems come from the config's `problems:` list, or a `queue:` file path
    (one problem markdown path per line, # comments allowed)."""
    if cfg.get("problems"):
        return list(cfg["problems"])
    qf = cfg.get("queue")
    if qf:
        lines = (REPO_ROOT / qf).read_text(encoding="utf-8").splitlines()
        return [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]
    return []


def cmd_pool(cfg: dict, dry_run: bool) -> int:
    problems = load_queue(cfg)
    if not problems:
        print("config has no 'problems:' list or 'queue:' file", file=sys.stderr)
        return 2
    concurrency = int(cfg.get("concurrency", 2))
    lock = threading.Lock()
    # Keyed by problem_id so re-runs are idempotent and status is live.
    records: dict[str, dict] = {
        problem_id_for(pf): {"problem_file": pf, "problem_id": problem_id_for(pf),
                             "status": "queued"}
        for pf in problems
    }
    state = {"name": cfg["name"], "mode": "pool", "concurrency": concurrency,
             "started_at": now(), "config": cfg, "results": list(records.values())}

    def flush():
        state["results"] = list(records.values())
        write_state(cfg["name"], state)

    print(f"== rethlas pool: {cfg['name']}  ({len(problems)} problems, "
          f"concurrency={concurrency}) ==\n")
    flush()

    def work(pf: str) -> None:
        pid = problem_id_for(pf)
        result_dir = GEN_DIR / "results" / pid
        # Idempotent: skip problems already verified.
        if (result_dir / "blueprint_verified.md").is_file() and not dry_run:
            v = classify(result_dir)
            with lock:
                records[pid].update(status="already_verified",
                                    verification_verdict=v.get("verification_verdict", ""),
                                    blueprint=v.get("blueprint", ""))
                print(f"  [skip] {pid}: already verified")
                flush()
            return
        if dry_run:
            with lock:
                records[pid].update(status="dry_run")
                print(f"  [dry-run] would attack {pf}")
                flush()
            return
        with lock:
            records[pid].update(status="running", started_at=now())
            print(f"  [start] {pid}")
            flush()
        proc = subprocess.run([str(SCRIPTS / "run_with_retries.sh")],
                              cwd=REPO_ROOT, env=solve_env(cfg, pf))
        v = classify(result_dir)
        with lock:
            records[pid].update(
                status=v.get("status", "error"),
                verification_verdict=v.get("verification_verdict", ""),
                blueprint=v.get("blueprint", ""),
                verification_path=v.get("verification_path", ""),
                exit_code=proc.returncode, finished_at=now(),
            )
            print(f"  [done]  {pid}: {records[pid]['status']}")
            flush()

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as ex:
        futs = [ex.submit(work, pf) for pf in problems]
        for f in as_completed(futs):
            f.result()

    state["finished_at"] = now()
    flush()
    print_scoreboard(state)
    write_harvest(cfg["name"], state)
    return 0


# --------------------------------------------------------------------------- #
# discover / triage / promote  — the exploration track (thin wrappers)
# --------------------------------------------------------------------------- #
def cmd_discover(cfg: dict, dry_run: bool) -> int:
    env = os.environ.copy()
    passthrough = {
        "PROBLEM_FILE": "problem_file", "BATCH_ID": "batch_id", "SAMPLES": "samples",
        "PARALLEL": "parallel", "MODEL": "model", "REASONING_EFFORT": "reasoning_effort",
        "DISCOVERY_PROFILE": "discovery_profile",
        "AUTO_LAUNCH_PROMOTION": "auto_launch_promotion",
        "AUTO_PROMOTE_OBSTRUCTION": "auto_promote_obstruction",
        "AUTO_LAUNCH_OBSTRUCTION": "auto_launch_obstruction",
    }
    for env_key, cfg_key in passthrough.items():
        if cfg_key in cfg and cfg[cfg_key] != "":
            val = cfg[cfg_key]
            env[env_key] = "1" if val is True else "0" if val is False else str(val)
    script = SCRIPTS / "run_unit_distance_cot_pipeline.sh"
    set_knobs = {k: env[k] for k in passthrough if k in env and env[k]}
    print(f"== rethlas discover: {cfg['name']} ==")
    print(f"   stage script: {script.relative_to(REPO_ROOT)}")
    print(f"   knobs: {set_knobs}")
    if dry_run:
        print("   DRY-RUN: not launching.")
        write_state(cfg["name"], {"name": cfg["name"], "mode": "discover",
                                  "status": "dry_run", "knobs": set_knobs, "at": now()})
        return 0
    proc = subprocess.run([str(script)], cwd=REPO_ROOT, env=env)
    write_state(cfg["name"], {"name": cfg["name"], "mode": "discover",
                              "exit_code": proc.returncode, "knobs": set_knobs,
                              "batch_id": env.get("BATCH_ID", ""), "at": now()})
    return proc.returncode


def cmd_triage(batch_dir: Path) -> int:
    print(f"== triage: {batch_dir} ==")
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "triage_route_cards.py"), str(batch_dir),
         "--fail-on-invalid"], cwd=REPO_ROOT).returncode


def cmd_promote(batch_dir: Path, launch: bool) -> int:
    print(f"== promote: {batch_dir} (launch={launch}) ==")
    args = [sys.executable, str(SCRIPTS / "apply_promotion_decision.py"), str(batch_dir)]
    if launch:
        args.append("--launch")
    return subprocess.run(args, cwd=REPO_ROOT).returncode


# --------------------------------------------------------------------------- #
# status / harvest
# --------------------------------------------------------------------------- #
def group_counts(results: list[dict]) -> dict[str, int]:
    groups: dict[str, int] = {}
    for r in results:
        g = STATUS_GROUPS.get(r.get("status", "error"), "other")
        groups[g] = groups.get(g, 0) + 1
    return groups


def print_scoreboard(state: dict) -> None:
    results = state.get("results", [])
    if not results:
        print(f"\n[{state.get('name')}] mode={state.get('mode')} "
              f"status={state.get('status', 'n/a')}")
        return
    groups = group_counts(results)
    print(f"\n== scoreboard: {state.get('name')} ==")
    print(f"   total problems : {len(results)}")
    for g in SCOREBOARD_ORDER:
        if groups.get(g):
            print(f"   {g:<14}: {groups[g]}")
    notable = [r for r in results if STATUS_GROUPS.get(r.get("status")) in ("verified", "partial")]
    if notable:
        print("\n   notable (candidates, pending human review):")
        for r in notable:
            print(f"     - {r['problem_id']}  [{r['status']}]")


def write_harvest(name: str, state: dict) -> Path:
    """A POOL_HARVEST-style markdown summary, for the writeup/registry."""
    results = state.get("results", [])
    groups = group_counts(results)
    lines = [f"# Pool harvest: {name}", "",
             f"- finished: {state.get('finished_at', 'n/a')}",
             f"- total: {len(results)}"]
    for g in SCOREBOARD_ORDER:
        if groups.get(g):
            lines.append(f"- {g}: {groups[g]}")
    lines += ["", "## Results", "",
              "| problem | status | verdict | blueprint |", "|---|---|---|---|"]
    for r in sorted(results, key=lambda x: x.get("status", "")):
        lines.append(f"| {r['problem_id']} | {r.get('status','')} | "
                     f"{r.get('verification_verdict','')} | {r.get('blueprint','')} |")
    lines += ["", "_A 'verified' result is a candidate: verifier-accepted, "
              "pending human review before it counts as a real result._", ""]
    out = RUNS_DIR / name / "harvest.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nharvest: {out}")
    return out


def cmd_status(name: str) -> int:
    state = read_state(name)
    if state is None:
        print(f"no state for campaign '{name}' (looked in "
              f"{RUNS_DIR / name / 'state.json'})", file=sys.stderr)
        return 1
    print_scoreboard(state)
    return 0


# --------------------------------------------------------------------------- #
def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    pp = sub.add_parser("pool", help="sweep a queue: N concurrent attack->verify->repair")
    pp.add_argument("config", type=Path)
    pp.add_argument("--dry-run", action="store_true", help="print what would run; no Codex")

    dp = sub.add_parser("discover", help="discovery -> triage -> promotion chain")
    dp.add_argument("config", type=Path)
    dp.add_argument("--dry-run", action="store_true", help="print what would run; no Codex")

    tp = sub.add_parser("triage", help="score the route cards in a discovery batch dir")
    tp.add_argument("batch_dir", type=Path)

    rp = sub.add_parser("promote", help="turn triaged route cards into problem files")
    rp.add_argument("batch_dir", type=Path)
    rp.add_argument("--launch", action="store_true", help="also launch the generated repair run")

    st = sub.add_parser("status", help="print the scoreboard for a campaign")
    st.add_argument("name", help="campaign name (config stem)")

    args = p.parse_args()
    if args.cmd == "status":
        return cmd_status(args.name)
    if args.cmd == "triage":
        return cmd_triage(args.batch_dir)
    if args.cmd == "promote":
        return cmd_promote(args.batch_dir, args.launch)

    cfg = load_config(args.config)
    if args.cmd == "discover":
        return cmd_discover(cfg, args.dry_run)
    return cmd_pool(cfg, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())

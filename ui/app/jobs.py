"""Job manager: launch, track, and stop pipeline scripts.

Jobs run detached in their own process group (so stop() can kill the whole
codex/script tree, mirroring run_with_retries' kill_tree). The registry is
persisted to <data_dir>/jobs.json and survives server restarts; a waiter
thread records the exit code while the server lives, and after a restart
liveness falls back to a pgid probe.
"""
import json
import os
import re
import signal
import subprocess
import threading
import time
import uuid
from pathlib import Path

from fastapi import HTTPException

from .config import Settings

_SAFE_REL = re.compile(r"^[A-Za-z0-9._/-]+$")


def _check_rel_path(value: str, suffix: str = None) -> str:
    if not value or not _SAFE_REL.match(value) or ".." in value or value.startswith("/"):
        raise HTTPException(400, f"invalid path: {value!r}")
    if suffix and not value.endswith(suffix):
        raise HTTPException(400, f"path must end with {suffix}: {value!r}")
    return value


def _check_id(value: str) -> str:
    if not value or not _SAFE_REL.match(value) or ".." in value or value.startswith("/"):
        raise HTTPException(400, f"invalid id: {value!r}")
    return value


def _check_provider(params) -> str:
    provider = params.get("provider", "") or ""
    if provider not in ("", "deepseek"):
        raise HTTPException(400, f"invalid provider: {provider!r}")
    return provider


def _int_param(params, key, default, lo, hi):
    try:
        v = int(params.get(key, default))
    except (TypeError, ValueError):
        raise HTTPException(400, f"{key} must be an integer")
    if not lo <= v <= hi:
        raise HTTPException(400, f"{key} out of range [{lo}, {hi}]")
    return str(v)


class JobManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.jobs_dir = settings.data_dir / "jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.registry_path = settings.data_dir / "jobs.json"
        self._lock = threading.Lock()
        self._jobs = self._load()

    # ---------- persistence ----------

    def _load(self):
        try:
            return json.loads(self.registry_path.read_text())
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self):
        tmp = self.registry_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._jobs, indent=1))
        tmp.replace(self.registry_path)

    # ---------- job types ----------

    def build_job(self, jtype: str, params: dict):
        """Returns (cmd, cwd, env_extra, link_run_id)."""
        s = self.settings
        repo = s.repo_dirs.get(params.get("root", "main"))
        if repo is None:
            raise HTTPException(400, "unknown root")
        gen = repo / "agents" / "generation"

        if jtype == "stub":
            if not os.environ.get("RETHLAS_STUB_JOBS"):
                raise HTTPException(400, "stub jobs disabled")
            secs = _int_param(params, "seconds", 5, 0, 600)
            return (["bash", "-c", f"echo stub started; sleep {secs}; echo stub done"],
                    repo, {}, None)

        if jtype == "retries":
            problem_file = _check_rel_path(params.get("problem_file", ""), ".md")
            if not (gen / problem_file).is_file():
                raise HTTPException(400, f"problem file not found: {problem_file}")
            problem_id = _check_id(params.get("problem_id")
                                   or problem_file.removeprefix("data/").removesuffix(".md"))
            env = {
                "PROBLEM_FILE": problem_file,
                "PROBLEM_ID": problem_id,
                "MAX_ATTEMPTS": _int_param(params, "max_attempts", 5, 1, 20),
                "BLIND_RUN": "1" if params.get("blind", True) else "0",
                "MODEL": _check_id(params.get("model", "gpt-5.5")),
                "REASONING_EFFORT": _check_id(params.get("reasoning_effort", "xhigh")),
                "PROVIDER": _check_provider(params),
            }
            return ([str(repo / "scripts" / "run_with_retries.sh")], repo, env, problem_id)

        if jtype == "discovery":
            problem_file = _check_rel_path(params.get("problem_file", ""), ".md")
            if not (gen / problem_file).is_file():
                raise HTTPException(400, f"problem file not found: {problem_file}")
            batch_id = _check_id(params.get("batch_id")
                                 or f"generated/discovery_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}")
            env = {
                "PROBLEM_FILE": problem_file,
                "BATCH_ID": batch_id,
                "SAMPLES": _int_param(params, "samples", 5, 1, 50),
                "PARALLEL": _int_param(params, "parallel", 2, 1, 8),
                "MIN_VALID_CARDS": _int_param(params, "min_valid_cards", 1, 0, 50),
                "DISCOVERY_PROFILE": _check_id(params.get("profile", "low_hint")),
                "MODEL": _check_id(params.get("model", "gpt-5.5")),
                "REASONING_EFFORT": _check_id(params.get("reasoning_effort", "xhigh")),
                "PROVIDER": _check_provider(params),
                "DRY_RUN": "1" if params.get("dry_run") else "0",
            }
            return ([str(repo / "scripts" / "run_discovery_batch.sh")], repo, env, batch_id)

        if jtype == "baseline":
            script = repo / "agents" / "generation" / "tests" / "run_example.sh"
            if not script.is_file():
                raise HTTPException(400, f"no run_example.sh in root {params.get('root')}")
            problem_file = _check_rel_path(params.get("problem_file", ""), ".md")
            env = {
                "PROBLEM_FILE": problem_file,
                "MODEL": _check_id(params.get("model", "gpt-5.5")),
                "REASONING_EFFORT": _check_id(params.get("reasoning_effort", "xhigh")),
                "MAX_ITERATIONS": _int_param(params, "max_iterations", 10, 1, 30),
            }
            rel = problem_file.removeprefix("data/").removesuffix(".md")
            return ([str(script)], gen, env, rel)

        if jtype == "promotion-launch":
            launch_rel = _check_rel_path(params.get("launch_script", ""), ".sh")
            script = (gen / launch_rel).resolve()
            if not str(script).startswith(str((gen / "results").resolve()) + os.sep):
                raise HTTPException(400, "launch script must live under results/")
            if not script.is_file():
                raise HTTPException(400, f"not found: {launch_rel}")
            return (["bash", str(script)], repo, {}, None)

        raise HTTPException(400, f"unknown job type: {jtype}")

    # ---------- lifecycle ----------

    def spawn(self, jtype: str, params: dict) -> dict:
        cmd, cwd, env_extra, link = self.build_job(jtype, params)
        job_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:6]
        log_path = self.jobs_dir / f"{job_id}.log"
        env = dict(os.environ, **env_extra)
        with open(log_path, "wb") as log:
            proc = subprocess.Popen(cmd, cwd=str(cwd), env=env,
                                    stdout=log, stderr=subprocess.STDOUT,
                                    start_new_session=True)
        job = {
            "id": job_id, "type": jtype, "params": params, "pid": proc.pid,
            "pgid": os.getpgid(proc.pid), "started_at": time.time(),
            "log": str(log_path), "link_run": link, "exit_code": None,
            "cmd": " ".join(cmd),
        }
        with self._lock:
            self._jobs[job_id] = job
            self._save()
        threading.Thread(target=self._wait, args=(job_id, proc), daemon=True).start()
        return self.describe(job)

    def _wait(self, job_id: str, proc: subprocess.Popen):
        code = proc.wait()
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["exit_code"] = code
                self._jobs[job_id]["finished_at"] = time.time()
                self._save()

    def _alive(self, job: dict) -> bool:
        if job.get("exit_code") is not None:
            return False
        try:
            os.killpg(job["pgid"], 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False

    def describe(self, job: dict) -> dict:
        out = dict(job)
        out["status"] = ("running" if self._alive(job)
                         else "done" if job.get("exit_code") == 0
                         else "stopped" if job.get("exit_code") in (-15, -9, 124, 130, 143)
                         else "failed" if job.get("exit_code") is not None
                         else "finished")
        return out

    def list_jobs(self):
        with self._lock:
            jobs = list(self._jobs.values())
        return sorted((self.describe(j) for j in jobs),
                      key=lambda j: j["started_at"], reverse=True)

    def get(self, job_id: str) -> dict:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise HTTPException(404, f"unknown job: {job_id}")
        return job

    def stop(self, job_id: str) -> dict:
        job = self.get(job_id)
        try:
            os.killpg(job["pgid"], signal.SIGTERM)
        except ProcessLookupError:
            return self.describe(job)
        for _ in range(20):
            if not self._alive(job):
                break
            time.sleep(0.25)
        else:
            try:
                os.killpg(job["pgid"], signal.SIGKILL)
            except ProcessLookupError:
                pass
        with self._lock:
            if self._jobs[job_id].get("exit_code") is None:
                self._jobs[job_id]["exit_code"] = -15
                self._jobs[job_id]["finished_at"] = time.time()
                self._save()
        return self.describe(self.get(job_id))

    def tail(self, job_id: str, max_bytes: int = 65536) -> str:
        job = self.get(job_id)
        try:
            with open(job["log"], "rb") as f:
                f.seek(0, 2)
                size = f.tell()
                f.seek(max(0, size - max_bytes))
                return f.read().decode(errors="replace")
        except OSError:
            return ""

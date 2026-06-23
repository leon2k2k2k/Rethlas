"""Quick synchronous pipeline tools (triage / promote / classify) and the
ad-hoc verification proxy."""
import hashlib
import json
import os
import subprocess
import threading
import time
import uuid

import requests
from fastapi import HTTPException

from .config import Settings

DEFAULT_VERIFY_PORTS = {"main": 8091, "original-normal": 8092, "original-blind": 8093}


def verify_endpoint(settings: Settings, root: str) -> str:
    env = os.environ.get("RETHLAS_VERIFY_ENDPOINTS")
    if env:
        mapping = json.loads(env)
        if root in mapping:
            return mapping[root]
        raise HTTPException(400, f"no verify endpoint for root {root}")
    port = DEFAULT_VERIFY_PORTS.get(root)
    if port is None:
        raise HTTPException(400, f"no verify endpoint for root {root}")
    return f"http://127.0.0.1:{port}/verify"


def _run_tool(cmd, cwd, timeout=180):
    try:
        proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True,
                              text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "tool timed out")
    return {"exit_code": proc.returncode, "stdout": proc.stdout[-20000:],
            "stderr": proc.stderr[-5000:]}


def run_triage(settings: Settings, run: dict) -> dict:
    repo = settings.repo_dirs[run["root"]]
    rdir = settings.roots[run["root"]] / "results" / run["rel_id"]
    if not rdir.is_dir():
        raise HTTPException(404, "no results dir")
    return _run_tool(["python3", str(repo / "scripts" / "triage_route_cards.py"), str(rdir)], repo)


def run_promote(settings: Settings, run: dict, source_templates=None) -> dict:
    repo = settings.repo_dirs[run["root"]]
    rdir = settings.roots[run["root"]] / "results" / run["rel_id"]
    if not rdir.is_dir():
        raise HTTPException(404, "no results dir")
    cmd = ["python3", str(repo / "scripts" / "apply_promotion_decision.py"), str(rdir),
           "--triage-if-missing"]
    for tpl in source_templates or []:
        if "/" in tpl or ".." in tpl:
            raise HTTPException(400, "source template must be a basename")
        cmd += ["--source-template", tpl]
    return _run_tool(cmd, repo)


def run_classify(settings: Settings, run: dict) -> dict:
    repo = settings.repo_dirs[run["root"]]
    rdir = settings.roots[run["root"]] / "results" / run["rel_id"]
    if not rdir.is_dir():
        raise HTTPException(404, "no results dir")
    out = _run_tool(["python3", str(repo / "scripts" / "classify_blueprint_status.py"), str(rdir)], repo)
    try:
        out["report"] = json.loads(out["stdout"])
    except json.JSONDecodeError:
        out["report"] = None
    return out


class VerifyProxy:
    """Submit ad-hoc statement+proof pairs to a verification API and track
    them. The referee run dir is locatable by the statement hash (the API's
    own run-id scheme)."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = threading.Lock()
        self._requests = {}

    def submit(self, root: str, statement: str, proof: str) -> dict:
        if not statement.strip() or not proof.strip():
            raise HTTPException(400, "statement and proof are required")
        endpoint = verify_endpoint(self.settings, root)
        vid = "verify-" + uuid.uuid4().hex[:8]
        entry = {
            "id": vid, "root": root, "status": "running",
            "statement_hash": hashlib.sha256(statement.encode()).hexdigest()[:12],
            "started_at": time.time(), "result": None,
        }
        with self._lock:
            self._requests[vid] = entry

        def worker():
            try:
                resp = requests.post(endpoint, json={"statement": statement, "proof": proof},
                                     timeout=3700)
                resp.raise_for_status()
                body = resp.json()
                entry.update(status="done", result=body)
            except Exception as exc:  # surface anything to the UI
                entry.update(status="failed", result={"error": str(exc)})
            entry["finished_at"] = time.time()

        threading.Thread(target=worker, daemon=True).start()
        return entry

    def get(self, vid: str) -> dict:
        with self._lock:
            entry = self._requests.get(vid)
        if entry is None:
            raise HTTPException(404, f"unknown verify request: {vid}")
        out = dict(entry)
        # locate the referee dir as soon as the API has created it
        vroot = self.settings.vroots.get(entry["root"])
        if vroot:
            matches = sorted((vroot / "results").glob(f"*_{entry['statement_hash']}"))
            if matches:
                out["referee_dir"] = matches[-1].name
                out["log_path"] = f"results/{matches[-1].name}/log.md"
        return out

    def list(self):
        with self._lock:
            return sorted(self._requests.values(),
                          key=lambda e: e["started_at"], reverse=True)

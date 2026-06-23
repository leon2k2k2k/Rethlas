import os
import time

import pytest
from fastapi import HTTPException

from app.jobs import JobManager


@pytest.fixture(autouse=True)
def stub_env(monkeypatch):
    monkeypatch.setenv("RETHLAS_STUB_JOBS", "1")


@pytest.fixture()
def manager(settings):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return JobManager(settings)


def _wait_status(manager, job_id, status, timeout=10):
    for _ in range(int(timeout * 10)):
        job = manager.describe(manager.get(job_id))
        if job["status"] == status:
            return job
        time.sleep(0.1)
    raise AssertionError(f"job never reached {status}: {job}")


def test_stub_job_runs_to_done(manager):
    job = manager.spawn("stub", {"seconds": 0})
    assert job["status"] == "running" or job["exit_code"] == 0
    done = _wait_status(manager, job["id"], "done")
    assert done["exit_code"] == 0
    log = manager.tail(job["id"])
    assert "stub started" in log and "stub done" in log


def test_stop_kills_process_group(manager):
    job = manager.spawn("stub", {"seconds": 300})
    assert manager.describe(manager.get(job["id"]))["status"] == "running"
    stopped = manager.stop(job["id"])
    assert stopped["status"] in ("stopped", "failed")
    # the process group is gone
    with pytest.raises(ProcessLookupError):
        os.killpg(job["pgid"], 0)


def test_registry_persists(settings, manager):
    job = manager.spawn("stub", {"seconds": 0})
    _wait_status(manager, job["id"], "done")
    reloaded = JobManager(settings)
    assert job["id"] in {j["id"] for j in reloaded.list_jobs()}


def test_retries_param_validation(manager):
    with pytest.raises(HTTPException) as e:
        manager.build_job("retries", {"problem_file": "../etc/passwd"})
    assert e.value.status_code == 400
    with pytest.raises(HTTPException):
        manager.build_job("retries", {"problem_file": "/abs/path.md"})
    with pytest.raises(HTTPException):
        manager.build_job("retries", {"problem_file": "data/alg/missing.md"})
    with pytest.raises(HTTPException):
        manager.build_job("retries", {"problem_file": "data/alg/fix_verified.md",
                                      "max_attempts": 9999})
    with pytest.raises(HTTPException):
        manager.build_job("retries", {"problem_file": "data/alg/fix_verified.md",
                                      "model": "gpt; rm -rf /"})


def test_provider_param(manager):
    _, _, env, _ = manager.build_job("retries", {"problem_file": "data/alg/fix_verified.md"})
    assert env["PROVIDER"] == ""
    _, _, env, _ = manager.build_job("retries", {"problem_file": "data/alg/fix_verified.md",
                                                 "provider": "deepseek"})
    assert env["PROVIDER"] == "deepseek"
    _, _, env, _ = manager.build_job("discovery", {"problem_file": "data/alg/fix_verified.md",
                                                   "provider": "deepseek", "dry_run": True})
    assert env["PROVIDER"] == "deepseek"
    with pytest.raises(HTTPException) as e:
        manager.build_job("retries", {"problem_file": "data/alg/fix_verified.md",
                                      "provider": "openrouter"})
    assert e.value.status_code == 400


def test_retries_job_shape(manager):
    cmd, cwd, env, link = manager.build_job("retries", {
        "problem_file": "data/alg/fix_verified.md", "max_attempts": 3, "blind": False})
    assert cmd[0].endswith("run_with_retries.sh")
    assert env["PROBLEM_ID"] == "alg/fix_verified"
    assert env["MAX_ATTEMPTS"] == "3"
    assert env["BLIND_RUN"] == "0"
    assert link == "alg/fix_verified"


def test_discovery_job_shape(manager):
    cmd, cwd, env, link = manager.build_job("discovery", {
        "problem_file": "data/alg/fix_verified.md", "dry_run": True, "samples": 2})
    assert cmd[0].endswith("run_discovery_batch.sh")
    assert env["DRY_RUN"] == "1"
    assert env["SAMPLES"] == "2"
    assert link == env["BATCH_ID"]


def test_promotion_launch_confined_to_results(manager, fixture_repo):
    with pytest.raises(HTTPException):
        manager.build_job("promotion-launch", {"launch_script": "data/evil.sh"})
    gen = fixture_repo / "agents" / "generation"
    script = gen / "results" / "alg" / "fix_verified" / "launch_promotion.sh"
    script.write_text("#!/bin/bash\necho ok\n")
    cmd, cwd, env, link = manager.build_job(
        "promotion-launch", {"launch_script": "results/alg/fix_verified/launch_promotion.sh"})
    assert cmd[0] == "bash"


def test_unknown_type(manager):
    with pytest.raises(HTTPException):
        manager.build_job("nope", {})


def test_jobs_api(client, monkeypatch):
    monkeypatch.setenv("RETHLAS_STUB_JOBS", "1")
    job = client.post("/api/jobs", json={"type": "stub", "params": {"seconds": 0}}).json()
    assert job["status"] in ("running", "done")
    for _ in range(50):
        listed = client.get("/api/jobs").json()
        mine = next(j for j in listed if j["id"] == job["id"])
        if mine["status"] == "done":
            break
        time.sleep(0.1)
    assert mine["status"] == "done"
    log = client.get(f"/api/jobs/{job['id']}/log").text
    assert "stub done" in log
    assert client.post("/api/jobs", json={"type": "bad"}).status_code == 400

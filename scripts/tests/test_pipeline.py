"""Unit tests for pipeline.py, the single front door over every Rethlas stage.

These lock in the pure logic that the writeup's claims rest on: problem-id
derivation, queue loading, the outcome taxonomy roll-up, the classify fallback,
state round-tripping, and the harvest summary. All offline, no Codex, no network.

Run:  python3 -m pytest scripts/tests/test_pipeline.py -q
"""
import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _load_pipeline():
    spec = importlib.util.spec_from_file_location("pipeline", REPO_ROOT / "pipeline.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pl = _load_pipeline()


# ---- problem_id_for: data/<id>.md -> <id> (keys records, drives result dirs) ----

def test_problem_id_strips_prefix_and_suffix():
    assert pl.problem_id_for("data/erdos_819.md") == "erdos_819"

def test_problem_id_keeps_nested_path():
    assert pl.problem_id_for("data/modrep/modrep.md") == "modrep/modrep"

def test_problem_id_without_prefix_or_suffix():
    assert pl.problem_id_for("plain") == "plain"


# ---- load_queue: problems come from an inline list OR a queue file ----

def test_load_queue_inline_list():
    cfg = {"problems": ["data/a.md", "data/b.md"]}
    assert pl.load_queue(cfg) == ["data/a.md", "data/b.md"]

def test_load_queue_from_file_skips_comments_and_blanks(tmp_path, monkeypatch):
    qf = tmp_path / "queue.txt"
    qf.write_text("data/a.md\n# a comment\n\n  data/b.md  \n", encoding="utf-8")
    monkeypatch.setattr(pl, "REPO_ROOT", tmp_path)
    assert pl.load_queue({"queue": "queue.txt"}) == ["data/a.md", "data/b.md"]

def test_load_queue_empty_when_neither_given():
    assert pl.load_queue({}) == []


# ---- group_counts: classify_blueprint_status.py taxonomy -> scoreboard groups ----

def test_group_counts_rolls_up_taxonomy():
    results = [
        {"status": "verified_final"},        # verified
        {"status": "verified_unpromoted"},   # verified
        {"status": "verified_conditioning"}, # partial
        {"status": "unverified_blueprint"},  # attempted
        {"status": "no_blueprint"},          # failed
    ]
    assert pl.group_counts(results) == {
        "verified": 2, "partial": 1, "attempted": 1, "failed": 1,
    }

def test_group_counts_unknown_status_is_other():
    assert pl.group_counts([{"status": "totally_new"}]) == {"other": 1}


# ---- classify: source of truth for outcome; missing dir => no_blueprint ----

def test_classify_missing_dir_is_no_blueprint(tmp_path):
    out = pl.classify(tmp_path / "does_not_exist")
    assert out["status"] == "no_blueprint"


# ---- load_config: fills name (from stem) and mode defaults ----

def test_load_config_defaults(tmp_path):
    cfg_path = tmp_path / "mycampaign.yaml"
    cfg_path.write_text("concurrency: 4\n", encoding="utf-8")
    cfg = pl.load_config(cfg_path)
    assert cfg["name"] == "mycampaign"
    assert cfg["mode"] == "pool"
    assert cfg["concurrency"] == 4


# ---- write_state / read_state: live scoreboard persistence round-trips ----

def test_state_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(pl, "RUNS_DIR", tmp_path)
    state = {"name": "c", "results": [{"problem_id": "x", "status": "verified_final"}]}
    pl.write_state("c", state)
    assert pl.read_state("c") == state

def test_read_state_missing_is_none(tmp_path, monkeypatch):
    monkeypatch.setattr(pl, "RUNS_DIR", tmp_path)
    assert pl.read_state("nope") is None


# ---- write_harvest: markdown summary carries the honesty caveat ----

def test_write_harvest_has_candidate_caveat_and_table(tmp_path, monkeypatch):
    monkeypatch.setattr(pl, "RUNS_DIR", tmp_path)
    state = {"name": "c", "finished_at": "t",
             "results": [{"problem_id": "erdos_819", "status": "verified_final",
                          "verification_verdict": "correct", "blueprint": "bp.md"}]}
    out = pl.write_harvest("c", state)
    text = out.read_text(encoding="utf-8")
    assert "erdos_819" in text
    assert "pending human review" in text   # the candidate-not-proven caveat
    assert "| problem | status | verdict | blueprint |" in text


# ---- cmd_pool: a problem that is already verified is skipped, no attack run ----

def test_cmd_pool_skips_already_verified(tmp_path, monkeypatch):
    # classify is stubbed so this never shells out to Codex / run_with_retries.sh:
    # reaching "already_verified" proves the skip branch fired.
    monkeypatch.setattr(pl, "GEN_DIR", tmp_path / "gen")
    monkeypatch.setattr(pl, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(pl, "classify",
                        lambda d: {"verification_verdict": "correct", "blueprint": "bp.md"})
    pid = "erdos_999"
    rdir = tmp_path / "gen" / "results" / pid
    rdir.mkdir(parents=True)
    (rdir / "blueprint_verified.md").write_text("done", encoding="utf-8")

    rc = pl.cmd_pool({"name": "skiptest", "problems": [f"data/{pid}.md"]}, dry_run=False)
    assert rc == 0
    rec = pl.read_state("skiptest")["results"][0]
    assert rec["status"] == "already_verified"

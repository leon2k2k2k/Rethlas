import pytest
from fastapi import HTTPException

from app.edits_api import (
    edit_kind, list_backups, list_editables, read_backup, read_for_edit, write_edit,
)


def test_edit_kind_whitelist():
    assert edit_kind("data/alg/x.md") == "data"
    assert edit_kind("AGENTS.md") == "config"
    assert edit_kind(".codex/config.toml") == "config"
    assert edit_kind(".codex/agents/subgoal-prover.toml") == "config"
    assert edit_kind("mcp/server.py") is None
    assert edit_kind("results/x/blueprint.md") is None
    assert edit_kind("data/../mcp/server.py") is None
    assert edit_kind("data/x.txt") is None


def test_roundtrip_with_backup(settings):
    doc = read_for_edit(settings, "main", "data/alg/fix_verified.md")
    assert doc["exists"] and doc["sha"]
    out = write_edit(settings, "main", "data/alg/fix_verified.md",
                     doc["content"] + "\nedited.\n", doc["sha"])
    assert out["backup"]
    doc2 = read_for_edit(settings, "main", "data/alg/fix_verified.md")
    assert doc2["content"].endswith("edited.\n")
    backups = list_backups(settings, "main", "data/alg/fix_verified.md")
    assert len(backups) == 1
    assert read_backup(settings, backups[0]["name"]) == doc["content"]


def test_sha_conflict(settings):
    doc = read_for_edit(settings, "main", "data/alg/fix_verified.md")
    write_edit(settings, "main", "data/alg/fix_verified.md", "v2", doc["sha"])
    with pytest.raises(HTTPException) as e:
        write_edit(settings, "main", "data/alg/fix_verified.md", "v3", doc["sha"])
    assert e.value.status_code == 409


def test_create_new_problem(settings):
    out = write_edit(settings, "main", "data/newcat/fresh.md", "# New\n")
    assert out["backup"] is None
    assert read_for_edit(settings, "main", "data/newcat/fresh.md")["content"] == "# New\n"


def test_config_create_forbidden(settings):
    with pytest.raises(HTTPException) as e:
        write_edit(settings, "main", ".codex/agents/new-agent.toml", "x")
    assert e.value.status_code == 403


def test_non_whitelisted_rejected(settings):
    for path in ["mcp/server.py", "results/alg/fix_verified/blueprint.md",
                 "data/../AGENTS.md.bak", "../outside.md"]:
        with pytest.raises(HTTPException) as e:
            write_edit(settings, "main", path, "x")
        assert e.value.status_code in (400, 403), path


def test_backup_name_traversal(settings):
    with pytest.raises(HTTPException):
        read_backup(settings, "../jobs.json")


def test_editables_listing(settings, fixture_repo):
    gen = fixture_repo / "agents" / "generation"
    (gen / "AGENTS.md").write_text("# agent\n")
    out = list_editables(settings, "main")
    assert "data/alg/fix_verified.md" in out["data"]
    assert "AGENTS.md" in out["configs"]


def test_edit_api(client):
    doc = client.get("/api/edit", params={"path": "data/alg/fix_verified.md"}).json()
    resp = client.put("/api/edit", json={"path": "data/alg/fix_verified.md",
                                         "content": "# changed\n", "sha": doc["sha"]})
    assert resp.status_code == 200
    assert client.get("/api/file",
                      params={"path": "data/alg/fix_verified.md"}).text == "# changed\n"
    conflict = client.put("/api/edit", json={"path": "data/alg/fix_verified.md",
                                             "content": "# again\n", "sha": doc["sha"]})
    assert conflict.status_code == 409
    forbidden = client.put("/api/edit", json={"path": "mcp/server.py", "content": "x"})
    assert forbidden.status_code == 403

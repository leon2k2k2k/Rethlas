def test_list_runs(client):
    rs = client.get("/api/runs").json()
    assert len(rs) >= 6
    assert all("attempts" not in r for r in rs)


def test_run_detail_includes_results(client):
    r = client.get("/api/runs/alg/fix_verified").json()
    assert r["status"] == "verified"
    names = {f["name"] for f in r["results"]}
    assert "blueprint_verified.md" in names


def test_unknown_run_404(client):
    assert client.get("/api/runs/alg/nope").status_code == 404
    assert client.get("/api/memory", params={"run": "alg/nope"}).status_code == 404


def test_memory_endpoint(client):
    d = client.get("/api/memory", params={"run": "alg/fix_verified"}).json()
    assert "branch_states" in d["channels"]
    rec = d["channels"]["branch_states"][0]
    assert rec["record"]["branch_id"] == "root"


def test_file_roundtrip(client):
    text = client.get("/api/file", params={
        "path": "results/alg/fix_verified/blueprint.md"}).text
    assert "theorem" in text


def test_file_ver_root(client):
    runs = client.get("/api/verifications", params={"run": "alg/fix_verified"}).json()
    log_path = runs["referee_runs"][0]["log_path"]
    text = client.get("/api/file", params={"path": log_path, "root": "main!ver"}).text
    assert "session id" in text


def test_file_traversal_blocked(client):
    for path in ["../secrets.txt", "/etc/passwd", "results/../../secret"]:
        resp = client.get("/api/file", params={"path": path})
        assert resp.status_code in (400, 404), path


def test_file_unknown_root(client):
    assert client.get("/api/file", params={"path": "x", "root": "nope"}).status_code == 400


def test_transcript_endpoint(client):
    from conftest import SESSION_A
    t = client.get(f"/api/transcript/{SESSION_A}").json()
    assert t["events"][0]["kind"] == "meta"
    assert client.get("/api/transcript/0000-missing").status_code == 404


def test_static_served(client):
    assert client.get("/run.html").status_code == 200

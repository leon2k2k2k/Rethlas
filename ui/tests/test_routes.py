import json

from app.routes_api import read_lineage, read_routes


def test_route_cards_read(settings, index, fixture_repo):
    run = index.find_run("geo/fix_batch")
    out = read_routes(settings, run)
    assert len(out["cards"]) == 1
    card = out["cards"][0]
    assert card["sample"] == "sample_001"
    assert card["card"]["stage"] == "number_field_source_identified"
    assert out["batch_manifest"]["batch_id"] == "geo/fix_batch"


def test_routes_empty_for_plain_run(settings, index):
    run = index.find_run("alg/fix_verified")
    out = read_routes(settings, run)
    assert out["cards"] == []
    assert out["promotion_decision"] is None


def test_lineage_parent_child(settings, index, fixture_repo):
    gen = fixture_repo / "agents" / "generation"
    # fix_batch promotes a generated child problem; the child has a run dir
    bdir = gen / "results" / "geo" / "fix_batch"
    (bdir / "promotion_manifest.json").write_text(json.dumps({
        "action": "launch_x", "generated_problem_id": "generated/fix_child"}))
    child = gen / "results" / "generated" / "fix_child"
    child.mkdir(parents=True)
    (child / "blueprint.md").write_text("x")
    import os, time
    old = time.time() - 3600
    for p in [child, child / "blueprint.md", bdir / "promotion_manifest.json"]:
        os.utime(p, (old, old))

    batch = index.find_run("geo/fix_batch")
    lin = read_lineage(settings, index, batch)
    assert lin["children"] == [{"id": "generated/fix_child",
                                "rel_id": "generated/fix_child", "exists": True}]

    child_run = index.find_run("generated/fix_child")
    lin2 = read_lineage(settings, index, child_run)
    assert lin2["parents"] == [{"id": "geo/fix_batch", "action": "launch_x"}]


def test_api_routes_and_lineage(client):
    out = client.get("/api/routes", params={"run": "geo/fix_batch"}).json()
    assert out["cards"][0]["card"]["construction_family"] == "fixture family"
    lin = client.get("/api/lineage", params={"run": "geo/fix_batch"}).json()
    assert "children" in lin and "parents" in lin

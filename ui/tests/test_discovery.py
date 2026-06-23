from conftest import SESSION_A


def test_discovers_all_fixture_runs(index):
    ids = {r["id"] for r in index.discover()}
    assert {"alg/fix_verified", "alg/fix_running", "alg/fix_dead",
            "alg/fix_resultsonly", "geo/fix_iter", "geo/fix_batch"} <= ids


def test_statuses(index):
    runs = {r["id"]: r for r in index.discover()}
    assert runs["alg/fix_verified"]["status"] == "verified"
    assert runs["alg/fix_running"]["status"] == "running"
    assert runs["alg/fix_dead"]["status"] == "stopped"
    assert runs["alg/fix_dead"]["dead"] is True
    assert runs["alg/fix_resultsonly"]["status"] == "stopped"
    assert runs["alg/fix_verified"]["dead"] is False


def test_attempt_header_parsing(index):
    run = index.find_run("alg/fix_verified")
    a = run["attempts"][0]
    assert a["session_id"] == SESSION_A
    assert a["model"] == "gpt-5.5"
    assert a["problem_file"] == "data/alg/fix_verified.md"
    assert run["problem_file"] == "data/alg/fix_verified.md"


def test_iter_logs_discovered_and_problem_file_fallback(index):
    run = index.find_run("geo/fix_iter")
    assert run["n_attempts"] == 3
    assert [a["name"] for a in run["attempts"]] == [
        "fix_iter_iter_0.md", "fix_iter_iter_1.md", "fix_iter_iter_2.md"]
    # iter logs have no problem_file header -> data/<rel_id>.md fallback
    assert run["problem_file"] == "data/geo/fix_iter.md"


def test_route_card_flag(index):
    runs = {r["id"]: r for r in index.discover()}
    assert runs["geo/fix_batch"]["has_route_cards"] is True
    assert runs["alg/fix_verified"]["has_route_cards"] is False


def test_result_files_recursive(index, settings):
    run = index.find_run("geo/fix_batch")
    files = index.result_files(settings.roots["main"], run["rel_id"])
    names = {f["name"] for f in files}
    assert "sample_001/route_card.json" in names
    assert "batch_manifest.json" in names


def test_header_cache_invalidation(index, settings):
    run = index.find_run("alg/fix_verified")
    path = settings.roots["main"] / run["attempts"][0]["path"]
    # mutate the log: model line changes
    text = path.read_text().replace("model: gpt-5.5", "model: gpt-6")
    path.write_text(text)
    import os
    st = path.stat()
    os.utime(path, (st.st_atime, st.st_mtime + 5))
    run2 = index.find_run("alg/fix_verified")
    assert run2["attempts"][0]["model"] == "gpt-6"

from app.verification import list_verifications
from conftest import SESSION_REF


def test_attempt_verdicts(settings, index):
    run = index.find_run("alg/fix_verified")
    out = list_verifications(settings, index, run)
    assert len(out["attempts"]) == 1
    a = out["attempts"][0]
    assert a["verdict"] == "correct"
    assert "correct" in a["summary"]


def test_referee_matched_by_statement_hash(settings, index):
    """The referee dir is named with sha256(extracted target statement)[:12];
    the problem title does NOT appear in the referee log, so only the hash
    join can find it."""
    run = index.find_run("alg/fix_verified")
    out = list_verifications(settings, index, run)
    assert len(out["referee_runs"]) == 1
    v = out["referee_runs"][0]
    assert v["verdict"] == "correct"
    assert v["session_id"] == SESSION_REF
    assert v["root"] == "main!ver"
    assert v["log_path"].endswith("log.md")


def test_no_referee_for_unrelated_run(settings, index):
    run = index.find_run("alg/fix_dead")
    out = list_verifications(settings, index, run)
    assert out["referee_runs"] == []


def test_title_fallback(settings, index, fixture_repo):
    """A referee dir with a non-hash name still matches via title substring."""
    ver = fixture_repo / "agents" / "verification" / "results" / "20260609T020000Z_zzzzzzzzzzzz"
    ver.mkdir(parents=True)
    (ver / "log.md").write_text(
        "command: codex exec 'Statement: # Fixture problem: toy theorem ...'\n"
        "session id: 01900000-0000-7000-8000-0000000000ff\n")
    run = index.find_run("alg/fix_verified")
    out = list_verifications(settings, index, run)
    assert len(out["referee_runs"]) == 2

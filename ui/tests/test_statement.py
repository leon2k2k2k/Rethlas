import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.statement import extract_target_statement  # noqa: E402
from conftest import PROBLEM_MD, TARGET_STATEMENT  # noqa: E402

REPO = Path(__file__).resolve().parents[2]


def test_target_statement_section():
    assert extract_target_statement(PROBLEM_MD) == TARGET_STATEMENT


def test_focus_question_fallback():
    text = "# T\n\n## Focus question\n\nDecide whether X.\n\n## Required analysis\n\nstuff\n"
    assert extract_target_statement(text) == "Decide whether X."


def test_problem_fallback():
    text = "# T\n\n## Problem\n\nLet P be finite.\n\n## Allowed baseline\n\nstuff\n"
    assert extract_target_statement(text) == "Let P be finite."


def test_whole_file_fallback():
    text = "no headings at all, just text"
    assert extract_target_statement(text) == text


def test_section_ends_at_same_level_heading():
    text = "## Target Statement\n\nA.\n\n### sub\n\nB.\n\n## Next\n\nC.\n"
    out = extract_target_statement(text)
    assert "A." in out and "B." in out and "C." not in out


def test_real_problem_files():
    """Every real problem file should yield a nonempty extraction that is
    not longer than the file itself."""
    data = REPO / "agents" / "generation" / "data"
    files = list(data.rglob("*.md"))[:20]
    assert files, "no problem files found"
    for f in files:
        text = f.read_text(errors="replace")
        out = extract_target_statement(text)
        assert out.strip()
        assert len(out) <= len(text)

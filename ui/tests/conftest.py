"""Pytest fixtures over the shared synthetic repo builder."""
import sys
from pathlib import Path

import pytest

UI_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(UI_DIR))
sys.path.insert(0, str(UI_DIR / "tests"))

from fixture_builder import (  # noqa: E402,F401
    PROBLEM_MD, SESSION_A, SESSION_B, SESSION_REF, TARGET_STATEMENT, build_repo,
)
from app.config import Settings  # noqa: E402
from app.discovery import RunIndex  # noqa: E402

@pytest.fixture()
def fixture_repo(tmp_path):
    return build_repo(tmp_path / "repo")


@pytest.fixture()
def settings(fixture_repo):
    repo = fixture_repo
    return Settings(
        roots={"main": repo / "agents" / "generation"},
        vroots={"main": repo / "agents" / "verification"},
        sessions_dir=repo / "sessions",
        data_dir=repo / "uidata",
        repo_dirs={"main": repo},
    )


@pytest.fixture()
def index(settings):
    return RunIndex(settings)


@pytest.fixture()
def client(settings):
    from fastapi.testclient import TestClient
    from app.main import create_app
    return TestClient(create_app(settings))

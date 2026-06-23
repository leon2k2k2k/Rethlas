"""Settings and repo-root resolution for the Rethlas workbench backend.

Roots resolution:
- Default: the repo containing this file is "main"; sibling ~/rethlas-* clones
  are added under their suffix name.
- Override: RETHLAS_ROOTS env var, a JSON object mapping root name -> repo path
  (the directory that contains agents/generation). Used by the test suites to
  point the server at a fixture tree. A "main" key is expected.
"""
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

UI_DIR = Path(__file__).resolve().parents[1]
REPO = UI_DIR.parent

RUNNING_WINDOW_SECONDS = 180


@dataclass
class Settings:
    roots: dict          # name -> generation dir
    vroots: dict         # name -> verification dir
    sessions_dir: Path   # ~/.codex/sessions (rollouts)
    data_dir: Path       # ui/data (jobs registry, edit backups)
    repo_dirs: dict = field(default_factory=dict)  # name -> repo root
    running_window: int = RUNNING_WINDOW_SECONDS


def _roots_from_repos(repos: dict) -> Settings:
    roots, vroots, repo_dirs = {}, {}, {}
    for name, repo in repos.items():
        repo = Path(repo)
        gen = repo / "agents" / "generation"
        if not gen.is_dir():
            continue
        roots[name] = gen
        repo_dirs[name] = repo
        ver = repo / "agents" / "verification"
        if ver.is_dir():
            vroots[name] = ver
    sessions = Path(os.environ.get("RETHLAS_SESSIONS_DIR", str(Path.home() / ".codex" / "sessions")))
    data_dir = Path(os.environ.get("RETHLAS_DATA_DIR", str(UI_DIR / "data")))
    return Settings(roots=roots, vroots=vroots, sessions_dir=sessions,
                    data_dir=data_dir, repo_dirs=repo_dirs)


def default_settings() -> Settings:
    env = os.environ.get("RETHLAS_ROOTS")
    if env:
        repos = {name: Path(p) for name, p in json.loads(env).items()}
    else:
        repos = {"main": REPO}
        for clone in sorted(Path.home().glob("rethlas-*")):
            repos[clone.name.removeprefix("rethlas-")] = clone
    return _roots_from_repos(repos)

#!/usr/bin/env python3
"""CLI: build the synthetic fixture repo at the given path (for e2e tests)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixture_builder import build_repo  # noqa: E402

if __name__ == "__main__":
    target = Path(sys.argv[1])
    build_repo(target)
    print(f"fixture repo at {target}")

"""Root-scoped file access with traversal protection.

Roots: "<name>" -> the repo's agents/generation dir; "<name>!ver" -> the
repo's agents/verification dir. All reads are confined inside the resolved
root directory.
"""
import os
from pathlib import Path

from fastapi import HTTPException

from .config import Settings


def resolve_root(settings: Settings, root: str) -> Path:
    if root.endswith("!ver"):
        base = settings.vroots.get(root.removesuffix("!ver"))
    else:
        base = settings.roots.get(root)
    if base is None:
        raise HTTPException(400, f"unknown root: {root}")
    return base


def safe_target(settings: Settings, root: str, path: str) -> Path:
    base = resolve_root(settings, root)
    target = (base / path).resolve()
    if not str(target).startswith(str(base.resolve()) + os.sep):
        raise HTTPException(400, "path escapes root")
    return target


def read_file(settings: Settings, root: str, path: str) -> str:
    target = safe_target(settings, root, path)
    if not target.is_file():
        raise HTTPException(404, f"not found: {path}")
    return target.read_text(errors="replace")

"""Browser editing of whitelisted files, with sha-conflict detection and
timestamped backups.

Editable surfaces per root:
- problem files:  data/**/*.md under the generation dir (create allowed)
- configs/prompts (exact whitelist): AGENTS.md, .codex/config.toml,
  .codex/agents/*.toml — these change live pipeline behavior; the UI shows a
  warning banner.
"""
import hashlib
import re
import time

from fastapi import HTTPException

from .config import Settings
from .files_api import safe_target

_DATA_RE = re.compile(r"^data/[A-Za-z0-9._/-]+\.md$")
_CONFIG_EXACT = ("AGENTS.md", ".codex/config.toml")
_CONFIG_AGENT_RE = re.compile(r"^\.codex/agents/[A-Za-z0-9._-]+\.toml$")


def edit_kind(path: str):
    if ".." in path:
        return None
    if _DATA_RE.match(path):
        return "data"
    if path in _CONFIG_EXACT or _CONFIG_AGENT_RE.match(path):
        return "config"
    return None


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def read_for_edit(settings: Settings, root: str, path: str) -> dict:
    kind = edit_kind(path)
    if kind is None:
        raise HTTPException(403, f"not editable: {path}")
    target = safe_target(settings, root, path)
    if not target.is_file():
        return {"path": path, "root": root, "kind": kind, "exists": False,
                "content": "", "sha": None}
    content = target.read_text(errors="replace")
    return {"path": path, "root": root, "kind": kind, "exists": True,
            "content": content, "sha": _sha(content)}


def _backup(settings: Settings, root: str, path: str, content: str) -> str:
    bdir = settings.data_dir / "edit_backups"
    bdir.mkdir(parents=True, exist_ok=True)
    name = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "__" + root + "__" + \
        path.replace("/", "__")
    (bdir / name).write_text(content)
    return name


def write_edit(settings: Settings, root: str, path: str, content: str,
               base_sha: str = None) -> dict:
    kind = edit_kind(path)
    if kind is None:
        raise HTTPException(403, f"not editable: {path}")
    if not isinstance(content, str) or len(content) > 2_000_000:
        raise HTTPException(400, "content must be a string under 2MB")
    target = safe_target(settings, root, path)
    backup = None
    if target.is_file():
        current = target.read_text(errors="replace")
        if base_sha != _sha(current):
            raise HTTPException(409, "file changed since you loaded it — reload and re-apply")
        backup = _backup(settings, root, path, current)
    elif kind == "config":
        raise HTTPException(403, "config files can be edited but not created")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return {"path": path, "root": root, "sha": _sha(content), "backup": backup}


def list_editables(settings: Settings, root: str) -> dict:
    gen = settings.roots.get(root)
    if gen is None:
        raise HTTPException(400, f"unknown root: {root}")
    data_files = []
    if (gen / "data").is_dir():
        data_files = sorted(str(p.relative_to(gen)) for p in (gen / "data").rglob("*.md"))[:1000]
    configs = [p for p in _CONFIG_EXACT if (gen / p).is_file()]
    configs += sorted(str(p.relative_to(gen)) for p in (gen / ".codex" / "agents").glob("*.toml")
                      if (gen / ".codex" / "agents").is_dir())
    return {"root": root, "data": data_files, "configs": configs,
            "roots": sorted(settings.roots)}


def list_backups(settings: Settings, root: str, path: str) -> list:
    bdir = settings.data_dir / "edit_backups"
    if not bdir.is_dir():
        return []
    suffix = "__" + root + "__" + path.replace("/", "__")
    out = []
    for p in sorted(bdir.iterdir(), reverse=True):
        if p.name.endswith(suffix):
            out.append({"name": p.name, "mtime": p.stat().st_mtime})
    return out[:20]


def read_backup(settings: Settings, name: str) -> str:
    if "/" in name or ".." in name:
        raise HTTPException(400, "bad backup name")
    target = settings.data_dir / "edit_backups" / name
    if not target.is_file():
        raise HTTPException(404, "no such backup")
    return target.read_text(errors="replace")

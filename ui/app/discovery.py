"""Run discovery and status derivation, with per-file caching.

Design: directory walks are cheap (hundreds of scandir calls); reading and
parsing every attempt log is not. Headers and dead-run scans are cached keyed
by (mtime, size), so steady-state requests only stat files. Statuses are
derived fresh on every call (they depend on wall-clock recency).
"""
import re
import time
from pathlib import Path

from .config import Settings

_HEADER_RE = re.compile(r"(started_at|problem_id|problem_file|model|reasoning_effort):\s*(.+)")
_SESSION_RE = re.compile(r"session id:\s*([0-9a-f-]+)")
_DEAD_MARKERS = ("terminating codex pid", "codex exited with code 1",
                 "codex exited with code 124", "codex exited with code 137")


class RunIndex:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._header_cache: dict = {}
        self._dead_cache: dict = {}

    # ---------- attempt logs ----------

    def parse_attempt_header(self, path: Path, gen: Path) -> dict:
        try:
            st = path.stat()
        except OSError:
            return {"path": str(path.relative_to(gen)), "name": path.name}
        key = str(path)
        cached = self._header_cache.get(key)
        if cached and cached[0] == (st.st_mtime, st.st_size):
            return dict(cached[1])
        meta = {"path": str(path.relative_to(gen)), "name": path.name}
        try:
            with open(path, errors="replace") as f:
                for i, line in enumerate(f):
                    if i > 60:
                        break
                    m = _HEADER_RE.match(line)
                    if m:
                        meta[m.group(1)] = m.group(2).strip()
                    m = _SESSION_RE.match(line)
                    if m:
                        meta["session_id"] = m.group(1)
        except OSError:
            pass
        self._header_cache[key] = ((st.st_mtime, st.st_size), dict(meta))
        return meta

    @staticmethod
    def _attempt_sort_key(path: Path):
        m = re.search(r"(\d+)\.md$", path.name)
        return (int(m.group(1)) if m else 0, path.name)

    @classmethod
    def attempt_logs(cls, rdir: Path) -> list:
        files = list(rdir.glob("attempt_*.md")) + list(rdir.glob("iter/*_iter_*.md"))
        return sorted(files, key=cls._attempt_sort_key)

    # ---------- status ----------

    def run_status(self, gen: Path, rel_id: str, attempts: list) -> str:
        rdir = gen / "results" / rel_id
        now = time.time()
        mtimes = []
        for p in [rdir / "heartbeat.txt"] + [gen / a["path"] for a in attempts]:
            try:
                mtimes.append(p.stat().st_mtime)
            except OSError:
                continue
        if mtimes and now - max(mtimes) < self.settings.running_window:
            return "running"
        if (rdir / "blueprint_verified.md").exists():
            return "verified"
        if (rdir / "blueprint.md").exists():
            return "stopped"
        return "no-result"

    def is_dead(self, gen: Path, attempts: list) -> bool:
        """True if the last attempt log shows a watchdog kill or crash."""
        if not attempts:
            return False
        path = gen / attempts[-1]["path"]
        try:
            st = path.stat()
        except OSError:
            return False
        key = str(path)
        cached = self._dead_cache.get(key)
        if cached and cached[0] == (st.st_mtime, st.st_size):
            return cached[1]
        dead = False
        try:
            with open(path, "rb") as f:
                f.seek(max(0, st.st_size - 4096))
                tail = f.read().decode(errors="replace").lower()
            dead = any(marker in tail for marker in _DEAD_MARKERS)
        except OSError:
            pass
        self._dead_cache[key] = ((st.st_mtime, st.st_size), dead)
        return dead

    # ---------- discovery ----------

    def discover(self) -> list:
        runs = {}
        for root, gen in self.settings.roots.items():
            prefix = "" if root == "main" else f"{root}/"
            logs, results = gen / "logs", gen / "results"
            if logs.is_dir():
                for cat in sorted(logs.iterdir()):
                    if not cat.is_dir():
                        continue
                    for rdir in sorted(cat.iterdir()):
                        if not rdir.is_dir():
                            continue
                        attempts = [self.parse_attempt_header(p, gen)
                                    for p in self.attempt_logs(rdir)]
                        if not attempts:
                            continue
                        rel_id = f"{cat.name}/{rdir.name}"
                        runs[prefix + rel_id] = {
                            "id": prefix + rel_id, "rel_id": rel_id, "root": root,
                            "category": cat.name, "attempts": attempts,
                        }
            if results.is_dir():
                for cat in sorted(results.iterdir()):
                    if not cat.is_dir():
                        continue
                    for rdir in sorted(cat.iterdir()):
                        if not rdir.is_dir():
                            continue
                        rel_id = f"{cat.name}/{rdir.name}"
                        runs.setdefault(prefix + rel_id, {
                            "id": prefix + rel_id, "rel_id": rel_id, "root": root,
                            "category": cat.name, "attempts": [],
                        })
        out = []
        for run in runs.values():
            gen = self.settings.roots[run["root"]]
            attempts = run["attempts"]
            last = attempts[-1] if attempts else {}
            problem_file = last.get("problem_file")
            if not problem_file and (gen / "data" / f"{run['rel_id']}.md").is_file():
                problem_file = f"data/{run['rel_id']}.md"
            rdir = gen / "results" / run["rel_id"]
            run.update({
                "title": run["rel_id"].split("/", 1)[1].replace("_", " "),
                "status": self.run_status(gen, run["rel_id"], attempts),
                "dead": self.is_dead(gen, attempts),
                "has_route_cards": bool(list(rdir.glob("route_card.json"))
                                        or list(rdir.glob("sample_*/route_card.json"))) if rdir.is_dir() else False,
                "model": last.get("model"),
                "reasoning_effort": last.get("reasoning_effort"),
                "problem_file": problem_file,
                "started_at": (attempts[0].get("started_at") if attempts else None),
                "n_attempts": len(attempts),
            })
            out.append(run)
        out.sort(key=lambda r: r.get("started_at") or "", reverse=True)
        return out

    def find_run(self, run_id: str):
        for run in self.discover():
            if run["id"] == run_id:
                return run
        return None

    # ---------- results ----------

    def result_files(self, gen: Path, rel_id: str) -> list:
        rdir = gen / "results" / rel_id
        if not rdir.is_dir():
            return []
        files = []
        for p in sorted(rdir.rglob("*")):
            if p.is_file():
                st = p.stat()
                files.append({
                    "name": str(p.relative_to(rdir)),
                    "path": str(p.relative_to(gen)),
                    "size": st.st_size,
                    "mtime": st.st_mtime,
                })
                if len(files) >= 500:
                    break
        return files

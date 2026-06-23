"""Join generation runs to their verification artifacts.

Two sources:
- verification*.json files saved inside the generation run's results dir
  (written by run_with_retries.sh)
- referee run dirs under agents/verification/results/<timestamp>_<hash>/,
  produced by the verification API for every /verify call

Referee matching strategy, strongest first:
1. statement hash — the API names dirs <ts>_<sha256(statement)[:12]>. We
   compute candidate hashes from everything the pipeline may have sent as the
   statement (currently the raw problem file; after the extractor fix, the
   extracted target statement as well) and match the dir suffix.
2. title substring — the problem's first markdown heading appearing in the
   head of the referee's log.md.
"""
import hashlib
import json
import re

from .config import Settings
from .discovery import RunIndex

_SESSION_RE = re.compile(r"session id:\s*([0-9a-f-]+)")


def _statement_hash(statement: str) -> str:
    return hashlib.sha256(statement.encode("utf-8")).hexdigest()[:12]


def problem_title(gen, problem_file: str) -> str:
    try:
        with open(gen / problem_file, errors="replace") as f:
            for line in f:
                if line.startswith("#"):
                    return line.lstrip("#").strip()
    except OSError:
        pass
    return ""


def _candidate_hashes(gen, run: dict) -> set:
    hashes = set()
    # strongest: statements echoed back in saved verifier responses
    rdir = gen / "results" / run["rel_id"]
    if rdir.is_dir():
        for p in rdir.rglob("verification*.json"):
            try:
                stmt = json.loads(p.read_text(errors="replace")).get("statement")
                if stmt:
                    hashes.add(_statement_hash(stmt))
            except (OSError, json.JSONDecodeError):
                continue
    pf = run.get("problem_file")
    if pf:
        try:
            raw = (gen / pf).read_text(errors="replace")
            hashes.add(_statement_hash(raw))
            # the extractor (scripts/extract_target_statement.py) sends a
            # trimmed statement; cover both forms
            from .statement import extract_target_statement
            hashes.add(_statement_hash(extract_target_statement(raw)))
        except OSError:
            pass
    return hashes


def list_verifications(settings: Settings, index: RunIndex, run: dict) -> dict:
    gen = settings.roots[run["root"]]
    out = {"attempts": [], "referee_runs": []}

    rdir = gen / "results" / run["rel_id"]
    if rdir.is_dir():
        for p in sorted(rdir.rglob("verification*.json")):
            try:
                body = json.loads(p.read_text(errors="replace"))
            except (json.JSONDecodeError, OSError):
                continue
            report = body.get("verification_report") or {}
            out["attempts"].append({
                "name": str(p.relative_to(rdir)),
                "verdict": body.get("verdict"),
                "summary": report.get("summary"),
                "critical_errors": report.get("critical_errors"),
                "repair_hints": body.get("repair_hints"),
            })

    vroot = settings.vroots.get(run["root"])
    if not vroot or not (vroot / "results").is_dir():
        return out

    hashes = _candidate_hashes(gen, run)
    title = problem_title(gen, run.get("problem_file") or "") if run.get("problem_file") else ""

    for vdir in sorted((vroot / "results").iterdir()):
        log = vdir / "log.md"
        if not log.is_file():
            continue
        suffix = vdir.name.rsplit("_", 1)[-1]
        matched = suffix in hashes
        if not matched and title:
            try:
                head = log.open(errors="replace").read(6000)
            except OSError:
                continue
            matched = title in head
        if not matched:
            continue
        verdict, summary = None, None
        vj = vdir / "verification.json"
        if vj.is_file():
            try:
                body = json.loads(vj.read_text(errors="replace"))
                verdict = body.get("verdict")
                summary = (body.get("verification_report") or {}).get("summary")
            except (json.JSONDecodeError, OSError):
                pass
        sid = None
        try:
            m = _SESSION_RE.search(log.open(errors="replace").read(200_000))
            if m:
                sid = m.group(1)
        except OSError:
            pass
        out["referee_runs"].append({
            "id": vdir.name,
            "verdict": verdict,
            "summary": summary,
            "session_id": sid,
            "log_path": str(log.relative_to(vroot)),
            "root": run["root"] + "!ver",
        })
    return out

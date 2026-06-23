"""FastAPI wiring for the Rethlas workbench.

Entry points:
- production:  uvicorn app.main:app  (or the legacy shim uvicorn server:app)
- tests:       create_app(settings) with fixture roots via RETHLAS_ROOTS
"""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from . import edits_api, memory_api, routes_api, tools_api, transcripts, verification
from .jobs import JobManager
from .tools_api import VerifyProxy
from .config import Settings, default_settings
from .discovery import RunIndex
from .files_api import read_file

STATIC_DIR = Path(__file__).resolve().parents[1] / "static"


def create_app(settings: Settings = None) -> FastAPI:
    settings = settings or default_settings()
    index = RunIndex(settings)
    jobs = JobManager(settings)
    verify_proxy = VerifyProxy(settings)
    app = FastAPI(title="Rethlas Workbench")
    app.state.settings = settings
    app.state.index = index

    def find_run_or_404(run_id: str) -> dict:
        run = index.find_run(run_id)
        if run is None:
            raise HTTPException(404, f"unknown run: {run_id}")
        return run

    @app.get("/sun")
    def sun_dashboard():
        from fastapi.responses import HTMLResponse
        from . import sun_dashboard as sd
        return HTMLResponse(sd.render(settings.roots["main"]))

    @app.get("/api/runs")
    def list_runs():
        return [{k: v for k, v in r.items() if k != "attempts"}
                for r in index.discover()]

    @app.get("/api/verifications")
    def verifications_route(run: str):
        return verification.list_verifications(settings, index, find_run_or_404(run))

    @app.get("/api/memory")
    def memory_route(run: str, limit_per_channel: int = 300):
        return memory_api.read_memory(settings, find_run_or_404(run), limit_per_channel)

    @app.get("/api/file", response_class=PlainTextResponse)
    def file_route(path: str, root: str = "main"):
        return read_file(settings, root, path)

    # ---------- jobs ----------

    @app.get("/api/jobs")
    def jobs_list():
        return jobs.list_jobs()

    @app.post("/api/jobs")
    def jobs_create(body: dict):
        jtype = body.get("type")
        params = body.get("params") or {}
        if not isinstance(params, dict):
            raise HTTPException(400, "params must be an object")
        return jobs.spawn(jtype, params)

    @app.post("/api/jobs/{job_id}/stop")
    def jobs_stop(job_id: str):
        return jobs.stop(job_id)

    @app.get("/api/jobs/{job_id}/log", response_class=PlainTextResponse)
    def jobs_log(job_id: str):
        return jobs.tail(job_id)

    # ---------- quick tools ----------

    @app.post("/api/tools/triage")
    def tools_triage(body: dict):
        return tools_api.run_triage(settings, find_run_or_404(body.get("run", "")))

    @app.post("/api/tools/promote")
    def tools_promote(body: dict):
        return tools_api.run_promote(settings, find_run_or_404(body.get("run", "")),
                                     body.get("source_templates"))

    @app.post("/api/tools/classify")
    def tools_classify(body: dict):
        return tools_api.run_classify(settings, find_run_or_404(body.get("run", "")))

    # ---------- ad-hoc verification ----------

    @app.post("/api/verify")
    def verify_submit(body: dict):
        return verify_proxy.submit(body.get("root", "main"),
                                   body.get("statement", ""), body.get("proof", ""))

    @app.get("/api/verify")
    def verify_list():
        return verify_proxy.list()

    @app.get("/api/verify/{vid}")
    def verify_get(vid: str):
        return verify_proxy.get(vid)

    @app.get("/api/data-files")
    def data_files(root: str = "main"):
        gen = settings.roots.get(root)
        if gen is None:
            raise HTTPException(400, f"unknown root: {root}")
        data = gen / "data"
        files = []
        if data.is_dir():
            for f in sorted(data.rglob("*.md")):
                files.append(str(f.relative_to(gen)))
                if len(files) >= 1000:
                    break
        return {"root": root, "files": files, "roots": sorted(settings.roots)}

    # ---------- editing ----------

    @app.get("/api/edit")
    def edit_read(path: str, root: str = "main"):
        return edits_api.read_for_edit(settings, root, path)

    @app.put("/api/edit")
    def edit_write(body: dict):
        return edits_api.write_edit(settings, body.get("root", "main"),
                                    body.get("path", ""), body.get("content", ""),
                                    body.get("sha"))

    @app.get("/api/editables")
    def editables(root: str = "main"):
        return edits_api.list_editables(settings, root)

    @app.get("/api/backups")
    def backups(path: str, root: str = "main"):
        return edits_api.list_backups(settings, root, path)

    @app.get("/api/backup-content", response_class=PlainTextResponse)
    def backup_content(name: str):
        return edits_api.read_backup(settings, name)

    @app.get("/api/routes")
    def routes_route(run: str):
        return routes_api.read_routes(settings, find_run_or_404(run))

    @app.get("/api/lineage")
    def lineage_route(run: str):
        return routes_api.read_lineage(settings, index, find_run_or_404(run))

    @app.get("/api/transcript/{session_id}")
    def transcript_route(session_id: str, offset: int = 0, limit: int = 2000):
        result = transcripts.read_transcript(settings, session_id, offset, limit)
        if result is None:
            raise HTTPException(404, f"no rollout found for session {session_id}")
        return result

    @app.get("/api/runs/{run_id:path}")
    def run_detail(run_id: str):
        run = find_run_or_404(run_id)
        run["results"] = index.result_files(settings.roots[run["root"]], run["rel_id"])
        return run

    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app


app = create_app()

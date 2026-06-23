import hashlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.tools_api import VerifyProxy


class MockVerifier(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        # mimic the real API: create a hash-named referee dir
        h = hashlib.sha256(body["statement"].encode()).hexdigest()[:12]
        vdir = self.server.vroot / "results" / f"20990101T000000Z_{h}"
        vdir.mkdir(parents=True, exist_ok=True)
        (vdir / "log.md").write_text("session id: 01900000-0000-7000-8000-0000000000aa\n")
        resp = json.dumps({"verdict": "correct",
                           "verification_report": {"summary": "mock ok"},
                           "run_id": f"20990101T000000Z_{h}",
                           "statement": body["statement"]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)

    def log_message(self, *args):
        pass


@pytest.fixture()
def mock_verifier(settings, monkeypatch):
    server = HTTPServer(("127.0.0.1", 0), MockVerifier)
    server.vroot = settings.vroots["main"]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("RETHLAS_VERIFY_ENDPOINTS",
                       json.dumps({"main": f"http://127.0.0.1:{server.server_port}/verify"}))
    yield server
    server.shutdown()


def test_verify_roundtrip(settings, mock_verifier):
    proxy = VerifyProxy(settings)
    entry = proxy.submit("main", "Theorem: \\(1+1=2\\).", "Proof: by arithmetic.")
    for _ in range(50):
        got = proxy.get(entry["id"])
        if got["status"] != "running":
            break
        time.sleep(0.1)
    assert got["status"] == "done"
    assert got["result"]["verdict"] == "correct"
    assert got["referee_dir"].endswith(got["statement_hash"])
    assert got["log_path"].endswith("log.md")


def test_verify_rejects_empty(settings):
    from fastapi import HTTPException
    proxy = VerifyProxy(settings)
    with pytest.raises(HTTPException):
        proxy.submit("main", "", "proof")


def test_verify_failure_surfaces(settings, monkeypatch):
    monkeypatch.setenv("RETHLAS_VERIFY_ENDPOINTS",
                       json.dumps({"main": "http://127.0.0.1:1/verify"}))
    proxy = VerifyProxy(settings)
    entry = proxy.submit("main", "s", "p")
    for _ in range(50):
        got = proxy.get(entry["id"])
        if got["status"] != "running":
            break
        time.sleep(0.1)
    assert got["status"] == "failed"
    assert "error" in got["result"]

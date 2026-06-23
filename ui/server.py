"""Legacy entry point shim — the backend now lives in the app/ package.

Run:  uvicorn server:app --host 0.0.0.0 --port 8080   (from ui/)
or:   uvicorn app.main:app ...
"""
from app.main import app  # noqa: F401

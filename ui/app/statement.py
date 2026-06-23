"""Bridge to the canonical statement extractor in scripts/.

The extractor is owned by the pipeline (scripts/extract_target_statement.py,
used by run_with_retries.sh) — the UI loads the same implementation so
verification matching stays in lockstep with what the pipeline actually sends.
"""
import importlib.util

from .config import REPO

_spec = importlib.util.spec_from_file_location(
    "extract_target_statement_script", REPO / "scripts" / "extract_target_statement.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

extract_target_statement = _mod.extract_target_statement

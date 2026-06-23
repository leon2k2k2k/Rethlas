#!/usr/bin/env python3
"""Classify a Rethlas blueprint result for autonomous continuation."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from promote_blueprint_obstruction import detect_action  # noqa: E402


CONDITIONAL_PATTERNS = [
    r"\bsharp conditioning\b",
    r"\bsharply condition",
    r"\bconditional\b",
    r"\bnot prove it unconditionally\b",
    r"\bdo not prove it unconditionally\b",
    r"\bnot an unconditional proof\b",
    r"\bnext (specific )?missing\b",
    r"\bfirst missing\b",
    r"\bexact missing\b",
    r"\bto be supplied\b",
    r"\btheorem is exactly\b",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result_dir", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional JSON output path. Defaults to stdout only.",
    )
    return parser.parse_args()


def load_verification(result_dir: Path) -> dict[str, Any]:
    reports = sorted(result_dir.glob("verification_attempt_*.json"))
    if not reports:
        return {}
    path = reports[-1]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"path": str(path), "verdict": "invalid"}
    if isinstance(data, dict):
        data = dict(data)
        data["_path"] = str(path)
        return data
    return {"path": str(path), "verdict": "invalid"}


def blueprint_path(result_dir: Path) -> Path | None:
    verified = result_dir / "blueprint_verified.md"
    if verified.is_file():
        return verified
    plain = result_dir / "blueprint.md"
    if plain.is_file():
        return plain
    return None


def is_conditional(text: str) -> bool:
    lower = text.lower()
    return any(re.search(pattern, lower) for pattern in CONDITIONAL_PATTERNS)


def classify(result_dir: Path) -> dict[str, Any]:
    bp = blueprint_path(result_dir)
    verification = load_verification(result_dir)
    verdict = str(verification.get("verdict") or "")
    if bp is None:
        status = "no_blueprint"
        text = ""
        next_action = ""
    else:
        text = bp.read_text(encoding="utf-8")
        next_action, _suffix = detect_action(text)
        if verdict == "correct" and bp.name == "blueprint_verified.md":
            status = "verified_conditioning" if is_conditional(text) else "verified_final"
        elif verdict == "correct":
            status = "verified_unpromoted"
        elif verdict:
            status = "unverified_blueprint"
        else:
            status = "blueprint_no_verdict"

    return {
        "result_dir": str(result_dir),
        "status": status,
        "blueprint": str(bp) if bp is not None else "",
        "verification_verdict": verdict,
        "verification_path": verification.get("_path", verification.get("path", "")),
        "conditional_markers_present": bool(text and is_conditional(text)),
        "next_action": next_action,
        "should_continue": status in {"verified_conditioning", "unverified_blueprint", "blueprint_no_verdict"},
    }


def main() -> int:
    args = parse_args()
    report = classify(args.result_dir)
    body = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(body, encoding="utf-8")
    print(body, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

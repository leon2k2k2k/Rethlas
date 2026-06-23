#!/usr/bin/env python3
"""Audit a blind Rethlas generation transcript for source-policy violations."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


SOURCE_TEMPLATE_RE = re.compile(r"source_templates/[A-Za-z0-9_.-]+\.md")
COMMAND_LINE_RE = re.compile(r"^/.+\s+in\s+/.+$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--problem-file", type=Path, required=True)
    parser.add_argument("--problem-id", required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def allowed_templates(problem_text: str, log_text: str = "") -> set[str]:
    allowed = set(SOURCE_TEMPLATE_RE.findall(problem_text))
    for line in log_text.splitlines():
        if "SOURCE_TEMPLATE_FILES=" not in line:
            continue
        tail = line.split("SOURCE_TEMPLATE_FILES=", 1)[1]
        tail = tail.split(" Read only", 1)[0]
        tail = tail.split(" Discovery objective", 1)[0]
        tail = tail.strip().rstrip(".")
        for token in tail.split():
            token = token.strip("`'\".,;:")
            if token.endswith(".md") and "/" not in token and ".." not in token:
                allowed.add(f"source_templates/{token}")
    return allowed


def is_command_line(line: str) -> bool:
    return bool(COMMAND_LINE_RE.match(line.strip()))


def audit(problem_text: str, log_text: str, problem_id: str) -> dict[str, Any]:
    allowed = allowed_templates(problem_text, log_text)
    violations: list[dict[str, Any]] = []

    for lineno, line in enumerate(log_text.splitlines(), start=1):
        stripped = line.strip()

        if is_command_line(stripped) and ".agents/skills" in stripped:
            violations.append(
                {
                    "type": "skill_doc_access",
                    "line": lineno,
                    "detail": stripped,
                }
            )

        if is_command_line(stripped) and re.search(
            r"\b(find|ls|rg|grep)\b[^|;&]*\bsource_templates\b", stripped
        ):
            violations.append(
                {
                    "type": "source_template_directory_scan",
                    "line": lineno,
                    "detail": stripped,
                }
            )

        for template in SOURCE_TEMPLATE_RE.findall(line):
            if template not in allowed:
                violations.append(
                    {
                        "type": "unlisted_source_template",
                        "line": lineno,
                        "path": template,
                        "detail": stripped,
                    }
                )

        # codex's native web_search tool runs outside the egress block and can
        # fetch the live post-cutoff proof; any use of it voids a cutoff run.
        if re.search(r"^web search:|\bweb_search\b|web\.run", stripped):
            violations.append({"type": "native_web_search", "line": lineno, "detail": stripped[:120]})

        if is_command_line(stripped) and re.search(r"\bsearch_arxiv_theorems\b", stripped):
            violations.append(
                {
                    "type": "arxiv_search_call",
                    "line": lineno,
                    "detail": stripped,
                }
            )

        # Egress-policy violations: under a literature cutoff the ONLY allowed
        # external access is the frozen_literature MCP tools. Any attempt to
        # reach the network directly, or to strip the egress block, voids the
        # run regardless of whether it succeeded.
        if is_command_line(stripped):
            if re.search(r"\benv\b[^|;&]*-u\s+LD_PRELOAD", stripped) or \
               re.search(r"\bunset\s+LD_PRELOAD\b", stripped):
                violations.append({"type": "egress_block_evasion", "line": lineno, "detail": stripped})
            if re.search(r"\b(curl|wget)\b[^|;&]*https?://(?!127\.0\.0\.1|localhost)", stripped):
                violations.append({"type": "direct_network_access", "line": lineno, "detail": stripped})
            if re.search(r"\b(urllib|requests|httpx|socket)\b", stripped) and \
               re.search(r"https?://(?!127\.0\.0\.1|localhost)", stripped):
                violations.append({"type": "direct_network_access", "line": lineno, "detail": stripped})

    # De-duplicate identical findings that can appear in both command echo and
    # transcript rendering.
    seen: set[tuple[str, int, str]] = set()
    unique: list[dict[str, Any]] = []
    for item in violations:
        key = (str(item.get("type")), int(item.get("line", 0)), str(item.get("detail", item.get("path", ""))))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    return {
        "ok": not unique,
        "problem_id": problem_id,
        "allowed_source_templates": sorted(allowed),
        "violations": unique,
    }


def main() -> int:
    args = parse_args()
    problem_text = args.problem_file.read_text(encoding="utf-8")
    log_text = args.log.read_text(encoding="utf-8") if args.log.exists() else ""
    report = audit(problem_text, log_text, args.problem_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Extract the theorem statement to verify from a Rethlas problem file.

Problem files are research task descriptions (background, blindness policy,
work instructions). The verifier should be judging a proof against a precise
statement, not the whole task file. This extractor returns, in order of
preference:

1. the "## Target Statement" section
2. the "## Focus question" section
3. the "## Problem" section
4. the whole file (no-regression fallback)

A section runs from its heading to the next heading of the same-or-higher
level. Usable both as a library (extract_target_statement) and as a CLI:

    python3 scripts/extract_target_statement.py <problem_file>
"""
import re
import sys

_PREFERRED = ("target statement", "focus question", "problem")


def _sections(text: str):
    """Yield (level, title, body) for every markdown heading section."""
    matches = list(re.finditer(r"^(#{1,6})\s+(.+)$", text, flags=re.M))
    for i, m in enumerate(matches):
        level = len(m.group(1))
        end = len(text)
        for nxt in matches[i + 1:]:
            if len(nxt.group(1)) <= level:
                end = nxt.start()
                break
        yield level, m.group(2).strip(), text[m.end():end].strip()


def extract_target_statement(text: str) -> str:
    sections = list(_sections(text))
    for wanted in _PREFERRED:
        for _level, title, body in sections:
            if title.lower().strip(" :.") == wanted and body:
                return body
    return text.strip()


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    with open(sys.argv[1], errors="replace") as f:
        sys.stdout.write(extract_target_statement(f.read()))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Turn a triaged discovery batch into a next-stage Rethlas problem."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from triage_route_cards import load_json, score_card, validate_card


DEFAULT_TEMPLATES = [
    "escape_operators.md",
    "hidden_coordinate_bridge.md",
    "source_family_discovery.md",
    "unit_distance_number_theory_transition.md",
    "number_field_source_menu.md",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "batch_result_dir",
        type=Path,
        help="Directory containing promotion_decision.json and sample route cards.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root. Defaults to the parent of scripts/.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of route cards to embed in the generated problem.",
    )
    parser.add_argument(
        "--model",
        default="gpt-5.5",
        help="Model for the generated launch command.",
    )
    parser.add_argument(
        "--reasoning-effort",
        default="xhigh",
        help="Reasoning effort for the generated launch command.",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="MAX_ATTEMPTS for the generated repair command.",
    )
    parser.add_argument(
        "--codex-silent-timeout-seconds",
        default="900",
        help="CODEX_SILENT_TIMEOUT_SECONDS for the generated launch command.",
    )
    parser.add_argument(
        "--codex-poll-seconds",
        default="30",
        help="CODEX_POLL_SECONDS for the generated launch command.",
    )
    parser.add_argument(
        "--source-template",
        action="append",
        default=[],
        help="Source template basename to allow. Can be passed more than once.",
    )
    parser.add_argument(
        "--launch",
        action="store_true",
        help="Run the generated next-stage command after writing manifests.",
    )
    parser.add_argument(
        "--triage-if-missing",
        action="store_true",
        help="Run scripts/triage_route_cards.py if promotion_decision.json is missing.",
    )
    return parser.parse_args()


def safe_stem(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text.strip())
    text = re.sub(r"_+", "_", text).strip("._")
    return text or "promotion"


def repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def load_manifest(batch_dir: Path) -> dict[str, Any]:
    path = batch_dir / "batch_manifest.json"
    if not path.exists():
        return {}
    data, err = load_json(path)
    if err or data is None:
        raise SystemExit(f"invalid batch_manifest.json: {err}")
    return data


def ensure_decision(batch_dir: Path, repo_root: Path, triage_if_missing: bool) -> dict[str, Any]:
    decision_path = batch_dir / "promotion_decision.json"
    if not decision_path.exists() and triage_if_missing:
        subprocess.run(
            [sys.executable, str(repo_root / "scripts" / "triage_route_cards.py"), str(batch_dir)],
            check=True,
        )
    data, err = load_json(decision_path)
    if err or data is None:
        raise SystemExit(
            f"missing or invalid promotion_decision.json at {decision_path}; "
            "run scripts/triage_route_cards.py first"
        )
    return data


def load_valid_cards(batch_dir: Path) -> list[tuple[Path, dict[str, Any], float]]:
    cards: list[tuple[Path, dict[str, Any], float]] = []
    for path in sorted(batch_dir.glob("**/route_card.json")):
        card, err = load_json(path)
        if err or card is None:
            continue
        if validate_card(card):
            continue
        cards.append((path, card, score_card(card)))
    return sorted(cards, key=lambda item: item[2], reverse=True)


def original_problem_text(repo_root: Path, manifest: dict[str, Any]) -> tuple[str, str]:
    problem_file = str(manifest.get("problem_file") or "data/discrete_geometry/unit_distance_disproof.md")
    if problem_file.startswith("/") or ".." in Path(problem_file).parts or not problem_file.startswith("data/"):
        raise SystemExit(f"unsafe problem_file in manifest: {problem_file}")
    path = repo_root / "agents" / "generation" / problem_file
    if not path.is_file():
        raise SystemExit(f"original problem file not found: {path}")
    return problem_file, path.read_text(encoding="utf-8")


def action_instructions(action: str) -> str:
    if action == "launch_number_field_source_repair":
        return """\
## Next-stage task: number-field source construction

The discovery batch promoted to arithmetic source repair. Develop the best route
cards into a candidate source construction that can supply many exact
same-length or unit-modulus displacements for a hidden-coordinate/product-window
bridge.

Requirements for this stage:

1. Compare at least three arithmetic source families before committing.
2. Track degree/rank, covolume or discriminant cost, source entropy, and
   projection/collision cost in formulas.
3. Start from the route-card transition evidence: equal-length bottleneck,
   fixed-rank failure, hidden-coordinate move, and entropy-vs-cost ledger.
4. Do not assume a split-prime, class-group, CM, or ideal construction wins.
   Treat each as a candidate to test.
5. If a number-field source appears viable, write the conditional bridge,
   source lemma, and parameter inequality slots needed for final assembly.
6. If no viable source is found, write the exact obstruction as a route card
   style summary inside the blueprint.
"""
    if action == "launch_source_family_discovery":
        return """\
## Next-stage task: source-family discovery

The discovery batch found a repeated source-entropy bottleneck. Compare broad
families that could provide many exact same-length displacements after all
realization costs are paid. Promote to number-field repair only if the route
cards justify it.
"""
    if action == "launch_growing_degree_arithmetic_discovery":
        return """\
## Next-stage task: growing-degree arithmetic discovery

The discovery batch suggests fixed-rank or sparse sources are not enough. Test
growing-degree arithmetic objects while tracking discriminant, covolume,
projection, and collision costs.
"""
    if action == "launch_hidden_coordinate_bridge":
        return """\
## Next-stage task: hidden-coordinate bridge

The discovery batch repeatedly asked for a representation change. Prove a
conditional bridge from an ambient product-space construction to planar
unit-distance sets, then identify the exact source property still missing.
"""
    if action == "launch_parameter_assembly_repair":
        return """\
## Next-stage task: parameter assembly

At least one route card reached parameter assembly. Turn the conditional lemmas
and source estimates into a complete proof blueprint, with explicit constants
or a clear existence argument.
"""
    if action == "launch_verification_and_repair":
        return """\
## Next-stage task: verification and repair

At least one route card claims a complete construction. Assemble the candidate
proof, run verifier-oriented repair, and write the final theorem only if every
major lemma has been stated and justified.
"""
    return """\
## Next-stage task: continue discovery

No strong promotion threshold was met. Use the embedded route cards to choose a
new independent family of routes, not local repair of a single failed attempt.
"""


def route_card_section(
    cards: list[tuple[Path, dict[str, Any], float]],
    batch_dir: Path,
    repo_root: Path,
    top_k: int,
) -> str:
    if not cards:
        return "## Promoted route cards\n\nNo valid route cards were found.\n"

    lines = ["## Promoted route cards", ""]
    for idx, (path, card, score) in enumerate(cards[:top_k], start=1):
        lines.extend(
            [
                f"### Route card {idx}: score {score:.1f}",
                "",
                f"- path: `{repo_relative(path, repo_root)}`",
                f"- stage: `{card.get('stage')}`",
                f"- discovery_mode: `{card.get('discovery_mode')}`",
                f"- construction_family: {card.get('construction_family', '')}",
                f"- transition_signal: {card.get('transition_signal', '')}",
                f"- positive_reduction: {card.get('positive_reduction', '')}",
                f"- missing_object: {card.get('missing_object', '')}",
                f"- failed_because: {card.get('failed_because', '')}",
                f"- next_stage: {card.get('next_stage', '')}",
                f"- next_source_families: {', '.join(card.get('next_source_families', []))}",
                "",
                "Cost formula:",
                "",
            ]
        )
        cost = card.get("cost_formula", {})
        if isinstance(cost, dict):
            for key, value in cost.items():
                lines.append(f"- `{key}`: {value}")
        signals = card.get("unit_distance_signals")
        if isinstance(signals, dict):
            lines.extend(["", "Unit-distance transition signals:", ""])
            for key, value in signals.items():
                lines.append(f"- `{key}`: {value}")
        evidence = card.get("stage_evidence")
        if isinstance(evidence, list) and evidence:
            lines.extend(["", "Stage evidence:", ""])
            for item in evidence:
                lines.append(f"- {item}")
        lines.append("")
    return "\n".join(lines)


def write_problem(
    repo_root: Path,
    batch_dir: Path,
    manifest: dict[str, Any],
    decision: dict[str, Any],
    cards: list[tuple[Path, dict[str, Any], float]],
    templates: list[str],
    top_k: int,
) -> tuple[Path, str]:
    action = str(decision.get("action") or "continue_general_discovery")
    batch_id = str(manifest.get("batch_id") or batch_dir.name)
    stem = f"{safe_stem(batch_id)}__{safe_stem(action)}"
    rel_problem = f"data/generated/{stem}.md"
    problem_path = repo_root / "agents" / "generation" / rel_problem
    problem_id = f"generated/{stem}"
    original_path, original_text = original_problem_text(repo_root, manifest)

    decision_json = json.dumps(decision, indent=2, sort_keys=True)
    template_list = "\n".join(f"- `source_templates/{name}`" for name in templates)

    body = f"""\
# Generated Rethlas promotion problem

Generated from discovery batch `{batch_id}`.

Original problem file: `{original_path}`
Promotion action: `{action}`

## Blindness and source policy

Do not search the web or arXiv. Do not read target-proof notes, OpenAI
chain-of-thought material, recent announcements, or unlisted local notes. You
may read only the listed generic source-template files:

{template_list}

This allowlist is complete. Do not read `.agents/skills/*.md`, sibling
`memory/` or `results/`, reference directories, or other local helper notes
unless a later prompt explicitly lists those exact files. Do not run `find`,
`ls`, `rg`, or `grep` over `source_templates/`; open only exact listed files by
path if needed.

The route-card summaries below are outputs of earlier independent discovery
samples. Treat them as hypotheses to test, not as trusted facts.

{action_instructions(action)}

## Promotion decision

```json
{decision_json}
```

{route_card_section(cards, batch_dir, repo_root, top_k)}

## Original problem

{original_text}
"""

    problem_path.parent.mkdir(parents=True, exist_ok=True)
    problem_path.write_text(body, encoding="utf-8")
    return problem_path, problem_id


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def write_manifest(
    batch_dir: Path,
    repo_root: Path,
    problem_path: Path,
    problem_id: str,
    decision: dict[str, Any],
    args: argparse.Namespace,
    templates: list[str],
) -> dict[str, Any]:
    rel_problem = repo_relative(problem_path, repo_root)
    problem_file = rel_problem.removeprefix("agents/generation/")
    command = (
        f"PROBLEM_FILE={shell_quote(problem_file)} "
        f"PROBLEM_ID={shell_quote(problem_id)} "
        f"MAX_ATTEMPTS={args.max_attempts} "
        f"MODEL={shell_quote(args.model)} "
        f"REASONING_EFFORT={shell_quote(args.reasoning_effort)} "
        f"CODEX_SILENT_TIMEOUT_SECONDS={shell_quote(str(args.codex_silent_timeout_seconds))} "
        f"CODEX_POLL_SECONDS={shell_quote(str(args.codex_poll_seconds))} "
        "BLIND_RUN=1 scripts/run_with_retries.sh"
    )
    manifest = {
        "action": decision.get("action"),
        "generated_problem_file": problem_file,
        "generated_problem_id": problem_id,
        "source_templates": templates,
        "launch_command": command,
    }
    path = batch_dir / "promotion_manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (batch_dir / "launch_promotion.sh").write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + command + "\n", encoding="utf-8")
    (batch_dir / "launch_promotion.sh").chmod(0o755)
    return manifest


def launch(repo_root: Path, manifest: dict[str, Any]) -> int:
    completed = subprocess.run(
        str(manifest["launch_command"]),
        cwd=repo_root,
        shell=True,
        executable="/bin/bash",
        check=False,
    )
    return completed.returncode


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    batch_dir = args.batch_result_dir.resolve()
    if not batch_dir.is_dir():
        raise SystemExit(f"batch result dir not found: {batch_dir}")

    decision = ensure_decision(batch_dir, repo_root, args.triage_if_missing)
    manifest = load_manifest(batch_dir)
    cards = load_valid_cards(batch_dir)
    templates = args.source_template or DEFAULT_TEMPLATES

    problem_path, problem_id = write_problem(
        repo_root=repo_root,
        batch_dir=batch_dir,
        manifest=manifest,
        decision=decision,
        cards=cards,
        templates=templates,
        top_k=args.top_k,
    )
    promotion_manifest = write_manifest(
        batch_dir=batch_dir,
        repo_root=repo_root,
        problem_path=problem_path,
        problem_id=problem_id,
        decision=decision,
        args=args,
        templates=templates,
    )

    print(f"action={promotion_manifest['action']}")
    print(f"generated_problem_file={promotion_manifest['generated_problem_file']}")
    print(f"generated_problem_id={promotion_manifest['generated_problem_id']}")
    print(f"launch_command={promotion_manifest['launch_command']}")

    if args.launch:
        return launch(repo_root, promotion_manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

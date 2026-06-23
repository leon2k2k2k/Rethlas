#!/usr/bin/env python3
"""Promote a failed blueprint obstruction into the next focused problem."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any


DEFAULT_TEMPLATES = [
    "number_field_source_menu.md",
    "relative_s_unit_source_lemma.md",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "run_result_dir",
        type=Path,
        help="Result directory containing blueprint.md from a promoted repair run.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root. Defaults to the parent of scripts/.",
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
        help="MAX_ATTEMPTS for the generated source-lemma run.",
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
    return parser.parse_args()


def safe_stem(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text.strip())
    text = re.sub(r"_+", "_", text).strip("._")
    return text or "source_obstruction"


def bounded_stem(stem: str, limit: int = 180) -> str:
    """Keep generated file and directory names below filesystem limits."""
    if len(stem) <= limit:
        return stem
    digest = hashlib.sha1(stem.encode("utf-8")).hexdigest()[:10]
    keep = max(20, limit - len(digest) - 2)
    prefix = stem[:keep].rstrip("._-") or "generated"
    return f"{prefix}__{digest}"


def repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def extract_section(markdown: str, heading: str) -> str:
    """Extract a markdown section headed by '# ... heading ...'."""
    pattern = re.compile(rf"^(#+)\s+.*{re.escape(heading)}.*$", re.IGNORECASE | re.MULTILINE)
    match = pattern.search(markdown)
    if not match:
        return ""
    level = len(match.group(1))
    start = match.end()
    next_heading = re.compile(rf"^#{{1,{level}}}\s+", re.MULTILINE)
    next_match = next_heading.search(markdown, start)
    end = next_match.start() if next_match else len(markdown)
    return markdown[start:end].strip()


def extract_field(markdown: str, field: str, limit: int = 2500) -> str:
    """Extract a possibly wrapped 'field: value' block from loose markdown."""
    lines = markdown.splitlines()
    start = None
    first_value = ""
    field_re = re.compile(rf"^{re.escape(field)}\s*:\s*(.*)$", re.IGNORECASE)
    next_field_re = re.compile(r"^[a-z][a-z0-9_ -]{1,60}\s*:")
    for idx, line in enumerate(lines):
        match = field_re.match(line.strip())
        if match:
            start = idx
            first_value = match.group(1).strip()
            break
    if start is None:
        return ""

    out = [first_value] if first_value else []
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if next_field_re.match(stripped):
            break
        out.append(line.rstrip())
    return compact_excerpt("\n".join(out).strip(), limit)


def compact_excerpt(text: str, limit: int = 14000) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    half = max(1000, limit // 2)
    return text[:half].rstrip() + "\n\n[...middle omitted...]\n\n" + text[-half:].lstrip()


def detect_action(blueprint: str) -> tuple[str, str]:
    """Return (manifest_action, filename_suffix) for the next promotion."""
    if re.search(
        r"relative norm-one coordinate input",
        blueprint,
        re.IGNORECASE,
    ) or extract_section(blueprint, "def:relative_norm_one_coordinate_input"):
        return "launch_relative_norm_one_coordinate", "relative_norm_one_coordinate"
    if re.search(
        r"cyclotomic decomposition-field principal-coordinate theorem",
        blueprint,
        re.IGNORECASE,
    ) or extract_section(blueprint, "def:cyclotomic_pc_input"):
        return "launch_cyclotomic_principal_coordinate", "cyclotomic_principal_coordinate"
    if re.search(
        r"bounded-coordinate principal split-prime CM source theorem",
        blueprint,
        re.IGNORECASE,
    ) or re.search(
        r"bounded-coordinate principal split-prime cm source",
        blueprint,
        re.IGNORECASE,
    ):
        return "launch_cm_mechanism_search", "cm_mechanism_search"
    if extract_section(blueprint, "aw:arithmetic_window_sequence") or re.search(
        r"positive-density principal norm-\s*p", blueprint, re.IGNORECASE
    ):
        return "launch_cm_sequence_existence", "cm_sequence_existence"
    if extract_section(blueprint, "thm:first_missing_arithmetic_window_theorem") or re.search(
        r"uniformly window-regular CM sequence", blueprint, re.IGNORECASE
    ):
        return "launch_arithmetic_window_assertion", "arithmetic_window_assertion"
    if extract_section(blueprint, "prop:needed_arithmetic_theorem") or re.search(
        r"balanced principal split-prime relative", blueprint, re.IGNORECASE
    ):
        return "launch_needed_arithmetic_theorem", "needed_arithmetic_theorem"
    return "launch_source_lemma_repair", "source_lemma_repair"


def source_policy_section(templates: list[str]) -> str:
    template_list = "\n".join(f"- `source_templates/{name}`" for name in templates)
    return f"""\
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
"""


def generated_needed_arithmetic_body(
    *,
    run_result_dir: Path,
    repo_root: Path,
    blueprint: str,
    templates: list[str],
) -> str:
    needed = extract_section(blueprint, "prop:needed_arithmetic_theorem")
    if not needed:
        needed = compact_excerpt(blueprint, 10000)
    theorem_summary = extract_section(blueprint, "thm:conditional_relative_s_unit_source")
    blueprint_rel = repo_relative(run_result_dir / "blueprint.md", repo_root)

    return f"""\
# Generated needed-arithmetic-theorem problem

Generated from source-lemma blueprint:

```text
{blueprint_rel}
```

The prior run reduced the source lemma to a balanced principal split-prime
relative S-unit theorem. This task isolates that arithmetic theorem.

{source_policy_section(templates)}

## Focused task

Prove, refute, or sharply condition the balanced principal split-prime relative
S-unit theorem. Do not re-prove the hidden-coordinate bridge or the conditional
source ledger unless you find an error in the stated reduction.

The target is to construct, in growing CM degree, linearly many bounded-norm
principal conjugate prime-pair generators with enough independence and regular
windows so that the entropy margin

```text
alpha log(2B+1) - kappa - gamma > 0
```

is strict.

## Required deliverable

Start by stating a precise arithmetic theorem with parameters. The theorem must
specify:

1. the CM field or field tower;
2. the source of linearly many conjugate prime-pair or ideal-ratio directions;
3. why the directions are principal or how principalization is paid for;
4. generator-height and common-denominator bounds;
5. independence of the exponent box;
6. discriminant/covolume or window-size bounds;
7. the constants in the final entropy-vs-loss inequality.

If the theorem cannot be proved from the allowed blind inputs, write a no-go or
conditional result identifying the first missing arithmetic theorem.

## Prior needed theorem excerpt

```markdown
{compact_excerpt(needed, 12000)}
```

## Prior conditional source theorem excerpt

```markdown
{compact_excerpt(theorem_summary, 9000) if theorem_summary else "(not extracted)"}
```
"""


def generated_arithmetic_window_body(
    *,
    run_result_dir: Path,
    repo_root: Path,
    blueprint: str,
    templates: list[str],
) -> str:
    missing = extract_section(blueprint, "thm:first_missing_arithmetic_window_theorem")
    if not missing:
        missing = compact_excerpt(blueprint, 10000)
    conditional = extract_section(blueprint, "thm:conditional_arithmetic_window_source")
    blueprint_rel = repo_relative(run_result_dir / "blueprint.md", repo_root)

    return f"""\
# Generated arithmetic-window assertion problem

Generated from needed-arithmetic blueprint:

```text
{blueprint_rel}
```

The prior run reduced the balanced principal split-prime theorem to a more
specific arithmetic-window assertion. This task isolates that assertion.

{source_policy_section(templates)}

## Focused task

Prove, refute, or sharply condition the existence of a growing CM sequence with:

1. positive-density bounded-norm principal conjugate prime-pair directions;
2. independent exponent boxes;
3. a common module/denominator with linear norm cost;
4. a uniform product-coordinate height bound for all source elements;
5. regular additive windows whose survival loss leaves a strict entropy margin.

Do not re-prove the hidden-coordinate bridge, the source ledger, or the
balanced split-prime reduction unless you find an error in those reductions.

## Required deliverable

State the arithmetic-window assertion first, with explicit parameters. Then
either prove it, disprove it in this blind setting, or identify the next
specific missing arithmetic theorem.

The critical point to resolve is whether positive-density principal small-prime
directions and a uniform window-height bound can be achieved simultaneously in
growing CM degree.

## Prior missing theorem excerpt

```markdown
{compact_excerpt(missing, 12000)}
```

## Prior conditional source excerpt

```markdown
{compact_excerpt(conditional, 9000) if conditional else "(not extracted)"}
```
"""


def generated_cm_sequence_body(
    *,
    run_result_dir: Path,
    repo_root: Path,
    blueprint: str,
    templates: list[str],
) -> str:
    assertion = extract_section(blueprint, "aw:arithmetic_window_sequence")
    if not assertion:
        assertion = compact_excerpt(blueprint, 10000)
    constraints = extract_section(blueprint, "lem:necessary_parameter_constraints")
    target = extract_section(blueprint, "thm:target_answer")
    blueprint_rel = repo_relative(run_result_dir / "blueprint_verified.md", repo_root)
    if not (run_result_dir / "blueprint_verified.md").exists():
        blueprint_rel = repo_relative(run_result_dir / "blueprint.md", repo_root)

    return f"""\
# Generated CM-sequence existence problem

Generated from verified arithmetic-window assertion blueprint:

```text
{blueprint_rel}
```

The prior run verified that the arithmetic-window stage is correctly reduced to
one simultaneous CM-sequence existence problem. This task isolates that
existence problem.

{source_policy_section(templates)}

## Focused task

Construct, refute, or sharply condition a growing CM sequence with simultaneous:

1. positive-density principal norm-p conjugate prime-pair directions;
2. independent exponent boxes;
3. a common denominator module with linear norm cost;
4. a basis in which the whole source exponent box has uniformly bounded
   product-coordinate height;
5. collision control small enough to leave a strict entropy margin.

Do not re-prove the source ledger or coordinate-window lemma unless you find an
error in those verified reductions.

## Required deliverable

Start with a precise CM-sequence theorem. Then either:

1. give an explicit infinite family and prove all five properties;
2. prove a no-go theorem showing the simultaneous conditions cannot hold; or
3. name the next strictly smaller arithmetic input needed, with formulas for
   exactly where it enters the ledger.

The key unresolved tension is between positive-density principal small-prime
generators and uniformly bounded product coordinates for all products in the
source box.

## Prior arithmetic-window assertion excerpt

```markdown
{compact_excerpt(assertion, 12000)}
```

## Necessary parameter constraints excerpt

```markdown
{compact_excerpt(constraints, 8000) if constraints else "(not extracted)"}
```

## Prior target-answer excerpt

```markdown
{compact_excerpt(target, 8000) if target else "(not extracted)"}
```
"""


def generated_cm_mechanism_search_body(
    *,
    run_result_dir: Path,
    repo_root: Path,
    blueprint: str,
    templates: list[str],
) -> str:
    missing = extract_section(
        blueprint, "thm:bounded_coordinate_principal_split_prime_cm_source"
    )
    if not missing:
        missing = compact_excerpt(blueprint, 9000)
    constraints = extract_section(blueprint, "lem:necessary_parameter_constraints")
    ledger = extract_section(blueprint, "thm:conditional_ledger_from_cm_source")
    blueprint_rel = repo_relative(run_result_dir / "blueprint_verified.md", repo_root)
    if not (run_result_dir / "blueprint_verified.md").exists():
        blueprint_rel = repo_relative(run_result_dir / "blueprint.md", repo_root)

    return f"""\
# Generated CM mechanism-search problem

Generated from a verified sharp conditional blueprint:

```text
{blueprint_rel}
```

The prior run verified a conditional reduction. It did not construct the
arithmetic source. This task deliberately backs off one level of hinting: stay
inside the number-field/CM corridor, but do not begin by restating the prior
five-property theorem as an assumption.

{source_policy_section(templates)}

## Focused task

Find a concrete arithmetic mechanism that could supply the missing source, or
prove that a natural mechanism cannot supply it. You may use the allowed source
templates as generic background, but you must choose and analyze the mechanism
yourself.

Start with a mechanism table containing at least four distinct candidates. For
each candidate, fill these slots with formulas or inequalities:

1. ambient field or tower;
2. module or fractional ideal for the point window;
3. source elements with exact visible unit length;
4. source entropy as a function of degree or rank;
5. common denominator or principalization cost;
6. coordinate/window survival cost;
7. collision or representation cost;
8. the sign of the resulting exponent margin.

Then select the strongest candidate and push it as far as possible.

## Anti-collapse rules

Do not output a theorem whose hypotheses already contain all desired ledger
properties. A conditional result is allowed only if the missing input is
strictly smaller than the previous five-property theorem, for example a
specific generator-height theorem, a principalization theorem for one explicit
tower, a bounded-coordinate basis theorem for one explicit source, or a no-go
inequality for one explicit family.

Do not spend the main run re-proving the hidden-coordinate bridge or the
coordinate-window ledger unless you find an error in the verified reduction.

## Required deliverable

The output must be one of:

1. an explicit infinite candidate family with all ledger terms proved;
2. a no-go theorem for one or more natural candidate families, with the exact
   losing term identified;
3. a strictly smaller arithmetic theorem that would close one selected family,
   together with the formulas showing exactly where it enters the ledger.

If you give option 3, explain why the new theorem is smaller than the prior
five-property CM source theorem.

## Prior conditional bottleneck excerpt

The excerpt below is included only so you know what the previous run failed to
construct. Do not simply restate it as the answer.

```markdown
{compact_excerpt(missing, 9000)}
```

## Necessary ledger constraints excerpt

```markdown
{compact_excerpt(constraints, 6000) if constraints else "(not extracted)"}
```

## Prior conditional ledger excerpt

```markdown
{compact_excerpt(ledger, 7000) if ledger else "(not extracted)"}
```
"""


def generated_cyclotomic_principal_coordinate_body(
    *,
    run_result_dir: Path,
    repo_root: Path,
    blueprint: str,
    templates: list[str],
) -> str:
    tower = extract_section(blueprint, "lem:cyclotomic_decomposition_tower")
    pc_input = extract_section(blueprint, "def:cyclotomic_pc_input")
    ledger = extract_section(blueprint, "prop:explicit_tower_ledger")
    blueprint_rel = repo_relative(run_result_dir / "blueprint_verified.md", repo_root)
    if not (run_result_dir / "blueprint_verified.md").exists():
        blueprint_rel = repo_relative(run_result_dir / "blueprint.md", repo_root)

    return f"""\
# Generated cyclotomic principal-coordinate problem

Generated from a verified CM mechanism-search blueprint:

```text
{blueprint_rel}
```

The prior run verified an explicit cyclotomic decomposition-field mechanism.
It did not prove the remaining principal-coordinate theorem. This task isolates
that theorem for the single selected tower.

{source_policy_section(templates)}

## Focused task

For the explicit tower

```text
m_k = 2^(2k+1) - 1
L_k = Q(zeta_{{m_k}})
K_k = L_k^{{<Frob_2>}}
```

prove, refute, or sharply condition the cyclotomic decomposition-field
principal-coordinate theorem.

You must not restate the theorem as an assumption. Analyze the two real
subproblems separately:

1. principality of the degree-one primes of `K_k` above `2`, after choosing one
   from each conjugation pair;
2. existence of a basis of the resulting denominator module in which the entire
   exponent box has fixed coordinate half-width.

## Required deliverable

The output must be one of:

1. a proof of the principal-coordinate theorem for this tower;
2. a no-go theorem for this tower, identifying whether principality,
   generator-height, or coordinate width is the first impossible term;
3. a strictly smaller arithmetic input for this tower only, with formulas
   showing exactly how it enters the ledger.

If option 3 is used, the new input must be smaller than the principal-coordinate
theorem. Examples: a class-group statement proving the selected primes are
principal, a generator-height theorem for the explicit prime generators, or a
basis-shaping theorem after generators are fixed.

## Explicit tower excerpt

```markdown
{compact_excerpt(tower, 9000) if tower else "(not extracted)"}
```

## Principal-coordinate theorem excerpt

```markdown
{compact_excerpt(pc_input, 9000) if pc_input else "(not extracted)"}
```

## Conditional ledger excerpt

```markdown
{compact_excerpt(ledger, 9000) if ledger else "(not extracted)"}
```
"""


def generated_relative_norm_one_coordinate_body(
    *,
    run_result_dir: Path,
    repo_root: Path,
    blueprint: str,
    templates: list[str],
) -> str:
    relative_input = extract_section(blueprint, "def:relative_norm_one_coordinate_input")
    principality = extract_section(blueprint, "lem:principality_first_term")
    smaller = extract_section(blueprint, "lem:smaller_than_principal_coordinate")
    ledger = extract_section(blueprint, "lem:relative_input_ledger")
    blueprint_rel = repo_relative(run_result_dir / "blueprint_verified.md", repo_root)
    if not (run_result_dir / "blueprint_verified.md").exists():
        blueprint_rel = repo_relative(run_result_dir / "blueprint.md", repo_root)

    return f"""\
# Generated relative norm-one coordinate problem

Generated from a verified principal-coordinate narrowing blueprint:

```text
{blueprint_rel}
```

The prior run verified that the principal-coordinate theorem can be replaced by
a smaller tower-specific relative norm-one coordinate input. It did not prove
that input. This task isolates that input for the same explicit tower.

{source_policy_section(templates)}

## Focused task

For the explicit tower

```text
m_k = 2^(2k+1) - 1
L_k = Q(zeta_{{m_k}})
K_k = L_k^{{<Frob_2>}}
```

prove, refute, or sharply condition the relative norm-one coordinate input.

Do not restate the relative input as an assumption. Analyze the three real
subproblems separately:

1. ideal-ratio principality: for one prime from each conjugation pair above
   `2`, whether `p_j c(p_j)^(-1)` is principal;
2. norm-one normalization: if `p_j c(p_j)^(-1)` has a generator `w_j`, whether
   one can choose a generator `v_j` with `v_j c(v_j)=1`;
3. basis shaping: after such `v_j` are fixed, whether the full exponent box in
   `2^(-B) O_K` has a basis with fixed coordinate half-width.

## Required deliverable

The output must be one of:

1. a proof of the relative norm-one coordinate input for this tower;
2. a no-go theorem for this tower, identifying whether ideal-ratio
   principality, norm-one normalization, or coordinate width is the first
   impossible term;
3. a strictly smaller arithmetic input for this tower only, with formulas
   showing exactly how it enters the ledger.

If option 3 is used, the new input must be smaller than the relative norm-one
coordinate input. Examples: an anti-invariant class-group statement for primes
above `2`, a unit-norm normalization theorem for explicit quotient generators,
or a basis-shaping theorem after the relative generators are fixed.

## Relative norm-one coordinate input excerpt

```markdown
{compact_excerpt(relative_input, 9000) if relative_input else "(not extracted)"}
```

## Prior principality comparison excerpt

```markdown
{compact_excerpt(principality, 5000) if principality else "(not extracted)"}
```

## Prior smaller-input proof excerpt

```markdown
{compact_excerpt(smaller, 6000) if smaller else "(not extracted)"}
```

## Conditional ledger excerpt

```markdown
{compact_excerpt(ledger, 9000) if ledger else "(not extracted)"}
```
"""


def generated_problem_body(
    *,
    run_result_dir: Path,
    repo_root: Path,
    blueprint: str,
    templates: list[str],
) -> str:
    action, _suffix = detect_action(blueprint)
    if action == "launch_relative_norm_one_coordinate":
        return generated_relative_norm_one_coordinate_body(
            run_result_dir=run_result_dir,
            repo_root=repo_root,
            blueprint=blueprint,
            templates=templates,
        )
    if action == "launch_cyclotomic_principal_coordinate":
        return generated_cyclotomic_principal_coordinate_body(
            run_result_dir=run_result_dir,
            repo_root=repo_root,
            blueprint=blueprint,
            templates=templates,
        )
    if action == "launch_cm_mechanism_search":
        return generated_cm_mechanism_search_body(
            run_result_dir=run_result_dir,
            repo_root=repo_root,
            blueprint=blueprint,
            templates=templates,
        )
    if action == "launch_cm_sequence_existence":
        return generated_cm_sequence_body(
            run_result_dir=run_result_dir,
            repo_root=repo_root,
            blueprint=blueprint,
            templates=templates,
        )
    if action == "launch_arithmetic_window_assertion":
        return generated_arithmetic_window_body(
            run_result_dir=run_result_dir,
            repo_root=repo_root,
            blueprint=blueprint,
            templates=templates,
        )
    if action == "launch_needed_arithmetic_theorem":
        return generated_needed_arithmetic_body(
            run_result_dir=run_result_dir,
            repo_root=repo_root,
            blueprint=blueprint,
            templates=templates,
        )

    obstruction = extract_section(blueprint, "route-card obstruction summary")
    if not obstruction:
        obstruction = extract_section(blueprint, "theorem target")
    if not obstruction:
        obstruction = compact_excerpt(blueprint, 9000)

    missing_object = extract_field(obstruction, "missing_object") or extract_field(
        blueprint, "missing_object"
    )
    next_stage = extract_field(obstruction, "next_stage") or "source_lemma_repair"
    construction_family = extract_field(obstruction, "construction_family")

    blueprint_rel = repo_relative(run_result_dir / "blueprint.md", repo_root)

    return f"""\
# Generated source-lemma obstruction problem

Generated from failed/partial blueprint:

```text
{blueprint_rel}
```

The prior run reached a conditional hidden-coordinate bridge, but it did not
prove the arithmetic source lemma needed for the final unit-distance theorem.
This task isolates that missing lemma.

{source_policy_section(templates)}

## Focused task

Prove, refute, or sharply condition the missing source lemma. Do not spend the
main run rediscovering the hidden-coordinate bridge unless you find an error in
it.

Prior construction family:

```text
{construction_family or "(not extracted)"}
```

Prior missing object:

```text
{missing_object or "(not extracted)"}
```

Prior next stage:

```text
{next_stage}
```

## Required source-lemma deliverable

Start by stating a precise source lemma with parameters. The lemma must specify:

1. the field or field tower;
2. the module or fractional ideal containing both points and displacements;
3. the source set with exact visible unit length;
4. the common denominator/module cost;
5. the window-survival fraction;
6. collision control;
7. the final positive exponent inequality.

Then test candidate constructions against the cost ledger. A viable proof must
show a strict positive margin after regulator, class-group, denominator,
discriminant/covolume, window-survival, and collision costs.

If no construction works, write a no-go obstruction that identifies the first
cost term that kills each family and says what new arithmetic theorem would be
needed.

## Prior obstruction excerpt

```markdown
{compact_excerpt(obstruction, 12000)}
```
"""


def write_problem(
    *,
    run_result_dir: Path,
    repo_root: Path,
    blueprint: str,
    templates: list[str],
) -> tuple[Path, str]:
    run_stem = safe_stem(run_result_dir.name)
    _action, suffix = detect_action(blueprint)
    stem = bounded_stem(f"{run_stem}__{suffix}")
    rel_problem = f"data/generated/{stem}.md"
    problem_path = repo_root / "agents" / "generation" / rel_problem
    problem_id = f"generated/{stem}"
    body = generated_problem_body(
        run_result_dir=run_result_dir,
        repo_root=repo_root,
        blueprint=blueprint,
        templates=templates,
    )
    problem_path.parent.mkdir(parents=True, exist_ok=True)
    problem_path.write_text(body, encoding="utf-8")
    return problem_path, problem_id


def write_manifest(
    *,
    run_result_dir: Path,
    repo_root: Path,
    problem_path: Path,
    problem_id: str,
    args: argparse.Namespace,
    templates: list[str],
) -> dict[str, Any]:
    rel_problem = repo_relative(problem_path, repo_root)
    problem_file = rel_problem.removeprefix("agents/generation/")
    source_blueprint_path = run_result_dir / "blueprint_verified.md"
    if not source_blueprint_path.exists():
        source_blueprint_path = run_result_dir / "blueprint.md"
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
    action, _suffix = detect_action((run_result_dir / "blueprint.md").read_text(encoding="utf-8"))
    manifest = {
        "action": action,
        "source_blueprint": repo_relative(source_blueprint_path, repo_root),
        "generated_problem_file": problem_file,
        "generated_problem_id": problem_id,
        "source_templates": templates,
        "launch_command": command,
    }
    path = run_result_dir / "source_obstruction_promotion_manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    launch_path = run_result_dir / "launch_source_obstruction.sh"
    launch_path.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + command + "\n", encoding="utf-8")
    launch_path.chmod(0o755)
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
    run_result_dir = args.run_result_dir.resolve()
    blueprint_path = run_result_dir / "blueprint.md"
    if not blueprint_path.is_file():
        raise SystemExit(f"blueprint.md not found: {blueprint_path}")

    templates = args.source_template or DEFAULT_TEMPLATES
    blueprint = blueprint_path.read_text(encoding="utf-8")
    problem_path, problem_id = write_problem(
        run_result_dir=run_result_dir,
        repo_root=repo_root,
        blueprint=blueprint,
        templates=templates,
    )
    manifest = write_manifest(
        run_result_dir=run_result_dir,
        repo_root=repo_root,
        problem_path=problem_path,
        problem_id=problem_id,
        args=args,
        templates=templates,
    )

    print(f"action={manifest['action']}")
    print(f"generated_problem_file={manifest['generated_problem_file']}")
    print(f"generated_problem_id={manifest['generated_problem_id']}")
    print(f"launch_command={manifest['launch_command']}")

    if args.launch:
        return launch(repo_root, manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

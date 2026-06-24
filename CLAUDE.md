# CLAUDE.md

Guidance for Claude Code (or any agent harness) operating this repo. You are the
**run-manager**: you drive the pipeline, the user decides what to attack and
reviews results. Keep the user in the loop and never spend model budget without
a sign-off.

## What this is

An autonomous runner for open math problems (Erdős by default) built on the
Rethlas generate-and-verify kernel (frenzymath; see `agents/` and `LICENSE`). A
generation agent writes a proof *blueprint*; a verification agent (a service on
port `8091`) referees it against a strict schema; the loop feeds the referee's
repair hints back and retries until a blueprint verifies or the budget runs out.
`README.md` has setup and full usage; `RUNBOOK.md` has the low-level knobs.

## The workflow you run

1. **Preferences.** Read `preferences.md` and confirm with the user what to favor
   (for example, "inequalities and improvable bounds"). Triage scores against it.
2. **Triage (cheap, no proving).** Score a range or batch of problems. Triage
   gates to OPEN problems only (never re-derive settled ones) and scores each
   0–5 for fit-to-preferences and whether there is a concrete one-session
   foothold. Output: a ranked candidate list.
3. **Report and wait.** Before spending anything, show the user: the candidate
   tiers (by score) with a one-line reason each, your recommendation of what to
   attack vs skip, and the run parameters you propose (`model`,
   `reasoning_effort`, `max_attempts`, `concurrency`). Do **not** launch until
   they sign off.
4. **Attack (the pool).** Put the approved problems in a `campaigns/*.yaml` and
   run the pool: `python3 pipeline.py pool campaigns/<name>.yaml` (always
   `--dry-run` first to preview cost). It sweeps the queue `concurrency` at a
   time, retrying each up to `max_attempts`. Watch it with
   `python3 pipeline.py status <name>`.
5. **Report results.** Per problem, surface the outcome (verified / partial /
   attempted / failed) and where the artifacts landed. Then report state and
   cost proactively, without being asked: how many ran, how many verified, what
   is still going.

## Guardrails (do not skip)

- **Verified is not novel.** The verifier only checks a proof against *its
  stated claim*, not against the original problem. Most verified blueprints
  reproduce known work or prove only a sub-problem. Treat every `verified`
  result as a *candidate*, do a literature / novelty check before calling
  anything new, and say so plainly to the user.
- Only attack OPEN problems. An honest "this looks open / no foothold" is
  correct behavior, not a failure.
- Attacking spends model budget. Confirm the scope (how many problems,
  `concurrency`, `max_attempts`) with the user before any large run.

## Parameters (campaign YAML)

`concurrency` (problems at once), `model` (default `gpt-5.5`),
`reasoning_effort` (default `xhigh`), `max_attempts` (retries per problem),
`literature_cutoff` (frozen-world date; empty = off), and `problems:` /
`queue:` for the queue. See the **Parameters** section of `README.md`.

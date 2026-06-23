# Rethlas pipeline

`pipeline.py` is the single front door to every stage of Rethlas. It replaces
the scattered 28-env-var invocations and the old pool-sweep shell with one
config file per campaign and one unified state file you can read at a glance.

```
python3 pipeline.py <command> -h
```

| Command | What it does |
|---|---|
| `pool`     | Sweep a queue of problems: N concurrent attack -> verify -> repair runs, auto-advancing the queue, harvested into one scoreboard. |
| `discover` | Discovery -> triage -> promotion chain (the exploration / research track). |
| `triage`   | Score the route cards in a discovery batch dir. |
| `promote`  | Turn triaged route cards into new problem files + launch scripts. |
| `status`   | Print the scoreboard for a campaign from its state file. |

The `pool` track (solving known problems) and the `discover` track (finding new
conjectures) are independent; they share the same generation + verification
engine and live here under one entrypoint.

## Prerequisites

The verification service must be running (port 8091):

```bash
cd agents/verification && uv venv && uv pip install -r requirements.txt
uv run uvicorn api.server:app --host 0.0.0.0 --port 8091
```

`codex` (or the DeepSeek bridge) must be installed for live runs. Everything
below works with `--dry-run` and no API access, so you can see the shape first.

## Quickstart

```bash
# 1. Preview a pool sweep (no Codex, no cost)
python3 pipeline.py pool campaigns/erdos_pool_example.yaml --dry-run

# 2. Run it for real (needs the verifier up + codex installed)
python3 pipeline.py pool campaigns/erdos_pool_example.yaml

# 3. Read the scoreboard
python3 pipeline.py status erdos_pool_example
```

Add your own problems by dropping markdown files under
`agents/generation/data/` and listing them in the campaign's `problems:`
(or point `queue:` at a text file with one `data/...md` path per line).

## Exploration track

```bash
python3 pipeline.py discover campaigns/unit_distance_discover_example.yaml --dry-run
python3 pipeline.py discover campaigns/unit_distance_discover_example.yaml
# then, on the batch result dir it produced:
python3 pipeline.py triage  agents/generation/results/<batch_id>
python3 pipeline.py promote agents/generation/results/<batch_id>
```

## State & harvest

Each campaign writes to `pipeline_runs/<name>/`:
- `state.json` — every problem's status (the single `classify_blueprint_status.py`
  taxonomy), verdict, and blueprint path. Updated live as the pool advances.
- `harvest.md` — a table summary for the writeup / registry.

Outcome taxonomy (rolled up for the scoreboard):

| classify status        | group     | meaning                                  |
|------------------------|-----------|------------------------------------------|
| verified_final         | verified  | verifier-correct, unconditional          |
| verified_unpromoted    | verified  | verifier-correct, not yet promoted       |
| verified_conditioning  | partial   | correct but names a next missing theorem |
| unverified_blueprint   | attempted | blueprint produced, verifier said wrong  |
| blueprint_no_verdict   | attempted | blueprint produced, no verdict           |
| no_blueprint           | failed    | no blueprint produced                    |

A **verified** result is a *candidate*: verifier-accepted, still pending human
review before it counts as a real result.

# Autonomous Rethlas Runner

Clone it, point it at open math problems, and it attacks them on its own. A
generation agent writes a proof, a verification agent referees it against a
strict schema, and the loop repairs and retries until a proof passes or the
budget runs out. It sweeps many problems in parallel, can discover new ones to
attack, and runs under integrity controls so a result is one it actually
derived rather than looked up. Defaults to Erdos problems; works on any domain.

Built on [Rethlas](https://github.com/frenzymath/Rethlas) by the frenzymath
group (PKU). The two-agent generate-plus-verify kernel, the
verification-as-a-service API, the schema verdict, and the MCP tool layer are
theirs (see `agents/` and `LICENSE`, both retained). This repository adds the
autonomous runner around that kernel.

## What this runner adds on top of the kernel

- **Unified CLI** (`pipeline.py`): one front door over every stage
  (`pool`, `discover`, `triage`, `promote`, `status`), driven by
  `campaigns/*.yaml`, with all state under `pipeline_runs/<name>/`.
- **Pool manager**: sweep a queue of problems N at a time, unattended,
  auto-advancing, with a live scoreboard. Idempotent: already-verified
  problems are skipped on re-run.
- **Proof-and-repair loop** (`scripts/run_with_retries.sh`): drives the
  kernel's verifier, feeds its repair hints back into the prover, and retries
  up to `max_attempts`.
- **Discovery to triage to promotion**: find new attack angles, score them,
  and promote the winners into runnable problems.
- **Integrity layer**: a frozen-world egress block (`scripts/net/noegress.so`),
  date-gated literature, and a blind-source transcript audit
  (`scripts/audit_blind_run.py`), so an unsupervised result is trustworthy.
- **Workbench dashboard** (`ui/`): browse, launch, and monitor runs with live
  transcript streaming. Runs locally.

## Quickstart

```bash
git clone https://github.com/leon2k2k2k/Rethlas.git && cd Rethlas

# 1. verifier service (the Rethlas kernel)
cd agents/verification && uv venv && uv pip install -r requirements.txt
uv run uvicorn api.server:app --host 0.0.0.0 --port 8091 &
cd ../..

# 2. integrity egress block
cd scripts/net && ./build.sh && cd ../..

# 3. the prover
npm install -g @openai/codex      # then: codex login

# 4. preview a run (no cost), then run it for real
python3 pipeline.py pool campaigns/erdos_pool_example.yaml --dry-run
python3 pipeline.py pool campaigns/erdos_pool_example.yaml
python3 pipeline.py status erdos_pool_example
```

## Usage

**Solve a queue of problems (the pool manager):**
```bash
python3 pipeline.py pool campaigns/erdos_pool_example.yaml
python3 pipeline.py status erdos_pool_example     # read the scoreboard
```

**Discover new problems, then triage and promote a batch:**
```bash
python3 pipeline.py discover campaigns/erdos_discover_example.yaml
python3 pipeline.py triage  agents/generation/results/<batch_id>
python3 pipeline.py promote agents/generation/results/<batch_id>   # add --launch to fire it
```

**Run your own problems (this is the flexible part):** drop markdown
statements under `agents/generation/data/` (subdirectories are preserved),
then list them in a campaign's `problems:` or point `queue:` at a file with
one path per line. Erdos is only the default example set; any domain works.

**Outcome taxonomy** (what the scoreboard groups into): `verified`, `partial`,
`attempted`, `failed`. A `verified` result is a *candidate*: verifier-accepted,
still pending human review before it counts as a real result.

## Parameters

Everything about a run lives in one `campaigns/*.yaml`. The pool config (sweep a
queue of problems, several at a time, retrying each until it verifies) is the
run shown in the [writeup](https://leon2k2k2k.github.io/posts/2026/rethlas-autonomous-erdos-pipeline/);
its knobs are the whole control surface:

```yaml
name: erdos_pool_example
mode: pool
concurrency: 5            # problems attacked at once; the queue auto-advances
model: gpt-5.5            # prover + referee model
reasoning_effort: xhigh   # thinking depth
max_attempts: 3           # draft -> verify -> repair cycles per problem before giving up
provider: ""              # "" = gpt via your Codex subscription; "deepseek" = local bridge
literature_cutoff: ""     # YYYY-MM-DD to freeze the world at a date (integrity mode); empty = off
problems:                 # the queue (or set `queue: path/to/list.txt`, one path per line)
  - data/erdos/erdos_708.md
  - data/erdos/erdos_709.md
```

```bash
python3 pipeline.py pool campaigns/erdos_pool_example.yaml --dry-run   # preview, no cost
python3 pipeline.py pool campaigns/erdos_pool_example.yaml             # attack the queue
python3 pipeline.py status erdos_pool_example                          # read the scoreboard
```

The same four knobs (`concurrency`, `model`, `reasoning_effort`, `max_attempts`)
are also exposed as env vars on the lower-level single-problem entry point
`scripts/run_with_retries.sh`; see `RUNBOOK.md` for that and the deep-run and
width-batch regimes.

## Integrity (the frozen world)

During a run the prover is sealed: `noegress.so` blocks network egress,
literature access is date-gated to a `literature_cutoff`, and
`audit_blind_run.py` scans the transcript afterward for any policy violation.
So a result the runner produces is one it derived under those constraints, not
one it retrieved. Set the cutoff per campaign (`literature_cutoff: YYYY-MM-DD`).

## Results

`research/erdos/` holds five featured partial results on open Erdos problems
(#153, #301, #327, #675a, #819), author-reviewed and externally verified, with
source and final PDF. These are candidates pending the problem owners' review;
the broad attempt pool is reported only in aggregate.

## Running the kernel directly, and viewing results

```bash
# one problem straight through the kernel (no pipeline)
cd agents/generation && PROBLEM_FILE=data/example.md ./tests/run_example.sh

# browse results in a local Zola site (installs the MATbook theme on first run)
cd agents/generation && ./site/serve.sh        # http://localhost:3264
```

## Layout

```
pipeline.py          unified CLI over every stage
campaigns/           one YAML per run (Erdos examples included)
scripts/             orchestration + the integrity layer + stage scripts
  net/               the frozen-world egress block
  tests/             pipeline + integrity unit tests
ui/                  the Workbench dashboard
research/erdos/      the five featured results
agents/              the Rethlas kernel (upstream): generation + verification
```

## Tests

```bash
python3 -m pytest scripts/tests -q
```

## Attribution and license

The reasoning kernel (generation + verification agents, verify API, schema,
MCP) is [frenzymath/Rethlas](https://github.com/frenzymath/Rethlas). The
autonomous runner, the integrity layer, the operations tooling, and the
research campaigns are this fork's additions. Licensed under Apache 2.0,
inherited from upstream.

# Rethlas Production Runbook

How to operate the two systems: the **Rethlas pipeline** (generation + verification
+ literature cutoff) and the **Workbench UI**. Both run as user-level systemd
services that survive reboots.

## Services (the production line)

Three always-on services, all `systemctl --user`, `Restart=always`, lingering enabled:

| Service | Port | What it is |
|---|---|---|
| `rethlas-ui` | 8080 | The Workbench dashboard (browse, launch, edit, monitor) |
| `rethlas-bridge` | 38440 | Moon Bridge — codex ⇄ DeepSeek translation (only needed for `PROVIDER=deepseek`) |
| `rethlas-verify` | 8091 | Verification Agent API — the referee that judges blueprints |

```bash
systemctl --user status  rethlas-ui rethlas-bridge rethlas-verify
systemctl --user restart rethlas-verify        # bounce one
journalctl --user -u rethlas-verify -f         # tail logs
# health
curl -s localhost:8080/ -o /dev/null -w '%{http_code}\n'
curl -s localhost:8091/health
curl -s localhost:38440/v1/models
```

Dashboard: **http://localhost:8080** (run locally; no auth, by design).

---

## System 1 — The Rethlas pipeline (CLI)

A run reads a problem markdown, runs `codex exec` (the prover) with MCP tools,
writes `blueprint.md`, and submits it to the referee. Verified blueprints are
promoted to `blueprint_verified.md`.

### Launch a single run

```bash
cd ~/rethlas
PROBLEM_FILE=data/discrete_geometry/unit_distance_disproof.md \
PROBLEM_ID=discrete_geometry/my_run \
MAX_ATTEMPTS=1 \
scripts/run_with_retries.sh
```

### The knobs (env vars)

| Var | Default | Meaning |
|---|---|---|
| `PROBLEM_FILE` | unit_distance_disproof | problem markdown under `data/` |
| `PROBLEM_ID` | derived from file | output id for memory/results/logs |
| `MODEL` | `gpt-5.5` | prover model (`deepseek-v4-pro` if `PROVIDER=deepseek`) |
| `PROVIDER` | empty (gpt) | `deepseek` routes through the bridge |
| `REASONING_EFFORT` | `xhigh` | thinking depth |
| `MAX_ATTEMPTS` | 5 | fresh-session attempts (memory carries over) |
| `CONTINUE_ROUNDS` | 0 | same-session resume rounds; with budget, makes a deep run |
| `TOKEN_BUDGET` | 0 | output-token target; stated as policy AND enforced |
| `BLIND_RUN` | 1 | blind-source audit on |
| `RETHLAS_LITERATURE_CUTOFF` | unset | **frozen-world mode** (see below) |

### gpt vs DeepSeek

- **gpt-5.5** (`PROVIDER` unset): runs on your codex subscription (no per-token $).
  Best rigor; referee-validated lemmas.
- **DeepSeek v4-pro** (`PROVIDER=deepseek`): cheap (~$0.50/run), fast, diverse;
  raw chain-of-thought is captured in the rollout. Needs `rethlas-bridge` up.
- The **referee is always gpt** regardless of prover, so verdict semantics stay
  constant across runs.

### Max-budget deep run (the OpenAI-style regime)

```bash
TOKEN_BUDGET=1500000 CONTINUE_ROUNDS=10 MAX_ATTEMPTS=1 \
PROBLEM_FILE=... PROBLEM_ID=... scripts/run_with_retries.sh
```
The model is told to spend the full budget and not wrap up early; between
rounds the referee's `repair_hints` are fed back into the same session.

### Width batches (many independent samples)

```bash
PARALLEL=5 MAX_ATTEMPTS=1 TOKEN_BUDGET=1500000 CONTINUE_ROUNDS=10 \
scripts/run_width_batch.sh scripts/width_specs/<spec>.spec
```
Spec lines: `<problem_id> <provider|-> <blind 0|1>`.

### Frozen-world mode (literature cutoff) — the safety feature

Set `RETHLAS_LITERATURE_CUTOFF=YYYY-MM-DD` and the run may search arXiv + the
web, but only the world frozen at that date. The post-cutoff target proof is
unreachable.

```bash
RETHLAS_LITERATURE_CUTOFF=2024-12-31 BLIND_RUN=0 \
PROBLEM_FILE=... PROBLEM_ID=... scripts/run_with_retries.sh
```

What it does, automatically:
- Starts `scripts/frozen_proxy.py` (the single egress gate) on :38450.
- Preloads `scripts/net/noegress.so` onto codex → shell `curl`/`wget`/python
  can't reach the network; only loopback + the model's own API endpoint.
- Disables codex's native (live) `web_search`.
- Mounts the frozen MCP tools: `literature_search` (arXiv ≤ cutoff),
  `literature_fetch_arxiv` (refuses post-cutoff ids), `literature_fetch_web`
  and `web_search` (Wayback snapshots ≤ cutoff only).
- Logs every external fetch to `results/<id>/retrieval_manifest.jsonl`.
- `audit_blind_run.py` voids any run that tries to bypass the gate.

The natural clock: a web link is reachable iff the Wayback Machine has a
snapshot ≤ cutoff; arXiv uses `submittedDate`. Anything published later is
blocked by date, for any URL. Caveat: this freezes *retrieval*, not the model's
training weights.

Rebuild the egress blocker after a pull: `scripts/net/build.sh`.

### Where outputs land (under `agents/generation/`)

- `results/<id>/blueprint.md`, `blueprint_verified.md`, `verification_attempt_*.json`
- `logs/<id>/attempt_*.md`, `retry_manager.log`
- `memory/<id>/*.jsonl` (branch_states, failed_paths, proof_steps, …)

### Check progress toward the goal

```bash
python3 scripts/detect_lattice_frame.py            # number-field lattice frame detector
```

---

## System 2 — The Workbench UI

http://localhost:8080 — read everything, launch runs, edit problems, verify.

- **Index** (`/`): all runs across repos; search + status/root/category filters.
- **Run page** (`/run.html?run=<id>`): tabs — Problem, Transcript (raw reasoning
  + tool calls), Blueprint, Routes, Verification (referee verdict + session),
  Memory, Logs, Files; lineage sidebar. `?session=<id>` views any rollout.
- **Launch** (`/launch.html`): typed forms — attempt runs, discovery batches,
  clone baselines — with a provider dropdown (gpt / deepseek). Submitting spawns
  a tracked job.
- **Jobs** (`/jobs.html`): live status, log tail, stop buttons.
- **Editor** (`/editor.html`): edit `data/**.md` problems + configs with live
  math preview, sha-conflict detection, timestamped backups.
- **Verify** (`/verify.html`): paste a statement + proof → referee verdict.

Tests (from `ui/`): `pytest` · `npm test` · `npm run e2e`.

---

## Using the two together (the normal loop)

1. **Author** a problem in the Editor (or drop a markdown under `data/`).
2. **Launch** it from the Launch page (or CLI for advanced knobs like
   `TOKEN_BUDGET` / `RETHLAS_LITERATURE_CUTOFF`).
3. **Watch** it on the Jobs page and the run's Transcript tab (reasoning streams
   live).
4. **Read** the verdict on the Verification tab; the referee's session is linked.
5. **Iterate**: on a conditional/`wrong` blueprint, promote the missing lemma to
   a sub-problem (Routes tab tools) and recurse, or re-run with more budget.

The north star and current strategy live in `notes/unit_distance_north_star.md`;
the latest experiment write-ups are alongside it in `notes/`.

# Generator gate on the remote Docker host

How-to plus results placeholder. Runs gate A from doc 50 section 2 against the three generated lots on `lake-vps-lor-main`: RST, SETA-Env, and TMax-15K. Protocol `verifier_invalid.fresh_environment.execution`, grade A, adjudicator machine. No model output enters the bound (doc 43). The code is `src/task_validation/evidence/generator_gate.py` with the CLI pair `generator-gate-sample` and `generator-gate-run`.

## Host and lots

| Lot | Source | Task count | Root on the VPS |
| --- | --- | ---: | --- |
| RST | `Zhongzhi1228/Recursive-Task-Synthesis`, `metadata/tasks.parquet` plus `data/tasks-*.tar` | 37,484 | `/home/evan/gen-sets/rst` |
| SETA-Env | `camel-ai/SETA-Env` Harbor task dirs with `solution/solve.sh` | 4,567 | `/home/evan/gen-sets/seta` |
| TMax-15K | `allenai/TMax-15K`, Harbor form `tmax/TMax-15K-Harbor` | pending count | `/home/evan/gen-sets/tmax` |

The task counts above are from the generator manifests; the runner re-enumerates the root and records its own `N` in each manifest under `data/gold/gen_gate_<name>_manifest.json`. RST ships tasks inside tar archives; enumeration reads tar member names only, and only sampled tasks are unpacked into `<root>-gate-extract/<name>`.

## Setup on the VPS

SSH in as `evan`. Docker 29 is installed and `evan` is in the docker group. Harbor is at `~/.local/bin/harbor`. Get the repo and the venv:

```bash
git clone <repo-url> ~/task_validation   # or rsync the working tree
cd ~/task_validation
python3 -m venv .venv
.venv/bin/pip install -e .
```

Every long command below runs under `systemd-run --user` with `MemoryMax=24G` and `CPUWeight=50`, per the host rules. Sampling is cheap and can run in the login shell; the run commands must be wrapped.

## Step 1: freeze the samples

One manifest per generator at `n=200`, seed `gen-gate-<name>-v0` (the default). The manifest freezes before any gate output is read (doc 32).

```bash
cd ~/task_validation
PYTHONPATH=src .venv/bin/python -m task_validation.cli generator-gate-sample \
    --name rst --root /home/evan/gen-sets/rst --n 200
PYTHONPATH=src .venv/bin/python -m task_validation.cli generator-gate-sample \
    --name seta --root /home/evan/gen-sets/seta --n 200
PYTHONPATH=src .venv/bin/python -m task_validation.cli generator-gate-sample \
    --name tmax --root /home/evan/gen-sets/tmax --n 200
```

Artifacts: `data/gold/gen_gate_rst_manifest.json`, `data/gold/gen_gate_seta_manifest.json`, `data/gold/gen_gate_tmax_manifest.json`. Each records `ids`, per-task `path` and `sha256`, `seed`, `N`, `n`.

## Step 2: run the gate

For each manifest task the runner issues one `harbor run` per trial: `--agent oracle` twice and `--agent nop` twice, each in a fresh container (`-k 1` per invocation). Harbor is invoked as

```bash
harbor run -p <task_dir> --agent <oracle|nop> --env docker --yes \
    -n <concurrency> -k 1 --job-name <slug>-<probe>-r<rep>-<ts> -o <jobs_dir> \
    --timeout-multiplier 1.0 \
    --verifier-timeout-multiplier 2.0 \
    --environment-build-timeout-multiplier 2.0
```

Rows append to `data/gold/gen_gate_<name>.jsonl`, one per `(task, probe, rep)` with reward, status, wall time, and log tails. Resume is automatic: re-running skips terminal trials. Environment build failures and timeouts are recorded as `infra` and `timeout` with null reward; no reward is ever fabricated.

```bash
cd ~/task_validation
systemd-run --user --collect -p MemoryMax=24G -p CPUWeight=50 \
    --unit=gen-gate-rst --same-dir \
    env PYTHONPATH=src .venv/bin/python -m task_validation.cli generator-gate-run \
    --name rst --concurrency 4
```

Follow progress with `journalctl --user -u gen-gate-rst -f`; the runner prints one line per trial. Repeat with `--name seta` and `--name tmax`. Run one generator at a time, or raise `--concurrency` on the 16-core host if disk and memory allow.

Docker hygiene is built in: after each task the runner `docker rm -f`s leftover containers matching the task slug, and every 20 tasks (`--prune-every`) it runs `docker image prune -af` and `docker builder prune -af` and logs reclaimed bytes into the summary under `maintenance`. With 950 GB free this is belt and braces, but it keeps the image store bounded over multi-day runs.

## Step 3: extend to n=300

If a certificate lands near epsilon, grow the sample rather than redraw. Same seed, larger n; the frozen 200 stay the prefix of the 300-draw, so completed trials still count and only the 100 new tasks need trials.

```bash
PYTHONPATH=src .venv/bin/python -m task_validation.cli generator-gate-sample \
    --name rst --root /home/evan/gen-sets/rst --n 300
systemd-run --user --collect -p MemoryMax=24G -p CPUWeight=50 \
    --unit=gen-gate-rst-300 --same-dir \
    env PYTHONPATH=src .venv/bin/python -m task_validation.cli generator-gate-run \
    --name rst --concurrency 4
```

The sampler refuses a seed change, a shrink, or a draw that does not extend the frozen ids; those errors mean the population changed under the manifest and the lot needs a new freeze.

## Outputs

| Artifact | Path |
| --- | --- |
| Frozen manifest | `data/gold/gen_gate_<name>_manifest.json` |
| Trial rows | `data/gold/gen_gate_<name>.jsonl` |
| Per-task verdicts | `data/gold/gen_gate_<name>_verdicts.jsonl` |
| Summary | `data/gold/gen_gate_<name>.summary.json` |
| Certificate | `data/gold/gen_gate_<name>.certificate.json` |
| Harbor logs | `/tmp/tv-gen-gate-<name>/jobs/` |

Invalid means an executed oracle rep returned reward below 1 or an executed nop rep returned reward 1 (doc 50 section 2). The certificate counts `k_invalid` over adjudicated tasks, computes the hypergeometric one-sided 95% UCB at population `N` via `build_certificate` (doc 32, doc 41), and reports `decision` release iff `ucb95 < epsilon` (epsilon default 0.05). Tasks left on `infra`, `timeout`, `not_run`, judge-stratum, or no-reference status are unadjudicated: they do not count as invalid and they make the certificate INCOMPLETE until resolved (doc 32). Re-run with `--redo-infra` to retry infra and timeout trials after a docker or registry hiccup.

## Verification and troubleshooting

- Row counts: `wc -l data/gold/gen_gate_<name>.jsonl` should approach `4 * n`; the summary reports `n_trials`, `n_executed`, `n_infra_trials`, `n_timeout_trials`.
- Certificate: `jq .decision,.k_invalid,.ucb95 data/gold/gen_gate_<name>.certificate.json`. `incomplete` means unadjudicated units remain; the `unadjudicated_reasons` map says why.
- Missing task dirs (moved root, wiped extract dir) record `infra` rows with `skip_reason=missing_task_dir`; fix the path or re-extract and re-run with `--redo-infra`.
- A stuck environment build is killed as infra when it outlives the trial cap (`--trial-cap-sec`, default 3,600 s in `src/task_validation/evidence/generator_gate.py`); the verifier and build multipliers cap time inside harbor itself.
- Leftover containers are removed per task; `docker ps -a | grep <task-slug>` should come back empty.
- Judge-verifier tasks (detected by `JUDGE_MODELS` markers, doc 44) are skipped to their own stratum and tasks without `solution/` are recorded `no_reference`; neither enters the execution bound.

## Results

Placeholder. Fill after the VPS runs finish, one table per generator: `N`, `n`, `k_invalid`, `p_hat`, `ucb95`, `decision`, infra and timeout counts, and the certificate path.

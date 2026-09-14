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

RST lot, run 2026-09-13 on `lake-vps-lor-main`. SRS n=200 of N=37,484, seed `gen-gate-rst-v0` (`data/gold/gen_gate_rst_manifest.json`). Of 200 sampled tasks, 195 were adjudicated: 188 valid, 7 invalid, 0 nop accepts in 390 executed nop trials (`data/gold/gen_gate_rst.summary.json`). Five tasks stayed unadjudicated after one `--redo-infra` pass and one targeted retry at concurrency 1 (828 rows in `data/gold/gen_gate_rst.jsonl`).

### Flagged tasks (k = 7 of 195 adjudicated)

All seven are the same defect class: the reference fails its own verifier (oracle reward below 1). One is also nondeterministic. Rewards are from `data/gold/gen_gate_rst_verdicts.jsonl`; the observed failure is from each oracle trial's `test_stdout_tail` in `data/gold/gen_gate_rst.jsonl`.

| Task | Oracle | Nop | Deterministic | Observed failure |
| --- | --- | --- | --- | --- |
| `rts_task_428772f088f387a5a5931b6a` | [0, 1] | [0, 0] | no | `dive_result.txt` not produced |
| `rts_task_ba03cac8d7d5c174ce9410e9` | [0, 0] | [0, 0] | yes | verifier expects cgroupfs, image runs systemd |
| `rts_task_e8aeaad81227334457f583a7` | [0, 0] | [0, 0] | yes | `/app/active_profile` missing |
| `rts_task_c7388d1bd61a8c0dbb452c37` | [0, 0] | [0, 0] | yes | spec field `memory_usage` absent from `docker inspect` |
| `rts_task_e645413836bf454030b0e9cd` | [0, 0] | [0, 0] | yes | reference fails own verifier |
| `rts_task_641f1e4025984f695f5de157` | [0, 0] | [0, 0] | yes | `/app/result.txt` missing |
| `rts_task_f7d8f7e15e98c120be6eea7d` | [0, 0] | [0, 0] | yes | wrapper file missing |

### Uncovered tasks (5 of 200)

Causes were read from the job logs under `/tmp/tv-gen-gate-rst/jobs/` and the task source under `/home/evan/gen-sets/rst-gate-extract/rst/`. The retry column counts the concurrency-1 closeout pass; each task also had one earlier `--redo-infra` pass.

| Task | Rows | Cause | Class | Retried |
| --- | ---: | --- | --- | --- |
| `rts_task_0e78f51893db713eac1293e7` | 12, all infra | image builds, env container exits 255 at start | environment defect | yes, reproduced |
| `rts_task_b5a102c27aae10a41d70205a` | 12, all infra | `yum install postgresql-contrib` exit 1 on CentOS-7 vault 403 in attempt 1; later attempts build from cache, then the env container exits 255 | environment defect | yes, reproduced |
| `rts_task_1f272b2057dfd63ab48abd38` | 8, all infra | `apt-get` exit 100, `deb.debian.org` bullseye-security 404s (libnghttp2) | environment build failure, repo rot | no |
| `rts_task_61ddd41585b5a4b23d5eb46a` | 8, all infra | `apt-get` exit 100, `deb.debian.org` bullseye-security 404s (gnupg2, python3.9) | environment build failure, repo rot | no |
| `rts_task_26236daa49379d10832f9905` | 8: oracle 2 executed [1, 1], nop 6 infra | verifier runs (21 failed, 3 passed) but `tests/test.sh` `set -e` exits before writing `reward.txt`; `RewardFileNotFoundError` | task defect | yes, nop only, reproduced |

### Bounds

Both bounds use `hypergeometric_upper` (`src/task_validation/sampling/estimators.py`) inside `build_certificate` (`src/task_validation/sampling/certificate.py`), one-sided alpha 0.05. Decision logic is unchanged: release iff ucb95 < epsilon = 0.05.

| Bound | N | n | k invalid | p-hat | UCB 95 | Decision | Artifact |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| (a) restricted population | 37,479 | 195 | 7 | 3.59% | 6.63% | reject | `data/gold/gen_gate_rst.certificate.json` |
| (b) conservative | 37,484 | 200 | 12 | 6.00% | 9.53% | reject | `data/gold/gen_gate_rst.conservative.certificate.json` |

Bound (a) is the headline. It treats the 5 uncovered units as outside the frame: coverage is 195 of 200 (0.975), the population drops to 37,479, and the claim extends to the full lot only if the uncovered units share the covered units' invalidity rate. Bound (b) needs no such assumption: it counts all 5 uncovered units invalid. The true value lies between the two bounds only under those stated readings, exchangeability for (a) and the worst case for (b). Under both bounds the lot fails the gate at epsilon 5 percent, so the decision is reject: the 7 flagged tasks must be dropped or repaired before the lot can ship (doc 50 section 2).

### Run cost

Wall clock about 4.1 h for the main pass (first harbor job 2026-09-13T17:32:18, last 21:38:59, from `result.json` timestamps under `/tmp/tv-gen-gate-rst/jobs/`), plus a 4 min `--redo-infra` pass and a 3.5 min closeout retry (`journalctl --user -u gen-gate-rst-200`, `-redo`, `-retry3`). Runner CPU was 1 h 25 min, 2 min, and 57 s on the three units. Summed trial time is 54,813 s, about 15.2 h, over 828 rows (`data/gold/gen_gate_rst.jsonl`). API cost is 0 dollars: oracle and nop are model-free agents and `cost_usd` is null in every job `result.json`. A second gate (SETA, then TMax) ran on the host at concurrency 3 throughout; the closeout retry ran at concurrency 1 with image pruning disabled.

### Where this sits

In the doc 42 ordering of populations by audit history, the RST covered-slice point estimate of 3.6 percent lands between TB 2.1 post-fix and Harbor-Index, and the conservative 6.0 percent lands just above TB 2.1.

| Population | Invalid rate | Source |
| --- | ---: | --- |
| TB 2.0 pre-fix | 33% | doc 42 |
| eval_tasks | 12.5% | doc 42 |
| RST, conservative k=12/200 | 6.0% | `data/gold/gen_gate_rst.conservative.certificate.json` |
| TB 2.1 post-fix | 5.6% | doc 42 |
| Harbor-Index | 3.8% | doc 42 |
| RST, restricted k=7/195 | 3.6% | `data/gold/gen_gate_rst.certificate.json` |
| SWE-bench random | 2% | doc 42 |

Two of the five uncovered tasks are environment rot, not verifier invalidity: `deb.debian.org` no longer resolves bullseye-security, so the image cannot be built today and the task cannot be adjudicated either way. That is a distinct construct from a verifier that runs and returns a wrong answer. The precedent is doc 23 section 7 on `django__django-10097`: a task is invalid on today's image regardless of what the 2024 environment did. The symmetric statement here is that a task whose environment cannot be built today is unadjudicated, not invalid; it enters the bound only as a worst-case unit in the conservative certificate.

Scope note: RST is the raw 37,484-task pool that generator T1 (arXiv 2609.11042) filtered down to about 15,000 and trained on, with a reported RL lift of 59.9 to 64.0 on TB 2.1 (doc 43, doc 46). This gate measures the raw pool. It is evidence about what T1's filter had to remove, not a claim that RST is unusable.

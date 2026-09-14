# Generator gate on the remote Docker host

How-to plus results placeholder. Runs gate A from doc 50 section 2 against the three generated lots on `lake-vps-lor-main`: RST, SETA-Env, and TMax-15K. Protocol `verifier_invalid.fresh_environment.execution`, grade A, adjudicator machine. The construct this assay certifies is verifier consistency, not verifier validity: passing the oracle and nop probes is necessary evidence, not sufficient. A consistent verifier may still under-test the requirement, accept a wrong implementation, be over-permissive, or depend on accidental environment state (docs 32, 56). No model output enters the bound (doc 43). The code is `src/task_validation/evidence/generator_gate.py` with the CLI pair `generator-gate-sample` and `generator-gate-run`.

## Host and lots

| Lot | Source | Task count | Root on the VPS |
| --- | --- | ---: | --- |
| RST | `Zhongzhi1228/Recursive-Task-Synthesis`, `metadata/tasks.parquet` plus `data/tasks-*.tar` | 37,484 | `/home/evan/gen-sets/rst` |
| SETA-Env | `camel-ai/SETA-Env` Harbor task dirs with `solution/solve.sh` | 4,569 | `/home/evan/gen-sets/seta` |
| TMax-15K | `allenai/TMax-15K`, Harbor form `tmax/TMax-15K-Harbor` | 8,047 Harbor dirs | `/home/evan/gen-sets/tmax-harbor` |

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
    --name tmax --root /home/evan/gen-sets/tmax-harbor --n 200
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

By default the runner dispatches all of a task's trials at once at `--concurrency`, and each trial builds its own environment image. `--warmup` is an opt-in alternative: the first pending trial (the first oracle rep on a fresh task, or the first nop rep when oracle trials do not run) runs alone to completion so its environment build populates the docker layer cache, then the remaining trials dispatch at `--concurrency` against that cached image. A warmup trial that comes back `infra` is recorded, and the task's remaining trials are recorded `not_run` for the pass with no retry inside the runner. The choice is not interchangeable across runs: the two schedulings measure different constructs (see "Scheduling and what it measures" below), so `build_certificate` stamps the certificate `scheduling` field with `concurrent` or `warmup`. Probes, statuses, resume keys, row schema, prune cadence and the certificate path are unchanged either way, and no verdict rule is affected.

The motivation for `--warmup` is measured in `data/gold/gen_gate_seta.jsonl` from the SETA gate at concurrency 3: the quickest executed trial per task medians 51 s (n=164) while the other three median 107 s (n=492). Under all-at-once dispatch the trials of one task build the same image concurrently, so the layer cache serves none of them and the builds contend for disk.

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

## Coverage and one-sided gating

The gate has two probes. The oracle probe asks the reference to pass its own verifier. The nop probe asks the verifier to reject an empty solution. A task takes a probe only if the probe has something to run, so coverage splits three ways (doc 44).

| Stratum | Oracle probe | Nop probe | How it enters a bound |
| --- | --- | --- | --- |
| execution | runs; a fail is grade-A invalid | runs; an accept is grade-A invalid | two-sided: all 2k trials adjudicate the unit |
| judge | needs `JUDGE_MODELS`; skipped to its own stratum | needs `JUDGE_MODELS`; skipped to its own stratum | no machine certificate; the human design only (doc 44) |
| none | impossible: no `solution/` shipped | runs; an accept is grade-A invalid, a reject is not evidence | one-sided only: accepts count invalid, rejects count toward n of the one-sided bound but are never clean units in a two-sided bound |

The none stratum is half-covered, not uncovered. A nop accept convicts with no reference needed. A nop reject cannot acquit, so the unit never counts as a clean unit in a two-sided bound (doc 44).

TMax-15K is the limiting case. The Harbor form on the Hub (`tmax/TMax-15K-Harbor`) holds 8,047 task directories and publishes no references by design: a spot check found 0 of the first 200 dirs with `solution/` (checked 2026-09-14), and the frozen SRS manifest records `has_reference` false on all 200 sampled tasks (`data/gold/gen_gate_tmax_manifest.json`, N=8,047, n=200, seed `gen-gate-tmax-v0`). The staged raw download `/home/evan/gen-sets/tmax/tasks.zip` agrees: its task dirs carry `solutions/` model summaries (for example `solutions/gemini_gemini-3-flash-preview_summary.json`), not `solution/` reference dirs. With no reference anywhere, the oracle probe is impossible on TMax as distributed, and the reference-fails-its-own-verifier defect class is unmeasurable. That class supplied all 7 flagged RST tasks and the 1 flagged SETA task (`data/gold/gen_gate_rst_verdicts.jsonl`, `data/gold/gen_gate_seta_verdicts.jsonl`). The TMax paper (arXiv 2606.23321) argues reinforcement learning soft-filters broken tasks so teacher correctness is unnecessary; this gate cannot test that claim in either direction.

The nop-only run took place on 2026-09-14. Results are in the TMax-15K lot section below. The manifest was already frozen, so the one command was the run with `--probes nop`: every verdict lands in the none stratum with `one_sided` true, a nop acceptance is the only invalid finding, and the certificate is a one-sided bound over the accepts-an-empty-solution defect class only (`src/task_validation/evidence/generator_gate.py`, `src/task_validation/sampling/certificate.py`).

```bash
cd ~/task_validation
systemd-run --user --collect -p MemoryHigh=22G -p MemoryMax=24G -p CPUWeight=50 -p IOWeight=50 \
    --unit=gen-gate-tmax --same-dir \
    env PYTHONPATH=src .venv/bin/python -m task_validation.cli generator-gate-run \
    --name tmax --probes nop --concurrency 3
```

## Scheduling and what it measures

The gate offers two dispatches, and the choice changes what a verdict means. Under `concurrent` (default; all of a task's trials fan out at once) each trial builds its own environment image, so package installs are refetched per trial and two trials of one task can run against different images; each trial approximates an independent deployment of the task. Under `warmup` (`--warmup`) the first trial builds alone and every later probe runs against that one cached image; the task is deployed once and probed repeatedly. The per-verdict `deterministic` flag (`task_verdict` in `src/task_validation/evidence/generator_gate.py`) compares rep rewards within a task; what a disagreement means depends on which scheduling produced it.

| | `concurrent` (default) | `warmup` (`--warmup`) |
| --- | --- | --- |
| Image per trial | Own build; installs refetched; two trials of one task can differ | One shared image from the warmup build |
| Rep disagreement reads as | Verifier nondeterminism or build nondeterminism, pooled; the flag cannot separate them | Verifier nondeterminism only; the image is held fixed |
| Detects | Both defect classes: a flaky verifier, and an environment that builds differently across builds or days (floating deps, repo rot between builds) | Verifier nondeterminism isolated from build |
| Misses | Attribution: a rep-to-rep reward change cannot be assigned to the verifier or to the build | Build nondeterminism: a task that would build differently tomorrow reads deterministic today. A single `infra` warmup build also orphans the task's remaining trials as `not_run`, where concurrent gives each trial an independent build attempt |

One observed case sits on the boundary. RST task `rts_task_428772f088f387a5a5931b6a` returned oracle rewards [0.0, 1.0] and is counted invalid as a nondeterministic reference (flagged table below). Its two oracle reps ran against separately built images, so under warmup scheduling (one shared image) the same task could have read as deterministic and stayed unflagged. The cause has not been isolated to the verifier or the build.

Recommendation: `warmup` is for speed on re-runs, and for future lots only where a separate build-determinism probe exists; otherwise the gate stops detecting environment-build instability, a defect class the concurrent runs did catch. Any certificate comparison across pools must state which scheduling produced each certificate. Provenance: `build_certificate` writes a `scheduling` field (`concurrent` or `warmup`) onto every certificate; the RST and SETA certificates in `data/gold` were produced under `concurrent`. The TMax run (unit `gen-gate-tmax`, 2026-09-14) ran `warmup`. Its certificate (`data/gold/gen_gate_tmax.certificate.json`) is stamped accordingly and is not scheduling-comparable to the other two.

## Results

RST lot, run 2026-09-13 on `lake-vps-lor-main`. SRS n=200 of N=37,484, seed `gen-gate-rst-v0` (`data/gold/gen_gate_rst_manifest.json`). Of 200 sampled tasks, 195 were adjudicated: 188 valid, 7 invalid, 0 nop accepts in 390 executed nop trials (`data/gold/gen_gate_rst.summary.json`). Five tasks stayed unadjudicated after one `--redo-infra` pass and one targeted retry at concurrency 1 (828 rows in `data/gold/gen_gate_rst.jsonl`). One draw, two certificates: the restricted bound (a) quotes N=37,479, n=195, k=7 with the 5 uncovered units excluded; the conservative bound (b) quotes N=37,484, n=200, k=12 with all 5 counted invalid. Any citation of this run must name which bound it quotes, since the populations and k differ.

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

Bound (a) is the headline. It treats the 5 uncovered units as outside the frame: coverage is 195 of 200 (0.975), the population drops to 37,479, and the claim extends to the full lot only if the uncovered units share the covered units' inconsistency rate. Bound (b) needs no such assumption: it counts all 5 uncovered units invalid. The true value lies between the two bounds only under those stated readings, exchangeability for (a) and the worst case for (b). Under both bounds the lot fails the gate at epsilon 5 percent, so the decision is reject: the 7 flagged tasks must be dropped or repaired before the lot can ship (doc 50 section 2).

### Run cost

Wall clock about 4.1 h for the main pass (first harbor job 2026-09-13T17:32:18, last 21:38:59, from `result.json` timestamps under `/tmp/tv-gen-gate-rst/jobs/`), plus a 4 min `--redo-infra` pass and a 3.5 min closeout retry (`journalctl --user -u gen-gate-rst-200`, `-redo`, `-retry3`). Runner CPU was 1 h 25 min, 2 min, and 57 s on the three units. Summed trial time is 54,813 s, about 15.2 h, over 828 rows (`data/gold/gen_gate_rst.jsonl`). API cost is 0 dollars: oracle and nop are model-free agents and `cost_usd` is null in every job `result.json`. A second gate (SETA, then TMax) ran on the host at concurrency 3 throughout; the closeout retry ran at concurrency 1 with image pruning disabled.

### Image-warmup benchmark

The warmup schedule was measured on 2026-09-14 against the first 12 ids of `data/gold/gen_gate_tmax_manifest.json`, run twice on `lake-vps-lor-main` at concurrency 3 with `docker container/image/builder prune` before each arm so both started cold. Artifacts are under `/home/evan/gate_bench/` (scratch manifest `gen_gate_tmaxbench_manifest.json`, generator `tmax-warmup-bench`, a benchmark sample and not a certificate). All 12 sampled TMax tasks turned out to be `no_reference`, so each task ran only its two nop trials; the oracle reps recorded `no_reference` rows in both arms, and both arms wrote the same 48 trial keys.

| Arm | Total wall | Median trial | First trial per task | Later trial per task | Sum of trial times |
| --- | ---: | ---: | ---: | ---: | ---: |
| `--no-warmup` | 36.3 min | 149.6 s | 149.7 s (rep 0) | 148.9 s (rep 1) | 4,301 s |
| warmup | 42.8 min | 93.7 s | 123.8 s (rep 0) | 61.3 s (rep 1) | 2,560 s |

"First" and "later" are dispatch order here. Under all-at-once dispatch (the default; this arm ran with the old `--no-warmup` flag) both nop reps build concurrently and land together (about 150 s each). Under warmup, rep 0 is the warmup trial: a solo cold build at 124 s median, faster than the contended 150 s; rep 1 then hits the image cache at 61 s. The mechanism works exactly as intended, but the change did not help wall clock on this lot: warmup was about 18 percent slower end to end (42.8 vs 36.3 min). With only two runnable trials per task, the serialized warmup costs more than the single cache hit saves. The win that does materialize is work, not wall: summed trial time fell 40 percent because each image is built once instead of twice, which means less disk and CPU contention for whatever else shares the host. On lots where all four trials run, the second wave is three cache hits rather than one and the wall trade is more favorable; this bench cannot measure that regime. Default stays all-at-once; pass `--warmup` only where the scheduling construct is acceptable (see below).

### Where this sits

In the doc 42 ordering of populations by audit history, the RST covered-slice point estimate of 3.6 percent lands between TB 2.1 post-fix and Harbor-Index, and the conservative 6.0 percent lands just above TB 2.1. SETA-Env at 0.5 percent lands below every other measured pool.

| Population | Invalid rate | Source |
| --- | ---: | --- |
| TB 2.0 pre-fix | 33% | doc 42 |
| eval_tasks | 12.5% | doc 42 |
| RST, conservative k=12/200 | 6.0% | `data/gold/gen_gate_rst.conservative.certificate.json` |
| TB 2.1 post-fix | 5.6% | doc 42 |
| Harbor-Index executable stratum (53 of 82) | 3.8% | doc 42 |
| RST, restricted k=7/195 | 3.6% | `data/gold/gen_gate_rst.certificate.json` |
| SWE-bench random | 2% | doc 42 |
| SETA-Env, k=1/200 | 0.5% | `data/gold/gen_gate_seta.certificate.json` |

Both generator-gate rows are `scheduling=concurrent` certificates (see above); a warmup-produced certificate would not be like-for-like in this table.

Two of the five uncovered tasks are environment rot, not verifier inconsistency: `deb.debian.org` no longer resolves bullseye-security, so the image cannot be built today and the task cannot be adjudicated either way. That is a distinct construct from a verifier that runs and returns a wrong answer. The precedent is doc 23 section 7 on `django__django-10097`: a task is invalid on today's image regardless of what the 2024 environment did. The symmetric statement here is that a task whose environment cannot be built today is unadjudicated, not invalid; it enters the bound only as a worst-case unit in the conservative certificate.

Scope note: RST is the raw 37,484-task pool that generator T1 (arXiv 2609.11042) filtered down to about 15,000 and trained on, with a reported RL lift of 59.9 to 64.0 on TB 2.1 (doc 43, doc 46). This gate measures the raw pool. It is evidence about what T1's filter had to remove, not a claim that RST is unusable.

### SETA-Env lot

SETA-Env lot, run 2026-09-14 on `lake-vps-lor-main`. SRS n=200 of N=4,569, seed `gen-gate-seta-v0` (`data/gold/gen_gate_seta_manifest.json`). All 200 sampled tasks were adjudicated: 199 valid, 1 invalid, 0 nop accepts in 400 executed nop trials (`data/gold/gen_gate_seta.summary.json`). One task needed a `--redo-infra` pass to close out: `SETA_Evolve/ask_ubuntu__13__d1` lost its two rep-0 trials to a transient infra exit at about 15 s and re-executed clean (802 rows in `data/gold/gen_gate_seta.jsonl`). One draw, one certificate: N=4,569, n=200, k=1.

#### Flagged tasks (k = 1 of 200 adjudicated)

The single flag is the same defect class as all seven RST flags: the reference fails its own verifier. Rewards are from `data/gold/gen_gate_seta_verdicts.jsonl`; the observed failure is from the oracle trials' `test_stdout_tail` in `data/gold/gen_gate_seta.jsonl`.

| Task | Oracle | Nop | Deterministic | Observed failure |
| --- | --- | --- | --- | --- |
| `SETA_Synth/kaggle_notebook__crawford_exercise-time-series-modeling` | [0, 0] | [0, 0] | yes | 10 failed assertions in `tests/test_outputs.py` |

#### Uncovered tasks (0 of 200)

None. Coverage is 200 of 200 (`data/gold/gen_gate_seta.certificate.json` carries `n_unadjudicated=0`).

#### Bound

Same machinery as RST: `hypergeometric_upper` inside `build_certificate`, one-sided alpha 0.05, release iff ucb95 < epsilon = 0.05.

| Bound | N | n | k invalid | p-hat | UCB 95 | Decision | Artifact |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| complete | 4,569 | 200 | 1 | 0.50% | 2.32% | release | `data/gold/gen_gate_seta.certificate.json` |

With zero uncovered units there is no restricted/conservative split: the certificate is complete and the decision at epsilon 5 percent is release.

#### Run cost

Wall clock about 10.3 h for the main pass (run start 2026-09-14T01:00:49, done 11:21:24 in `logs/gen_gate_seta.log` on the VPS; first harbor job 01:00:51, last 11:29:17 from `result.json` timestamps under `/tmp/tv-gen-gate-seta/jobs/`), plus a 7.6 min `--redo-infra` pass. Runner CPU was 1 h 33 min on the queue unit and 40 s on the redo unit. Summed trial time is 90,563 s, about 25.2 h, over 802 rows (`data/gold/gen_gate_seta.jsonl`). API cost is 0 dollars: oracle and nop are model-free agents and `cost_usd` is null in every job `result.json`.

### TMax-15K lot

TMax-15K lot, run 2026-09-14 on `lake-vps-lor-main`. SRS n=200 of N=8,047, seed `gen-gate-tmax-v0` (`data/gold/gen_gate_tmax_manifest.json`). No task in the pool ships a reference, so the run used `--probes nop`: all 200 verdicts sit in the none stratum with `one_sided` true, protocol `verifier_invalid.fresh_environment.execution`, grade A, adjudicator machine (`data/gold/gen_gate_tmax_verdicts.jsonl`). The run ran under warmup scheduling (see "Scheduling and what it measures"). The operator stopped it inside its 3 h budget after 41 tasks were covered, each with two executed nop trials. The other 159 sampled tasks were never dispatched (`logs/gen_gate_tmax.log`, `data/gold/gen_gate_tmax.summary.json`).

#### Accepted empty solutions (0 of 41 covered)

None. All 82 executed nop trials returned reward 0.0, two per covered task (`data/gold/gen_gate_tmax.jsonl`). There are no ids or rewards to list. A nop rejection is not evidence of validity, so the 41 covered tasks count in the bound but are never called valid (doc 44).

#### Uncovered tasks (159 of 200)

All 159 are undispatched, not failed. No retained row is `infra` or `timeout` (`data/gold/gen_gate_tmax.summary.json`: `n_infra_trials` 0, `n_timeout_trials` 0). An earlier attempt the same day wrote an infra row per trial in under a second when `harbor` was missing from the unit PATH. Those rows were wiped before the restart and the manifest was reused unchanged (`logs/gen_gate_tmax.log`).

#### Bound

One draw, two certificates, both one-sided over the accepts-an-empty-solution defect class only (doc 44). The restricted bound (a) drops the 159 uncovered units from the sample and the frame, so N falls from 8,047 to 7,888. The conservative bound (b) keeps the full frame and counts all 159 uncovered units invalid. Any citation of this run must name which bound it quotes, since the populations and k differ.

| Bound | N | n | k invalid | p-hat | UCB 95 | Decision | Artifact |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| (a) restricted population | 7,888 | 41 | 0 | 0% | 7.04% | reject | `data/gold/gen_gate_tmax.certificate.json` |
| (b) conservative | 8,047 | 200 | 159 | 79.5% | 84.04% | reject | `data/gold/gen_gate_tmax.conservative.certificate.json` |

Bound (a) is the headline. With zero acceptances in 41 covered units its one-sided 95 percent bound is 7.04 percent, above epsilon 5 percent, so the decision is reject. Bound (b) needs no exchangeability assumption: it counts every undispatched unit as an acceptance and rejects at 84.04 percent. The true one-sided rate lies between the two bounds only under those stated readings, exchangeability for (a) and the worst case for (b). Both certificates carry `one_sided` true, `verifier_kind` none, `scheduling` warmup, and an `interpretation` field naming the covered defect class. Nothing is imputed under (a): the 159 units leave the frame rather than receiving labels (doc 32).

#### Run cost

Wall clock about 2.5 h: the restart is logged at 2026-09-14T12:48:53 and the stop at 15:17:31 (`logs/gen_gate_tmax.log`). Runner-measured wall clock is 8,748 s (`data/gold/gen_gate_tmax.summary.json`). Summed trial time is 8,689 s over 82 rows (`data/gold/gen_gate_tmax.jsonl`). API cost is 0 dollars: the oracle probe did not run and nop is a model-free agent. Two builder prunes fired, after tasks 20 and 40 (`data/gold/gen_gate_tmax.summary.json`).

#### What this measures and what it cannot

The result is a bound on one defect class on a covered subpopulation: how often a TMax verifier returns a passing reward to an empty submission. Zero accepts in 41 covered tasks means the class was not observed there. At n=41 the bound cannot reach epsilon 5 percent even with zero findings, so TMax does not release. Three things are unmeasured. First, the reference-fails-its-own-verifier class: TMax ships no references, and that class supplied all 7 RST flags and the 1 SETA flag (`data/gold/gen_gate_rst_verdicts.jsonl`, `data/gold/gen_gate_seta_verdicts.jsonl`). Second, validity in either direction for the 41 covered tasks: a nop rejection is consistent with a correct verifier and with a verifier that accepts nothing. Third, the 159 uncovered units: the restricted bound reaches them only under exchangeability with the covered units. The warmup scheduling does not confound this bound, because a nop outcome does not depend on whether the image was built alone or under contention. It does mean the certificate is not scheduling-comparable to the RST and SETA certificates.

### Sensitivity to epsilon

Epsilon is a policy parameter the consumer supplies, not a number the method produces; the 5 percent default carries no scientific meaning. Re-deciding every certified population at other epsilons, using the ucb95 values already in the certificate files (release iff ucb95 < epsilon):

| Population | One-sided 95% UCB | epsilon 1% | epsilon 2% | epsilon 5% | epsilon 10% | Source |
| --- | ---: | --- | --- | --- | --- | --- |
| SETA-Env generated pool | 2.32% | reject | reject | release | release | `data/gold/gen_gate_seta.certificate.json` |
| SWE-bench SRS-300 completed prefix | 4.65% | reject | reject | release | release | `data/gold/swe_srs300.certificate.json` |
| TB 2.1 full pool, census | 5.62% | reject | reject | reject | release | `data/gold/tb21_census.certificate.json` |
| SWE-bench SRS-100 | 6.06% | reject | reject | reject | release | `data/gold/swe_srs100.certificate.json` |
| RST generated pool, restricted bound | 6.63% | reject | reject | reject | release | `data/gold/gen_gate_rst.certificate.json` |
| TB 2.1 SRS-30, machinery check | 7.87% | reject | reject | reject | release | `data/gold/tb21_srs30.certificate.json` |
| RST generated pool, conservative bound | 9.53% | reject | reject | reject | release | `data/gold/gen_gate_rst.conservative.certificate.json` |

The TMax certificate produces no row: its bound is one-sided over the accepts-an-empty-solution defect class only, a different estimand from the verifier-consistency bounds above (restricted N=7,888 covered, n=41, k=0, ucb95 7.04 percent, and conservative N=8,047, n=200, k=159, ucb95 84.04 percent; reject at epsilon 5 percent under both, `data/gold/gen_gate_tmax.certificate.json`, `data/gold/gen_gate_tmax.conservative.certificate.json`, TMax-15K lot section). No bound was re-run. Every decision above is the stored ucb95 compared against each epsilon.

## TMax scheduling, recorded 2026-09-14

The TMax run uses warmup scheduling. RST and SETA used concurrent scheduling. The TMax process loaded the warmup-on-by-default build before the default was flipped to opt-in, and its certificate is stamped `warmup` rather than rewritten, because restating it as concurrent would fabricate provenance.

The run was not restarted. Two reasons. The TMax measurement is one-sided already, covering only the accepts-an-empty-solution defect class, so it is not scheduling-matched to RST and SETA regardless. And scheduling changes what the oracle-determinism flag conflates, which a nop-only gate does not measure: an empty submission either passes the verifier or it does not, and that outcome does not depend on whether the image was built alone or under contention.

What the difference does cost: both nop trials of a task run against one cached image, so a task whose environment builds differently on different days cannot be detected. Any comparison of the TMax rate to the RST or SETA rate must state both the one-sided coverage and the scheduling difference.

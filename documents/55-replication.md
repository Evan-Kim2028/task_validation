# Replicating the Harbor-Index funnel on the public dump

How-to for an agent operator: a person driving coding agents, not typing the commands. Every step names its command, its input, its output artifact, and the count that tells you it worked. Docs 45, 48, 52, and 54 are the run record; this file is the operator version.

## The open dataset

`kendx/Harbor-Adapter` on Hugging Face, revision `fa3538157a4b372b8ed36723ba0aa6dc30f6e22e` (`data/raw/harbor-adapter/CLAIMS.md`).

| Field | Value | Source |
| --- | ---: | --- |
| Files | 495 | `logs/vps/harbor_dump.log` |
| Size | about 340 GB | doc 45, `CLAIMS.md` |
| Trials | 793,698 | `data/gold/harbor_adapter_trials.summary.json` |
| Benchmarks | 60 | `harbor_adapter_trials.summary.json`, `rows_per_benchmark` |
| Tasks | 8,468 | `harbor_adapter_trials.summary.json`, `n_distinct_task_pairs` |
| Stage-1 candidates | 6,627 | `data/raw/harbor-adapter/adapters54.json`, `n_task_pairs` |
| Manifest rows | 178,647 | `CLAIMS.md` |
| Models | 16 | `harbor_adapters.manifest.parquet` |
| Agents | 6 | `harbor_adapters.manifest.parquet` |
| License | other | `CLAIMS.md`, dataset card |

Three companion sources. `harbor-index/harbor-index-1.0` on Harbor Hub holds the 82 published survivors (doc 28). The `harbor-framework/harbor-index` GitHub repo carries a per-task README whose "Original upstream task" section is the bridge from index id to manifest pair (doc 48). `harborframework/harbor-datasets` on Hugging Face holds the upstream task dirs (245,732 files fetched, `logs/vps/harbor_datasets.log`); the funnel pipeline below never needs it, because task directories stay unfetched (doc 52).

## Hardware and time actually used

All numbers are from the 2026-09-13 run on lake-vps-lor-main and the home machine.

| Stage | Throughput or time | Source |
| --- | --- | --- |
| Home fetch, single stream | 29 MB/s | doc 48 |
| VPS fetch, 8 streams | 193 MB/s | doc 48 |
| Reward extraction | about 10 shards per minute, 4 workers, about 3 GB per worker | `logs/vps/harbor_extract.log` (492 shards), doc 48 |
| Trajectory extraction | about the same | `logs/vps/harbor_traj.log` (492 shards) |
| Funnel analysis | minutes | `harbor_funnel.py` run for doc 52 |

Disk: 340 GB for the dump plus one shard in flight per worker, under 4 GB each (doc 48). The fetch needs a fat pipe, not a big machine. The extraction needs about 12 GB of worker memory headroom. The analysis runs on a laptop.

## The pipeline

Run from the repo root with `PYTHONPATH=src .venv/bin/python`. Steps 3 to 5 run on the remote host; the rest run anywhere the artifacts land.

1. Download the manifest. `hf_hub_download("kendx/Harbor-Adapter", "harbor_adapters.manifest.parquet", repo_type="dataset", local_dir="data/raw/harbor-adapter")`. Output: `data/raw/harbor-adapter/harbor_adapters.manifest.parquet`, 178,647 rows (`CLAIMS.md`).
2. Verify the candidate pool. Encode paper Table 5 and appendix H.1 into `data/raw/harbor-adapter/adapters54.json`, then count distinct `(benchmark, task_name)` over the 54 slugs. Expected: 6,627 pairs, of which 5,684 carry at least 3 trials in all six frontier cells (`adapters54.json`).
3. Snapshot the dump. `snapshot_download(repo_id="kendx/Harbor-Adapter", repo_type="dataset", local_dir="/home/evan/harbor-adapter-dump", max_workers=8)` under `systemd-run --user -p MemoryHigh=6G -p MemoryMax=8G --unit=tv-harbor-dump`. Expected: 495 files, about 340 GB (doc 48). Keep the whole dump; it answers later questions without a refetch (doc 48).
4. Extract every trial row: `-m task_validation.cli harbor-extract-local --dump-dir /home/evan/harbor-adapter-dump --out data/gold --workers 4`. Outputs: `data/gold/harbor_adapter_trials.jsonl` (793,698 rows) and `data/gold/harbor_funnel_rewards.jsonl` (768,956 in-scope rows). Expected in `harbor_adapter_trials.summary.json`: 492 shards, 0 failures, 8,468 task pairs, 6,627 in-scope pairs.
5. Extract trajectory and verifier features: `-m task_validation.ingest.harbor_adapter_traj --dump-dir /home/evan/harbor-adapter-dump --out data/gold --workers 4`. Outputs: `data/gold/harbor_adapter_traj.jsonl` (793,698 rows, 757 MB, doc 54) and `data/gold/harbor_adapter_task_traj.jsonl` (8,468 tasks). Expected in `harbor_adapter_traj.summary.json`: 492 shards, 7 parse errors.
6. Rebuild stage 1, labels, and evaluation: `-m task_validation.evidence.harbor_funnel`. Outputs: `data/gold/harbor_funnel_stage1.jsonl` (6,627 rows, 1,331 survivors), `data/gold/harbor_funnel_labels.jsonl` (6,627 rows), mapper JSON and PNG, all summarized in `harbor_funnel_stage1.summary.json`. Then `-m task_validation.evidence.harbor_funnel traj-eval` writes `harbor_funnel_traj_eval.json` and `harbor_funnel_hidden_requirement.jsonl` (doc 54).
7. Bridge the 82 survivors. The join is `INDEX_TO_MANIFEST` in `src/task_validation/evidence/harbor_funnel.py`, transcribed from each task README in `harbor-framework/harbor-index`. Expected: 81 of 82 matched; `dacode-predict-essay-scores` has no manifest pair (doc 52). A replication that adds survivors re-reads the READMEs and extends the map.
8. Build the decontam index: `-m task_validation.cli build-decontam-index` with the four population roots as flags. Output: `data/gold/decontam_index/`, one jsonl per population plus `validation.json`. Expected counts: tb4 66, harbor_index 82, tb21 89, swe_verified 500 (doc 49).
9. Run the generator gate. Freeze with `-m task_validation.cli generator-gate-sample --name rst --root /home/evan/gen-sets/rst --n 200`, then `-m task_validation.cli generator-gate-run --name rst --concurrency 4` under `systemd-run --user -p MemoryMax=24G -p CPUWeight=50` (doc 53). Expected: trial rows approaching 4 times n (oracle twice, nop twice), then `gen_gate_rst.certificate.json`.

## Traps we hit

| Trap | Fix | Evidence |
| --- | --- | --- |
| Row-group layout blocks per-trial fetch: one row group per shard, no page index, the hosted API refuses the scan | Take the whole dump. Every cheaper granularity is closed (doc 48) | doc 48 |
| systemd user units do not see a new docker group: a unit launched before `usermod -aG docker` keeps the old groups | Launch through `sg docker` or a fresh login | `logs/vps/gen_gate_rst.log`, permission denied lines then the `sg docker` relaunch |
| `docker image prune` during a run kills trials still building | Never prune by hand while a gate runs; the runner prunes on its own cadence, `--prune-every` 20 tasks | `src/task_validation/evidence/generator_gate.py` |
| Stale compose networks exhaust the docker address pool | `docker network prune`, then pin `default-address-pools` in daemon.json | this doc |
| HF small-file repos are file-count bound, not byte bound: SETA-Env is 49,273 files at about 20 files per second with 429s | Raise `max_workers` and the unit's LimitNOFILE | `logs/vps/gensets.log`, `logs/vps/harbor_datasets.log` (245,732 files) |
| Agent timeouts of 8 h inside harbor tasks | Cap them: `--timeout-multiplier`, `--verifier-timeout-multiplier`, `--environment-build-timeout-multiplier`, plus `--trial-cap-sec` (default 3,600 s) | `generator_gate.py`, doc 53 |
| `pkill -f` matches your own shell | Stop by unit name (`systemctl --user stop <unit>`) or match the venv path, never a bare substring | this doc |

## Driving it with agents

One agent per module. The module boundaries in this repo are already the right size: `harbor_adapter.py` fetches, `harbor_adapter_local.py` extracts, `harbor_adapter_traj.py` extracts features, `harbor_funnel.py` evaluates, `decontam.py` indexes, `generator_gate.py` gates. Do not give one agent two modules.

Prompts name the exact files and artifacts. A good prompt reads like a step above: command, input path, output path, expected count. An agent that cannot state the expected count does not know when it is done.

Hold a RESULT contract. Every agent ends its report with a RESULT section listing artifacts written and counts observed versus expected. The main session reads the RESULT sections and commits; agents never commit.

Long docker runs launch detached: `setsid nohup` or `systemd-run --user`, never inside an agent session. The session dies, the run dies with it, and `harbor run` leaves half-built containers behind. The fetch and both extractors are resume-aware at shard granularity, and the gate skips terminal trials, so a dead run loses minutes, not hours.

Use monitors instead of polling. A monitor tails `logs/` or `journalctl --user -u <unit>` and reports; a polling loop re-reads state on a timer and burns context. If an agent times out, retry it after 30 minutes; resume logic picks up where it stopped.

## What to expect

| Check | Expected | Observed | Source |
| --- | ---: | ---: | --- |
| Stage-1 survivors vs published | within 10 percent | 1,331 vs 1,311, +1.5 percent | doc 52, `harbor_funnel_stage1.summary.json` |
| `survived_2_to_4` AUROC, leave-one-benchmark-out | about 0.71 | 0.711 (0.650, 0.771) | doc 54, `harbor_funnel_traj_eval.json` |
| `survived_2_to_4` AUROC, leave-one-family-out | under 0.65 | 0.612 (0.529, 0.697) | doc 54, `harbor_funnel_traj_eval.json` |

The stop rule (doc 45): family-held-out AUROC for `survived_2_to_4` under 0.65 means the footprint is benchmark-family identity and the plan stops. It triggered at 0.612 (doc 54). Do not retune features to beat it; every wider feature set scored lower held out (doc 54).

## Not reproducible from public data

Three things stay private. The stage-1 filtering database: the paper scored 18 trials per task from a private store, so the public dump approximates the input and lands within 1.5 percent, not exactly (doc 45, doc 52). The rejected task ids for stages 2 to 4: only the 82 survivors are published, so the funnel labels are reconstructed, not recovered (doc 45). The shipped judge keys: 16 of 82 tasks grade through `JUDGE_MODELS` env vars (`data/gold/harbor_index_strata.json`), and the judge configuration the authors ran is not public (doc 28).

## RESULT

- Wrote `documents/55-replication.md`: dataset table, measured hardware and time, a 9-step pipeline with commands and expected counts, seven traps with fixes, agent-driving rules, expected numbers, and the three private gaps.
- Anchors: docs 45, 48, 49, 52, 53, 54; `data/raw/harbor-adapter/CLAIMS.md` and `adapters54.json`; `data/gold/harbor_adapter_trials.summary.json`, `harbor_adapter_traj.summary.json`, `harbor_funnel_stage1.summary.json`, `harbor_funnel_traj_eval.json`; `logs/vps/`.

## Scripts and the data index

The ingest and extraction scripts, together with an index of the public evaluation run data they cover, are published at [`evaltrials`](https://github.com/Evan-Kim2028/evaltrials): 26 datasets, about 1 TB, 881,660 recorded agent trials, $376,563 of disclosed compute. Start there for what exists and how large it is, then return here for the pipeline that turns it into labels and certificates.

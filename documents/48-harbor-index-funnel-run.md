# Harbor-Index funnel fetch: run reference

Status: blocked before download. Nothing is running. `data/gold/harbor_funnel_rewards.jsonl` does not exist.

## What was planned

Doc 45 step 1: fetch `result.json` and `verifier/reward.txt` for the stage-1 trials of the 6,627 Harbor-Index candidates. The worklist is the 6 frontier cells of paper appendix H.1 (arXiv 2609.04298) at up to 3 stored trials per cell:

| Cell | Agent | Model |
| --- | --- | --- |
| 1 | claude-code | claude-opus-4-6 |
| 2 | terminus-2 | claude-opus-4-6 |
| 3 | codex | gpt-5.4 |
| 4 | terminus-2 | gpt-5.4 |
| 5 | gemini-cli | gemini-3.1-pro-preview |
| 6 | terminus-2 | gemini-3.1-pro-preview |

Source: `data/raw/harbor-adapter/adapters54.json`. The manifest (`data/raw/harbor-adapter/harbor_adapters.manifest.parquet`, 178,647 rows) gives 115,020 needed trial_ids across the 54 paper adapters.

## Why it is blocked: no per-archive fetch granularity

The `trajectories` config stores each trial as `archive` bytes inside `data/harbor_adapters/<benchmark>/NNNNN.parquet`. Three facts close every cheaper granularity than a whole shard:

1. **One row group per file.** Measured on `codepde/00000.parquet` (495 rows, 127.7 MB), `sldbench/00000.parquet` (1,014 rows, 483.8 MB), `widesearch/00000.parquet` (1,935 rows, 734.3 MB). The minimum parquet read unit is the column chunk, i.e. effectively the whole file.
2. **No page index.** Footer metadata on codepde, sldbench, and labbench shards reports `has_offset_index = False` and `has_column_index = False` on all three columns. A single row cannot be located by byte range.
3. **The hosted API agrees.** `GET https://datasets-server.huggingface.co/rows?dataset=kendx/Harbor-Adapter&config=trajectories&split=full` returns: `Parquet error: Scan size limit exceeded: attempted to read 734296860 bytes, limit is 300000000 bytes ... contain a page index to enable random access without loading entire row groups`.

Coverage is also worst-case. The cached trial index (`data/raw/harbor-adapter/trial_shards.jsonl`, built by reading only the `trial_id` column of every in-scope shard) shows all 471 in-scope shards contain needed trials. Median needed-row fraction per shard is 15.2%; the median shard's last needed row sits at 98.9% of file length, so streaming with early stop saves about 1%.

## Byte estimate

| Granularity | Bytes for the stage-1 trials | Basis |
| --- | ---: | --- |
| Whole shard (only real unit) | 327.1 GB | all 471 in-scope shards, `adapters54.json` `trajectory_bytes` |
| Per trial (hypothetical) | about 49 GB | 115,020 trials x 428 KB mean archive (340.0 GB / 793,698 trials, HF `size` endpoint) |
| Hard budget (doc 45 cost cap) | 40 GB | task rule |

Measured archive sizes on the fetched sample shard `codepde/00000.parquet` (495 trials): median 64.6 KB, mean 257.8 KB, p90 242.5 KB, max 28.8 MB. Extraction verified: every sampled archive contains `result.json` and `verifier/reward.txt`.

At shard granularity the run needs 327.1 GB, about 8x the 40 GB budget. Even ideal per-trial fetching is about 49 GB, over budget. The run is parked; it needs either a budget of about 330 GB or a dataset re-share with page indexes or per-trial files.

## Fetcher, written but not launched

`src/task_validation/ingest/harbor_adapter.py`, exposed as `task-validation harbor-funnel-fetch`. It is resume-aware: the trial index is cached in `trial_shards.jsonl`, completed shards are recorded in `harbor_funnel_rewards.state.json`, and trial_ids already in the output JSONL are skipped. Per shard it downloads to `data/raw/harbor-adapter/shards/`, verifies `archive_sha256`, extracts `result.json` and `verifier/reward.txt` for needed trials only, appends rows to `data/gold/harbor_funnel_rewards.jsonl`, deletes the shard, and stops when the byte budget would be exceeded. Shards are ordered by needed trials per byte, descending.

Plan check (no download):

```
PYTHONPATH=src .venv/bin/python -m task_validation.cli harbor-funnel-fetch --dry-run
```

Resume command, if a budget of 330 GB is ever approved:

```
cd /home/evan/Documents/task_validation
setsid nohup env PYTHONPATH=src .venv/bin/python -m task_validation.cli \
    harbor-funnel-fetch --budget-gb 330 >> logs/harbor_funnel_fetch.log 2>&1 &
```

## Analysis commands after a fetch finishes

1. Stage-1 solve rates. Group `harbor_funnel_rewards.jsonl` by `(benchmark, task_name)`; `n_succ` counts trials with `reward > 0` (benchmark cutoffs per appendix H.1 where a benchmark is not binary). `survived_stage1 = n_succ <= 6` over the up-to-18 fetched trials. Compare the reconstructed survivor count against the published 1,311 (doc 45) to measure how far the public dump approximates the private filtering database.
2. Three labels (doc 45): `survived_stage1`, `survived_funnel` (82 positives), `survived_2_to_4` (82 positives, conditional on stage-1 survival). The positives are the 82 task_ids in `data/gold/harbor_index_control.jsonl` (doc 28). The join to manifest `task_name` is not string equality: the index renamed tasks. The bridge is each index task's `README.md` in `harbor-framework/harbor-index`, which names the upstream record (e.g. `bix-diff-expr-mirna` is BixBench `bix-30-q1`; `hle-identify-city-from-photo` is HLE item `676762beff30b300db258691`, matching manifest `hle/hle__676762beff30b300db258691`). Every label row carries protocol `harbor-index-funnel-v1` and treatment grade `external-audit, eval-only` (doc 21, doc 32; eval-only per doc 43).
3. Footprint extraction. Apply `layout_static_features` from `src/task_validation/evidence/footprint.py` to the candidate task packages (doc 40); task materials come from the benchmark sources, not from the reward JSONL.
4. Leave-one-benchmark-out AUROC per label (doc 45 step 4). Compare against the 0.71 curated-vs-generated held-out number in doc 40.
5. Stop rule (doc 45): if leave-one-benchmark-out AUROC for `survived_2_to_4` is under 0.65, the footprint is benchmark identity and the plan stops.

## Relaunch 2026-09-13

The 40 GB budget in doc 45 was a guess and is withdrawn. Streaming shard-at-a-time keeps disk at one shard (up to 3.5 GB), so the real cost is bandwidth, about 327 GB at roughly 19 MB/s, five to six hours. The fetch was relaunched with `--budget-gb 350` under a user unit `tv-funnel-fetch` with MemoryHigh 6G and MemoryMax 8G, because one shard is held in memory and peaked at 3.1 GB. It is resume-aware. Log: `logs/harbor_funnel_fetch.log`. Output: `data/gold/harbor_funnel_rewards.jsonl`. Status: `systemctl --user status tv-funnel-fetch`.

## Moved to lake-vps-lor-main 2026-09-13

Decision (Evan): keep the whole dump, not just the extracted rewards, so later questions can be answered without refetching. The home fetch was stopped at 275 of 471 shards (182 GB streamed, 107,977 trial rows in `data/gold/harbor_funnel_rewards.jsonl`, kept as a partial). The full dataset `kendx/Harbor-Adapter` (495 files, about 340 GB) is downloading on lake-vps-lor-main as user evan into `/home/evan/harbor-adapter-dump` via `snapshot_download` with hf_transfer and 8 workers, under user unit `tv-harbor-dump` with MemoryHigh 6G, MemoryMax 8G, IOWeight 50, CPUWeight 50 so the lakehouse timers keep priority. Measured throughput 193 MB/s on 8 streams against 29 MB/s single-stream at home. Extraction of rewards runs on the VPS from local files afterwards; only the rewards table comes back to this repo. Fetcher code and manifest are at `/home/evan/task_validation` on the VPS.

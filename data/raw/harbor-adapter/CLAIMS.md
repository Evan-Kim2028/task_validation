# Harbor-Adapter manifest (eval-only)

Downloaded 2026-09-13. Source of the Harbor-Index stage-1 candidate pool.

- Dataset: `kendx/Harbor-Adapter` on Hugging Face (`https://huggingface.co/datasets/kendx/Harbor-Adapter`), revision `fa3538157a4b372b8ed36723ba0aa6dc30f6e22e`
- Paper: arXiv 2609.04298 (`https://arxiv.org/html/2609.04298`), appendix E.1
- License: `other` (dataset card `license` field; no LICENSE file in the repo)
- Use: evaluation labels only. No trajectory bytes were pulled (documents/48).

| File | Bytes | sha256 |
| --- | ---: | --- |
| `harbor_adapters.manifest.parquet` | 15,952,527 | `b669eb58c7685f7f8bd818c810435419e77b9dfe5ff3bec5d61c1d78fadf8bc2` |
| `README.md` | 6,923 | dataset card, fetched the same day |

The manifest holds 178,647 rows: one per `(benchmark, task_name, agent, model)` cell with a `trial_ids` list (up to 5 most recent). No reward column. Rewards live inside per-trial `.tar.gz` archives in the `trajectories` config (`data/harbor_adapters/<benchmark>/NNNNN.parquet`, 340.0 GB total, `verifier/reward.txt` and `result.json` inside each archive).

`adapters54.json` records the 54 paper adapters (arXiv 2609.04298 Table 5), their manifest slugs, per-benchmark task counts, and the six frontier cells from appendix H.1. On those 54 adapters the manifest holds exactly 6,627 `(benchmark, task_name)` pairs; 5,684 have at least 3 stored trials in all 6 frontier cells.

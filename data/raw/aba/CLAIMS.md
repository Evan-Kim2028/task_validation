# ABA coding slice (eval-only)

Downloaded 2026-09-12. Sequential, retry once. Never use these IDs as features (ADR-0011).

- Host: `https://data.autobenchaudit.com/`
- Paper: arXiv 2605.26079 (License: CC BY 4.0 on the arXiv html)
- Code: `https://github.com/IsThatYou/auto-bench-audit` (GitHub `license` field is null; no LICENSE file in the repo or on the data host)
- Index `generated_at`: 2026-05-18T02:42:15Z
- Agent audit (Opus 4.7), not a human census. Expert check in the paper is a sample.

| Path | Bytes |
| --- | ---: |
| `index.json` | 106939 |
| `swe_bench_verified/benchmark.json` | 1328234 |
| `swe_bench_pro/benchmark.json` | 2455841 |
| `tb2/benchmark.json` | 268957 |

Per-task files: `benchmarks/{slug}/{static,trajectory}_audits/{task_file}.json` as referenced by `task_file` in each `benchmark.json`. 500 + 731 + 89 tasks, two audits each (2640 files). Sizes recorded in `download_summary.json` / `download_manifest.jsonl` after the sequential pull.

Join:

- SWE Verified: `task_id` = `instance_id` (e.g. `astropy__astropy-12907`)
- Pro: `task_id` is the Scale instance id with org/repo lowercased (`instance_nodebb__nodebb-...` vs public `instance_NodeBB__NodeBB-...`). Join by casefold. `task_file` suffix `__<hex>` is an audit-artifact hash, not a Scale hash.
- TB2: `task_id` = task directory name (`build-pmars`)

Counts opened on the site and reproduced from `benchmark.json`: Verified 500 (105 any finding, 39 major); Pro 731 (363 any, 85 static-major, 220 traj-major); TB2 89 (36 any, 5 static-major, 16 traj-major).

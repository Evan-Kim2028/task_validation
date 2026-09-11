# Gold artifacts

| File | What |
| --- | --- |
| `swe_verified_compact.jsonl` | 1,699 SWE-bench 2024 ensemble rows, notes stripped |
| `eval_tasks.jsonl` | Harbor packages discovered under the sister repo |
| `coverage_n50.json` | 200-rep UCB coverage at n=50 |
| `coverage_n100.json` | 200-rep UCB coverage at n=100 |
| `sample_size_ucb.json` | n required for UCB < epsilon |

Rebuild the full notes table from the OpenAI zip via `ingest-swe`. That file is gitignored (`swe_verified.jsonl`).

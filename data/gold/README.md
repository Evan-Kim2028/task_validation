# Gold artifacts

| File | What |
| --- | --- |
| `swe_verified_compact.jsonl` | 1,699 SWE-bench 2024 ensemble rows, notes stripped |
| `swe_verified_features.jsonl` | Same IDs plus cheap artifact features (no severity axes) |
| `risk_model_by_repo.json` | Logistic + HGB, repo holdout |
| `eval_tasks.jsonl` | Harbor packages discovered under the sister repo |
| `eval_tasks_with_evidence.jsonl` | Static + mutant menu + attached jobs |
| `coverage_n50.json` | 200-rep UCB coverage at n=50 |
| `coverage_n100_r200.json` | 200-rep UCB coverage at n=100 |
| `coverage_n100_r2000.json` | 2,000-rep coverage at n=100 |
| `coverage_n100_p02.json` | 2,000-rep coverage on a 2% invalid population |
| `coverage_lab.json` / `coverage_lab.summary.json` | 500-rep five-design lab, n=100 (draft) |
| `coverage_lab_r5000.json` / `coverage_lab_r5000.summary.json` | 5,000-rep five-design lab, n=100, seed `coverage-lab-v0` |
| `tb21_census_montecarlo.json` | 4,000-draw SRS coverage check against the TB 2.1 census, seed scheme `tb21-census-mc:n{n}:r{r}` |
| `sample_size_ucb.json` | n required for UCB < epsilon |
| `swe_rater_targets.jsonl` | conservative / majority / unanimous + votes |
| `oof_*.json` | grouped-CV metrics, retain curves, SRC |
| `hello_world_evidence.json` | first live Harbor oracle/nop/mutant run |
| `swe_pro_features.jsonl` | SWE-Bench Pro 731 cheap family features |
| `pro_reconstruction.json` | June Kim overlap / retain / OpenAI example rank |
| `vev_ablation_conservative.json` | A (OOF logistic) vs B (untrained spec gap) retain-tail |
| `hello_world_vev.json` | Harbor VEV with execution primitives filled |
| `causal_ablation.summary.json` | 150-task A–E retain-tail (static assays) |

Rebuild the full notes table from the OpenAI zip via `ingest-swe`. That file is gitignored (`swe_verified.jsonl`).

# EvalQA-Gold

Each row is a task. Heterogeneous provenance matters more than raw N.

## Fields

```
task_id
benchmark
benchmark_version
provenance                  EXPERT_VERIFIED | AUTHOR_ACKNOWLEDGED_FIX | HISTORICAL_MAINTENANCE | PENDING_HUMAN
language
repository
domain
human_validity_label        valid | invalid | ambiguous | pending
human_label_provenance
human_severity              protocol-specific axes, not the estimand
n_raters
difficulty
evidence                    oracle, nop, mutation, fuzz, exploit, LLM audit, static
artifacts
```

Implemented as `task_validation.schema.GoldRow`.

## Sources in this checkout

### A. SWE-bench Verified ensemble (loaded)

- File: `data/raw/swe-bench-verified/ensembled_annotations_public.csv`
- Derived: `data/gold/swe_verified_compact.jsonl`
- N = 1,699 unique `instance_id`
- Invalid under 2024 conservative filter: 1,160 (68.275%)
- Valid under that filter: 539
- Raters: 3 per task
- Provenance: `EXPERT_VERIFIED`
- Download: [OpenAI zip](https://cdn.openai.com/introducing-swe-bench-verified/swe-bench-annotation-results.zip)

The 500-task Verified *release* is a subset of the 539 that passed the filter, with extra weight on harder items. Do not treat the 539 as identical to the 500.

### B. Task Verification Bench

**Not loaded.** OpenReview `QdDcI0Ftvo` did not resolve in this search. If it becomes available, ingest it as `AUTHOR_ACKNOWLEDGED_FIX` and **do not** mix labels with A during training.

### C. Terminal-Bench maintenance

Usable later as `HISTORICAL_MAINTENANCE`. TB 2.1 changed 28 of 89 tasks (26 in one GitHub README). That is a defect history, not a 3-rater gold set.

### D. Harbor-Index

External validation population, not primary gold. They already reviewed survivors. Useful for asking whether our bound on a *source* population recovers a similar qualitative conclusion with fewer humans.

### E. eval_tasks Harbor packages (loaded, unlabeled)

- File: `data/gold/eval_tasks.jsonl`
- Complete packages queued: 16 (hello-world and planted `scripts/checks/test-tasks` excluded)
- Provenance: `PENDING_HUMAN`

## Dedup rule

Key is `(benchmark, benchmark_version, task_id)`. SWE-bench `instance_id` is already unique in the ensemble file.

## Target size

1,500–2,000 labeled rows after dedup is the research aim. This checkout has 1,699 labeled (SWE-bench) plus 16 pending Harbor tasks. Do not pad with synthetic rows.

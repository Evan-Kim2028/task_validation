# Empirical bridge (this checkpoint)

The statistical machinery was ahead of the evidence. This checkpoint builds the chain:

existing human labels → cheap machine evidence → first non-circular risk model

Human auditing of the 16 Harbor packets is **deferred** until this chain exists. The highest-value question is whether cheap signals predict the labels we already have.

## What ran

### SWE-bench join

`data/gold/swe_verified_features.jsonl`

- 1,699 / 1,699 ensemble IDs matched the public SWE-bench test parquet
- Predictors: frozen `CHEAP_FEATURE_NAMES` (statement shape, patch/test diff stats, identifier overlap, warning/exact-string asserts)
- Mutation menu counted (hunks/files) but **not executed** in Docker
- Label protocol remains `openai-swe-bench-verified-2024-conservative`

### Harbor attach

`data/gold/eval_tasks_with_evidence.jsonl`

- Deeper static checks (separate verifier, nobody, default reward 0, solution/env file overlap, instruction–test identifier overlap)
- File-level mutant menu (solution vs environment copies that differ)
- Oracle / nop / cheat rewards attached from local `eval_tasks/jobs` when the job name contains those tokens

### Risk model

`data/gold/risk_model_by_repo.json`

Held-out **repositories** (150 tasks, base invalid rate 0.707), not a random row split.

| Model | AUROC | AUPRC | Invalid among accepted at 0.5 |
| --- | ---: | ---: | ---: |
| Logistic | 0.762 | 0.883 | 0.514 |
| HGB | 0.750 | 0.876 | 0.414 |

Chance AUROC is 0.5. AUPRC chance is the base rate (0.71). So cheap artifact features rank 2024-invalid tasks above chance, without using the severity axes.

Largest logistic weights toward invalid: gold-patch changed lines, `match=` in tests, warning asserts, deprecation in the gold patch. Toward valid: reproduction hint in the issue, statement–test identifier overlap.

**This does not certify an accepted benchmark.** Invalid-among-accepted is still high because 68% of the 1,699 are invalid under the 2024 filter. The model is a ranker. The certificate remains a probability sample.

### Coverage (2,000 replicates, n=100)

On the raw 1,699 (true p = 0.683): SRS coverage 0.958, stratified 0.955, hybrid SRS-arm 0.964.

On a constructed ~2% invalid population: SRS coverage 1.00 (conservative), hybrid SRS-arm 1.00, **stratified normal+FPC coverage 0.902**. Do not publish the stratified normal bound at low prevalence. Use SRS / hypergeometric, or fix the stratified interval before using it as a release rule.

## What this does not claim

- It does not certify SWE-bench Verified residual error.
- It does not say Docker oracle/nop ran on 1,699 instances in this repo.
- It does not replace Harbor-Index.
- It does not start synthetic generation.

## Next on the same chain

1. Execute mutation kill-rate on Harbor tasks (hello-world first, then lakehouse hunks).
2. SWE-bench gold-eval on a **small** instance subset if images are affordable; do not block on 1,699.
3. Second gold source (TB 2.1 maintenance IDs), still not TVB until verified.
4. Then the 6-packet human pilot, with complete evidence in the packet.

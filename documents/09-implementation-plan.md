# Implementation plan

This is the plan of record for Part 1. Internal notes sit in the same file so a later agent does not have to reconstruct them from chat.

Stop condition for *this* checkout: packets ready, no human labels invented.

## Phase 0. Literature lock

**Done in this checkout.** Matrix in [03-prior-art.md](03-prior-art.md).

Notes:

- Harbor-Index (6,627 → 82) is the novelty challenge. Our paper has to say "statistical certification with coverage," not "automated filtering plus some humans."
- FAQ / Noisy but Valid / PRECISE are the statistical toolkit, aimed at model scores. We retarget them at task invalidity.
- **TVB is unverified.** Do not ingest it. Do not put 431 TVB rows in any table.
- OpenAI 59.4% is 138 o3-fail Verified tasks. 68.3% is 1,699 2024 annotations. 30% is SWE-Bench Pro 731 after targeted review. Never add those percentages as if they were the same estimand.

## Phase 1. Human-ground-truth corpus

**Partial.** SWE-bench 1,699 ensemble rows ingested. Provenance tagged `EXPERT_VERIFIED`. Compact JSONL committed.

Deferred: TB maintenance history, Harbor-Index as external validation, any TVB dump that later appears.

Note: 1,160/1,699 invalid under the 2024 filter is the right Y for "can we recover a conservative discard rule?" It is the wrong Y for "residual error of the 500-task Verified release." We do not have residual labels on all 500. The 138-task 2026 audit is biased toward hard failures.

## Phase 2. Evidence pipeline

**Schema and Harbor static ingest: done.** Oracle/nop/cheat/mutation/fuzz/LLM audit: not run from this repo.

`eval_tasks` already has oracle 1.0 and nop 0.0 on every complete package we queued, in local gitignored `jobs/`. Those rewards are **not** copied here (possible secrets, large traces). Packets say `oracle_pass: None` unless a later attach step reads `jobs/**/reward.txt` with an explicit allowlist.

Note from `eval_tasks`: mutation Q2a is design-only. Cheat coverage is two tasks. `results/` lags `jobs/`. Do not pretend public evidence is complete.

## Phase 3. Risk model

**Not trained.** Circular if we predict `filter_out` from the severities that define it. Needs execution features on a labeled set, or a second gold source.

## Phase 4. Freeze

Before any *final* test population:

- freeze classifier, features, thresholds, sampling procedure, validity definition, analysis

That freeze has not happened. Coverage simulations in this checkout used the 2024 labels as a **known population** to test estimators, which is allowed. They are not the Phase 5 experiment.

## Phase 5. Population experiment

**Not started.** Candidate populations: SWE-bench test (2,294) using 1,699 as a subset with labels already; Harbor adapter pool (6,627) if adapters are runnable; Terminal-Bench 2.0/2.1 (89). Machine filter then probability sample from survivors.

## Phase 6. Human audit

**Packets ready. Audit not started.** Sixteen `eval_tasks` Harbor tasks. Protocol in [08-human-review-protocol.md](08-human-review-protocol.md). One human, small budget, Approach A.

Priority order (internal):

1. `tasks/lakehouse-publish-recovery` (submission, richest evidence story)
2. `experimental/logged-bandit-ope` (family + cheat)
3. `experimental/gold-retry-publisher`
4. `tasks/durable-prefix-ack` (SWE-2 capability fail, Grok pass)
5. `tasks/keydir-merge`, `tasks/late-session-gc`
6. `tasks/shared-limit-si`, `tasks/week-hours` (SWE-2 pass: valid-but-easy)
7. `experimental/catalog-contention-recovery`, `schema-evolution-cdc`
8. `experimental/bootstrap-merge-resume` (known easy)
9. `experimental/lakehouse-stack-incident` (heavy)
10. `experimental/payments-ledger-reconciliation`
11. decoys last: catalog-shift-*, warehouse-drift-closure

## Phase 7. Compare sampling strategies

Estimator coverage on SWE-bench 2024 labels: **ran** at n=50 and n=100, 200 replicates. H2 efficiency (defects found per review) needs a *good* risk model. The FAIL_TO_PASS-severity proxy barely moved discovery (69.4 vs 68.3 invalids at n=100). That is expected and useful: a bad proxy must not be trusted. Matches Berti-Équille's warning.

## Phase 8. Validate the statistics

Same runs as Phase 7. SRS coverage 95.5–97%. Hybrid UCB from the SRS arm is conservative (wider, 96–98.5% coverage). Stratified normal UCB at n=100 was 94.5% on 200 reps. Re-run 2,000 before calling it miscalibrated.

## Phase 9. Benchmark comparison

Table of N, audited n, observed invalid, 95% UCB, human-review cost. Empty until Phase 6 has labels.

## Phase 10. Part 2 (synthetic)

Only after Part 1 certifies existing populations. Then: learn structure → generate → evidence → sample → certify. The generator may be noisy. The accepted set must still satisfy UCB < epsilon.

## Mapping to eval_tasks "1 → 1000"

`eval_tasks` research note 04 wants ~25 families × ~40 instances. Verification is the bottleneck (Q20: residual rate; Q12: 100 dossiers/day). This repo is the certification layer those 1000 instances must pass. We do **not** generate the 1000 here. We make it possible to claim a bound on whatever `eval_tasks` later accepts.

Frontier cost note from `eval_tasks` Q6: ~$80k if every candidate gets Opus×3 + Sol×3. SWE-2 Max as a pre-filter is still an open question (Q1). That cost sits in `eval_tasks`, not in the UCB sample size. The UCB sample is tens to hundreds of *human* reviews, almost independent of N.

## Explicitly out of this checkout

- New synthetic tasks
- Training GBT/logistic on circular features
- Filling packet verdicts
- Publishing a bound on SWE-bench Verified residual error
- Claiming TVB gold
- Copying Harbor job traces into the public tree

# Internal notes

Written 2026-09-11 while standing up this repo from `eval_tasks` plus the locked certification thesis.

## eval_tasks in one page

Public GitHub: `Evan-Kim2028/eval_tasks`. MIT. One TB3 submission (`lakehouse-publish-recovery`): hermetic Docker, seven coupled defects, 18 hidden tests, separate verifier, GLM cheat 17/18 tests with reward still 0.0 then hardening. Experimental tree has 10 full Harbor packages. `tasks/` also has five complete WIP storage/payroll tasks (durable-prefix-ack, keydir-merge, late-session-gc, shared-limit-si, week-hours) plus leftovers that only exist fully under `experimental/`.

Research notes 01–05 (gitignored in that repo) already concluded verification is the bottleneck for 1 → 1000, and that "verified" without a residual rate is a weak claim. Q20 asked for the subsample size. This repo is the answer to Q20, not a new generator.

## What surprised us in the tree

Portfolio text said catalog-contention-recovery and lakehouse-stack-incident were not built out. They are. Packets include them.

Grok 1.0 on several WIP tasks vs SWE-2 Max 1.0 on week-hours and shared-limit-si: those are difficulty failures relative to a frontier bar, not automatic invalidity.

## Annotation file

OpenAI zip has `ensembled_annotations_public.csv` (1,699 unique) and `samples_with_3_annotations_public.csv` (~15k rows, three raters). Line counts on the ensemble CSV lie because notes contain newlines. Always parse as CSV.

filter_out True = 1,160. Matches 68.3%.

## Coverage sim interpretation

Do not tweet "we certified SWE-bench at 68% invalid." We *used* the 2024 labels as a known finite population to see whether our UCB covers. High p makes n=100 look like a prevalence study, not a rare-defect QC study. The rare-defect numbers are in `sample_size_ucb.json`.

## TVB

User plan treated TVB as the negative class. Search could not open OpenReview `QdDcI0Ftvo`. Nearby names are different papers. Leave a hole in the gold table.

## First risk model (same day, second pass)

Cheap artifact features, repo holdout, n_test=150, base rate 0.71 invalid. Logistic AUROC 0.76. `match=` and deprecation in tests/gold patch push toward invalid, reproduction hint toward valid. That matches the 2024 rubric's "narrow tests" story without using the rubric scores as X.

Stratified UCB coverage 0.90 at 2% prevalence / 2000 reps. Do not ship that bound.

## Harbor-Index

Paper arXiv 2609.04298, site, hub dataset `harbor-index/harbor-index-1.0`. GitHub README still says 80 in one sentence; site and paper say 82. Funnel numbers 6627 / 1311 / 307 / 100 / 82 confirmed.

## Risk of leaking eval_tasks

Packets embed a 400-character instruction preview. eval_tasks is already on GitHub. Solutions are not copied. Planted fail-* tasks were excluded from the human queue so we do not ask a person to "review" a task that is designed to fail static checks.

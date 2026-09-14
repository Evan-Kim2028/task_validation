# Taste conditional on validity (task 24)

Code: `src/task_validation/evidence/conditional_taste.py` (dispatch `python -m task_validation.evidence.conditional_taste`). Tests: `tests/test_conditional_taste.py`. Inputs: `data/gold/swe_rater_targets.jsonl` (1,699 annotated SWE-bench instances, three human raters, 2024 protocol), `data/raw/aba/swe_bench_verified/static_audits/` (500 audit filenames, `<instance_id>__<hash>.json`), `data/gold/swe_verified_features.jsonl` (24 cheap artifact features), `data/gold/swe_irt.json` (p_i, a_i, b_i), `data/gold/footprint.jsonl` (shared non-LLM footprint), `data/gold/tb21_census_verdicts.jsonl` (89 verifier verdicts), `data/gold/tb21_maintenance.jsonl` (28 maintainer repairs), `data/gold/harbor_funnel_traj_eval.json` and `data/gold/harbor_funnel_within_benchmark.json` (funnel evals, docs 52, 54). Outputs: `data/gold/swe_verified500_ids.json`, `data/gold/swe_taste_labels.jsonl`, `data/gold/conditional_taste_eval.json`, `data/gold/conditional_taste_oof/*.oof.jsonl`. All external labels are eval-only (doc 43); no model score enters a bound.

The result: Verified-500 membership is nearly determined by validity, and the residual taste signal that survives conditioning is weak inside SWE-bench (grouped OOF AUROC 0.590 on cheap features, 0.624 with IRT added, n = 935 majority-valid tasks), at chance on Terminal-Bench 2.1, and unmeasurable per-benchmark on Harbor-Index. Across populations the kept sets do not overlap: pairwise held-out separability on the shared footprint features runs 0.94 to 1.00, so a taste model fitted on one population's kept tasks cannot be expected to score another's. Quality does not transfer; it has to be measured inside each population, among tasks already certified valid.

## taste_kept is defined only on valid tasks

`data/gold/swe_taste_labels.jsonl` carries one row per annotated instance: `task_id`, `repository`, the three 2024 validity labels with protocol and grade, `in_verified500`, and `taste_kept`. `taste_kept` equals Verified-500 membership on majority-valid rows and is null on majority-invalid rows. A kept label on a broken task would conflate "not broken" with "worth keeping"; the null keeps the estimands separate (Evan's design, 2026-09-14).

The Verified-500 membership list itself was rebuilt from the static-audit filenames: 500 files parsed, 500 unique ids, zero malformed names, identical to the ABA id set already in `labels_2026.jsonl`, and all 500 inside the 1,699 annotated rows (`data/gold/swe_verified500_ids.json`).

## Validity x Verified-500: the selection was mostly a validity filter

Cross-tab of the three 2024 validity protocols against Verified-500 membership, n = 1,699 annotated SWE-bench tasks (`conditional_taste_eval.json`, `swe.validity_x_verified500`).

Majority protocol (the conditioning used below):

| | in Verified-500 | not | total |
| --- | ---: | ---: | ---: |
| majority-valid | 500 | 435 | 935 |
| majority-invalid | 0 | 764 | 764 |

Conservative protocol:

| | in Verified-500 | not | total |
| --- | ---: | ---: | ---: |
| conservative-valid | 500 | 39 | 539 |
| conservative-invalid | 0 | 1,160 | 1,160 |

Unanimous protocol:

| | in Verified-500 | not | total |
| --- | ---: | ---: | ---: |
| unanimous-valid | 500 | 809 | 1,309 |
| unanimous-invalid | 0 | 390 | 390 |

Base rates, n = 1,699: kept overall 500/1,699 = 0.294. Kept given majority-valid 500/935 = 0.535. Kept given conservative-valid 500/539 = 0.928. Kept given unanimous-valid 500/1,309 = 0.382. Under every protocol, every kept task is valid (500/500).

Two readings follow. Under the strict 2024 conservative screen, the Verified-500 selection is a validity filter plus almost nothing: 93 percent of conservative-valid tasks were kept and no invalid task was kept. Under the majority protocol a real taste component remains, since 435 of 935 valid tasks were dropped. The conditional model below measures whether that residual choice is visible in cheap features.

## SWE-bench: conditional taste model

Fit on the 935 majority-valid tasks, y = `taste_kept`, grouped out-of-fold by repository (leave-one-repo-out, 12 folds), doc 40 model class (median imputation, missingness indicators, standardized matrix, class-weighted L2 logistic; `conditional_taste_eval.json`, `swe.evals`).

| Feature set | n | kept | OOF AUROC | 95% CI |
| --- | ---: | ---: | ---: | --- |
| cheap 24 artifact features | 935 | 500 | 0.590 | 0.553-0.629 |
| cheap 24 + IRT p_i, a_i, b_i | 935 | 500 | 0.624 | 0.586-0.662 |

The signal is above chance but weak. Compare validity on the same feature class and pool: grouped static features rank majority-invalid at about AUROC 0.70 on the annotated 1,699 (doc 14). Brokenness is easier to see than taste.

Risk-coverage tail, doc 14 format. Score is p(kept); the lowest-risk tail is the top of the ranking. Kept rate within each retained slice (`swe.evals.*.risk_tail`):

| Retain lowest-risk | n | kept rate (cheap 24) | kept rate (+IRT) |
| --- | ---: | ---: | ---: |
| 5% | 47 | 0.660 (31/47) | 0.638 (30/47) |
| 10% | 94 | 0.681 (64/94) | 0.755 (71/94) |
| 20% | 187 | 0.642 (120/187) | 0.711 (133/187) |
| 100% | 935 | 0.535 (500/935) | 0.535 (500/935) |

With IRT the top decile reaches 0.755 kept against a 0.535 base rate: enrichment exists, and 29 percent of the top decile is still tasks the selectors dropped. There is no clean tail.

## Within-repository: group identity earns some of the pooled number

Every comparison pair restricted to one repository, pooled-trained OOF scores (`swe.evals.*.within_group`).

| Quantity | cheap 24 | + IRT |
| --- | ---: | ---: |
| Same-repository pairs, concordance | 0.573 (50,219 pairs, CI 0.527-0.617) | 0.604 (CI 0.561-0.651) |
| Cross-repository pairs, concordance | 0.595 (167,281 pairs) | 0.630 |
| Positives-weighted mean per-repo AUROC | 0.609 (CI 0.574-0.645) | 0.634 (CI 0.599-0.669) |

Nine repositories qualify (at least 5 kept and 5 dropped among valid tasks). Per-repository AUROC (+IRT set; cheap-only in the artifact):

| Repository | valid | kept | AUROC | 95% CI |
| --- | ---: | ---: | ---: | --- |
| astropy | 33 | 22 | 0.632 | 0.413-0.815 |
| django | 399 | 231 | 0.584 | 0.534-0.644 |
| matplotlib | 77 | 34 | 0.712 | 0.591-0.841 |
| psf | 17 | 8 | 0.667 | 0.333-0.955 |
| pydata | 44 | 22 | 0.607 | 0.420-0.760 |
| pytest-dev | 46 | 19 | 0.700 | 0.542-0.862 |
| scikit-learn | 63 | 32 | 0.725 | 0.583-0.868 |
| sphinx-doc | 84 | 44 | 0.719 | 0.603-0.814 |
| sympy | 153 | 75 | 0.649 | 0.556-0.729 |

Within-repository ranking is mildly better than the pooled number suggests once group identity is stripped out and per-repository AUROCs are positive-weighted (0.609 vs the 0.573 all-pairs concordance), but no repository's interval leaves 0.5 by much and several straddle it. The honest reading: a weak, real, within-repository taste signal, not a transferable one.

## Other populations: small n or a derived label, never both clean

| Population | Validity signal | Keep decision | n conditional | kept | Powered to fit? |
| --- | --- | --- | ---: | ---: | --- |
| SWE-bench | 2024 majority, 3 human raters | Verified-500 membership | 935 | 500 | yes |
| Terminal-Bench 2.1 | census verifier verdicts, 89 tasks | 28 maintainer repairs | 84 | 26 | marginal; interval straddles chance |
| Harbor-Index funnel | stage-1 screen (difficulty, not validity) | survived_2_to_4, derived | 1,331 | 67 | pooled fit only; max 8 kept per benchmark |
| SWE-bench Pro | none inside the dump | none measurable: only the 731 published tasks are present | — | — | no keep decision exists in the data |

Terminal-Bench 2.1. The 89-task census flags 5 invalid (grade A, machine verifier, `tb21_census_verdicts.jsonl`). The 28-entry maintenance list marks tasks maintainers repaired rather than dropped between 2.0 and 2.1 (`tb21_maintenance.jsonl`). Two repaired tasks are census-invalid (build-pov-ray, mcmc-sampling-stan) and leave the conditional set: 26 kept of 84 valid, base rate 0.310. Stratified 5-fold OOF on the 11 shared footprint features gives AUROC 0.515, 95% CI 0.383-0.644 (`conditional_taste_eval.json`, `tb21`). At chance. The lowest-risk decile retains 8 tasks of which 2 are kept. The catalog-retention variant is degenerate: nothing was dropped between 2.0 and 2.1, so kept-among-valid is 84/84.

Harbor-Index. The funnel offers no validity label inside its 1,331 reconstructed stage-1 survivors; stage 1 is a frontier-solve-rate screen, not a validity verdict (doc 52). Conditioned on that screen, kept = survived_2_to_4, n = 67 of 1,331 (5.0 percent). The stored evals stand: leave-one-benchmark-out AUROC 0.711 (0.650-0.771) on execution features, leave-one-family-out 0.698 (0.634-0.766), and within-benchmark concordance 0.685 over 2,843 same-benchmark pairs with positives-weighted mean 0.602 (doc 54, `harbor_funnel_within_benchmark.json`). No benchmark holds more than 8 kept tasks, so no per-population model can be fitted and validated honestly there.

## Kept sets do not overlap across populations

Each pair of shipped kept sets (SWE Verified-500 n = 500, TB 2.1 catalog n = 89, Harbor-Index published n = 82, SWE-bench Pro n = 731) is fed to the doc 40 classifier on the 11 shared footprint features, seeded stratified 5-fold OOF, missingness indicators off (`conditional_taste_eval.json`, `overlap`).

| Held-out AUROC, positive = row | harbor_index | swe_pro | swe_verified | tb21 |
| --- | ---: | ---: | ---: | ---: |
| harbor_index | — | 0.974 | 0.989 | 0.941 |
| swe_pro | | — | 0.995 | 0.993 |
| swe_verified | | | — | 1.000 |

Every lower 95% bound sits at or above 0.898. Mean feature-wise standardized differences run 0.56 to 1.28 (`overlap.pairs.*.mean_abs_std_diff`). Even the two SWE-origin kept sets separate at 0.995: different construction pipelines leave different footprints. High separability means the kept sets occupy disjoint regions of the shared feature space, and a taste model fitted on one population's kept tasks has no basis for scoring another's. This is the cross-population version of the doc 54 stop result.

## What follows for the intake specification (doc 50)

Three consequences. First, conditioning is mandatory, and this dataset now carries the label that enforces it: `taste_kept` is null on invalid tasks, so a keep decision can never silently reward "not broken". Second, the keep decision needs a human label per population. The Verified-500 selection is mostly a validity filter, the residual taste signal ranks weakly (0.59-0.62 grouped OOF) with no clean tail, and the kept sets of the four populations share almost no feature-space region, so no fitted taste model can substitute for per-population measurement. Third, stage 8 stays as doc 50 wrote it: footprint features may order a review queue inside a population, and the funnel labels remain provenance context, but every published bound still rests on a fresh human sample drawn inside the target population after the validity gate.

## Method

- Verified-500 ids: parsed from `data/raw/aba/swe_bench_verified/static_audits/` filenames, `<instance_id>__<hexhash>.json`, split on the final separator; 500 files, 500 unique ids (`parse_verified500_ids`, `swe_verified500_ids.json`).
- Labels: `taste_kept` = Verified-500 membership restricted to `majority_invalid == 0`; every label carries protocol, grade, adjudicator and eval-only flag (`build_swe_taste_labels`, `swe_taste_labels.jsonl`).
- Model class: doc 40. Median imputation, missingness indicators, standardized design matrix, class-weighted L2 logistic (`design_matrix`, `fit_logit` in footprint.py; the parameterized transform applies log1p to the same count features doc 40 transforms).
- Evaluation: leave-one-repository-out OOF for SWE; seeded stratified 5-fold for TB21 and for every kept-set pair; AUROC intervals by 400-replicate bootstrap, seed 20260914; risk tail = kept rate in the top-scoring 5/10/20 percent; within-repository eval restricts pairs to one repository and averages per-repo AUROC weighted by positives (`within_group_eval`, reusing `within_group_concordance` from harbor_funnel.py).
- Overlap: held-out AUROC distinguishing population A kept from population B kept, plus mean absolute standardized feature difference on the model scale.
- Harbor numbers are read from the stored doc 52/54 eval artifacts, not refitted.

## Limits

- Verified-500 membership is a published list, grade A, but the selectors' criteria are not observable. "Kept" mixes taste with whatever else the selection optimized for (difficulty spread, repository spread, decontamination). The label is eval-only.
- The keep decision on TB21 is exercised only on tasks that were once defective: a never-broken task cannot be "repaired". The 26/84 conditional label therefore entangles taste with defect incidence, and n = 84 with 26 positives is marginal power regardless.
- Harbor-Index has no validity label inside the stage-1 survivors and `survived_2_to_4` is derived (grade A conditioned on a grade-B reconstruction; 14 matched survivors do not pass the screen, doc 52). The funnel rows measure a difficulty-conditioned keep decision, not a validity-conditioned one.
- Within-repository AUROCs are computed on pooled-trained OOF scores; scores are honest, but per-repository fitted models are not validated here.
- The overlap result is about footprint space. Two kept sets could differ in footprint and still agree on the trait a human would call taste; the classifier proves the kept sets do not overlap on these features, which is the claim, and nothing more.
- SWE-bench Pro appears in the overlap matrix as a kept set but not in the conditional analysis: the dump holds only its 731 published tasks, so no validity-conditional keep label exists for it.

## RESULT

- Label: `data/gold/swe_taste_labels.jsonl`, 1,699 rows; `taste_kept` defined on the 935 majority-valid tasks only, 500 kept, base rate 0.535 (`conditional_taste_eval.json`).
- 2x2, majority protocol: 500 valid-kept, 435 valid-dropped, 0 invalid-kept, 764 invalid-dropped. Every Verified-500 task is valid under all three 2024 protocols; under the conservative protocol 92.8 percent of valid tasks are kept, so the selection was mostly a validity filter with a real but secondary taste component.
- Conditional taste, SWE: grouped OOF AUROC 0.590 (0.553-0.629) on the cheap 24, 0.624 (0.586-0.662) with IRT added, n = 935. Above chance, far below the 0.70 the same features give for validity (doc 14).
- Risk tail: with IRT, kept rate 0.755 in the lowest-risk decile vs 0.535 base; enrichment without a clean tail.
- Within-repository: positives-weighted mean AUROC 0.609 (cheap) and 0.634 (+IRT) over 9 qualified repositories; all same-repo-pair concordance 0.573 / 0.604; cross-repo pairs earn 0.595 / 0.630.
- TB21: 26 kept of 84 census-valid, AUROC 0.515 (0.383-0.644). At chance. Harbor-Index: 67 kept of 1,331, pooled transfer 0.711 LOBO stands but no benchmark exceeds 8 kept, so no per-population fit is possible.
- Overlap: pairwise kept-set separability 0.941-1.000, all lower bounds >= 0.898, mean |d| 0.56-1.28. Kept sets occupy disjoint footprint regions.
- Intake spec: condition taste labels on validity, measure taste inside each population with human labels, keep model scores out of bounds (doc 43), keep stage 8 provenance-only.

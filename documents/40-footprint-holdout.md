# Non-LLM validity footprint, held-out

Code: `src/task_validation/evidence/footprint.py`. Rows: `data/gold/footprint.jsonl` (3,117). Lab: `data/gold/footprint.holdout.json`. No model API. Judge scores and human severity are not features. Every AUROC, Se/Sp, and coverage number below is from a population or repository the calibration did not see. Shared task IDs (SWE vs Verified-500) were dropped from train.

Frozen before any cell (F1): the transfer UCB covers the held-out rate in at least 4 of 5 populations for the verifier construct, and in at least 3 of 5 for the spec construct. The five are swe, swe_verified, swe_pro, tb21, harbor_index. **FAIL** (verifier 2/5, spec 2/5).

## Footprint

Per task: execution gate (`reference_pass`, `nop_reject`, `determinism`, `environment_failure`; LLM-judge verifiers left null) + static artifacts (instruction length, test file count, assertion count, literal pins in tests not in the instruction, solution size, resource limits, network mode, judge-verifier flag, plus the existing SWE cheap extractors) + solve-rate band where public submissions exist (SWE only; otherwise null).

| population | n | spec Y | verifier Y | execution observed |
| --- | ---: | --- | --- | ---: |
| swe | 1699 | 2024 conservative (p=0.683) | none (SRS verdicts are the gate) | 120 |
| swe_verified | 500 | ABA major (p=0.078) | ABA major, verifier or mixed | 49 |
| swe_pro | 731 | ABA major (p=0.331) | OpenCompass narrow/broad tests | 0 |
| tb21 | 89 | ABA major (p=0.180) | 2.1 solution/test/env repair (22) | 89 |
| harbor_index | 82 | accepted set, p=0 | accepted set, p=0 | 66 (not judge) |
| eval_tasks | 16 | none | our diagnosis (2 INVALID) | 16 |

## Instruments

Execution gate vs independent verifier gold. Exact binomial 95% CI. eval_tasks is circular (diagnosis used the same reference probe) and is not in F1.

| pop | n | n_pos | sens | spec |
| --- | ---: | ---: | ---: | ---: |
| swe_verified | 49 | 3 | 0.33 (0.01, 0.91) | 1.00 (0.92, 1.00) |
| tb21 (post-fix) | 89 | 22 | 0.09 (0.01, 0.29) | 0.96 (0.87, 0.99) |
| harbor_index | 66 | 0 | n/a | 0.89 (0.79, 0.96) |
| eval_tasks | 16 | 2 | 1.00 (circular) | 1.00 (circular) |
| swe, swe_pro |  |  | no independent gold / no execution |  |

Post-fix TB mostly passes, so the gate does not recover the repair class. High specificity, low sensitivity: it is a residual-fail detector, not a ranking of historical repairs.

Static logistic for spec invalidity (train on one population, test on the others). Diagonal omitted. Harbor has no spec positives (AUROC undefined). Verified cannot train for SWE: the 500 IDs sit inside the 1,699.

| train \ test | swe | verified | pro | tb21 |
| --- | ---: | ---: | ---: | ---: |
| swe |  | 0.68 (0.59, 0.77) | 0.67 (0.63, 0.71) | 0.58 (0.44, 0.73) |
| verified | (overlap) |  | 0.59 (0.55, 0.63) | 0.51 (0.34, 0.69) |
| pro | 0.69 (0.67, 0.72) | 0.66 (0.57, 0.75) |  | 0.48 (0.31, 0.64) |
| tb21 | 0.60 (0.57, 0.63) | 0.60 (0.49, 0.69) | 0.59 (0.54, 0.63) |  |

Within-SWE holdout by repository (2024 conservative): AUROC **0.72 (0.68, 0.76)**, n_train=985, n_test=714. Same neighborhood as the grouped-OOF cheap score (0.70). Top coefficients: patch/solution size, n_fail_to_pass, identifier count.

Combined score (static logit + execution flags + solve-rate where present), same matrix. Material change is only SWE train -> Verified test: **0.76 (0.70, 0.82)**, which is the public solve rate on that slice (doc 33/38), not a new static signal. Other cells match static to two decimals because Pro/TB/Harbor have no solve rate and almost no execution on the spec Y.

Verifier LOPO AUROC sits at 0.46-0.61 wherever it is defined. Static features do not rank verifier invalidity.

## Transfer bound (F1)

Calibrate Youden threshold and Se/Sp of the combined instrument on the other four populations (IDs in the holdout removed), apply Rogan-Gladen bootstrap UCB to the holdout's instrument prevalence, ask whether that UCB covers the holdout's human/repair rate. Compare width to an SRS of n=100 (or N if smaller) that happened to see k ~ pN invalids.

| construct | pop | true p | RG UCB | RG width | SRS n=100 UCB | SRS width | covers |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| verifier | swe | n/a |  |  |  |  | no (no Y) |
| verifier | verified | 0.044 | 0.00 | -0.04 | 0.086 | 0.046 | no |
| verifier | pro | 0.153 | 0.87 | 0.72 | 0.218 | 0.068 | yes (vacuous-wide) |
| verifier | tb21 | 0.247 | 0.00 | -0.25 | 0.334 | 0.087 | no |
| verifier | harbor | 0.000 | 1.00 | 1.00 | 0.036 | 0.036 | yes (vacuous) |
| spec | swe | 0.683 | 0.045 | -0.64 | 0.755 | 0.075 | no |
| spec | verified | 0.078 | 1.00 | 0.92 | 0.134 | 0.054 | yes (vacuous-wide) |
| spec | pro | 0.331 | 0.039 | -0.29 | 0.410 | 0.080 | no |
| spec | tb21 | 0.180 | 0.00 | -0.18 | 0.260 | 0.080 | no |
| spec | harbor | 0.000 | 0.00 | 0.00 | 0.036 | 0.036 | yes (p=0) |

**F1 FAIL.** Two of the four "covers" cells are UCB=1. Negative width means the point sits above the UCB: the instrument, calibrated elsewhere, is not measuring the holdout's construct. SWE spec p=0.68 vs a bound of 0.045 is the cleanest illustration. An SRS of 100 humans is narrower than every usable RG cell here and is the only bound that knows the holdout's label.

## Curated vs raw

Positives: Harbor-Index 82 + TB 2.1 89 + Verified 500. Negatives: 200 SWE-smith + 200 SWE-rebench (seeded HF samples, patches and tests; smith has no separate test_patch, tests taken from the patch). Shared static features only; missingness flags were not used (they encode layout, which is source identity).

| held out | AUROC (95%) |
| --- | ---: |
| Harbor-Index | 0.71 (0.66, 0.77) |
| TB 2.1 | 0.75 (0.70, 0.80) |
| SWE Verified | 0.57 (0.53, 0.61) |
| SWE-smith | 0.61 (0.57, 0.65) |
| SWE-rebench | 0.41 (0.37, 0.46) |

Top |coef| across folds: test_file_count, has_reproduction_hint, solution_size, has_code_fence, identifier count, has_http_url.

This is distribution membership (Harbor/TB look less like generated SWE than Verified does; held-out SWE-rebench scores on the curated side of a smith-trained boundary). It is not expert taste. Closing that gap without human ratings would need an independent taste instrument (frontier-agent discrimination, construction quotas) whose error is itself bounded on a fresh human sample of the population being shipped.

## What this allows on a new population

Not a certificate. Static transfer AUROC is 0.58-0.69 on spec and chance on verifier. The execution gate is a high-spec residual check where we can run it, not a portable invalidity rate. Rogan-Gladen from other benches undercovers or goes vacuous. Doc 23 section 6 still stands: cheap evidence on every task, then a probability sample of the accepted pool. The footprint is the cheap layer and the prior. The bound is still humans on that pool.

# Consolidated results

This document consolidates every measured result of the task-validity project. The estimand is the share of materially invalid units in a frozen finite pool under the `verifier_invalid.fresh_environment.execution` label protocol: a unit is invalid when its packaged verifier fails the execution assay (reference fails, nop accepted, or no deterministic separation) in a fresh pinned environment. The release rule is a one-sided hypergeometric upper confidence bound at 95 percent against threshold epsilon (doc 32). Every number below cites the artifact that produced it.

## What was certified and what was not

Two pools released at epsilon 5 percent. The completed prefix of the SWE-bench SRS-300 draw bounded execution-verifier invalidity at 4.65 percent (`data/gold/swe_srs300.certificate.json`), and the SETA-Env pool bounded it at 2.32 percent (`data/gold/gen_gate_seta.certificate.json`). Four certificates rejected: Terminal-Bench 2.1 at a census rate of 5.62 percent, the RST generator pool at 6.63 percent restricted and 9.53 percent conservative, and the SWE SRS-100 draw at 6.06 percent. TMax-15K is PENDING. No specification-invalidity bound exists on any pool except SWE-bench and TB 2.1, where human labels measured it. No taste measurement exists as a gate anywhere.

The estimator itself was verified before use. In 5,000-replicate coverage experiments at true invalidity at or below 5 percent, the SRS-hypergeometric bound covered 97.2 to 100 percent of the time; the stratified-normal bound covered 46.9 to 90.6 percent and is not a release rule (`data/gold/coverage_lab_r5000.summary.json`).

## Certification table

One row per population. Diagnostic rows are censuses or targeted samples without an inferential release bound.

| Population | Kind | Estimand population | N | n | Adjudicated | Invalid | Point est. | 95% UCB | Decision at eps 5% | Artifact |
|---|---|---|---|---|---|---|---|---|---|---|
| TB 2.0 maintained pairs | diagnostic census | diffable pre/post pairs | 27 | 27 | 27 | 9 | 33.3% | n/a | diagnostic | `tb21_pairs.summary.json`, doc 25 |
| eval_tasks packages | diagnostic census | complete local packages | 16 | 16 | 16 | 2 | 12.5% | n/a | diagnostic | docs 20/21 |
| RST, conservative | certificate | full frozen manifest, unadjudicated counted invalid | 37,479 | 200 | 195 | 12 | 6.00% | 9.53% | reject | `gen_gate_rst.conservative.certificate.json` |
| TB 2.1 census | certificate (census) | all tasks, full enumeration | 89 | 89 | 89 | 5 | 5.62% | 5.62% | reject | `tb21_census.certificate.json` |
| SWE frozen 2x2 pilot | diagnostic sample | stratified 20-unit draw | 1,699 | 20 | 20 | 1 | 5.0% | n/a | diagnostic | `swe_2x2_exec.summary.json` |
| Harbor-Index executable stratum | diagnostic census | tasks with reference-oracle structure, 53 of 82 | 82 | 53 | 53 | 2 | 3.77% | n/a | diagnostic | `harbor_index_control.summary.json`, doc 28 |
| RST, restricted | certificate | adjudicated subset of frozen manifest | 37,479 | 195 | 195 | 7 | 3.59% | 6.63% | reject | `gen_gate_rst.certificate.json` |
| SWE SRS-300 prefix | certificate | completed prefix, 190 of frozen 300 draw | 1,699 | 190 | 190 | 4 | 2.11% | 4.65% | release | `swe_srs300.certificate.json` |
| SWE SRS-100 | certificate | SWE-bench test pool | 1,699 | 100 | 100 | 2 | 2.00% | 6.06% | reject | `swe_srs100.certificate.json` |
| SETA-Env | certificate | frozen manifest | 4,569 | 200 | 200 | 1 | 0.50% | 2.32% | release | `gen_gate_seta.certificate.json` |
| TB 2.1 SRS-30 check | certificate | same 89-task pool vs known census | 89 | 30 | 30 | 0 | 0.0% | 7.87% | covers census | `tb21_srs30.certificate.json` |
| TMax-15K | certificate, one-sided | accepts-an-empty-solution share of frozen manifest | 8,047 | 200 | 1 | PENDING | PENDING | PENDING | PENDING | `gen_gate_tmax.certificate.json` |

Three qualifications fix the scope of these rows.

The SWE SRS-300 certificate covers the completed prefix only. The frozen draw was 300 units; 297 executed both treatments; 3 matplotlib units returned no report; 4 further units beyond the 190-unit prefix were flagged (`data/gold/swe_srs300.certificate.json`, doc 47). A bound over all 297 executed units would also be 4.65 percent, but the certificate as issued covers 190.

RST reports two bounds over the same 200-unit draw. The restricted bound covers the 195 adjudicated units and excludes 5 unadjudicated units. The conservative bound counts those 5 as invalid, giving 12 of 200 and 9.53 percent (`data/gold/gen_gate_rst.certificate.json`, `data/gold/gen_gate_rst.conservative.certificate.json`, doc 53).

Harbor-Index is stratified. The 2 invalid units come from the 53-task executable stratum with reference oracles. The 13 no-reference tasks received one-sided nop probes only, with 0 false accepts in 82 nop trials. The 16 judge-configured tasks have no machine certificate (`data/gold/harbor_index_control.summary.json`, doc 28). The TMax draw is entirely no-reference: all 200 frozen units carry `has_reference: false`, so its bound is the one-sided nop probe (`data/gold/gen_gate_tmax_manifest.json`).

## Epsilon sensitivity

Decisions at epsilon 1, 2, 5, and 10 percent from the existing bounds. Release requires the upper bound below epsilon.

| Population | 95% UCB | eps 1% | eps 2% | eps 5% | eps 10% |
|---|---|---|---|---|---|
| RST, conservative | 9.53% | reject | reject | reject | release |
| TB 2.1 SRS-30 check | 7.87% | reject | reject | reject | release |
| RST, restricted | 6.63% | reject | reject | reject | release |
| SWE SRS-100 | 6.06% | reject | reject | reject | release |
| TB 2.1 census | 5.62% | reject | reject | reject | release |
| SWE SRS-300 prefix | 4.65% | reject | reject | release | release |
| SETA-Env | 2.32% | reject | reject | release | release |
| TMax-15K | PENDING | PENDING | PENDING | PENDING | PENDING |

The five rejected pools sit between 5.6 and 9.5 percent, so all of them would release at epsilon 10 percent and none at 2 percent. The two released pools sit between 2.3 and 4.7 percent, so both would reject at epsilon 2 percent.

## Generated pools versus curated pools

The generated pools measured no worse on execution-verifier invalidity than the human-curated pools. RST bounded its adjudicated share at 3.59 percent and SETA-Env at 0.50 percent; TB 2.1 measured 5.62 percent, the Harbor-Index executable stratum 3.77 percent, and the SWE-bench prefix 2.11 percent.

This is an observation, not a causal claim. The confounds:

- One defect class is measured. The bound covers execution-verifier invalidity, not specification invalidity or taste.
- The pools differ in construction order. The generators emit reference solutions first, which produces oracle-passing tasks by construction and targets exactly the measured defect class.
- RST was bounded as a raw manifest before any quality filter. Curated pools passed maintainer review.
- Environments, image ages, and tooling stacks differ across pools.
- The judge-configured and no-reference strata of every pool remain unmeasured by the two-sided assay.

## Negative results

Each result is scoped to the populations evaluated.

**0.41 and 0.42.** Static specification features do not separate valid from invalid tasks. On 150 human-adjudicated Harbor tasks, change-causality features scored AUROC 0.41 and contract-provenance features 0.42 (`data/gold/causal_ablation.summary.json`, docs 33/34). The strongest specification model, grouped out-of-fold AUROC 0.70 on 1,699 SWE tasks, still left 34 percent conservative-invalid inside its lowest-risk 5 percent (`data/gold/oof_openai_2024_conservative.json`, doc 23).

**1.11x.** Model-assisted bounds do not beat simple random sampling under the tested conditions. Prediction-powered inference gave an effective-sample-size gain of about 1.11x at judge AUROC 0.70 on the dirty full set, and its normal bound undercovered on thin populations (`data/gold/ppi_lab.json`, `data/gold/coverage_n100_p02.json`, doc 30). The judge-calibrated bound at judge AUROC 0.807 never beat the SRS Clopper-Pearson bound (`data/gold/judge_bound_lab.json`, doc 33).

**8 of 10.** Cross-population calibration transfer fails. Rogan-Gladen transfer undercovered or went vacuous in 8 of 10 holdout cells, and the transfer predicate failed on 2 of 5 verifier and 2 of 5 specification transfers (`data/gold/footprint.holdout.json`, doc 40). SRS remains the valid release baseline on a new pool.

**0.612.** Funnel transfer fails family-held-out. The full trajectory feature family scored AUROC 0.612 on leave-one-family-out evaluation, below the 0.65 stop line; the signal concentrates in the stage-1 solve-rate scalar, whose leave-one-benchmark-out AUROC is 0.711 (`data/gold/harbor_funnel_traj_eval.json`, doc 54). Within-benchmark concordance measured 0.685 over 2,843 same-benchmark pairs (0.589 to 0.765), concentrated in one benchmark, with at most 8 kept tasks per benchmark (`data/gold/harbor_funnel_within_benchmark.json`, doc 52). The funnel signal does not travel between task populations.

**0.590, 0.624, 0.515.** Conditional taste is weakly predictable where validity holds and at chance where it does not. On the 935 majority-valid SWE tasks, grouped out-of-fold AUROC measured 0.590 with cheap features and 0.624 with IRT added; on the 84 census-valid TB 2.1 tasks it measured 0.515 (0.383 to 0.644) (`data/gold/conditional_taste_eval.json`, doc 59). The Verified-500 selection behaves mostly as a validity filter: all 500 kept tasks are majority-valid, and 92.8 percent of conservative-valid tasks are kept.

**0.941 to 1.000.** Kept sets are trivially separable from each other. Pairwise held-out AUROC between the four kept sets ran 0.941 to 1.000 with lower confidence bounds at or above 0.898 and mean standardized feature differences of 0.56 to 1.28 (`data/gold/conditional_taste_eval.json`, doc 59). The selections occupy different footprint regions; nothing here measures whether a human would agree with any of them.

## Data contribution

The Harbor-Adapter dump is the largest recovered artifact: 793,698 trial rows yielded 768,956 in-scope reward-bearing rows across 60 benchmarks and 8,468 task pairs, produced by 16 models and 6 agent harnesses in 492 shards (doc 44).

From it the project rebuilt: the stage-1 funnel labels for all 6,627 candidates, reproducing the published survivor count within 1.5 percent (1,331 reconstructed versus 1,311 published); kept labels for every candidate rather than the 82 published tasks; 81 of 82 published tasks matched to dump aggregates; the benchmark topology mapper at 62 nodes and 88 edges; and the demonstration that the hidden-requirement feature family is empty by construction, since the dump carries no specification text (docs 44, 52, 54; `data/gold/harbor_funnel_stage1.summary.json`, `data/gold/harbor_funnel_labels.jsonl`, `data/gold/harbor_funnel_within_benchmark.json`).

## Lot-001 end to end

Lot-001 is a 20-task generated lot (`ope-01` to `ope-20`, generator `estimator-pair`, skeleton `experimental/logged-bandit-ope`, 214 of 234 draws rejected at generation) run through the full intake pipeline (doc 50, `eval_tasks/lots/lot-001/`).

| Gate | Result | Artifact |
|---|---|---|
| A, execution | 20 of 20 pass: oracle rewards [1,1], nop [0,0], deterministic across reruns, 3,040 s wall | `eval_tasks/lots/lot-001/gate_a.summary.json` |
| B, decontamination | 0 of 20 flagged after adjudication | `eval_tasks/lots/lot-001/gate_b.jsonl`, `gate_b_adjudication.json` |
| C, difficulty | 11 of 20 inside the [0.10, 0.70] solve-rate band | `eval_tasks/lots/lot-001/runs/*/manifest.json`, `data/gold/typicality_lot001.jsonl` |

Gate B initially flagged all 20 tasks against `tb4/cargo-flight-dispatch` on two pytest import-header 13-grams. Family-level adjudication ruled the matches scaffold false positives; with import-header grams masked, no task flags (doc 49).

Gate C ran 3 solver trials per task under devin/swe-2-max, completed 2026-09-14. Per-task solve rates over the scheduled trials: 0 of 3 for 4 tasks, 1 of 3 for 4, 2 of 3 for 7, and 3 of 3 for 5, leaving 11 of 20 inside the band, 4 below, and 5 above. 17 of 60 trials recorded a rate-limit exception, including every trial of the four 0-of-3 tasks, so the below-band calls carry an under-measurement caveat.

The typicality picture places the lot outside every reference cloud: pooled median 0.067 (range 0.024 to 0.207) against kept-region median 0.506, with per-source best match to Gaia at 1.0 on source features alone (`data/gold/typicality_lot001.jsonl`, `data/gold/typicality_kept_region.json`, doc 60).

## Limits

Every limitation of the evidence base, in one place.

- The nop probe is one-sided. For the 13 no-reference Harbor tasks and all 200 TMax units it detects only accepts-an-empty-solution invalidity and misses every other defect class.
- The assay has false negatives by construction. A verifier can pass the execution assay and still be invalid on specification grounds. Specification invalidity was measured only where human labels exist: 1,699 SWE tasks and 89 TB 2.1 tasks.
- The 16 judge-configured Harbor-Index tasks have no machine certificate. Judge-swap evidence is grade B and enters no bound.
- Verdicts are environment-relative. A task invalid under one image may be valid under another; certificates transfer only with the pinned environment.
- Two certificates are partial. The SWE bound covers the 190-unit completed prefix of the frozen 300-unit draw, and the RST restricted bound covers 195 of 200 drawn units.
- The per-population taste hypothesis is untested. No benchmark retains more than 8 kept tasks, so whether a per-benchmark taste model can beat the pooled 0.59 to 0.62 range is unknown.
- No human ratings of kept sets exist. The taste numbers are feature associations with maintainer selections, not judgments of what a user wants.
- No downstream training result exists. Nothing here shows that kept data improves a trained model.
- Gate C contamination. 17 of 60 Lot-001 trials recorded rate-limit exceptions, including all trials of the four 0-of-3 tasks.
- The trajectory evaluation has 82 positives, and the Monte-Carlo checks ran on TB 2.1 only.
- Funnel labels are external and evaluation-only; they never enter a certificate.
- TMax-15K is pending. Its row, its epsilon row, and its mention in section one fill from `data/gold/gen_gate_tmax.certificate.json` when the running gate lands.

## RESULT

Wrote `documents/61-results.md` (this file): the standalone results document covering 12 measured populations, the epsilon-sensitivity grid, the generator comparison with confounds, six scoped negative results, the dump-reconstruction data contribution, the Lot-001 three-gate demonstration, and a single limits section. TMax-15K is marked PENDING in the certification table, the sensitivity table, and the limits, with `data/gold/gen_gate_tmax.certificate.json` as the fill-in artifact. Added a two-line pointer to `documents/56-paper-draft.md`. Full test suite: see session report.

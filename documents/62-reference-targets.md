# Reference distributions as a generation target (task 30)

Code: `src/task_validation/evidence/content_features.py` and `src/task_validation/evidence/reference_target.py` (dispatch `python -m task_validation.evidence.content_features run`, `python -m task_validation.evidence.reference_target run`). Tests: `tests/test_content_features.py`, `tests/test_reference_target.py`. Inputs: `data/gold/swe_taste_labels.jsonl` and `swe_verified500_ids.json` (935 valid, 500 kept, doc 59), `data/gold/swe_verified_features.jsonl` (24 artifact features), `data/raw/swe-bench/test.parquet` (problem_statement, patch, test_patch for the 1,699 annotated instances), `data/gold/tb21_census_verdicts.jsonl` and `tb21_maintenance.jsonl` (84 valid, 26 kept), `data/gold/harbor_index_strata.json` and `footprint.jsonl` (82 kept), `/home/evan/Documents/eval_tasks/lots/lot-001` (20 candidate tasks). Outputs: `data/gold/content_features.jsonl`, `data/gold/reference_targets.json`, `data/gold/reference_target_eval.json`, `data/gold/lot001_gap_report.json`. External labels define the kept sets and remain eval-only (doc 43). No label is imputed. Nothing here enters a bound.

## Result

The reference target is not vacuous on the one population with power. A distribution fitted to 400 of the 500 SWE-bench Verified kept tasks ranks the held-out 100 kept above the 435 valid rejected tasks at mean AUROC 0.596 on the full feature set (20 split seeds, every seed above 0.5), 0.592 on the content features alone and 0.581 on the artifact features alone (`data/gold/reference_target_eval.json`, `validation_swe`). The one-class distance reaches the same ceiling as the supervised conditional-taste model on the same artifact features (grouped OOF AUROC 0.590, doc 59): the description of what was kept carries the same signal the keep-versus-reject classifier found.

The target does not transfer. A reference built on one population never ranks another population's kept above its rejected: SWE reference on TB 2.1 gives AUROC 0.440, TB 2.1 reference on SWE-bench gives 0.462, Harbor-Index reference on SWE-bench gives 0.492, and Harbor-Index on TB 2.1 gives 0.253 (`cross_population`). The doc-59 kept-set separability of 0.94 to 1.00 predicts exactly this: kept sets occupy disjoint regions, so a foreign reference sits closer to another population's rejected mass than to its kept. A generation target must be population-specific.

## Content features

Nineteen features are now extracted from task text (`data/gold/content_features.jsonl`): instruction token count, sentence count, mean sentence length, imperative openers, fenced code-block presence and count, expected-output presence, acceptance-criteria phrasings, reproduction steps, error text, named files and the fraction of them the reference patch touches, test count, assertion count, mean assertion length, the fraction of assertions comparing literals, reference patch size in lines and files, and the ratio of test lines to reference lines. Tokenization is the decontam tokenizer. For SWE-bench the patch and test patch are unified diffs (test features count added lines). For Harbor directories the `solution/` and `tests/` trees are the reference and test text, with the doc-40 test-file filter applied so helper subtrees do not count as tests.

Coverage, `content_features.summary.json`: all 19 features are observed on all 20 lot-001 tasks. On SWE-bench, `instr_named_files_touched_frac` is unobserved on 875 of 1,699 tasks whose instructions name no file, and `assert_mean_tokens`/`assert_literal_frac` are unobserved on 195 whose test diffs add no assertion line. A missing field yields None, never a zero.

## The target

A reference target describes a kept set on a recorded feature subset: per-feature median, interquartile range, and the share of kept tasks inside the middle 80 percent on the raw scale, plus a standardized centroid and a correlation matrix shrunk toward the identity with an eigenvalue floor on the model scale (the doc-60 fit). Distance to the target is the mask-marginalized Mahalanobis distance: a feature a population never observes contributes nothing.

| Reference | Kept n | Feature subset | Universe dims | Shrinkage alpha |
| --- | ---: | --- | ---: | ---: |
| swe_verified_kept | 500 | 24 artifact + 19 content | 43 | 0.079 |
| tb21_kept | 26 | 32 footprint statics | 13 | 0.333 |
| harbor_index_kept | 82 | 64 statics + behaviour | 44 | 0.349 |

The middle-80 share exposes degenerate features: binary fields where every kept task sits in the band (share 1.0), such as `has_instr_error_text` on SWE kept and `hints_chars` on TB 2.1 kept (`reference_targets.json`, `per_feature`).

## Validation

On the 500 kept SWE tasks, 400 are drawn at a fixed seed (split seed `reference-target-split:0`) and the reference is fitted on them alone. Distance to that reference scores the held-out 100 kept and all 435 valid rejected tasks. AUROC measures whether proximity ranks kept above rejected, with a 400-replicate bootstrap interval, repeated over 20 split seeds (`reference_target_eval.json`, `validation_swe`).

| Feature set | Dims | Mean AUROC, 20 seeds | Seed range | Primary-seed AUROC | 95% CI |
| --- | ---: | ---: | --- | ---: | --- |
| artifact 24 | 24 | 0.581 | 0.536-0.616 | 0.581 | 0.523-0.641 |
| content 19 | 19 | 0.592 | 0.562-0.628 | 0.610 | 0.554-0.670 |
| both | 43 | 0.596 | 0.546-0.636 | 0.592 | 0.535-0.655 |

n per seed: 400 kept in the fit, 100 held-out kept scored, 435 rejected scored.

Every one of the 20 seeds ranks held-out kept above rejected on all three feature sets. The reference distribution does describe what the curators kept, and the content features carry slightly more of that signal than the artifact features do. The effect is real and modest: distance is a generation compass, not a filter.

## Cross-population check

Each reference scores the other populations' kept against their rejected on the features both sides share (`cross_population`).

| Reference | Scored population | Dims | Kept / rejected | AUROC | 95% CI |
| --- | --- | ---: | ---: | ---: | --- |
| swe_verified_kept | tb21 | 11 | 26 / 58 | 0.440 | 0.314-0.551 |
| tb21_kept | swe | 7 | 500 / 435 | 0.462 | 0.426-0.502 |
| harbor_index_kept | swe | 10 | 500 / 435 | 0.492 | 0.454-0.536 |
| harbor_index_kept | tb21 | 18 | 26 / 58 | 0.253 | 0.147-0.381 |

No direction ranks kept above rejected, and the Harbor-Index reference anti-ranks TB 2.1 kept at 0.253 (0.147-0.381), which is the signature of disjoint kept regions: a foreign kept centre is farther from the scored kept set than the scored rejected mass is. The doc-59 prediction is confirmed on distance space as well as classifier space. A generator targeting population A cannot aim at population B's reference and expect to hit A's kept region.

## Lot-001 gap report

The 20 lot tasks score against each reference on the shared dimensions (`data/gold/lot001_gap_report.json`). Median Mahalanobis distance: 5.63 against the SWE reference (all 20 identical, since every lot instruction is byte-identical and the text-derived features collapse to one point), 2.91 against TB 2.1 (identical for the same reason), and 9.07 against Harbor-Index (range 7.14 to 20.80, where gate-C behaviour features do vary across the lot). Every line below is a description of distance, not a quality judgement.

Largest gaps against `swe_verified_kept` (33 shared dims, ranked by absolute IQR-standardized difference):

| Feature | Lot median | Ref median | Ref IQR | Diff (IQR) | Direction |
| --- | ---: | ---: | ---: | ---: | --- |
| n_tests | 11.0 | 1.0 | 1.0 | +10.00 | above |
| n_assert_lines | 11.0 | 2.0 | 2.0 | +4.50 | above |
| ref_patch_n_lines | 42.0 | 7.0 | 10.0 | +3.50 | above |
| n_instr_named_files | 4.0 | 0.0 | 2.0 | +2.00 | above |
| test_to_ref_line_ratio | 6.7 | 2.2 | 3.0 | +1.47 | above |
| n_instr_imperative_openers | 1.0 | 0.0 | 1.0 | +1.00 | inside |
| assert_literal_frac | 0.0 | 0.5 | 1.0 | -0.50 | inside |
| test_stmt_id_overlap | 0.117 | 0.188 | 0.158 | -0.45 | inside |
| test_only_id_frac | 0.883 | 0.812 | 0.158 | +0.45 | inside |
| instr_named_files_touched_frac | 0.0 | 0.143 | 0.575 | -0.25 | inside |

Largest gaps against `harbor_index_kept` (37 shared dims):

| Feature | Lot median | Ref median | Ref IQR | Diff (IQR) | Direction |
| --- | ---: | ---: | ---: | ---: | --- |
| assertion_count | 11.0 | 0.0 | 1.0 | +11.00 | above |
| output_tokens_mean | 50,964 | 16,146 | 13,506 | +2.58 | above |
| traj_agent_wall_sec_mean | 1,241 | 379 | 401 | +2.15 | above |
| reward_var | 0.333 | 0.105 | 0.191 | +1.19 | above |
| agent_wall_sec_mean | 1,241 | 564 | 591 | +1.15 | above |
| has_code_fence | 0.0 | 1.0 | 1.0 | -1.00 | inside |
| test_file_count | 2.0 | 1.0 | 1.0 | +1.00 | inside |
| cost_usd_mean | 0.0 | 0.523 | 0.610 | -0.86 | below |
| cache_tokens_mean | 1,397,622 | 483,921 | 1,134,328 | +0.81 | above |
| input_tokens_mean | 1,506,407 | 537,061 | 1,205,463 | +0.80 | above |

Largest gaps against `tb21_kept` (13 shared dims):

| Feature | Lot median | Ref median | Ref IQR | Diff (IQR) | Direction |
| --- | ---: | ---: | ---: | ---: | --- |
| instruction_lines | 23.0 | 10.0 | 16.75 | +0.78 | above |
| timeout_sec | 480 | 1,050 | 900 | -0.63 | below |
| stmt_n_identifiers | 74.0 | 45.5 | 53.0 | +0.54 | inside |
| instruction_chars | 975 | 543 | 845 | +0.51 | inside |
| resource_memory_mb | 2,048 | 4,096 | 5,120 | -0.40 | inside |
| solution_size | 1,477 | 2,867 | 4,874 | -0.29 | inside |
| assertion_count | 11.0 | 8.5 | 11.75 | +0.21 | inside |
| test_stmt_id_overlap | 0.117 | 0.100 | 0.085 | +0.20 | inside |
| test_only_id_frac | 0.883 | 0.900 | 0.085 | -0.20 | inside |
| literal_pins_absent | 27.0 | 26.0 | 31.0 | +0.03 | inside |

The actionable set is the top of each ranking. Against the SWE target the lot diverges most on test-side mass (test count, assertion count, reference patch size, named files, test-to-reference ratio). Against Harbor-Index the divergence concentrates in execution cost and assertion count. Against TB 2.1 nothing exceeds one IQR. The lot sits inside TB 2.1's marginal bands on nearly every shared feature, which is a statement about feature-space distance only.

## Where a target belongs in the intake pipeline

For doc 50: the reference target belongs upstream of the pipeline entirely, at the generator, not inside it. A target shapes generation: the producer of a lot fits the kept set of the population it wants to resemble and aims new tasks at that distribution, then ships the lot to intake unchanged. The target never gates acceptance. Gates A through C and the probability sample decide what ships, exactly as doc 50 stages 2 through 7 write it. A lot close to its target earns nothing there, and a lot far from it loses nothing there. The dossier may carry the gap report as descriptive evidence alongside the Mapper picture (doc 50 stage 8, diagnostic only). No bound may use the target: the certificate remains the design-based hypergeometric UCB on a human-adjudicated sample, and a distance to a curated centroid is not evidence about the lot's invalid rate, its difficulty, or its taste.

## Method

- Content features: `extract_content_features` on instruction, reference, and tests text; diffs via `diff_stats`, directory tasks via `harbor_fields` plus the doc-40 test-file filter; sentences split on enders and newlines; imperative openers match a fixed verb list on the first sentence token; named files match a code-extension path pattern; touch fraction matches named files against reference files by path suffix or basename.
- Canonicalization: the doc-59 cheap 24 map onto footprint names (`CHEAP_TO_CANON`) so one feature space serves SWE, TB 2.1, Harbor-Index and lot-001; `patch_n_changed_lines` stays a line count because `solution_size` is bytes on directory tasks.
- Reference fit: features observed on at least 10 kept tasks with nonzero model-scale spread form the universe; robust stats on the raw scale; centroid and correlation shrunk toward the identity with a 0.05 eigenvalue floor on the model scale (log1p on the doc-60 count features plus the content counts).
- Validation: 20 deterministic split seeds (`reference-target-split:0..19`), 400-task kept fit, 100 held-out kept versus 435 rejected, AUROC of negative distance, 400-replicate bootstrap, seed 20260914.
- Cross-population: same scorer, dims = reference universe intersected with the scored population's observed features.
- Gap report: lot median versus reference median and IQR on the raw scale; the standardized difference is IQR units; direction is inside/above/below the reference IQR; features need 10 observed lot tasks to score.

## Limits

- The validation measures ranking, not closeness. A target can rank kept above rejected and still sit far from anything a generator should imitate. The AUROC says the description is non-vacuous, not that hitting it produces good tasks.
- The kept labels are eval-only and taste-laden: Verified-500 membership mixes validity, difficulty spread, repository spread and decontamination choices (doc 59). The reference describes the kept set as published, whatever the selectors optimized for.
- The TB 2.1 kept set is 26 tasks and the Harbor-Index kept set is 82 across 29 benchmarks. Both fits are shrunk heavily (alpha 0.333 and 0.349), and no cross-population direction was expected to work, so the negative results are confirmation, not news.
- Lot-001 is 20 copies of one task's text: every `instruction.md` is byte-identical, so every text-derived feature takes the same value on all 20 tasks, distances under text-only references are identical, and the gap table describes a single point. The behavior-side distances do vary.
- Mask-marginalized distances compare populations on different dimension sets (33 for lot versus SWE, 13 versus TB 2.1, 37 versus Harbor-Index). A distance is only interpretable against its own reference cloud.
- Feature availability is not symmetric: TB 2.1 and Harbor-Index references carry no content features because their task text was never fetched as diffs, and the shared SWE-TB21 space is 11 statics.

## RESULT

- Content features: `data/gold/content_features.jsonl`, 19 features on 1,699 SWE-bench instances and 20 lot-001 tasks. Coverage gaps recorded per source (`content_features.summary.json`).
- Targets: `data/gold/reference_targets.json`. SWE kept n = 500 on 43 dims (alpha 0.079), TB 2.1 kept n = 26 on 13 dims (alpha 0.333), Harbor-Index kept n = 82 on 44 dims (alpha 0.349).
- Validation: the reference ranks held-out kept above rejected. Mean AUROC over 20 seeds: 0.581 artifact, 0.592 content, 0.596 both. Every seed above 0.5; primary-seed intervals 0.523-0.641, 0.554-0.670, 0.535-0.655 (`reference_target_eval.json`). The target is not vacuous.
- Cross-population: 0.440, 0.462, 0.492, 0.253 on the four directions; no foreign reference ranks kept above rejected. A generation target must be population-specific, as doc 59 predicted.
- Gap report: `data/gold/lot001_gap_report.json`. Lot-001 diverges most from the SWE target on test-side mass (n_tests +10 IQR, n_assert_lines +4.5 IQR, ref_patch_n_lines +3.5 IQR) and from Harbor-Index on execution cost (assertion_count +11 IQR, output_tokens_mean +2.6 IQR). It sits inside TB 2.1's bands.
- Intake spec: the target lives at the generator. It shapes generation, never gates acceptance, and no bound may use it.
- Tests: 296 pass, 0 fail (`pytest tests`), including 11 content-extractor fixture tests and 5 synthetic-distance tests with known answers.

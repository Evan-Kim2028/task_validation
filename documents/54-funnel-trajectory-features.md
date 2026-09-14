# Funnel trajectory and verifier features (doc 52 extension)

Code: `src/task_validation/evidence/harbor_funnel.py`, `run_traj_eval` (dispatch `python -m task_validation.evidence.harbor_funnel traj-eval`) and `run_within_benchmark` (dispatch `within-eval`). Tests: `tests/test_harbor_funnel.py`. Inputs: `data/gold/harbor_funnel_labels.jsonl` (6,627 candidates, doc 52), `data/gold/harbor_funnel_stage1.jsonl` (group A features), `data/gold/harbor_adapter_task_traj.jsonl` (per-task aggregates, 8,468 tasks), `data/gold/harbor_adapter_traj.jsonl` (793,698 trial rows, 757 MB, streamed once; `data/gold/harbor_adapter_traj.summary.json`). Outputs: `data/gold/harbor_funnel_traj_eval.json`, `data/gold/harbor_funnel_hidden_requirement.jsonl`, `data/gold/harbor_funnel_within_benchmark.json`. External labels remain eval-only (doc 43); no model-generated score enters any bound.

## Join coverage

Per-task trajectory aggregates joined to labels on (benchmark, task_name) (`join_task_traj`, `join_coverage` in `data/gold/harbor_funnel_traj_eval.json`).

| Count | Value | Source |
| --- | ---: | --- |
| Label rows | 6,627 | `harbor_funnel_labels.jsonl` |
| Matched to a trajectory aggregate | 6,627 (100 percent) | `harbor_funnel_traj_eval.json` |
| Unmatched label rows | 0 | same |
| Duplicate aggregate keys | 0 | same |
| Aggregate rows not in labels | 1,841 | same (out-of-scope tasks, e.g. multi-swe-bench, featbench) |
| Stage-1 survivors matched | 1,331 of 1,331 | same |
| Published survivors matched | 81 of 81 | same |

Every candidate carries a trajectory aggregate. One candidate has no frontier-cell trials at all (`n_frontier_trials_seen` = 0 in the streamed stats), the same gap doc 52 noted in the Mapper input.

## Feature groups

All B, C, D features are measured over the six frontier cells of `adapters54.json` (all stored frontier trials, not only the 18 stage-1-selected). Mapping in `_FRONTIER_BUNDLE_MAP`, `FEATURE_GROUPS` in `harbor_funnel.py`.

| Group | Features | Availability on the 1,331 survivors |
| --- | --- | --- |
| A execution (doc 52 set) | `n_frontier_trials`, `n_cells_ge3`, `full_18`, `n_all_trials`, token, cost, wall, exception means | all survivors, from `harbor_funnel_stage1.jsonl` |
| B trajectory | `traj_n_steps_mean`, `traj_n_tool_calls_mean`, `traj_assistant_chars_mean`, `traj_observation_chars_mean`, `traj_hit_timeout_rate`, `traj_exception_rate`, `traj_agent_wall_sec_mean` | all survivors with frontier trials |
| C verifier | `ver_has_report_json_rate`, `ver_n_tests_total_mean`, `ver_n_tests_failed_mean`, `ver_reward_partial_rate`, `ver_top_failed_share`, `ver_n_distinct_failed_tests` | sparse, see below |
| D shortcut | `shortcut_answer_file_rate`, `shortcut_git_probe_rate`, `shortcut_network_fetch_rate` | nonzero on 322, 282, 583 of 1,331 survivors (`harbor_adapter_task_traj.jsonl`) |

Group C is thin. `report.json` exists on 40,093 in-scope trial rows but only 133 rows, all skillsbench, parse to named failed tests (`_report_stats` accepts pytest-style reports only; the swebench-verified and spreadsheetbench reports use other schemas). `ver_n_tests_total_mean`, `ver_n_tests_failed_mean`, `ver_top_failed_share`, and `ver_n_distinct_failed_tests` are missing on every survivor. `ver_has_report_json_rate` is positive only for spreadsheetbench (26 of 26 survivors) and swebench-verified (23 of 23) and is effectively a benchmark-membership bit. The two failed-test features are recomputed per frontier cell by streaming `harbor_adapter_traj.jsonl` (`frontier_failed_test_stats`); the per-task aggregate stores them across all cells.

## Held-out evaluation

Model class identical to doc 52: median imputation, missingness indicators, standardized design matrix, L2 logit. The numpy mirror `_fit_logit_fast` is used for speed; it reproduces the doc 52 A-only numbers to the printed digits (0.711 and 0.837), and a fixture test pins it to `fit_logit` at 1e-6. LOBO is leave-one-benchmark-out; LOFO is leave-one-benchmark-family-out, with swe-family (swebench-verified, swebenchpro, swesmith, swebench-multilingual, swtbench, multi-swe-bench, swe-lancer), terminal-family (terminal-bench, skillsbench, compilebench), and math/QA (aime, omnimath, ineqmath, gpqa-diamond, hle, simpleqa, mmmlu, arc-agi-2) each folding as one unit, everything else by benchmark (`benchmark_family`). Bootstrap intervals are 400 replicates, seed 20260913.

survived_2_to_4, 1,331 rows, 67 positives (`evals.survived_2_to_4` in `harbor_funnel_traj_eval.json`):

| Feature set | LOBO AUROC (95% CI) | LOFO AUROC (95% CI) | pooled AUROC |
| --- | --- | --- | --- |
| A | 0.711 (0.650, 0.771) | 0.698 (0.635, 0.766) | 0.782 |
| A+B | 0.691 (0.618, 0.756) | 0.679 (0.609, 0.751) | 0.803 |
| A+B+C | 0.615 (0.525, 0.699) | 0.606 (0.517, 0.689) | 0.803 |
| A+B+C+D | 0.633 (0.545, 0.718) | 0.612 (0.529, 0.697) | 0.820 |
| B+C+D (no A) | 0.610 (0.530, 0.690) | 0.580 (0.498, 0.660) | 0.765 |

survived_funnel, 6,627 rows, 81 positives (`evals.survived_funnel`):

| Feature set | LOBO AUROC (95% CI) | LOFO AUROC (95% CI) | pooled AUROC |
| --- | --- | --- | --- |
| A | 0.837 (0.793, 0.871) | 0.830 (0.781, 0.866) | 0.871 |
| A+B | 0.798 (0.742, 0.853) | 0.794 (0.739, 0.852) | 0.886 |
| A+B+C | 0.759 (0.692, 0.822) | 0.760 (0.691, 0.822) | 0.890 |
| A+B+C+D | 0.763 (0.694, 0.822) | 0.736 (0.666, 0.804) | 0.894 |
| B+C+D (no A) | 0.751 (0.685, 0.810) | 0.734 (0.674, 0.799) | 0.865 |

Adding trajectory, verifier, and shortcut features lowers held-out AUROC on both labels while raising pooled AUROC (0.782 to 0.820 on survived_2_to_4): the wider the in-sample gap over held-out, the more the fit is source recognition. Group C is sparse enough to act as a benchmark indicator, and the B magnitudes (steps, chars, wall) are agent- and benchmark-typical rather than task-typical. Fold counts: 48 LOBO folds (26 single-class, no per-fold AUROC) and 35 LOFO folds (21 undefined) on survived_2_to_4; 54 LOBO (26 undefined) and 40 LOFO (20 undefined) on survived_funnel (`n_folds`, `n_folds_undefined_auroc` in the eval JSON).

## Within-benchmark evaluation

Two corrections to the reading above. First, LOBO and LOFO are transfer tests. They answer whether a signature learned on other benchmarks predicts an unseen one. They cannot refute the different hypothesis that each benchmark population carries its own signature. Second, the pooled AUROC is confounded. AUROC is a pairwise ranking statistic, and pooling lets the model earn credit for separating tasks from different benchmarks. The fix is the within-benchmark AUROC: every comparison pair is restricted to tasks from the same benchmark, so benchmark identity carries no information. Code: `run_within_benchmark`, `within_group_concordance`, `within_benchmark_eval`, `within_benchmark_cv` in `harbor_funnel.py`. Output: `data/gold/harbor_funnel_within_benchmark.json`. Population: survived_2_to_4 on the 1,331 stage-1 survivors, 67 kept tasks across 48 benchmarks (`population` in the output JSON).

Per-benchmark counts (`benchmark_counts` in the output JSON; the 26 benchmarks with zero kept tasks omitted):

| Benchmark | Stage-1 survivors | Kept | OOF eval (5+ kept, 5+ rejected) | Per-benchmark CV (5+ kept) |
| --- | ---: | ---: | --- | --- |
| hle | 107 | 8 | yes | yes |
| gso | 54 | 7 | yes | yes |
| gaia2 | 55 | 5 | yes | yes |
| bixbench | 29 | 5 | yes | yes |
| swebench-verified | 23 | 5 | yes | yes |
| arc-agi-2 | 22 | 5 | yes | yes |
| featurebench-modal | 106 | 4 | no | no |
| swebenchpro | 42 | 4 | no | no |
| labbench | 40 | 4 | no | no |
| scicode | 13 | 3 | no | no |
| spider2 | 38 | 2 | no | no |
| swe-lancer | 35 | 2 | no | no |
| skillsbench | 33 | 2 | no | no |
| omnimath | 18 | 2 | no | no |
| terminal-bench | 17 | 2 | no | no |
| bigcodebench | 75 | 1 | no | no |
| swesmith | 56 | 1 | no | no |
| gaia | 30 | 1 | no | no |
| swtbench | 10 | 1 | no | no |
| gpqa-diamond | 8 | 1 | no | no |
| qcircuitbench | 7 | 1 | no | no |
| codepde | 2 | 1 | no | no |

No benchmark has 10 or more kept tasks; the maximum is 8, and 26 of 48 benchmarks have none (`population` in the output JSON).

### Pooled-trained, within-benchmark evaluated

Scores are the same grouped out-of-fold scores behind the LOBO numbers above, so no task is scored by a model that saw it. Recomputing the pooled OOF AUROC from these scores reproduces the table above to the printed digits (0.711 on A, 0.633 on A+B+C+D). AUROC is computed inside each benchmark with at least 5 kept and at least 5 rejected survivors; intervals are 400 bootstrap replicates over that benchmark's tasks, seed 20260914 (`pooled_trained_within_evaluated` in the output JSON):

| Benchmark | n (kept) | A | A+B | A+B+C+D |
| --- | ---: | --- | --- | --- |
| hle | 107 (8) | 0.874 (0.774, 0.948) | 0.874 (0.765, 0.951) | 0.847 (0.749, 0.922) |
| gso | 54 (7) | 0.486 (0.185, 0.785) | 0.541 (0.264, 0.804) | 0.511 (0.235, 0.815) |
| gaia2 | 55 (5) | 0.348 (0.120, 0.642) | 0.292 (0.095, 0.572) | 0.236 (0.047, 0.529) |
| bixbench | 29 (5) | 0.692 (0.350, 0.962) | 0.625 (0.440, 0.808) | 0.650 (0.343, 0.923) |
| swebench-verified | 23 (5) | 0.556 (0.199, 0.917) | 0.600 (0.232, 0.981) | 0.611 (0.277, 1.000) |
| arc-agi-2 | 22 (5) | 0.541 (0.259, 0.802) | 0.494 (0.219, 0.762) | 0.506 (0.221, 0.762) |

The same statistic aggregated three ways, with 400-replicate stratified bootstrap intervals (`positives_weighted_mean`, `concordance_qualified_pairs`, `concordance_all_pairs`, `concordance_cross_pairs`):

| Statistic | Pairs | A | A+B | A+B+C+D |
| --- | ---: | --- | --- | --- |
| Positives-weighted mean of per-benchmark AUROC | 6 benchmarks | 0.602 (0.487, 0.706) | 0.595 (0.482, 0.704) | 0.582 (0.466, 0.694) |
| Single concordance, qualified benchmarks | 1,666 | 0.671 (0.549, 0.776) | 0.669 (0.538, 0.773) | 0.645 (0.522, 0.742) |
| Single concordance, all within-benchmark pairs | 2,843 | 0.685 (0.589, 0.765) | 0.607 (0.498, 0.712) | 0.593 (0.487, 0.702) |
| Cross-benchmark pair concordance (the confounded component) | 81,845 | 0.711 | 0.694 | 0.635 |

The decomposition is exact: a pooled AUROC is a pair-count weighted mean of the within-benchmark and cross-benchmark pair concordances. On A the held-out model earns 0.685 on the 2,843 within-benchmark pairs and 0.711 on the 81,845 cross-benchmark pairs. The within-benchmark component is materially above chance with an interval excluding 0.5 on the execution set, and it stays above chance on the qualified-pair variant for all three feature sets. It is also concentrated: hle alone carries a 0.874 interval that excludes 0.5, on the largest kept sample (8 of 107 survivors). The in-sample pooled model earns 0.712 on the same within-benchmark pairs (`in_sample_pooled_concordance`), so the held-out within-benchmark signal on A is nearly as large as the in-sample one. The earlier pooled numbers are still confounded as stated, but the correction cuts against the old conclusion in one place: a signature trained on other benchmarks does rank kept tasks above rejected survivors inside a benchmark, at small n and mostly in hle.

### Within-benchmark trained and evaluated

Any benchmark with at least 5 kept tasks is eligible. Five-fold requires at least 10 of each class so that each test fold carries about two of each, so every eligible benchmark falls back to leave-one-out (`within_benchmark_cv` in `harbor_funnel.py`; `within_benchmark_cv` in the output JSON). OOF AUROC with 400-replicate bootstrap intervals:

| Benchmark | n (kept) | Method | A | A+B | A+B+C+D | Fits and validates honestly |
| --- | ---: | --- | --- | --- | --- | --- |
| hle | 107 (8) | LOO | 0.691 (0.488, 0.848) | 0.549 (0.266, 0.806) | 0.495 (0.240, 0.745) | no, 8 kept |
| gso | 54 (7) | LOO | 0.593 (0.386, 0.772) | 0.499 (0.271, 0.739) | 0.571 (0.272, 0.858) | no, 7 kept |
| gaia2 | 55 (5) | LOO | 0.656 (0.319, 0.936) | 0.620 (0.326, 0.852) | 0.672 (0.348, 0.910) | no, 5 kept |
| swebench-verified | 23 (5) | LOO | 0.544 (0.095, 0.953) | 0.522 (0.214, 0.868) | 0.511 (0.182, 0.857) | no, 5 kept |
| bixbench | 29 (5) | LOO | 0.442 (0.074, 0.815) | 0.408 (0.000, 0.797) | 0.642 (0.232, 0.910) | no, 5 kept |
| arc-agi-2 | 22 (5) | LOO | 0.282 (0.056, 0.581) | 0.706 (0.406, 0.938) | 0.706 (0.406, 0.938) | no, 5 kept |

Every interval straddles 0.5 across a wide range and every kept count is under 10. No benchmark has enough kept tasks to fit and validate a per-population model honestly. These numbers are suggestive small-n statistics, not fitted models.

## Univariate held-out AUROC

Per-feature leave-one-benchmark-out AUROC on survived_2_to_4 and survived_funnel, top 15 by the former (`univariate_lobo` in `harbor_funnel_traj_eval.json`):

| Feature | Group | survived_2_to_4 | survived_funnel |
| --- | --- | ---: | ---: |
| output_tokens_mean | A | 0.726 | 0.834 |
| traj_assistant_chars_mean | B | 0.709 | 0.844 |
| traj_agent_wall_sec_mean | B | 0.690 | 0.833 |
| cost_usd_mean | A | 0.676 | 0.805 |
| agent_wall_sec_mean | A | 0.649 | 0.807 |
| traj_n_steps_mean | B | 0.622 | 0.773 |
| traj_observation_chars_mean | B | 0.621 | 0.726 |
| input_tokens_mean | A | 0.614 | 0.796 |
| traj_n_tool_calls_mean | B | 0.610 | 0.758 |
| cache_tokens_mean | A | 0.608 | 0.793 |
| cost_usd_total | A | 0.608 | 0.734 |
| n_all_trials | A | 0.597 | 0.641 |
| exception_rate | A | 0.589 | 0.420 |
| traj_exception_rate | B | 0.589 | 0.420 |
| ver_n_tests_total_mean | C | 0.589 | 0.298 |

Two cautions on this table. The best single feature (output_tokens_mean, 0.726) beats every multivariate set, which is itself evidence that the joint fit is overfitting benchmark identity rather than composing task signal. And a feature that is missing on every survivor produces fold-constant scores whose pooled AUROC is an artifact of fold-level base rates, not 0.5: the three identical 0.589 rows and the other C rows should be read as noise floor, not signal.

## Stop rule

Doc 45: if leave-one-benchmark-out AUROC for survived_2_to_4 is under 0.65, the funnel footprint is benchmark identity and the plan stops. Applied to the family-held-out variant, which is the stronger form of the same test (`stop_rule` in `harbor_funnel_traj_eval.json`):

| Application | Value | Threshold | Triggers |
| --- | ---: | ---: | --- |
| survived_2_to_4, A+B+C+D, LOFO | 0.612 (0.529, 0.697) | 0.65 | yes |
| survived_2_to_4, A only, LOFO | 0.698 (0.635, 0.766) | 0.65 | no |

Decision: STOP. With the completed feature set the family-held-out number is 0.612, under 0.65 with the interval straddling the line. The doc 52 caveat is now measured: removing benchmark families, not just benchmarks, costs about 1.3 points on the execution set (0.711 LOBO to 0.698 LOFO) and more on every extended set; nothing added recovers it. The stop rule measures transfer, and the transfer result stands: a signature learned on other benchmarks does not predict an unseen one at useful accuracy.

What the run does not show is that the funnel footprint is only benchmark identity. Within-benchmark concordance of the same held-out scores is materially above chance on the execution set (0.685 over 2,843 same-benchmark pairs, interval 0.589 to 0.765, `concordance_all_pairs` in `harbor_funnel_within_benchmark.json`), concentrated in hle (0.874 over 107 survivors, the largest kept sample at 8). That is suggestive evidence for a per-population signature at small n, not a fitted model. The per-population hypothesis is untested on this data rather than refuted, because no benchmark has enough kept tasks to fit and validate a per-population model, the maximum being 8. The honest summary is that taste is learnable only inside a population you already have labels for. Doc 40 reached the same conclusion for specification validity by a different route, and it is why doc 50 puts a fresh human sample on every lot.

## Hidden-requirement signature

Candidate flag: among stage-1 survivors, tasks where a large share of failing frontier trials hit the same named test, with at least 6 failing frontier trials. Rationale: every frontier agent failing one identical check is what a hidden requirement or broken verifier looks like, and it is what the funnel's stage-2 screen should catch. Implementation: `frontier_failed_test_stats`, `hidden_requirement_flags` in `harbor_funnel.py`; output `data/gold/harbor_funnel_hidden_requirement.jsonl`.

Result: the list is empty. Zero stage-1 survivors have even one verifier-named failing frontier trial, because named failed tests exist only for skillsbench in this extract (133 of 768,956 in-scope rows; `harbor_adapter_traj.summary.json`, `hidden_requirement.coverage_note` in the eval JSON). The signature is computable for exactly two in-scope tasks, neither of which survived stage 1 (`signature_computable_tasks` in the eval JSON):

| Task | Failing frontier trials | Share on top failed test | Top failed test | Stage-1 outcome |
| --- | ---: | ---: | --- | --- |
| skillsbench taxonomy-tree-merge | 9 | 1.00 | test_outputs.py::test_prefix_removal | rejected (solve rate 1.0 on selected trials) |
| skillsbench trend-anomaly-causal-inference | 13 | 0.62 | test_outputs.py::test_purchase_aggregation_correctness | rejected (solve rate 1.0) |

So the count among the 82 survivors versus rejected is 0 of 0: the flag is defined, stored, and eval-only (doc 43), but it cannot be assessed on this dump. Evaluating it needs either a normalizer for the non-pytest report schemas (swebench-verified and spreadsheetbench ship report.json in other shapes) or a parse of verifier test-stdout, neither of which this extract carries. taxonomy-tree-merge is what the flag would look like when it works: all 9 failing frontier trials share `test_prefix_removal`, a plausible single hidden assertion.

## Implication for doc 50 stage 8

The footprint prior in stage 8 should stay benchmark-provenance only, and this run strengthens that: the completed feature set ranks funnel survival at family-held-out AUROC 0.612, below the doc 45 stop line, and the strongest single feature is an output-volume number (0.726 univariate, `univariate_lobo`) rather than anything task-semantic. No trajectory or verifier feature buys transferable signal here because the verifier fields are too sparse to be anything but benchmark bits (report.json parses only on skillsbench, and swebench-verified plus spreadsheetbench only for presence). The within-benchmark correction does not change the prior: held-out scores rank kept tasks above rejected survivors inside a benchmark at 0.685 concordance over 2,843 pairs, but the signal concentrates in hle at 8 kept tasks and no benchmark has enough kept tasks to validate a per-population model, so it enters nothing (`harbor_funnel_within_benchmark.json`). If a machine flag for hidden-requirement tasks is wanted inside the gates, it has to be rebuilt on normalized verifier output or test stdout, since the named failed tests this signature needs are absent for 53 of 54 in-scope benchmarks; until then the stage-8 prior orders review attention by family at most, the human sample still carries every bound, and the funnel labels stay a sanity check on provenance rather than a per-task taste score.

## RESULT

- Join: 100 percent of the 6,627 label rows matched a per-task trajectory aggregate; all 1,331 stage-1 survivors and all 81 published survivors matched (`harbor_funnel_traj_eval.json`).
- Feature groups: A execution (doc 52), B trajectory (7 frontier-cell features), C verifier (6, mostly missing on survivors), D shortcut (3 trial-rate features).
- Held-out survived_2_to_4: A = 0.711 LOBO / 0.698 LOFO; A+B+C+D = 0.633 / 0.612; B+C+D = 0.610 / 0.580. Adding features degrades held-out AUROC on both labels (`evals` in the eval JSON).
- Stop rule: family-held-out survived_2_to_4 on A+B+C+D = 0.612 < 0.65. STOP stands as a transfer result: a signature learned on other benchmarks does not predict an unseen one at useful accuracy.
- Within-benchmark, pooled-trained OOF: single concordance over all within-benchmark pairs = 0.685 on A (2,843 pairs, 95% CI 0.589-0.765), 0.607 on A+B, 0.593 on A+B+C+D; positives-weighted mean over the 6 qualifying benchmarks = 0.602 on A; hle alone = 0.874 (0.774, 0.948). Cross-benchmark pairs earn 0.711 on A (`harbor_funnel_within_benchmark.json`).
- Per-benchmark CV: all 6 eligible benchmarks fall back to leave-one-out; every interval straddles 0.5; maximum kept is 8, so no benchmark can fit and validate a per-population model honestly. The within-benchmark signal is suggestive evidence for the per-population hypothesis at small n, not a fitted model; the per-population hypothesis is untested rather than refuted. Taste is learnable only inside a population you already have labels for, the same conclusion doc 40 reached for specification validity by a different route, and the reason doc 50 puts a fresh human sample on every lot.
- Hidden-requirement flag: defined and stored but unevaluable on this dump; named failed tests exist only for skillsbench (133 in-scope rows), zero survivors eligible, 0 of 0 flagged tasks among the 82 (`harbor_funnel_hidden_requirement.jsonl` is empty by construction).
- Doc 50 stage 8: the prior remains a family-level provenance check; nothing in the trajectory or verifier groups transfers as per-task signal, and the within-benchmark signal is too small to validate.

# Typicality of the expert-kept region (task 26)

Code: `src/task_validation/evidence/typicality.py` (dispatch `python -m task_validation.evidence.typicality run`). Tests: `tests/test_typicality.py`. Inputs: `data/gold/harbor_funnel_labels.jsonl` (6,627 candidates, 82 published survivors, doc 52), `data/gold/harbor_funnel_stage1.jsonl`, `data/gold/harbor_adapter_task_traj.jsonl` (docs 52, 54), `data/gold/footprint.jsonl` (doc 40 shared features), `data/gold/harbor_index_strata.json` (82 kept ids), `data/gold/tb21_census.jsonl`, `data/gold/swe_verified_features.jsonl`. Outputs: `data/gold/typicality_kept_region.json`, `data/gold/typicality_lot001.jsonl`. External labels define the kept set and remain eval-only (doc 43). No model output enters any bound. The analysis is descriptive throughout.

## Result

Expert-kept tasks occupy a distinctive region of the shared feature space, and a second expert-curated population lands inside it while funnel rejects land outside. Under the pooled kept cloud, leave-one-out kept tasks score a median typicality of 0.506 (n = 82, near the 0.5 that exchangeability guarantees). Stage-1 survivors that the funnel then rejected score 0.086 (n = 1,264). A seeded random sample of non-stage-1 candidates scores 0.074 (n = 1,000). SWE-bench Verified rows score 0.073 (n = 1,699). The TB 2.1 census scores 0.549 (n = 89), inside the kept cloud (`data/gold/typicality_kept_region.json`, `calibration.pooled`).

The distinctiveness is benchmark-shaped. The kept set spans 29 benchmarks, and 36 of the 44 universe features carry a benchmark η² above the stated 0.5 threshold. After those features are dropped, rejected survivors score a median typicality of 0.716 (n = 1,264), deeper inside the kept region than the kept leave-one-out median of 0.506 on the same retained features. Random candidates still score 0.074. Removing source identity collapses the kept-rejected gap but not the survivor-candidate gap (`calibration.desourced`, `anova_desourced`).

The kept set is not one cloud. Per-source typicality takes each task's best score across 29 per-benchmark kept fits. Under that construction every calibration population saturates: kept 1.0, rejected 1.0, candidates 1.0, TB 2.1 0.988, SWE-bench 0.683. Resembling at least one expert-kept source is nearly free, because 29 anchor clouds cover most of the space that stage-1-shaped tasks occupy (`calibration.per_source`).

Lot-001 lands outside both the kept region and the rejected cloud under the pooled variant. Its 20 tasks observe 37 of 44 universe features and score a median pooled typicality of 0.067 (range 0.024 to 0.207), farther from the kept center than all 1,264 rejected survivors. On the three source-free features the lot shares (reward_var, ver_reward_partial_rate, has_traceback) it scores 0.963, and per-source it matches the gaia anchor at 1.0, as does nearly everything else. This is the expected placement for a generated lot from an unseen generator. It is not evidence of low quality (`data/gold/typicality_lot001.jsonl`).

## Calibration

Typicality is the share of the kept set's leave-one-out distances at least as large as the task's own distance to the kept fit, computed on the dimensions the task's population actually observes. The table reports median typicality with the 10th to 90th percentile range, the share scoring 0.5 or higher, and the number of retained dimensions (pop = dimensions in that population's mask).

| Variant | Population | n | Median | p10-p90 | Share ≥ 0.5 | Dims |
| --- | --- | ---: | ---: | --- | ---: | ---: |
| pooled | kept (LOO) | 82 | 0.506 | 0.111-0.901 | 0.512 | 44 |
| pooled | rejected | 1,264 | 0.086 | 0.086-0.136 | 0.000 | 24 |
| pooled | cand_sample | 1,000 | 0.074 | 0.049-0.086 | 0.000 | 24 |
| pooled | tb21 census | 89 | 0.549 | 0.146-0.732 | 0.629 | 20 |
| pooled | swe verified | 1,699 | 0.073 | 0.000-0.429 | 0.095 | 12 |
| per_source | kept (LOO) | 82 | 1.000 | 1.000-1.000 | 0.988 | 29 sources |
| per_source | rejected | 1,264 | 1.000 | 1.000-1.000 | 1.000 | 29 sources |
| per_source | cand_sample | 1,000 | 1.000 | 1.000-1.000 | 0.996 | 29 sources |
| per_source | tb21 census | 89 | 0.988 | 0.890-1.000 | 1.000 | 29 sources |
| per_source | swe verified | 1,699 | 0.683 | 0.333-0.976 | 0.738 | 29 sources |
| desourced | kept (LOO) | 82 | 0.506 | 0.111-0.901 | 0.512 | 8 |
| desourced | rejected | 1,264 | 0.716 | 0.259-0.864 | 0.712 | 7 |
| desourced | cand_sample | 1,000 | 0.074 | 0.049-0.173 | 0.000 | 7 |
| desourced | tb21 census | 89 | 1.000 | 1.000-1.000 | 1.000 | 1 |
| desourced | swe verified | 1,699 | 1.000 | 0.049-1.000 | 0.721 | 1 |

The overlap is the finding. Pooled, the kept region separates expert-curated mass from everything the funnel produced: rejected survivors peak at p90 = 0.136 against a kept median of 0.506. Desourced, the same rejected tasks sit inside the kept region at 0.716 against kept 0.506. The separation lives in features that identify the source benchmark. Per-source, nothing separates at all, because the kept set covers the space as 29 anchors.

The kernel-density score tells the same story on the three eigendirections carrying the most kept variance per population mask: kept 0.506 (n = 81), rejected 0.444 (n = 1,264), candidates 0.099 (n = 1,000), TB 2.1 0.634 (n = 89), SWE-bench 0.183 (n = 1,699). Rejected tasks already sit near the kept cloud's densest directions. The pooled Mahalanobis separation comes from the remaining dimensions, not from the dominant axes (`kde.calibration`).

## Lot-001 placement

The lot is 20 generated tasks (`ope-01` to `ope-20`, generator `estimator-pair`). Each task carries the doc 40 static features, gate A execution fields, and the trajectory, verifier, and shortcut features derivable from its k = 3 gate C trial outputs without docker: 37 of 44 universe features. Unavailable on all 20: the frontier-cell block (`n_frontier_trials`, `n_cells_ge3`, `full_18`, `frontier_solve_rate`, `all_trials_solve_rate`, `n_all_trials`, `cache_tokens_mean`, `input_tokens_mean`, `output_tokens_mean`, `cost_usd_total`), the patch and test-file counts (`patch_n_files`, `patch_n_hunks`, `patch_n_changed_lines`, `test_n_files`, `test_n_hunks`, `test_n_changed_lines`), and the gold/test ratios (`gold_to_test_line_ratio`, `f2p_in_statement_frac`, `n_fail_to_pass`, `n_pass_to_pass`, `test_has_exact_string_literal`) (`typicality_lot001.jsonl`, `features_unavailable`).

| Score | Lot-001 median (n = 20) | Reference |
| --- | ---: | --- |
| Pooled typicality vs kept | 0.067 | kept LOO median 0.506 |
| Pooled typicality vs rejected | 0.000 | beyond all 1,264 rejected distances |
| Desourced typicality vs kept | 0.963 | 3 shared retained dims |
| Desourced typicality vs rejected | 0.013 | same 3 dims |
| Per-source typicality | 1.000 | best anchor: gaia |
| Per-source vs rejected | 1.000 | rejected also saturate |
| KDE typicality | 0.346 | kept LOO 0.506 |
| Marginal coverage | 0.892 | share of observed features inside kept q05-q95 |

The pooled reading is the honest one. The lot sits outside the kept region and beyond the entire rejected cloud: generated tasks from an unseen source occupy a part of feature space that the funnel did not produce. The desourced and per-source readings are uninformative by construction, since three shared dims and a max over 29 anchors cannot localize anything. The marginal picture agrees: 89 percent of each lot task's observed features fall inside the kept 5th-to-95th-percentile band, so no single feature is exotic. The combination is. Falling outside both clouds is the expected result for a generated lot from an unseen generator and is not evidence of low quality.

## Method

The feature universe is the union of what each population carries: doc 52 and 54 behaviour features for the funnel populations, doc 40 static and gate features for the kept set's footprint rows, the static set for TB 2.1 and SWE-bench, and the docker-free subset for lot-001. A feature enters the universe when at least 10 kept tasks observe it, and 44 features qualify (`features.universe`). Heavy-tailed count and cost features take a log1p transform. Each task's feature vector is standardized on the kept fit's means and spreads, and a feature the task never observes contributes nothing rather than being imputed.

The region fit shrinks the kept correlation matrix toward the identity (Ledoit-Wolf-style alpha 0.349) with an eigenvalue floor, because the kept n of 82 sits near the 44-feature count. A task's distance is the Mahalanobis distance on the mask-restricted submatrix, and its typicality is the fraction of kept leave-one-out distances at least as large. The KDE is a product Gaussian on the three highest-variance eigendirections of the mask-restricted kept covariance, bandwidth by the normal reference rule (`fit`, `kde`).

The three variants differ only in the reference. Pooled uses one fit over all 82 kept tasks. Per-source fits one region per benchmark's kept subset (identity covariance under global standardization for the 11 singletons) and scores a task by its best typicality across sources, referenced against within-source leave-one-out distances for sources with two or more members and against the all-kept cloud for singletons. Desourced drops every feature whose one-way ANOVA across benchmarks explains more than 0.5 of its variance: behaviour features are measured on the 1,331 stage-1 survivors across 48 benchmarks, and static and gate features on the 82 kept across 29, since that is the only frame that carries them. The dropped list is 36 features. The retained list is n_frontier_trials, n_cells_ge3, full_18, frontier_solve_rate, reward_var, all_trials_solve_rate, ver_reward_partial_rate, and has_traceback (`anova_desourced`).

## What this licenses for stage 8

Doc 50 stage 8 already fixes the rule for descriptive pictures: the Mapper coverage picture is diagnostic only, never a gate and never a bound. A typicality figure belongs in the same slot of the lot dossier. It states where the lot sits relative to the region that expert selection produced, which is the only shape information the 82 kept tasks support at 29 sources and 8 kept tasks at most per source (doc 54). The caveats are fixed: typicality is descriptive, it enters no bound, and it cannot substitute for the stage-9 validity certificate. A lot that scores inside the kept region is not thereby valid, and a lot outside it is not thereby invalid, as lot-001's outside-both placement shows.

## Limits

- The kept set is 82 tasks across 29 benchmarks, with 11 singleton sources. Per-source fits with two to eight members are the widest statistical object here, and the singleton anchors use an identity covariance under global standardization. The per-source saturation is partly a property of that construction, not only of the data.
- Distances are mask-marginalized, not imputed. Populations are compared on different dimension sets (44 kept, 24 funnel, 20 TB 2.1, 12 SWE-bench, 37 lot-001), so cross-population typicalities share a reference but not a geometry. The desourced TB 2.1 and SWE-bench scores rest on a single shared feature (has_traceback) and should be read as absent, not as 1.0.
- The desourced retained set is 8 features, and n_frontier_trials survives at η² = 0.496 just under the 0.5 threshold. A different stated threshold moves that feature and the desourced numbers with it.
- Static-feature η² is measured on the kept 82 across 29 benchmarks, where constant-per-benchmark features score η² = 1 by construction. The behaviour-feature η² uses the 1,331-survivor frame, which is the right denominator for the source confound but includes rejected tasks.
- Lot-001 lacks the frontier-cell block entirely. Its pooled typicality is computed on 37 observed dims, and its outside-both placement could narrow if those features were ever measured.
- One kept task carries no frontier trials and one Harbor-Index id has no reconstructed footprint row. Both are handled by the same observation rules as every other task.

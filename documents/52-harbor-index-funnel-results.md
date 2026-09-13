# Harbor-Index funnel on the public dump: results

Code: `src/task_validation/evidence/harbor_funnel.py`. Tests: `tests/test_harbor_funnel.py`. This doc reports the doc 45 run on the fully extracted public trial dump (doc 48, `data/gold/harbor_funnel_rewards.jsonl`, 768,956 in-scope rows; `data/gold/harbor_adapter_trials.summary.json`).

All labels carry protocol `harbor_index_funnel.reconstructed.2026-09-13`. `survived_stage1` is treatment grade B (reconstructed from public trials, not the private filtering database). `survived_funnel` is grade A (the published 82-task list). External labels are eval-only (doc 43). No model-generated score enters any bound.

## Stage-1 reconstruction

Method. For each of the 6,627 `(benchmark, task_name)` candidates we took the first 3 manifest trial_ids in each of the six frontier cells (`data/raw/harbor-adapter/adapters54.json`), that is `trial_index` 0-2, up to 18 trials per task. A trial counts as a success when `reward > 0` (doc 48). `survived_stage1` is a frontier solve rate at or below 33 percent over the selected trials. Artifacts: `data/gold/harbor_funnel_stage1.jsonl`, `data/gold/harbor_funnel_stage1.summary.json`.

| Count | Value | Expected | Source |
| --- | ---: | ---: | --- |
| Candidates | 6,627 | 6,627 | doc 45; `harbor_funnel_stage1.summary.json` |
| Full 18-trial coverage | 5,684 | 5,684 (doc 48) | `harbor_funnel_stage1.summary.json` |
| At least 3 trials in all six cells | 5,684 | 5,684 (doc 48) | `harbor_funnel_stage1.summary.json` |
| Stage-1 survivors, rate at most 33 percent | 1,331 | 1,311 (doc 45) | `harbor_funnel_stage1.summary.json` |
| Difference vs published | +20, 1.5 percent | within 10 percent rule | `harbor_funnel_stage1.summary.json` |
| Alternative rule `n_succ <= 6` (doc 48 phrasing) | 1,457 | +146, 11.1 percent | `harbor_funnel_stage1.summary.json` |

The rate rule reproduces the published count within 1.5 percent, so no tuning was done. The `n_succ <= 6` phrasing over-admits sparse tasks (6 successes in 9 trials is a 67 percent solve rate) and lands 11 percent high. Six benchmarks produce zero reconstructed survivors under `reward > 0`: aime, algotune, cybergym, humanevalfix, lawbench, quixbugs (`harbor_funnel_stage1.summary.json`, `survivors_by_benchmark`). algotune, cybergym, aime, humanevalfix and quixbugs are binary-reward benchmarks that frontier cells simply solve in this dump (for example, 85 percent of algotune frontier trials return reward at least 1.0, a speedup over the reference). lawbench is graded on a fractional scale where `reward > 0` admits 93 percent of trials (21,819 of 23,358 in-scope lawbench rows in `data/gold/harbor_adapter_trials.jsonl`); the paper presumably applied the appendix H.1 benchmark cutoffs, which are not public. These six benchmarks account for most of the residual disagreement below.

## Labels

Artifact: `data/gold/harbor_funnel_labels.jsonl`, one row per candidate. The 82 index task ids were joined to manifest pairs through each index task's README in `harbor-framework/harbor-index`, which names the upstream record (doc 48 documents this bridge; e.g. `bix-diff-expr-mirna` is BixBench `bix-30-q1`).

| Count | Value | Source |
| --- | ---: | --- |
| Published index tasks | 82 | `data/gold/harbor_index_strata.json` |
| Matched to a manifest pair | 81 | `harbor_funnel_stage1.summary.json`, `label_summary` |
| Unmatched | 1 | same |

The unmatched survivor is `dacode-predict-essay-scores`. Its upstream record is DA-Code `ml-competition-017` (automated essay scoring), but the manifest's dacode sample contains only `dacode-ml-competition-003` and `dacode-ml-competition-007` in that family, so no candidate pair exists for it (task-name set of `data/gold/harbor_funnel_stage1.jsonl`; upstream id from the task README in `harbor-framework/harbor-index` and DA-Code `ml.jsonl`).

Of the 81 matched pairs, 67 also survived the reconstructed stage 1 and therefore carry `survived_2_to_4 = true`. The 14 matched pairs that did not survive our stage-1 reconstruction are: the five algotune tasks, `cybergym-arvo-368`, `cybergym-ossfuzz-42m`, `gaia-compare-sciencedirect-domains`, `gaia-find-flavor-graveyard-rhyme`, `replicationbench-find-galactic-vz-peaks`, `sldbench-discover-vocab-scaling-law`, `tb-train-fasttext`, `usaco-assign-cows-to-barns`, `widesearch-list-bri-projects-2025` (`label_summary.matched_but_not_stage1`). For these the public dump's frontier trials solve above 33 percent where the paper's private database scored them at or below it; algotune and cybergym contribute 7 of the 14 and are the same zero-survivor benchmarks flagged above. `survived_2_to_4` is null, not false, on the 5,296 non-stage-1 candidates (`harbor_funnel_labels.jsonl`).

## Footprint features

Task directories were not fetched. The candidate-level features computable from manifest plus trial rows alone (`harbor_funnel_stage1.jsonl`, per row `features`):

| Group | Features | Availability |
| --- | --- | --- |
| Coverage | `n_frontier_trials`, `n_cells_ge3`, `full_18`, `n_all_trials` | all 6,627 |
| Execution | `input_tokens_mean`, `cache_tokens_mean`, `output_tokens_mean`, `cost_usd_mean`, `cost_usd_total`, `agent_wall_sec_mean`, `exception_rate` | frontier-selected trials, missing only where the cell stored no stats |
| Reward-derived | `frontier_solve_rate`, `frontier_n_succ`, `reward_var`, `all_trials_solve_rate`, six per-cell rates | all rows with at least one frontier trial |

Benchmark id and the six `(agent, model)` cell identities define folds and per-cell features; they are not model inputs. Instruction length is not available: the trial `result.json` config carries a task path but no instruction text (`documents/48` notes the same gap). The remaining doc 40 static features are all unavailable without task directories: execution-gate flags, instruction and test counts, solution size, resource limits, network mode, judge-verifier flag, patch and test diff features, and the solve-rate band (full list in `harbor_funnel_stage1.summary.json`, `unavailable_doc40_features`). "Unavailable" here means not present in manifest or trial rows at all, distinct from a feature that exists but is missing for some candidates.

## Held-out evaluation

Model class identical to doc 40: median imputation, missingness indicators, standardized design matrix, L2 logistic fit (`design_matrix`, `fit_logit`, `predict_logit` in `src/task_validation/evidence/footprint.py`). Leave-one-benchmark-out AUROC is computed on pooled out-of-fold scores with a 400-replicate bootstrap 95 percent interval (`bootstrap_auroc` in `src/task_validation/evidence/irt.py`). The evaluation matrix uses execution features only. Reward-derived features are excluded because `survived_stage1` is a deterministic function of them. Folds whose held-out benchmark has a single class have no per-fold AUROC; pooled out-of-fold AUROC remains defined.

| Label | n | positives | LOBO AUROC (95% CI) | pooled AUROC | folds / undefined |
| --- | ---: | ---: | ---: | ---: | ---: |
| survived_stage1 | 6,627 | 1,331 | 0.663 (0.645, 0.680) | 0.706 | 54 / 6 |
| survived_funnel | 6,627 | 81 | 0.837 (0.793, 0.871) | 0.871 | 54 / 26 |
| survived_2_to_4 | 1,331 | 67 | 0.711 (0.650, 0.771) | 0.782 | 48 / 26 |
| stage-1 solve rate alone on survived_2_to_4 | 1,331 | 67 | 0.502 (0.450, 0.554) | | |

Numbers: `harbor_funnel_stage1.summary.json`, `evals`. Pooled exceeds held-out in every row, the source-recognition gap doc 45 predicted. The single-feature check is the clean result: inside the surviving band, the stage-1 solve rate itself carries no signal (0.50). Whatever the execution footprint ranks, it is not residual difficulty.

## Stop rule

Doc 45: if leave-one-benchmark-out AUROC for `survived_2_to_4` is under 0.65, the funnel footprint is benchmark identity and the plan stops.

The measured value is 0.711 (0.650, 0.771), so the letter of the rule does not trigger. Two cautions before using it. First, leave-one-benchmark-out removes exact benchmark identity but not benchmark family; the five swe-* and related families share execution signatures, so part of the 0.71 can still be source recognition at family level. Second, the confidence interval lower bound sits at 0.65, exactly the stop threshold. The honest reading is that execution footprint predicts funnel survival only at benchmark-family granularity; there is no evidence it transfers to held-out sources as task quality.

## Mapper (diagnostic only)

`data/gold/harbor_funnel_mapper.json` and `harbor_funnel_mapper.png`. Standardized feature matrix (execution plus reward-derived features), lens = stage-1 solve rate, 12 intervals, 40 percent overlap, per-interval DBSCAN (min_samples 5, eps = median 5-NN distance within the interval subset). NumPy and scikit-learn only. Nodes are colored by `survived_funnel` rate.

| Count | Value |
| --- | ---: |
| Points (one candidate had no frontier trials) | 6,626 |
| Nodes | 62 |
| Edges | 88 |
| Nodes with zero survivors | 45 |

Dominant benchmarks among the 45 zero-survivor nodes: labbench 9; bfcl, omnimath, reasoning-gym, spreadsheetbench, swesmith 3 each; simpleqa, usaco, mmmlu, hle, aider-polyglot, research-code-bench 2 each (`harbor_funnel_mapper.json`, `zero_survivor_dominant_benchmarks`). The graph is mostly dark: survivor-containing nodes sit almost entirely in the lowest solve-rate intervals, which restates stage 1 rather than discovering structure. This picture is diagnostic only. It enters no gate, bound, or label.

## Meaning for doc 50 stage 8

The funnel can serve as a taste prior only in the weak sense. The reconstructed stage-1 filter agrees with the published count (1,331 vs 1,311, 1.5 percent), so the public dump is a usable proxy for the private stage-1 input. But stages 2 to 4 are the actual taste step, and the only features available without task directories rank them at AUROC 0.71 held out, plausibly via benchmark-family signatures, while the solve-rate feature that defines stage 1 is at chance inside the band. A prior built on this footprint would encode which benchmark families the funnel preferred, not which tasks. Doc 50 stage 8 should therefore treat the funnel labels as a sanity prior on benchmark provenance, not as a per-task taste signal, and should keep requiring a human sample for any bound (doc 23 section 6, doc 40).

## RESULT

- Stage 1 reconstructed: 6,627 candidates, 5,684 with full 18-trial coverage, 1,331 survivors at solve rate at most 33 percent, +1.5 percent vs the published 1,311. No tuning.
- Labels written for all 6,627 candidates; 81 of 82 published survivors matched to manifest pairs; `dacode-predict-essay-scores` unmatched; 67 matched pairs are also reconstructed stage-1 survivors.
- Held-out AUROC: survived_2_to_4 = 0.711 (0.650, 0.771); stop rule does not trigger by its letter, but the signal is consistent with benchmark-family identity, and stage-1 solve rate alone is at chance (0.502).
- Mapper: 62 nodes, 45 with zero survivors; diagnostic only.
- The funnel is usable as a coarse provenance prior in doc 50 stage 8, not as a per-task taste prior.

# Durability: what keeps a task hard after the models improve

Code: `src/task_validation/evidence/durability.py`. Curves: `data/gold/task_capability_curves.jsonl`. Tiers: `data/gold/model_tiers.json`. No model output enters any bound (doc 43). External labels are eval-only (doc 43).

## Result

A task that is good today and solved by the next model generation is not a good task. The trial dump measures this directly. Across the 6,613 in-scope tasks with at least three trials in each outer capability tier, the median rise in solve rate from the weakest third of models to the strongest is 0.13, tenth percentile 0.00, ninetieth percentile 0.48 (`data/gold/task_capability_curves.summary.json`). 1,035 tasks (15.7% of 6,613) rise more than 0.40 and are already saturating. 1,837 (27.8%) are durable, with a flat curve at a level off the floor and ceiling. 522 (7.9%) are floored and 557 (8.4%) ceilinged (`data/gold/task_capability_curves.summary.json`).

Durability is not predictable from artifact, trajectory, or verifier features. The doc 40 model class reaches leave-one-benchmark-out AUROC 0.605 (0.589, 0.620) on the durable class, and its concordance over same-benchmark task pairs is 0.514 (0.493, 0.533), at chance (`data/gold/durability_prediction.json`). The 0.60 held-out figure is benchmark identity, not a per-task signature.

Expert review did not select for durability. The 80 scored Harbor-Index survivors have a median slope of 0.029 against 0.002 for the 1,262 stage-1 survivors the funnel rejected (Mann-Whitney two-sided p = 0.090, `data/gold/durability_benchmarks.json`). Reviewers removed floored tasks, not steep curves.

Terminal-Bench 4 is already saturating: 27 of its 66 tasks (40.9%) rise more than 0.40 across its own 13 submissions (`data/gold/durability_tb4.json`).

## Preliminary pass reproduction

The preliminary numbers reproduce exactly on task count, median, and tenth percentile, and do not reproduce on the other three cells. The discrepancy is reported, not adopted (`data/gold/task_capability_curves.summary.json`, field `preliminary_pass_comparison`).

| Quantity | Preliminary | Reproduced |
| --- | ---: | ---: |
| tasks with >=3 weak and >=3 strong trials | 6,613 | 6,613 |
| median rise | 0.13 | 0.129 |
| tenth percentile | 0.00 | 0.00 |
| ninetieth percentile | 0.46 | 0.483 |
| flat or negative | 2,234 | 1,292 (rise <= 0) |
| rising more than 0.40 | 921 | 1,035 |

The stated flat count matches a cutoff of rise <= 0.058 and the stated steep count a cutoff near 0.42. Neither has a defensible reading under the module's definitions, so the frozen definitions in this document stand: success is reward > 0, tier rates pool a task's trials per tier, and rise is the top-tier rate minus the bottom-tier rate.

## Capability tiers

The ordering is derived from the data, not asserted. Each model's overall solve rate over all 768,956 in-scope trial rows orders the 16 models, and the ordered list splits into three contiguous tiers of sizes 6, 5, and 5 (`data/gold/model_tiers.json`).

| Tier | Model | Overall solve rate | Trials |
| --- | --- | ---: | ---: |
| bottom | claude-haiku-4-5 | 0.074 | 555 |
| bottom | gpt-5-nano | 0.375 | 54,740 |
| bottom | qwen3-max | 0.512 | 55,128 |
| bottom | claude-haiku-4-5-20251001 | 0.540 | 61,997 |
| bottom | MiniMax-M2.5 | 0.561 | 54,953 |
| bottom | gpt-5-mini | 0.578 | 61,681 |
| mid | mimo-v2-pro | 0.635 | 47,093 |
| mid | deepseek-reasoner | 0.644 | 24,448 |
| mid | glm-5 | 0.649 | 39,559 |
| mid | gemini-3-flash-preview | 0.657 | 60,504 |
| mid | deepseek-chat | 0.664 | 25,673 |
| top | gpt-5.4 | 0.673 | 63,982 |
| top | kimi-k2.5 | 0.684 | 37,252 |
| top | claude-sonnet-4-6 | 0.686 | 59,008 |
| top | claude-opus-4-6 | 0.717 | 60,596 |
| top | gemini-3.1-pro-preview | 0.754 | 61,787 |

Ordering models by their own aggregate performance and then measuring per-task slope against that ordering is circular at the population level. The top tier is guaranteed a higher pooled rate than the bottom tier, so the population median slope is positive by construction. It is not circular at the task level: the ordering only fixes which models are stronger on average, and a single task's slope honestly measures how that task's solve rate changes between the weaker and stronger thirds of the ordering. The population median is licensed as a descriptive statistic of the dump. Per-task slopes and their bootstrap intervals are licensed as measurements of those tasks.

## Per-task curves

Each task gets a solve rate per tier, a slope (top rate minus bottom rate), a level (the mid-tier rate), and a 400-rep per-model-cell parametric bootstrap interval on the slope. Classification uses frozen constants in `durability.py`: floored when every measured tier rate is at or below 0.05, ceilinged when every rate is at or above 0.95, saturating when the slope exceeds 0.40, durable when the slope is at most 0.10, and rising for the residual mid-level band.

| Class | Count | Share of 6,613 |
| --- | ---: | ---: |
| durable | 1,837 | 27.8% |
| rising | 2,662 | 40.3% |
| saturating | 1,035 | 15.7% |
| floored | 522 | 7.9% |
| ceilinged | 557 | 8.4% |

The median level is 0.788: most in-scope tasks sit high. 1,292 tasks have a non-positive rise (`data/gold/task_capability_curves.summary.json`).

## What predicts durability

The label is the durable class among the 6,091 eligible tasks that are not floored (1,837 positives). Features are the stage-1 execution fields plus the trajectory, verifier, and shortcut aggregates joined in `data/gold/harbor_funnel_stage1.jsonl` and `data/gold/harbor_adapter_task_traj.jsonl`, the doc 54 A+B+C+D set minus the two failed-test-signature fields that exist only in the per-trial extract. Solve-rate fields are excluded for the doc 52 reason: they are a near-deterministic function of the same trials the label is built from. The model is the doc 40 class: median imputation, missingness indicators, standardized design, L2 logistic.

| Instrument | Value | Interval | Population |
| --- | ---: | ---: | --- |
| LOBO AUROC, 25 features | 0.605 | (0.589, 0.620) | 6,091 tasks, 54 folds |
| pooled in-sample AUROC | 0.658 | | same |
| same-benchmark pair concordance | 0.514 | (0.493, 0.533) | 213,961 pairs |
| concordance, qualified benchmarks | 0.514 | (0.493, 0.533) | 212,847 pairs, 44 benchmarks |
| positives-weighted mean within AUROC | 0.525 | (0.508, 0.541) | 44 qualified benchmarks |
| cross-benchmark pair concordance | 0.608 | | 7,600,637 pairs |

Source: `data/gold/durability_prediction.json`. Durability is not predictable in any useful sense. The held-out 0.60 is carried entirely by cross-benchmark pairs: same-benchmark pairs sit at 0.51, indistinguishable from chance. A feature that knows a task's benchmark earns the whole score; nothing ranks durable against saturating tasks inside a benchmark.

The ten strongest single features by leave-one-benchmark-out AUROC are all effort proxies (`data/gold/durability_prediction.json`).

| Feature | LOBO AUROC | 95% interval |
| --- | ---: | ---: |
| traj_n_tool_calls_mean | 0.619 | (0.602, 0.633) |
| traj_n_steps_mean | 0.619 | (0.601, 0.633) |
| traj_assistant_chars_mean | 0.611 | (0.594, 0.626) |
| traj_observation_chars_mean | 0.604 | (0.589, 0.618) |
| cost_usd_mean | 0.599 | (0.582, 0.614) |
| traj_agent_wall_sec_mean | 0.597 | (0.579, 0.612) |
| input_tokens_mean | 0.589 | (0.573, 0.604) |
| output_tokens_mean | 0.587 | (0.570, 0.603) |
| agent_wall_sec_mean | 0.587 | (0.569, 0.600) |
| cost_usd_total | 0.584 | (0.567, 0.599) |

Tasks that make frontier agents work longer are modestly more durable. No single feature exceeds 0.62, and the same-benchmark analysis says even that signal does not travel inside a population.

## Durability by benchmark

Slope and level distributions for the twenty benchmarks with the most eligible tasks (`data/gold/durability_benchmarks.json`).

| Benchmark | n | slope median (p25, p75) | level median | durable | rising | saturating | floored | ceilinged |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| reasoning-gym | 575 | 0.041 (0.000, 0.114) | 0.923 | 276 | 130 | 30 | 9 | 130 |
| hle | 249 | 0.253 (0.000, 0.477) | 0.167 | 24 | 75 | 83 | 67 | 0 |
| aider-polyglot | 218 | 0.327 (0.165, 0.487) | 0.746 | 15 | 96 | 84 | 4 | 19 |
| kumo | 212 | 0.043 (0.021, 0.083) | 1.000 | 75 | 37 | 2 | 3 | 95 |
| research-code-bench | 212 | 0.122 (0.027, 0.214) | 0.300 | 71 | 118 | 2 | 21 | 0 |
| dacode | 200 | 0.124 (0.000, 0.267) | 0.760 | 50 | 86 | 25 | 38 | 1 |
| omnimath | 200 | 0.042 (0.000, 0.189) | 0.867 | 78 | 56 | 14 | 14 | 38 |
| simpleqa | 200 | 0.188 (0.104, 0.300) | 0.800 | 42 | 134 | 20 | 1 | 3 |
| spreadsheetbench | 200 | 0.237 (0.121, 0.389) | 0.884 | 39 | 110 | 46 | 5 | 0 |
| gpqa-diamond | 198 | 0.100 (0.040, 0.278) | 0.906 | 60 | 68 | 28 | 1 | 41 |
| featurebench-modal | 185 | 0.229 (0.051, 0.396) | 0.091 | 32 | 74 | 46 | 33 | 0 |
| labbench | 181 | 0.294 (0.200, 0.391) | 0.400 | 24 | 113 | 41 | 3 | 0 |
| lawbench | 181 | 0.120 (0.082, 0.143) | 0.973 | 66 | 113 | 0 | 0 | 2 |
| gaia | 164 | 0.227 (0.102, 0.385) | 0.729 | 31 | 87 | 37 | 3 | 6 |
| humanevalfix | 164 | 0.060 (0.040, 0.080) | 1.000 | 73 | 12 | 1 | 0 | 78 |
| algotune | 154 | 0.080 (-0.024, 0.136) | 0.917 | 88 | 65 | 1 | 0 | 0 |
| mmmlu | 150 | 0.030 (-0.012, 0.129) | 0.766 | 89 | 44 | 2 | 15 | 0 |
| strongreject | 150 | 0.000 (0.000, 0.023) | 0.933 | 102 | 1 | 0 | 0 | 47 |
| bigcodebench | 145 | 0.084 (0.000, 0.199) | 0.258 | 55 | 54 | 11 | 25 | 0 |
| bfcl | 123 | 0.044 (0.000, 0.170) | 1.000 | 49 | 45 | 2 | 6 | 21 |

Benchmarks are built from different stock. strongreject, algotune, mmmlu, kumo, humanevalfix, and reasoning-gym are built from flat curves, most of them at high levels: durable plus ceilinged tasks are 99% of strongreject, 57% of algotune, 59% of mmmlu, and 71% of reasoning-gym (`data/gold/durability_benchmarks.json`). lawbench sits just past the durable cutoff, rising at a median slope of 0.12 with no saturating tasks at all. aider-polyglot, hle, labbench, spreadsheetbench, gaia, and featurebench-modal are built from curves that are still climbing: saturating tasks are 39% of aider-polyglot, 33% of hle, and 23% of spreadsheetbench. hle also carries the largest floored share in the top twenty at 27% (67 of 249), consistent with the broken-task findings the funnel already reported (doc 52, doc 54).

## The funnel's 82 survivors

81 of the 82 published survivors join to manifest tasks (doc 45). 80 have a computable curve (`data/gold/durability_benchmarks.json`).

| Group | n | slope median (p25, p75) | level median | durable | rising | saturating | floored |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| kept survivors | 80 | 0.029 (0.000, 0.116) | 0.026 | 33 | 20 | 3 | 24 |
| rejected stage-1 survivors | 1,262 | 0.002 (0.000, 0.112) | 0.000 | 406 | 354 | 4 | 498 |
| all other eligible tasks | 5,271 | 0.164 | | | | | |

The kept tasks are not flatter than the survivors the funnel rejected. Their median slope is slightly higher (Mann-Whitney two-sided p = 0.090). What review actually selected against was the floor: 30% of kept tasks are floored against 39% of rejected survivors, and the kept level median of 0.026 says the survivors are hard without being dead. Expert reviewers were selecting for valid hard tasks. Durability was incidental to that, in both directions: they kept 33 durable tasks and also kept 20 tasks still rising.

## TB4 and lot-001

Terminal-Bench 4, 66 tasks, scored over its 13 submissions (one model each, five scored trials per task) with the same tier machinery (`data/gold/durability_tb4.json`).

TB 4 and TB 2.1 share no tasks. Normalizing the `terminal-bench/` prefix and case, the 66 TB 4 task names and the 89 TB 2.1 census ids intersect in 0 elements (`data/gold/durability_tb4.json`, `data/gold/tb21_census_manifest.json`). The soundness figures in this repository come from the 2.x pools and the durability figures here come from TB 4, so the two describe different task sets rather than one set measured twice. No figure from one carries to the other.

| Tier | Models | Overall solve rates |
| --- | --- | --- |
| bottom | gemini-3.7-flash, claude-sonnet-5, grok-4.5, gpt-5.6-luna, gemini-3.8-flash | 0.112 to 0.191 |
| mid | grok-4.6, gpt-5.6-terra, claude-opus-4-8, gpt-5.6-sol | 0.203 to 0.373 |
| top | glm-5.3, claude-fable-5, claude-opus-5, claude-fable-5-1 | 0.418 to 0.579 |

| Class | Count of 66 |
| --- | ---: |
| saturating | 27 |
| rising | 22 |
| floored | 11 |
| durable | 6 |

41% of TB4 already rises more than 0.40 across the submission span. The steep tasks include batched-eval-parity (0.49), distributed-dedup (0.68), embedding-drift-monitor (0.76), formal-crypto (0.70), hof-topology-interpenetration (1.00), interleaved-vigenere (0.86), payments-pipeline-fix (0.88), and sound-change-cascade (0.88) (`data/gold/durability_tb4.json`). Only 6 TB4 tasks are durable by the 0.10 slope cutoff. TB4 was built before the 2026 frontier and it shows: a benchmark assembled to be hard for one generation is ordinary work for the next.

lot-001 ran one agent (devin/swe-2-max, k up to 3) through gate C, so no capability ordering exists inside the lot: slope is unavailable and only the level is computable (`data/gold/durability_lot001.json`). Overall solve rate is 0.71 over 52 usable trials. 12 of 20 tasks sit in the [0.10, 0.70] band, 7 are too easy, 1 is too hard (`/home/evan/Documents/eval_tasks/lots/lot-001/gate_c/gate_c.summary.json`). Whether those 12 stay hard is not measurable from this data. It needs trials from a second model family.

## Limits

- The tier ordering is derived from the same trials the slopes are computed on. The circularity is population-level only, as stated above, but it means the median slope of 0.13 cannot be read as "tasks rise by 0.13 in general". Per-task statements stand.
- Slope is measured between two thirds of the model list, not between generations. The 2026-09 models in the top tier and the bottom tier span one snapshot of capability, roughly 0.07 to 0.75 in aggregate solve rate. A task flat across this span can still fall to the next generation, and a task rising here may already be flat at a higher level tomorrow.
- The bootstrap interval treats each model cell's trials as binomial. Cells with few trials give wide intervals. Intervals are not reported per task in this document but are stored per task in `data/gold/task_capability_curves.jsonl`.
- Floored tasks are not certified broken. A floor says every tier failed the task, which is also the signature of a broken verifier. The execution certificate (doc 32, doc 35) decides which of those is true, not this analysis.
- The TB4 comparison uses a different trial count (5 per submission) and a different model span (0.11 to 0.58 aggregate) than the harbor curves. The 0.40 saturating cutoff is applied to both anyway. The TB4 count is a placement, not a claim of identical measurement.
- The durable class is a residual defined by cutoffs (slope <= 0.10, level off the floor and ceiling). The counts move with the constants in `durability.py`. The prediction result, the benchmark ordering, and the funnel comparison do not depend on the exact boundary.

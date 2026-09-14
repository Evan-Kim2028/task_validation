# Harbor-Index 1.0 as an external control

Harbor-Index (arXiv 2609.04298) funnelled 6,627 candidates to 82 tasks with AI audit, exhaustive human audit, and audit-and-fix. If reference/nop interrogation is a valid instrument, its flag rate on these 82 should be near zero, against 2 of 16 on our unaudited eval_tasks pilot and 9 of 27 on TB 2.0 pre-fix (doc 25).

Run 2026-09-12 on the Harbor Hub dataset `harbor-index/harbor-index-1.0` (82 tasks, 69 with a `solution/`). Official verifier, `--agent oracle` and `--agent nop`, one docker job at a time. Runner: `task_validation.evidence.harbor_index_control`. Artifacts: `data/gold/harbor_index_control.jsonl` (164 trials), `.summary.json`. Two infrastructure fixes were needed mid-run: `docker buildx` was absent, which broke every task with `network_mode = "no-network"` (31 tasks, all rerun), and five `bix` tasks write `reward.json` rather than `reward.txt` (read by hand below).

## Results by outcome

| Outcome | Tasks | Notes |
| --- | ---: | --- |
| Reference accepted, nop rejected | 51 | 46 via `reward.txt` plus the 5 `bix` tasks via `reward.json` |
| Reference rejected | 2 | `featurebench-add-feature-xarray-backend-chunks` (NameError `_contains_cftime_datetimes` in 9 tests), `sldbench-discover-vocab-scaling-law` |
| Verifier is an LLM judge (`JUDGE_MODELS` / `JUDGE_REPEATS` env required) | 15 | hle 7, gaia2 5, omnimath 2, widesearch 1; outcome rows observed. A 16th judge-configured task sits in the infra row below, so the judge stratum is 16 (`data/gold/harbor_index_strata.json`) |
| No reference solution shipped | 13 | algotune 5, gso 7, codepde 1; nop rejected on all 13 |
| Infra after the buildx fix | 1 | `hle-shock-wave-density-profile` (judge task) |
| nop accepted (false accept) | 0 | of 82 nop trials |

Six of the 15 judge outcome rows (the five gaia2 tasks plus widesearch) ran to `JudgeConfigurationError` (`JUDGE_MODELS` unset in the control run): the verifier crashed before judging, so their reward-0 rows are not verifier decisions. `data/gold/harbor_index_control.summary.json` splits these as `n_judge_config_crashes` (6); `n_reference_fails` is the real verifier rejections (2).

Reference failure rate among executable, model-free verifiers: **2 of 53 (3.8%)**.

## By source benchmark

| Source | Pass | Ref fail | LLM judge | No reference |
| --- | ---: | ---: | ---: | ---: |
| swebenchverified 5, swebenchpro 4, swelancer 2, swesmith 1, swtbenchverified 1 | 13 | 0 | 0 | 0 |
| featurebench | 3 | 1 | 0 | 0 |
| arcagi2 5, cybergym 2, gaia 3, labbench 4, scicode 3, spider2 2, skillsbench 2, tb 3 | 24 | 0 | 0 | 0 |
| bix | 5 | 0 | 0 | 0 |
| build, dacode, gpqadiamond, qcircuitbench, replicationbench, usaco | 6 | 0 | 0 | 0 |
| sldbench | 0 | 1 | 0 | 0 |
| hle | 0 | 0 | 8 (one went infra) | 0 |
| gaia2 | 0 | 0 | 5 | 0 |
| omnimath, widesearch | 0 | 0 | 3 | 0 |
| algotune, gso, codepde | 0 | 0 | 0 | 13 |

## Comparison across populations (reference fails own verifier, fresh container, no LLM)

| Population | Audit status | Ref failures / executable | Rate |
| --- | --- | ---: | ---: |
| Harbor-Index 1.0 | exhaustive human audit and fix | 2 / 53 | 3.8% |
| SWE-bench test, SRS 100 | 3-rater 2024 read, no execution | 2 / 100 (1 false-accept, 1 ref fail) | 2.0% |
| TB 2.1 post-fix (28 maintained) | maintainer fixes | 2 / 27 | 7.4% |
| eval_tasks (ours) | none | 2 / 16 | 12.5% |
| TB 2.0 pre-fix (28 maintained) | none, later repaired | 9 / 27 | 33% |

The instrument orders these populations the way their audit history predicts. Audited pools are low but not zero.

## Two boundaries the control exposed

1. **LLM-judge verifiers.** 16 of 82 Harbor-Index tasks (19.5%) are judge-configured: a model ensemble driven by environment variables (`data/gold/harbor_index_strata.json`). 15 returned a judge outcome row in this run; `hle-shock-wave-density-profile` went infra on the oracle. Reference/nop interrogation cannot run without supplying a judge, and supplying one puts a model inside the evaluator being certified. These tasks need a separate protocol: run the official judge as configured, treat judge nondeterminism as a verifier property, and keep the human sample.
2. **Tasks without a reference.** 13 of 82 ship no solution (optimization and speed-up families). Only the nop probe applies; correct acceptance is unmeasured. A certification intake should require a reference or an equivalent positive control.

## What is not established

Whether the two reference failures reproduce upstream. `featurebench-add-feature-xarray-backend-chunks` is a missing helper in the shipped environment and looks like a real residual defect; `sldbench` produced no test names in its failure output. Both are queued for human review. The five `bix` rewards were read from `reward.json` by hand; the runner should be extended to read both files.

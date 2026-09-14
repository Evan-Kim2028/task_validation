# A design-based bound on residual task invalidity in agent benchmarks

All consolidated numbers live in `documents/61-results.md`.
This draft cites the same artifacts; doc 61 is the reference table.

Status: draft. Every number cites a document or a `data/gold/` artifact. Anything that could not be verified against an artifact is marked TODO-VERIFY.

## Abstract

A benchmark buyer asks two questions: how many of these tasks are broken, and how good are they. Only the first currently has a numeric answer. We give it one: a one-sided 95% upper confidence bound on the residual rate of materially invalid tasks in a frozen task pool, computed from a probability sample adjudicated by humans or by a grade-A execution assay of verifier consistency. Cheap evidence ranks the review queue but never enters the bound, and taste stays out of the validity estimand. Across the populations measured so far, the method released two bounds (a completed prefix of the SWE-bench extension draw at 4.65% and the 4,569-task generated SETA-Env pool at 2.32%, `data/gold/swe_srs300.certificate.json`, `data/gold/gen_gate_seta.certificate.json`), rejected a Terminal-Bench 2.1 census at 5.6% (`data/gold/tb21_census.certificate.json`), and rejected a 37,484-task generated pool at 6.6% under a restricted bound and 9.5% under a conservative one (`data/gold/gen_gate_rst.certificate.json`, `data/gold/gen_gate_rst.conservative.certificate.json`). Every cheaper substitute failed: static specification features rank at chance, model-assisted bounds never beat the plain sample, specification calibration does not transport across benchmarks, and a reconstruction of the Harbor-Index curation funnel predicts survivor status at only 0.61 to 0.71 held-out AUROC (`data/gold/harbor_funnel_traj_eval.json`). The reconstruction is itself a data contribution: curation labels for all 6,627 Harbor-Index candidates (docs 52, 54).

## 1. The problem

A buyer of an agent benchmark asks two questions. How many of these tasks are broken? And how good are they? These are different questions, and only the first currently has a numeric answer (docs 23, 24).

Broken means materially invalid under a named protocol. The execution construct is verifier consistency: in a fresh container, the reference solution passes its own verifier and an empty submission is rejected. A unit is invalid under this protocol when the reference fails its own verifier or an empty submission is accepted (protocol `verifier_invalid.fresh_environment.execution`, a historical string that names the consistency construct; docs 21, 32, 35). A second construct, specification invalidity, is a reading property: a competent reader cannot tell what behavior the task rewards, or the specification rewards the wrong thing. It is measured by human raters, as in the 2024 three-rater SWE-bench labels (protocol `openai-swe-bench-verified-2024-conservative`; docs 4, 33). That construct has measured reliability: human Fleiss kappa on the per-rater material bit is 0.39, and one rater against the three-rater majority agrees 0.85 with false-negative rate 0.16 (doc 23 section 6, doc 34, `data/gold/rater_noise.json`). That noise floor is why the human protocol mandates two raters plus tiebreak on disagreement (doc 30). The two constructs are different estimands and are never pooled (doc 32).

### Consistency is necessary, not sufficient

Passing the execution assay establishes verifier consistency, not verifier validity. A consistent verifier may still:

1. under-test the requirement: its checks run and behave but cover less than the specification asks;
2. accept a wrong implementation: the nop probe shows the empty solution fails, not that a wrong non-empty solution fails;
3. be over-permissive: a verifier that passes nearly everything is consistent on the two probes and wrong on the rest;
4. depend on accidental environment state: the pass can hold only on the image as built today.

Consistency is necessary evidence. It is not sufficient evidence that the verifier measures the intended capability.

Good means taste: realistic, difficult, discriminating, diverse, novel, and the other population-design properties a buyer wants (doc 24, doc 31). Taste is graded, not binary. It needs frontier-agent trials and human rubric labels. It is measured on the accepted pool and never defines it (doc 24).

Both questions matter, but they fail differently. A task can be valid and boring, or invalid and beautiful (doc 24). Answering "how good" requires taste instruments the field does not yet have. Answering "how many are broken" requires only a count and a sample. This paper reports the count.

## 2. The estimand

The estimand is p, the share of materially invalid units in a frozen pool of N tasks, under one named label protocol. Y_i is binary per unit per protocol. A label is valid evidence only when it carries its protocol and a treatment grade; only grades A and B enter a bound, and grade C or D evidence leaves the unit unadjudicated rather than counted (doc 32). Protocols are never pooled into one Y (doc 32).

Three rules keep the estimand honest:

1. No model output enters a published bound. A model may order the review queue and nothing more (doc 43).
2. External audit labels are eval-only. They evaluate transfer of the instrument; they are not gold labels for a certificate (doc 43).
3. Taste is never folded into the validity estimand. Difficulty, discrimination, realism, diversity, and novelty are separate instruments applied after acceptance (doc 24).

## 3. Method

The pipeline has six steps.

1. **Cheap evidence on every task.** Static features and the execution gate run over the whole pool. The gate is reference-passes and nop-rejected in a fresh container, at roughly 30 s to 3 min per trial, with no model in the loop (doc 23). Evidence ranks a review queue. It does not label the population (doc 43).
2. **Freeze the manifest.** IDs, N, n, seed, and design are recorded before any verdict is read. Units may not be dropped after outcomes are seen (doc 32).
3. **Draw a probability sample.** Simple random sampling without replacement is the inferential arm. Risk-guided arms are discovery only (docs 7, 22).
4. **Adjudicate the sample.** Either humans under a two-rater-plus-tiebreak design (doc 30), or the grade-A machine assay for execution-verifier tasks (docs 35, 41, 47, 53). Judge-verifier strata have no machine certificate, and no-reference strata get only a one-sided machine bound on the nop probe; the two-sided estimand on both requires the human design (doc 44).
5. **Compute the bound.** A one-sided 95% hypergeometric upper confidence bound on p. Release iff UCB < epsilon, currently epsilon = 0.05. When n = N the bound equals the observed rate (doc 32).
6. **Check coverage by Monte Carlo.** On known populations the SRS hypergeometric bound covers at or above nominal at low prevalence, while the stratified normal bound undercovers (coverage 0.90 at p = 0.02, `data/gold/coverage_n100_p02.json`; docs 7, 12). As a machinery check on a population whose truth is known by census, a frozen SRS of 30 from Terminal-Bench 2.1 drew 0 invalid units and produced UCB 7.9%, covering the census truth of 5.6% (doc 41; `data/gold/tb21_srs30.certificate.json`).

Machine certificates carry `replaces_human_sample: false` and never substitute for the human probability sample (doc 32).

## 4. Results

Every population certified or measured so far, ordered by measured invalidity. The kind column says whether the row is a design-based certificate or a diagnostic census or sample; diagnostic rows are measurements on enumerated sets or pilots, not bounds.

| Population | Kind | Design | N | n | k | p-hat | One-sided 95% UCB | Decision | Protocol, grade, adjudicator | Source |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| TB 2.0 pre-fix pairs | diagnostic census | all diffable pairs, a natural counterfactual set | 27 | 27 | 9 | 0.333 | none | n/a | execution gate, A, machine | doc 25, `data/gold/tb21_pairs.summary.json` |
| eval_tasks pilot | diagnostic census | census of the 16 complete local packages | 16 | 16 | 2 | 0.125 | none | n/a | execution interrogation, A/B, machine | docs 20, 21 |
| TB 2.1 full pool | certificate, census | census, n = N | 89 | 89 | 5 | 0.0562 | 0.0562 | reject | `verifier_invalid.fresh_environment.execution`, A, machine | `data/gold/tb21_census.certificate.json`, doc 41 |
| SWE-bench frozen 20 | diagnostic sample | stratified 2x2 pilot by 2024 label and cheap risk | 1,699 | 20 | 1 | 0.050 on the drawn set | none | n/a | execution gate, A, machine | `data/gold/swe_2x2_exec.summary.json`, doc 26 |
| Harbor-Index executable stratum (53 of 82 tasks) | diagnostic census | census of the execution stratum | 53 | 53 | 2 | 0.0377 | none | n/a | `verifier_invalid.fresh_environment.execution`, A, machine | `data/gold/harbor_index_control.summary.json`, `data/gold/harbor_index_strata.json`, docs 28, 44 |
| RST generated pool | certificate | SRS of frozen manifest; coverage 195 of 200 | 37,484 | 200 | 7 restricted; 12 conservative | 0.0359; 0.060 | 0.0663 restricted; 0.0953 conservative | reject under both | `verifier_invalid.fresh_environment.execution`, A, machine | `data/gold/gen_gate_rst.certificate.json`, `data/gold/gen_gate_rst.conservative.certificate.json`, doc 53 |
| SWE-bench SRS-300 completed prefix | certificate, partial | SRS prefix of the frozen 300 draw | 1,699 | 190 of 300 planned | 4 | 0.0211 | 0.0465 | release, partial | `verifier_invalid.fresh_environment.execution`, A, machine | `data/gold/swe_srs300.certificate.json`, doc 47 |
| SWE-bench SRS-100 | certificate | SRS | 1,699 | 100 | 2 | 0.020 | 0.0606 | reject | `verifier_invalid.fresh_environment.execution`, A, machine | `data/gold/swe_srs100.certificate.json`, doc 35 |
| SETA-Env generated pool | certificate | SRS of frozen manifest | 4,569 | 200 | 1 | 0.005 | 0.0232 | release | `verifier_invalid.fresh_environment.execution`, A, machine | `data/gold/gen_gate_seta.certificate.json`, doc 53 |
| TB 2.1 SRS-30 | certificate, machinery check | SRS against a pool with known census truth | 89 | 30 | 0 | 0.0 | 0.0787 | covers truth | `verifier_invalid.fresh_environment.execution`, A, machine | `data/gold/tb21_srs30.certificate.json`, doc 41 |

Three qualifications belong next to the table.

The SRS-300 row is a completed-prefix certificate. The frozen manifest drew 300 units; 297 executed both treatments; three matplotlib units returned no gold report; the bound covers the first 190 adjudicated units of the draw, not all 300 (`data/gold/swe_srs300.certificate.json`, `data/gold/swe_srs300_exec.summary.json`, doc 47).

The RST row reports two bounds, not a disagreement. Five of the 200 sampled units stayed unadjudicated after retries. The restricted bound drops them and covers the covered subpopulation of 37,479; the conservative bound counts all five as invalid over the full 37,484. Both reject (doc 53).

The Harbor-Index row covers only the executable stratum: 29 of the 82 published tasks sit outside it, 16 judge-configured and 13 with no reference (`data/gold/harbor_index_strata.json`, doc 44). Its 3.8% is a measurement on the executable stratum of an externally curated population, not a certificate.

Every certified row uses the identical execution assay on a frozen manifest under one protocol string, so the cross-population comparison is one estimand measured on several pools, not a comparison of different definitions. Label disagreement across external audit sources (docs 37, 38, 40) is a caveat on the specification construct, not on this table.

The generated pools measured so far are not worse than the human-curated ones on verifier consistency. RST measures 3.6% on the restricted bound and SETA-Env measures 0.5% (`data/gold/gen_gate_rst.certificate.json`, `data/gold/gen_gate_seta.certificate.json`), against Terminal-Bench 2.1 at 5.6% (`data/gold/tb21_census.certificate.json`) and the Harbor-Index executable stratum at 3.8% (`data/gold/harbor_index_control.summary.json`). That is an observation across four pools, not an established effect. The populations differ on every axis that could produce it: task complexity, verifier design, authoring pipeline, environment and base image, benchmark age and maintenance state, domain mix, test count, task size, and the selection effects of each pool's keep rule. One hypothesis consistent with the observation is construction order: a generator that builds the solution first and wraps a task around it gets oracle-passes-nop-fails by construction, while a human author writes the reference and the tests separately and must make them agree by hand. The comparison motivates the solution-first explanation. It does not establish it. And the observation covers one defect class only: the bound is on verifier consistency, not on specification invalidity, taste, or the judge and no-reference strata (docs 24, 44).

The remaining pattern is that unmaintained pools sit high and maintained pools sit near the boundary: TB 2.0 pre-fix at 33%, our own pilot at 12.5%, the raw RST pool at 3.6% measured and bounded at 6.6 to 9.5%, TB 2.1 rejecting at 5.6%, and the Harbor-Index executable stratum at 3.8%. The released bounds are the SWE-bench prefix at 4.65% and SETA-Env at 2.32%.

### Sensitivity to epsilon

The decision rule is release iff the bound is below epsilon. Epsilon is a policy parameter the consumer supplies, not a number the method produces. The 5 percent value used throughout carries no scientific meaning. The same certificates re-decided at other epsilons, using the ucb95 values already in the certificate files:

| Population | One-sided 95% UCB | epsilon 1% | epsilon 2% | epsilon 5% | epsilon 10% | Source |
| --- | ---: | --- | --- | --- | --- | --- |
| SETA-Env generated pool | 2.32% | reject | reject | release | release | `data/gold/gen_gate_seta.certificate.json` |
| SWE-bench SRS-300 completed prefix | 4.65% | reject | reject | release | release | `data/gold/swe_srs300.certificate.json` |
| TB 2.1 full pool, census | 5.62% | reject | reject | reject | release | `data/gold/tb21_census.certificate.json` |
| SWE-bench SRS-100 | 6.06% | reject | reject | reject | release | `data/gold/swe_srs100.certificate.json` |
| RST generated pool, restricted bound | 6.63% | reject | reject | reject | release | `data/gold/gen_gate_rst.certificate.json` |
| TB 2.1 SRS-30, machinery check | 7.87% | reject | reject | reject | release | `data/gold/tb21_srs30.certificate.json` |
| RST generated pool, conservative bound | 9.53% | reject | reject | reject | release | `data/gold/gen_gate_rst.conservative.certificate.json` |

The TMax-15K manifest produces no row: its certificate is incomplete with 199 of 200 units unadjudicated (`data/gold/gen_gate_tmax.certificate.json`, doc 53). The diagnostic rows of the results table carry no bound, so no decision.

## 5. Negative results

Each candidate shortcut was tried on the populations evaluated and failed there. These are claims about those populations, not general impossibility results. On them, none replaces the probability sample.

| Shortcut tried | Result on the populations evaluated | Source |
| --- | --- | --- |
| Static specification features | On the 1,699 SWE-bench tasks under the 2024 conservative label: at chance, AUROC 0.41 / 0.42 | doc 23, `data/gold/causal_ablation.summary.json` |
| Better static ranker as certificate | On the same SWE-bench label set: grouped-OOF AUROC about 0.70 still leaves 34% invalid in the lowest-risk 5% tail | docs 23, 27, 33 |
| Prediction-powered inference | On the SWE-bench label set and the synthetic coverage lab: at AUROC 0.70 the effective-sample gain is about 1.11x and the normal UCB undercovers at low prevalence | doc 27, `data/gold/ppi_lab.json` |
| Judge-calibrated bound | On the 1,699-task SWE-bench label set with a ranking instrument of AUROC 0.81: never narrower than the SRS arm | doc 36, doc 43, `data/gold/judge_bound_lab.json` |
| Cross-benchmark spec calibration | Across the five label populations of the footprint holdout: Rogan-Gladen transfer undercovers or goes vacuous in 8 of 10 cells | doc 40, `data/gold/footprint.holdout.json` |
| Funnel reconstruction as predictor | On the Harbor-Index candidate funnel: stage-1 rule reconstructs within 1.5% (1,331 vs published 1,311); curation survival transfer predicts at 0.711 leaving out benchmarks and 0.612 leaving out families; adding trajectory, verifier, and shortcut features degrades held-out performance; stage-1 solve rate alone is at chance (0.502) inside the survivor band. The pooled AUROC is confounded by cross-benchmark pairs; restricting pairs to the same benchmark, held-out scores still rank kept tasks above rejected survivors at 0.685 concordance on the execution set (2,843 pairs, 95% CI 0.59 to 0.76), concentrated in HLE at 8 kept tasks. No benchmark has more than 8 kept tasks, so a per-population model cannot be fit and validated on this data: the transfer claim is refuted, the per-population hypothesis is untested | `data/gold/harbor_funnel_stage1.summary.json`, `data/gold/harbor_funnel_traj_eval.json`, `data/gold/harbor_funnel_within_benchmark.json`, docs 52, 54 |

The AUROC rows deserve a precise reading. Ranking accuracy and inferential validity are different objectives. A predictor that orders a review queue well does not become a valid estimator of the residual rate. The finding is that ordering works and estimation fails on these populations, not that the judge or the ranker was insufficiently accurate.

The implication is the paper's working rule: a fresh probability sample from the frozen pool remains necessary. Models and cheap features order the queue. They do not certify (doc 43).

## 6. The funnel reconstruction as a data contribution

The public Harbor-Adapter trial dump (`kendx/Harbor-Adapter`, revision fa353815, doc 55) contains 793,698 trial rows, of which 768,956 are in-scope reward rows spanning 60 benchmarks and 8,468 distinct task pairs (`data/gold/harbor_adapter_trials.summary.json`, `data/gold/harbor_adapter_traj.summary.json`). The manifest carries 16 models and 6 agents (doc 55). From it we reconstructed the Harbor-Index funnel and publish per-task labels.

| Artifact | Content | Counts |
| --- | --- | --- |
| `data/gold/harbor_funnel_stage1.summary.json` | Stage-1 reconstruction | 6,627 candidates; 5,684 with full 18-trial coverage; 1,331 reconstructed survivors vs 1,311 published, a difference of 20 or 1.5% |
| `data/gold/harbor_funnel_labels.jsonl` | One label row per candidate | 6,627 rows; `survived_stage1` grade B, `survived_funnel` and `survived_2_to_4` grade A; protocol `harbor_index_funnel.reconstructed.2026-09-13`; external, eval-only (doc 43) |
| Published-survivor match | Join against the 82-task list | 81 of 82 matched; `dacode-predict-essay-scores` unmatched |
| `data/gold/harbor_funnel_traj_eval.json` | Feature-group held-out evaluation | 0.711 benchmark-held-out, 0.612 family-held-out |
| `data/gold/harbor_funnel_within_benchmark.json` | Within-benchmark evaluation correcting the pooled-AUROC confound | Held-out within-benchmark concordance 0.685 on the execution set (2,843 pairs); per-benchmark cross-validation unevaluable, maximum 8 kept tasks per benchmark |
| `data/gold/harbor_funnel_mapper.json` | Topological map of the candidate space | 62 nodes, 88 edges (doc 52) |
| `data/gold/harbor_funnel_hidden_requirement.jsonl` | Hidden-requirement flag | Empty by construction: the named failed-test signature is computable only for two rejected skillsbench tasks, so the flag is unevaluable on the public dump, not evidence that hidden requirements are absent (doc 52) |

These labels are provenance and a queue-ordering prior. They are external labels, eval-only, and they are not a per-task taste certificate and not a bound (doc 43, doc 52).

## 7. What we do not claim

- We do not claim the bound exists elsewhere. The claim is that within agent-benchmark task populations, nobody else reports a design-based bound on residual invalidity (docs 30, 46). The search behind it ran on 2026-09-13 and 2026-09-14 and is recorded in doc 46. Audits are not new.
- We do not claim the assay proves verifier validity. Passing it establishes verifier consistency, which is necessary evidence, not sufficient. The four false-negative modes are listed in section 1 (doc 32).
- We do not claim machine coverage of judge-verifier or no-reference tasks on the two-sided consistency estimand. Those strata need the human design (doc 44); the no-reference stratum gets at most a one-sided nop bound, which measures incorrect_accept only.
- We do not claim a model admission filter certifies anything. Models order the queue (doc 43).
- We do not claim taste. The funnel labels are provenance, not taste scores (docs 45, 52).
- We do not claim a bound from external audit labels. They are eval-only (doc 43).
- We do not claim environment-independent verdicts. The bound is on today's image; `django__django-10097` may be image drift and is invalid under today's image regardless (doc 23).
- We do not claim the RST gate measured a filtered release. It measured the raw generator pool (doc 53).
- We do not claim a complete 300-unit certificate for SWE-bench. The released bound covers a completed prefix of 190 (doc 47).
- We do not claim a bound on specification invalidity for the new pools. The only specification labels are the 2024 SWE-bench three-rater labels and the TB 2.0 maintenance diff (docs 25, 33), and they do not transfer (doc 40).

## 8. Limitations

| Limitation | Detail | Source |
| --- | --- | --- |
| 82 positives | The funnel evaluation has 82 positive labels, 81 matched to manifest pairs | doc 45, `data/gold/harbor_funnel_stage1.summary.json` |
| Behaviour-only features | Funnel features are execution, trajectory, verifier, and shortcut signals; no instruction semantics | doc 52 (`unavailable_doc40_features`) |
| One review panel | The curation label reflects Harbor-Index's single review pipeline (14 reviewers plus a 3-person panel); our own human probability sample has not run | docs 31, 50 |
| Diversity quotas inside the label | `survived_2_to_4` conflates broken, too easy, diversity quota, and panel taste | doc 45 |
| Judge stratum uncovered | 16 judge-configured and 13 no-reference tasks of 82 have no machine certificate | doc 44, `data/gold/harbor_index_strata.json` |
| No downstream lift experiment | Whether gating improves downstream evaluation or training outcomes is unmeasured | doc 50 |
| Execution-assay false negatives | A consistent verifier can still under-test the requirement, accept a wrong implementation, be over-permissive, or depend on accidental environment state; none of the four modes enters the bound | section 1, doc 32 |
| Per-population taste hypothesis untested | The funnel and conditional-taste results motivate measuring taste inside each population; no per-population taste instrument has run on any pool | docs 52, 59 |
| No human ratings collected | Every bound in this draft is machine-adjudicated grade A; no new human rating was collected | doc 23 section 8, docs 43, 50 |
| TMax one-sided coverage | TMax-15K ships no reference solutions; at most a one-sided bound on the accepts-an-empty-solution class is possible there, and the run is deferred | doc 53, `data/gold/gen_gate_tmax_manifest.json` |
| Partial certificates | SRS-300 covers 190 of 300 drawn units; the RST restricted bound covers 195 of 200 | docs 47, 53 |
| Environment dependence | Execution verdicts are per-image; drift can change a verdict | doc 23 |
| Specification invalidity unbounded on new pools | Human spec review has not run on the RST or Harbor pools | doc 50 |

## 9. Related work

Audits report found-issue rates. Generation pipelines ship keep rules. None reports a design-based bound on the residual invalid-task rate of a filtered agent-benchmark pool (docs 30, 46). The search behind this claim ran on 2026-09-13 and 2026-09-14 and is recorded in doc 46.

| Work | What it reports | Why it is not this bound | Source |
| --- | --- | --- | --- |
| ABA (arXiv 2605.26079) | Agentic audit of 168 benchmarks; 25.7% of audited tasks with major issues; sampled precision 72.7 to 81.8% | A found-issue rate, not a population CI | docs 3, 30, 46 |
| BenchGuard (arXiv 2604.24955) | Cross-artifact LLM audit; 12 author-confirmed defects on ScienceAgentBench; 83.3% match on BIXBench-50 | Defect discovery, no CI | docs 3, 30 |
| Harbor-Index (arXiv 2609.04298) | Funnel 6,627 to 82 with AI audit, exhaustive human review, audit-and-fix | Reviewed every survivor; the about-a-third-broken remark is a funnel observation, not a bound on 6,627 | docs 3, 28, 30 |
| OpenAI Pro audit | 286 of 731 auto-flagged, 200 pipeline-broken, 249 human-broken | Targeted review after flags, no designed sample CI | docs 3, 15, 46 |
| GateTruth (arXiv 2608.12635) | Mutant-kill floor at 95%; self-audit 46 of 60 | Verifier scoring, not a task-validity bound | doc 46 |
| T1 (arXiv 2609.11042) | Statistical filter over RST-38k with a model audit | A model admission filter, no bound | doc 46 |
| CalibForge (arXiv 2608.06352) | Adversarial calibration; 19% first-probe keep rising to 96% after revisions | Construction-time QC, no residual bound | doc 46 |
| FrogNano / TaskPilot (arXiv 2609.07925) | Band-gated admission on a 4B solve rate | A difficulty gate, not a validity bound | doc 46 |
| Kato and Nakagawa (arXiv 2604.06116) | Sequential audit sampling; bounds a financial-statement lot deviation rate and the sequential procedure's own error probabilities (v1, 7 Apr 2026, titled Sequential Audit Sampling with Statistical Guarantees) | Financial-statement auditing, not agent-benchmark tasks | doc 30 |
| Dong et al. (arXiv 2607.28367) | Wilson interval on the rate of wrong FAIL verdicts over 150 failure trajectories | A verdict-error CI among failures, not a bound on a task pool's residual invalidity | doc 30 |

The exact gap statement: none of these reports a design-based, coverage-checked, one-sided finite-population confidence bound on residual task invalidity of an accepted agent-benchmark pool (doc 30, doc 46 part 2; search run 2026-09-13 and 2026-09-14, recorded in doc 46). The nearest statistical neighbors bound different estimands: FAQ and Noisy but Valid bound model scores and judge error; Gema et al. report a sampled item-error point estimate on MMLU without a UCB; Kato and Nakagawa bound a financial lot deviation rate; Dong et al. bound a wrong-verdict rate among failure trajectories (doc 30).

The inference itself is not new. The design is ordinary finite-population attribute sampling: one-sided Clopper-Pearson and hypergeometric bounds, in the tradition of acceptance sampling (Dodge-Romig LTPD plans, ANSI/ASQ Z1.4) and model-assisted survey estimation (Särndal) (doc 30). The nearest 2026 statistical neighbor is Kato and Nakagawa (arXiv 2604.06116), which works in accounting rather than benchmark auditing. Dong et al. (arXiv 2607.28367) apply a standard interval to a verdict error rate. The contribution here is narrower: the application of design-based certification to agent-benchmark task populations, and the empirical demonstration that several tempting shortcuts fail to preserve coverage.

## 10. Reproducibility

The replication note is doc 55. Certificates, manifests, and summaries cited above live under `data/gold/`. The gate's decontamination rule is doc 49. Drift known at draft time is listed in doc 57.

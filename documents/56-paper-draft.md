# A design-based bound on residual task invalidity in agent benchmarks

Status: draft. Every number cites a document or a `data/gold/` artifact. Anything that could not be verified against an artifact is marked TODO-VERIFY.

## Abstract

A benchmark buyer asks two questions: how many of these tasks are broken, and how good are they. Only the first currently has a numeric answer. We give it one: a one-sided 95% upper confidence bound on the residual rate of materially invalid tasks in a frozen task pool, computed from a probability sample adjudicated by humans or by a grade-A execution assay. Cheap evidence ranks the review queue but never enters the bound, and taste stays out of the validity estimand. Across the populations measured so far, the method released one bound (a completed prefix of the SWE-bench extension draw at 4.65%, `data/gold/swe_srs300.certificate.json`), rejected a Terminal-Bench 2.1 census at 5.6% (`data/gold/tb21_census.certificate.json`), and rejected a 37,484-task generated pool at 6.6% under a restricted bound and 9.5% under a conservative one (`data/gold/gen_gate_rst.certificate.json`, `data/gold/gen_gate_rst.conservative.certificate.json`). Every cheaper substitute failed: static specification features rank at chance, model-assisted bounds never beat the plain sample, specification calibration does not transport across benchmarks, and a reconstruction of the Harbor-Index curation funnel predicts survivor status at only 0.61 to 0.71 held-out AUROC (`data/gold/harbor_funnel_traj_eval.json`). The reconstruction is itself a data contribution: curation labels for all 6,627 Harbor-Index candidates (docs 52, 54).

## 1. The problem

A buyer of an agent benchmark asks two questions. How many of these tasks are broken? And how good are they? These are different questions, and only the first currently has a numeric answer (docs 23, 24).

Broken means materially invalid under a named protocol. The execution construct is concrete: the reference solution fails its own verifier, or an empty submission is accepted, in a fresh container (`verifier_invalid.fresh_environment.execution`; docs 21, 32, 35). A second construct, specification invalidity, is a reading property: a competent reader cannot tell what behavior the task rewards, or the specification rewards the wrong thing. It is measured by human raters, as in the 2024 three-rater SWE-bench labels (protocol `openai-swe-bench-verified-2024-conservative`; docs 4, 33). The two constructs are different estimands and are never pooled (doc 32).

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
4. **Adjudicate the sample.** Either humans under a two-rater-plus-tiebreak design (doc 30), or the grade-A machine assay for execution-verifier tasks (docs 35, 41, 47, 53). Judge-verifier and no-reference strata have no machine certificate; they require the human design (doc 44).
5. **Compute the bound.** A one-sided 95% hypergeometric upper confidence bound on p. Release iff UCB < epsilon, currently epsilon = 0.05. When n = N the bound equals the observed rate (doc 32).
6. **Check coverage by Monte Carlo.** On known populations the SRS hypergeometric bound covers at or above nominal at low prevalence, while the stratified normal bound undercovers (coverage 0.90 at p = 0.02, `data/gold/coverage_n100_p02.json`; docs 7, 12). As a machinery check on a population whose truth is known by census, a frozen SRS of 30 from Terminal-Bench 2.1 drew 0 invalid units and produced UCB 7.9%, covering the census truth of 5.6% (doc 41; `data/gold/tb21_srs30.certificate.json`).

Machine certificates carry `replaces_human_sample: false` and never substitute for the human probability sample (doc 32).

## 4. Results

Every population certified or measured so far, ordered by measured invalidity. Rows marked diagnostic are not design-based bounds: they are measurements on enumerated sets or stratified pilots.

| Population | Design | N | n | k | p-hat | One-sided 95% UCB | Decision | Protocol, grade, adjudicator | Source |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| TB 2.0 pre-fix pairs | Natural counterfactual set, all diffable pairs | 27 | 27 | 9 | 0.333 | none | diagnostic | execution gate, A, machine | doc 25, `data/gold/tb21_pairs.summary.json` |
| eval_tasks pilot | Census of the 16 complete local packages | 16 | 16 | 2 | 0.125 | none | diagnostic | execution interrogation, A/B, machine | docs 20, 21 |
| RST pool, conservative bound | SRS of frozen manifest, uncovered units counted invalid | 37,484 | 200 | 12 | 0.060 | 0.0953 | reject | `verifier_invalid.fresh_environment.execution`, A, machine | `data/gold/gen_gate_rst.conservative.certificate.json`, doc 53 |
| TB 2.1 census | Census, n = N | 89 | 89 | 5 | 0.0562 | 0.0562 | reject | `verifier_invalid.fresh_environment.execution`, A, machine | `data/gold/tb21_census.certificate.json`, doc 41 |
| SWE-bench frozen 20 | Stratified 2x2 pilot by 2024 label and cheap risk | 1,699 | 20 | 1 | 0.050 on the drawn set | none | diagnostic | execution gate, A, machine | `data/gold/swe_2x2_exec.summary.json`, doc 26 |
| Harbor-Index control | Census of the 82 published tasks; 53 in the execution stratum | 82 | 53 | 2 | 0.0377 of executed | none | diagnostic, external labels eval-only | `verifier_invalid.fresh_environment.execution`, A, machine | `data/gold/harbor_index_control.summary.json`, `data/gold/harbor_index_strata.json`, docs 28, 44 |
| RST pool, restricted bound | SRS restricted to the covered subpopulation | 37,479 | 195 | 7 | 0.0359 | 0.0663 | reject | `verifier_invalid.fresh_environment.execution`, A, machine | `data/gold/gen_gate_rst.certificate.json`, doc 53 |
| SWE-bench SRS-300 | SRS prefix certificate, partial | 1,699 | 190 of 300 planned | 4 | 0.0211 | 0.0465 | release, partial | `verifier_invalid.fresh_environment.execution`, A, machine | `data/gold/swe_srs300.certificate.json`, doc 47 |
| SWE-bench SRS-100 | SRS | 1,699 | 100 | 2 | 0.020 | 0.0606 | reject | `verifier_invalid.fresh_environment.execution`, A, machine | `data/gold/swe_srs100.certificate.json`, doc 35 |
| TB 2.1 SRS-30 | SRS machinery check against known census truth | 89 | 30 | 0 | 0.0 | 0.0787 | covers truth | `verifier_invalid.fresh_environment.execution`, A, machine | `data/gold/tb21_srs30.certificate.json`, doc 41 |

Three qualifications belong next to the table.

The SRS-300 row is a completed-prefix certificate. The frozen manifest drew 300 units; 297 executed both treatments; three matplotlib units returned no gold report; the bound covers the first 190 adjudicated units of the draw, not all 300 (`data/gold/swe_srs300.certificate.json`, `data/gold/swe_srs300_exec.summary.json`, doc 47).

The two RST rows are different bounds, not a disagreement. Five of the 200 sampled units stayed unadjudicated after retries. The restricted bound drops them and covers the covered subpopulation of 37,479; the conservative bound counts all five as invalid over the full 37,484. Both reject (doc 53).

The Harbor-Index row leaves 29 of 82 tasks unadjudicated under this protocol: 16 judge-configured tasks and 13 with no reference (`data/gold/harbor_index_strata.json`, doc 44). Its 3.8% is a measurement on the executable stratum of an externally curated population, not a certificate.

The pattern is consistent. Pools without maintenance or curation sit above epsilon: TB 2.0 pre-fix at 33%, our own pilot at 12.5%, the raw generator pool at 6.0 to 9.5%. Maintained and curated pools sit near the boundary: TB 2.1 rejects at 5.6%, the Harbor-Index executable stratum measures 3.8%. The only released bound is the SWE-bench prefix at 4.65%.

## 5. Negative results

Each candidate shortcut was tried and failed. None replaces the probability sample.

| Shortcut tried | Result | Source |
| --- | --- | --- |
| Static specification features | At chance: AUROC 0.41 / 0.42 under the 2024 conservative label | doc 23, `data/gold/causal_ablation.summary.json` |
| Better static ranker as certificate | Grouped-OOF AUROC about 0.70 still leaves 34% invalid in the lowest-risk 5% tail | docs 23, 27, 33 |
| Prediction-powered inference | At AUROC 0.70 the effective-sample gain is about 1.11x and the normal UCB undercovers at low prevalence | doc 27, `data/gold/ppi_lab.json` |
| Judge-calibrated bound | Never narrower than the SRS arm at a ranking instrument of AUROC 0.81 | doc 36, doc 43, `data/gold/judge_bound_lab.json` |
| Cross-benchmark spec calibration | Rogan-Gladen transfer undercovers or goes vacuous in 8 of 10 footprint-holdout cells | doc 40, `data/gold/footprint.holdout.json` |
| Funnel reconstruction as predictor | Stage-1 rule reconstructs within 1.5% (1,331 vs published 1,311); curation survival predicts at 0.711 leaving out benchmarks and 0.612 leaving out families; adding trajectory, verifier, and shortcut features degrades held-out performance; stage-1 solve rate alone is at chance (0.502) inside the survivor band | `data/gold/harbor_funnel_stage1.summary.json`, `data/gold/harbor_funnel_traj_eval.json`, docs 52, 54 |

The implication is the paper's working rule: a fresh probability sample from the frozen pool remains necessary. Models and cheap features order the queue. They do not certify (doc 43).

## 6. The funnel reconstruction as a data contribution

The public Harbor-Adapter trial dump (`kendx/Harbor-Adapter`, revision fa353815, doc 55) contains 793,698 trial rows, of which 768,956 are in-scope reward rows spanning 60 benchmarks and 8,468 distinct task pairs (`data/gold/harbor_adapter_trials.summary.json`, `data/gold/harbor_adapter_traj.summary.json`). The manifest carries 16 models and 6 agents (doc 55). From it we reconstructed the Harbor-Index funnel and publish per-task labels.

| Artifact | Content | Counts |
| --- | --- | --- |
| `data/gold/harbor_funnel_stage1.summary.json` | Stage-1 reconstruction | 6,627 candidates; 5,684 with full 18-trial coverage; 1,331 reconstructed survivors vs 1,311 published, a difference of 20 or 1.5% |
| `data/gold/harbor_funnel_labels.jsonl` | One label row per candidate | 6,627 rows; `survived_stage1` grade B, `survived_funnel` and `survived_2_to_4` grade A; protocol `harbor_index_funnel.reconstructed.2026-09-13`; external, eval-only (doc 43) |
| Published-survivor match | Join against the 82-task list | 81 of 82 matched; `dacode-predict-essay-scores` unmatched |
| `data/gold/harbor_funnel_traj_eval.json` | Feature-group held-out evaluation | 0.711 benchmark-held-out, 0.612 family-held-out |
| `data/gold/harbor_funnel_mapper.json` | Topological map of the candidate space | 62 nodes, 88 edges (doc 52) |
| `data/gold/harbor_funnel_hidden_requirement.jsonl` | Hidden-requirement flag | Empty by construction: the named failed-test signature is computable only for two rejected skillsbench tasks, so the flag is unevaluable on the public dump, not evidence that hidden requirements are absent (doc 52) |

These labels are provenance and a queue-ordering prior. They are external labels, eval-only, and they are not a per-task taste certificate and not a bound (doc 43, doc 52).

## 7. What we do not claim

- We do not claim the bound exists elsewhere. The claim is that nobody else reports a design-based bound on residual invalidity (docs 30, 46), not that audits are new.
- We do not claim machine coverage of judge-verifier or no-reference tasks. Those strata need the human design (doc 44).
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
| No downstream lift experiment | Whether gating improves downstream evaluation results is unmeasured | doc 50 |
| Partial certificates | SRS-300 covers 190 of 300 drawn units; the RST restricted bound covers 195 of 200 | docs 47, 53 |
| Environment dependence | Execution verdicts are per-image; drift can change a verdict | doc 23 |
| Specification invalidity unbounded on new pools | Human spec review has not run on the RST or Harbor pools | doc 50 |

## 9. Related work

Audits report found-issue rates. Generation pipelines ship keep rules. None reports a design-based bound on the residual invalid-task rate of a filtered pool (docs 30, 46).

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

The exact gap statement: none of these reports a design-based, coverage-checked, one-sided finite-population confidence bound on residual task invalidity of an accepted agent-eval pool (doc 30, doc 46 part 2). The nearest statistical neighbors bound different estimands: FAQ and Noisy but Valid bound model scores and judge error; Gema et al. report a sampled item-error point estimate on MMLU without a UCB (doc 30).

## 10. Reproducibility

The replication note is doc 55. Certificates, manifests, and summaries cited above live under `data/gold/`. The gate's decontamination rule is doc 49. Drift known at draft time is listed in doc 57.

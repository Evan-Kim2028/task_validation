# Part 2 intake specification

Reference. The pipeline every generated lot passes before it can ship as training data. Stage order is fixed: lot freeze, gate A, gate B, gate C, review queue, strata, probability sample, footprint prior, certificate and dossier. Rules in force: no api.x.ai, no OpenRouter (doc 43). No model output enters a bound (doc 43). Every label carries a protocol and a treatment grade (doc 21, doc 32).

## Parameters

| Parameter | Default | Source |
| --- | --- | --- |
| epsilon, release threshold | 0.05 | doc 23 section 6 |
| difficulty band | [0.10, 0.70] solve rate | gate C below |
| k trials per task | 3 | gate C below |
| open agent | terminus-2 | doc 48 worklist cells |
| frontier probe | `harbor run --agent devin --model devin/swe-2-max` | eval_tasks LANDSCAPE.md section 5 |
| decontam n-gram | 13 words, 1 shared gram flags | `src/task_validation/evidence/decontam.py`, doc 49 |
| decontam Jaccard | 0.5 on 5-shingle sets | same |
| decontam scaffold df | 0.5 | same |
| adjudication | 2 raters plus tiebreak | doc 23 section 6 |

## 1. Lot definition

A lot is a frozen manifest: the list of generated task ids from exactly one generator at one recorded version, with the generator config hash and the freeze timestamp. One lot is one stratum. A run of several generators produces several lots. Bounds are reported per stratum, or pooled with a per-stratum floor, because one pooled number can hide a fully broken generator (doc 23 section 5).

The intake manifest freezes before any gate output is read. No unit is dropped after outcomes are seen (doc 32). The accepted lot is frozen a second time after the gates, and the probability sample is drawn after that freeze (doc 23 section 5).

## 2. Gate A: execution

Every task runs the verifier interrogation in a fresh container (`task-validation interrogate-verifier`). The oracle solution must pass twice. The nop solution must fail twice. Repeated runs must return identical rewards (determinism). Protocol `verifier_invalid.fresh_environment.execution`, treatment grade A, adjudicator machine (doc 32, doc 47). Cost is 30 s to 3 min per trial (doc 23 section 7). On unaudited populations this gate has found 2 to 12 percent materially invalid tasks (doc 23 section 7).

A task that fails is dropped or repaired. Repaired tasks re-run gate A in full before the accepted lot freezes (doc 23 section 5).

## 3. Gate B: decontamination

`task-validation decontam-check` against `data/gold/decontam_index/`. Four reference populations: TB4 (66 tasks), Harbor-Index 1.0 (82), Terminal-Bench 2.1 (89), SWE-bench Verified (500) (doc 49). Three fields per task: instruction, tests, solution. Flag rules: any shared word 13-gram, and Jaccard at or above 0.5 on word 5-shingle sets. Scaffold lines are masked and grams above 0.5 document frequency are dropped (doc 49, `decontam.py`).

Any flag blocks the task from shipping until a human adjudicates it. The review reads the shared grams and the nearest reference id in the report. Adjudicated-clean tasks carry the adjudication record in the dossier. Thresholds may tighten; loosening needs an ADR (doc 49). The asymmetry is intended: a flag costs one review, a missed copy ships a memorized benchmark item.

## 4. Gate C: difficulty band

Solve rate for the target model family, measured by k trials (default 3) per task with a named open agent (default terminus-2). The devin harbor lane runs first as the cheap frontier probe: `harbor run --agent devin --model devin/swe-2-max`. It is free on this rig, and a task it solves is unlikely to survive a paid frontier run (eval_tasks LANDSCAPE.md section 5). Keep a task when its measured solve rate lands inside the band, default [0.10, 0.70]. Record agent, model, k, and band per lot.

The band is a parameter. It is not frontier-unsolved because the lot is training data, not an eval (doc 46 part 4). Zero-pass tasks give no gradient, so generators already soft-filter them at RL time (TMax, doc 46 part 1). Max-hard selection kills discrimination: frontier gain peaks in the 0.3 to 0.7 solve band and is near zero at both ends (doc 31). And unsolved correlates with broken: about a third of the hardest Harbor-Index candidates reaching human review were rejected (doc 28, doc 31).

## 5. Model-ordered review queue

A model may order the review and reject queue over candidate tasks (doc 43). Each stored row carries the model id and the prompt hash. It is a ranking feature, never a label. A model-flagged task outside the probability sample does not change the estimate. Ordering decides which units humans see first, not what the sample says (doc 43).

## 6. Judge and no-reference strata

Per doc 44. A task whose verifier is an LLM-judge ensemble, and a task that ships no reference solution, each goes to its own stratum or is excluded from the lot.

Judge stratum: run the task's declared `JUDGE_MODELS` and `JUDGE_REPEATS` environment, k=3 runs on the reference output and k=3 on the nop output. Record every verdict, the judge model id, and the agreement counts. A judge stratum gets a human-adjudicated bound under the same sample design. It has no machine certificate (doc 44).

No-reference task: obtain or write a reference and grade it per doc 21; only grade A or B references enter the assay. Or hold the task out of the certified population and report it uncovered (doc 44).

## 7. Probability sample and release rule

On the frozen accepted lot, draw the sample manifest first: design, N, n, ids, seed. The SRS arm is always present (doc 23 section 5, doc 43). Human adjudication is two raters plus a tiebreak on disagreement. One rater agrees with the majority at 0.85 with FNR 0.16, so one rater is not consensus (doc 23 section 6).

Estimator: hypergeometric one-sided 95% UCB when n < N; the observed rate when n = N (doc 32). Release iff UCB < epsilon. Otherwise reject, or repair and re-freeze. Any unadjudicated sample unit leaves the certificate INCOMPLETE (doc 32).

Sample size for UCB below epsilon when the sample shows zero invalids (doc 23 section 6):

| epsilon | n |
| ---: | ---: |
| 5% | 59 |
| 3% | 99 |
| 2% | 149 |
| 1% | 299 |

Budget 200 to 300 adjudications per lot at epsilon 5% unless the pool is under about 1% invalid (doc 23 section 6). The cost depends on epsilon and on pool cleanliness, not on N.

The per-lot certificate uses the doc 32 fields plus the doc 44 fields: `verifier_kind`, `judge_model`, `judge_agreement`, and the `strata` count. A verdict whose declared `verifier_kind` differs from the certificate's is unadjudicated, so judge-verified units cannot pool into an execution bound (doc 44).

## 8. Footprint prior

Compute the footprint on every task with `src/task_validation/evidence/footprint.py`: execution gate fields, instruction length, test file count, assertion count, literal pins in tests not in the instruction, solution size, resource limits, network mode, judge-verifier flag, and solve rate where public submissions exist (doc 40).

The Harbor-Index funnel labels join the prior: `survived_stage1`, `survived_funnel`, `survived_2_to_4`, protocol `harbor_index_funnel.reconstructed.2026-09-13`, with `survived_stage1` grade B (reconstructed), `survived_funnel` and `survived_2_to_4` grade A (published list), all external and eval-only (doc 45, doc 48, doc 52). The fetch completed on 2026-09-13; the earlier "blocked at 327.1 GB against a 40 GB budget" note is stale (docs 48, 52, 55).

Report the prior with its held-out error, never as a bound. Held-out curated-vs-generated AUROC is 0.71 on Harbor-Index, 0.75 on TB 2.1, 0.57 on SWE-bench Verified, and 0.41 on SWE-rebench (doc 40). Cross-population transfer of any validity bound fails in 8 of 10 cells (doc 40), so the prior orders attention; it certifies nothing.

The lot dossier carries a Mapper coverage picture over the footprint features with solve rate as the lens (doc 45 step 5). It is diagnostic only: parameter-sensitive, no inference, never a gate and never a bound.

Result 2026-09-13 (doc 52): the funnel reconstructed from the public dump matches the published stage-1 count within 1.5 percent, but execution-only features rank stage 2 to 4 survival at leave-one-benchmark-out AUROC 0.71 with a lower bound at the 0.65 stop line, and stage-1 solve rate alone is at chance inside the band. Doc 54 then added trajectory, verifier and shortcut features: held-out AUROC fell to 0.61 with benchmark families held out while pooled AUROC rose, and the doc 45 stop rule triggered. The funnel is not a per-task taste prior. Stage 8 keeps only the curated-vs-generated membership footprint from doc 40 and the funnel labels as provenance context.

## 9. Certificate and dossier

Certificate: the doc 32 fields (N, n, k_invalid, p_hat, ucb95, method, epsilon, decision, p_certify, label_protocol, grade, adjudicator, replaces_human_sample, flagged, unadjudicated) plus `verifier_kind`, `judge_model`, `judge_agreement`, `strata` (doc 44). Code: `src/task_validation/sampling/certificate.py`.

Dossier, one per lot: the frozen intake manifest; gate A evidence rows; the decontam report with adjudications; the gate C solve-rate matrix with agent, model, k, band; the review-queue order with model id and prompt hash; the sample manifest, verdicts, and certificate JSON; the footprint prior with held-out error; the Mapper picture; and the yield ledger from candidates through gates to accepted to sampled (eval_tasks DIRECTION-1000-TASKS.md section 5).

What a frontier-lab buyer is told, per doc 46 part 4:

| Claim | Claimed | Not claimed |
| --- | --- | --- |
| Residual invalidity | one-sided 95% UCB on the frozen accepted lot, per stratum (doc 32, doc 47) | a specification-invalidity bound; taste |
| Decontamination | every shipped task passed the four-population lexical gate or was adjudicated (doc 49) | that decontamination measures validity |
| Difficulty | solve rate measured in the stated band on the stated agent and model | frontier-unsolved (doc 46 part 4) |
| Footprint | prior reported with held-out error (doc 40) | certification of a new pool; taste measurement |
| Judge and no-reference strata | human bound under the same design (doc 44) | a machine certificate |
| Model role | queue ordering only, model id and prompt hash stored (doc 43) | any model output inside a bound |

## Operator checklist, one page per lot

1. Freeze the intake manifest: ids, N, generator name and version, config hash. One generator per lot.
2. Gate A on every task: oracle passes twice, nop fails twice, determinism, fresh container. Drop or repair; re-run repairs.
3. `task-validation decontam-check` at default thresholds. Route every flag to human adjudication. No flagged task ships unresolved.
4. Gate C: k trials with the open agent plus the devin lane. Keep tasks inside the band. Record agent, model, k, band.
5. Assign `verifier_kind` per task. Judge and no-reference tasks go to their own strata or leave the lot.
6. Build the review queue from the model ordering. Store model id and prompt hash.
7. Freeze the accepted lot. Draw the SRS sample manifest (N, n, seed) before any verdicts.
8. Adjudicate the sample: two raters plus tiebreak. Only grade A or B evidence counts toward the bound.
9. Compute the hypergeometric one-sided 95% UCB. Release iff UCB < epsilon. INCOMPLETE if any unit is unadjudicated.
10. Attach the footprint prior with held-out error and the Mapper picture to the dossier. Neither is a bound.
11. Emit the certificate and the dossier. Ship only on RELEASE.

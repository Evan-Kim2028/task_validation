# Handoff: where the program is and what decides it

Written 2026-09-11 at head `60c1399` plus uncommitted decision-tree work. This page is the operating story. The ADRs and documents 12 through 22 are research provenance. They record the wrong turns. They are not the interface.

## 0. The story in three sentences

1. Cheap metadata ranks historically broken tasks (grouped-OOF AUROC ~0.70) but the accepted tail is still too dirty to certify (34% invalid in the lowest-risk 5% under the 2024 conservative label).
2. Static specification/test proxies are chance (AUROC 0.41/0.42), so validity has to be interrogated by executing the evaluator against controlled implementations.
3. Once a validity signal exists, certification is a finite-population survey problem: run the cheap evidence on everything, draw a probability sample of the accepted set, adjudicate it, and bound residual invalidity.

Everything else is implementation detail.

## 1. The actual goal, stated honestly

The operational target is roughly 1,000 Terminal-Bench-level tasks in three weeks, with human review that does not grow with N. Two clarifications that change the design:

**Constant, not zero.** A design-based confidence bound needs human labels on a probability sample of the population being certified. That cost is constant in N (section 6) but not zero. The only way to get to zero is transfer: calibrate the automated instrument on already-labeled benchmarks (SWE-bench 2024, TB 2.1 repairs, Harbor-Index rejects) and assume the calibration holds on the new population. That assumption is exactly what fails under distribution shift, and a synthetic population is the largest shift there is. So the design is: transfer gives the prior and the risk score, a small fresh sample (tens to low hundreds, once per population, not per task) gives the bound.

**Validity first, taste second.** "High-taste task" bundles two estimands. Material invalidity (the evaluator cannot be read as evidence) is binary and samplable. Taste (realism, difficulty, discrimination) is graded and needs a different instrument. Part 1 certifies validity only. Taste enters in Part 2 as construction quotas and frontier-agent trials, not as part of Y.

**Using existing benchmark mistakes as a prior is the right idea and is already the plan.** The 1,699 SWE-bench labels, June Kim's 109, TB 2.1's 28 repairs, and Harbor-Index's funnel are the calibration corpus. The independent replication of other labs' audit results (section 8) is the transfer test.

## 2. Estimand

A task is **materially invalid** when its evaluation can no longer be read as evidence about the intended capability. Binary. Protocol-tagged.

Split it into two constructs and never conflate them again:

| Construct | Examples | Gold available | Instrument |
| --- | --- | --- | --- |
| Specification invalidity | underspecified prompt, hidden requirements, prompt vs test disagreement | SWE-bench 2024 (3 raters), June Kim, OpenAI Pro | prompt-vs-test evidence, later a cheap model plus human sample |
| Verifier invalidity | wrong solution accepted, correct solution rejected, nondeterministic, gameable | TB 2.1 pre/post pairs, Harbor pilot outliers, Harbor-Index rejects | executable interrogation |

Every gate before doc 22 tested the verifier instrument against specification gold. That is why nothing could pass.

Realism, difficulty, diversity, coverage, novelty are population-design properties. Measure them. Do not fold them into Y.

## 3. What has been established

| Question | Answer | Artifact |
| --- | --- | --- |
| Cheap artifacts carry signal | Yes, AUROC 0.70 (0.67–0.73) grouped OOF | `data/gold/oof_*.json` |
| Cheap artifacts produce a certifiable tail | No, 34% / 15% / 6% residual at 5% retain for conservative / majority / unanimous | `data/gold/oof_*.json` |
| Static spec/test structure predicts the 2024 label | No, AUROC 0.41 / 0.42 | `data/gold/causal_ablation.summary.json` |
| Cheap evidence recovers OpenAI's Pro rejection | Weakly. A passes (named example rank 38/731). B is a 1.4 to 1.6x top-decile enrichment of June Kim / OpenCompass repairs, but AUROC against the 102 OpenCompass repairs is 0.51 (0.45 to 0.57). **C is vacuous** (see below) | `data/gold/pro_reconstruction.json`, `data/gold/pro_verified_transfer.json` |
| Real evaluators can be interrogated mechanically | Yes, 16/16, ~3 min/task, no LLM | `data/gold/harbor_interrogate.summary.json` |
| Interrogation finds verifier invalidity on unaudited populations | Yes. eval_tasks 2/16; SWE-bench SRS-100 2/100 (1 false-accept, 1 env-dependent reference failure); frozen SWE 20: 1/20 env-dependent; TB 2.0 pre-fix: 9/27 reference failures on the diffable pairs (doc 25) | `harbor_outlier_diagnosis.json`, `swe_srs100.certificate.json`, `swe_2x2_exec.summary.json`, `tb21_pairs.jsonl` |
| Interrogation separates pre-fix from post-fix TB 2.1 | Partial: `build-pmars` separates; `build-pov-ray` fails both; several pre-fix failures are environment drift on this machine. Full table in doc 25 once the post-fix rerun lands | `tb21_pairs.summary.json` |
| Model-free interrogation coverage boundary | Harbor-Index: 16 of 82 verifiers are judge-configured (`JUDGE_MODELS`), not interrogable without a model; egress-control tasks need docker buildx (fixed) | doc 28, `data/gold/harbor_index_strata.json` |
| First population certificate | SWE-bench 1,699, SRS n=100, k=2, p-hat 2.0%, UCB95 6.1%, REJECT at 5%, machine-adjudicated grade A | doc 35 |
| Census plus coverage check on someone else's benchmark | TB 2.1: 5 of 89 references fail (5.6%), nop rejected 89/89; SRS-30 UCB 7.9% covers; Monte Carlo coverage 0.9875 to 1.00 | doc 41, `data/gold/tb21_census_montecarlo.json` |
| 2026 per-task labels exist | ABA (agent audit, expert-sampled) covers SWE-Verified 500, Pro 731, TB2 89 by ID; BenchGuard 29, tau2 78, Z.ai 20 are human. OpenAI's 138/249 IDs and Harbor-Index rejects are not public | docs 37, 38 |
| ABA agrees with our instruments | On spec (SWE Verified): solve rate 0.86 AUROC vs ABA majors. On verifier: no (TB pre-fix failures are not ABA majors). Static Pro scores are chance vs ABA | doc 38 |
| Calibration transfers across benchmarks without new labels | **No.** Leave-one-population-out: static spec AUROC 0.58 to 0.69, verifier at chance; Rogan-Gladen from other benches undercovers or is vacuous in 8 of 10 cells (F1 FAIL) | doc 40 |
| Curated vs generated tasks separable by non-LLM footprint | Partly: held-out AUROC 0.71 (Harbor-Index), 0.75 (TB 2.1), 0.57 (Verified), 0.41 (SWE-rebench). Distribution membership, not taste | doc 40 |
| PPI with the cheap score saves human labels | No at AUROC 0.70: ~10% n_eff gain on dirty populations, undercovers on clean ones | doc 27 |
| Cheap LLM auditor ranks the 2024 spec label | Yes: AUROC 0.78 (s) / 0.81 (p_invalid) vs conservative, 0.84 vs majority; kappa 0.50 vs majority (humans 0.39); $0.008/task | doc 34 |
| Agent solve rate (public submissions) ranks the 2024 label | Yes: AUROC 0.76; 649 never-solved items are 89% invalid; broken tests are tasks agents never solve | doc 33 |
| Any instrument produces a certifiable spec tail | No: best combination 27.5% invalid at retain-20% on conservative Y | docs 33, 34 |
| Judge-calibrated bound (humans calibrate the judge) | No. On the full 1,699 the judge reaches AUROC 0.81 vs majority, but Rogan-Gladen, calibrated FPR/FNR, judge-stratified, and PPI bounds are all wider than SRS-CP or undercover at p=0.02. The judge orders the queue; the human SRS sets the bound. Spend $15.37 for 1,699 audits | doc 36 |
| SRS hypergeometric bound covers at low p | Yes (0.97–1.00 at p ≤ 5%, 5,000 reps). Stratified-normal does not (0.47–0.91) | `data/gold/coverage_lab_r5000.json` |
| Any population certified | No | |

**On the Pro transfer (doc 29).** OpenCompass's SWE-Bench Pro Verified repaired 102 tasks. Those IDs are almost the same set as June Kim's 109 (Jaccard 0.88), so it is one audit lineage seen twice, not two. Against it the static prompt-vs-test score has AUROC 0.51 and the frozen enrichment predicate fails (1.37x versus the 1.5x threshold). The static layer surfaces one named example and a modest top-decile enrichment; it does not rank Pro defects. That is consistent with doc 18: static evidence is not the instrument.

**On predicate C.** June Kim's base rate is 14.9%. Any random 20% slice of Pro exceeds 5%, so C passes with no contribution from the cheap layer. The recovery result rests on A (named example at rank 38/731) and B (1.56× enrichment). Cite those two. Drop C from the claim.

**On the Harbor pilot.** Two of sixteen references scored 0 (`bootstrap-merge-resume`, `logged-bandit-ope`) and one partial gold was accepted (`schema-evolution-cdc`). Diagnosed from artifacts on 2026-09-11, no LLM (`data/gold/harbor_outlier_diagnosis.json`):

| Task | Verifier evidence | Label | Grade |
| --- | --- | --- | --- |
| bootstrap-merge-resume | tests import `warehouse.jobs.first_load`; no such module in environment, solution, or instruction | INVALID (reference fails own verifier, hidden path) | A |
| logged-bandit-ope | 1/17 tests reads `/app/policies/live.json`; absent from environment, instruction, solution | INVALID (hidden test requirement) | A |
| schema-evolution-cdc | the dropped `runner.py` differs from the environment copy only by an unused import, a comment, and formatting | VALID (grade-C probe dropped a no-op file; verifier was right) | C |

Two of sixteen tasks we wrote ourselves are materially invalid and the reference probe alone flagged both. The third flag was a treatment-label error, which is the case ADR-0018 predicted for grade-C probes. A/B-only false-accept stays 0. That is the first live verifier-invalidity evidence.

**On TB 2.1 as gold.** The 2.1 tasks live in a separate repo (`harbor-framework/terminal-bench-2-1`, also `harbor datasets download terminal-bench/terminal-bench-2-1`). Diffed against TB 2.0 at `f5b891c`, all 28 maintained tasks differ; the mechanical change classes are multi-tag: test_fix 9, solution_fix 10, misspec 11, docker_env 9, resource_timeout 8 (`data/gold/tb21_pairs.summary.json`). That is enough pairs. PR #53 on terminal-bench-2 carries the per-task rationale. Z.ai's `terminal-bench-2-verified` on Hugging Face is the upstream for many fixes and is a second provenance. SWE-Bench Pro Verified (arXiv 2609.08149, 102 of 731 repaired) is a third pair source for later.

## 4. Rules that earned their place

- No fitting OpenAI's 30%, 200, or 249. External audit labels are eval-only.
- No human severity axes as features. They define the label.
- No model in the published bound. ML allocates and assists; sampling infers.
- Every label carries its protocol. Never pool SWE-bench raters with TB maintenance with Harbor rubric into one Y.
- Every treatment carries a grade. A: semantically guaranteed from an independent source. B: strongly justified by artifact evidence. C: heuristic. D: unknown. Only A/B enter the assay. Natural counterfactuals (before repair vs after repair) beat invented mutations because they carry no semantic assumption.
- One experiment, then one document. Not the reverse.

## 5. Certification design

```
task population
    → cheap evidence on every task (static + interrogation, ~3 min/task, no LLM)
    → risk score (calibrated on existing labeled benchmarks)
    → accepted pool
    → probability sample (SRS arm always present)
    → human adjudication, two raters plus tiebreak
    → estimate residual invalidity
    → one-sided 95% upper bound
    → release if UCB < ε, else reject or repair and re-freeze
```

**Estimator.** SRS with hypergeometric / Clopper-Pearson is the safe baseline and covers at low prevalence. Stratified-normal is not a release rule. Sequential stopping needs alpha spending before it is used for repeated looks.

**Model-assisted inference was tested and does not shrink the human sample.** Docs 27 and 36: with real auxiliaries at AUROC 0.70 (metadata) and 0.81 (LLM judge), PPI++ undercovers at low prevalence and every calibrated or stratified alternative is wider than SRS-CP. Keep the paragraph below as the record of why.

**Prediction-powered inference (tested, rejected for the bound).** The automated verdict is the auxiliary variable. The human sample estimates its bias. Coverage still comes from the design, so this does not violate the no-model-in-the-bound rule, and effective sample size grows with how well the cheap signal correlates. This is the mechanism that keeps human cost constant when the accepted pool is not already near-clean. FAQ and Noisy-but-Valid are the nearest published versions.

**Post-repair population.** Tasks found invalid get fixed. The certified population is the one after repairs, frozen, and the sample is drawn after the freeze. Repaired tasks re-run interrogation.

**Strata.** A 10K or 100K population from several generators is several strata. Report per-stratum bounds or a pooled bound with a per-stratum floor. One pooled number can hide a fully broken generator.

## 6. What the human budget actually is

Sample needed for a one-sided 95% bound below ε when the sample shows zero invalids:

| ε | n |
| ---: | ---: |
| 5% | 59 |
| 3% | 99 |
| 2% | 149 |
| 1% | 299 |

That table is the cost only if the population is much cleaner than ε. Probability the release rule fires at ε = 5%:

| n | true p 1% | true p 2% | true p 3% |
| ---: | ---: | ---: | ---: |
| 59 | 0.55 | 0.30 | 0.17 |
| 100 | 0.74 | 0.40 | 0.19 |
| 200 | 0.95 | 0.63 | 0.28 |
| 300 | 1.00 | 0.85 | 0.45 |

Budget 200 to 300 adjudications per certification at ε = 5% unless the pool is under 1% invalid. This is classical acceptance sampling. The cost does not depend on N; it depends on ε and on how clean the pool is. That is the sublinear claim, stated correctly.

Rater noise: one rater vs majority agrees 0.85 with FNR 0.16. One rater is not consensus. The protocol is two raters plus tiebreak on disagreement.

## 7. The open question, answered so far

> When a benchmark maintainer fixes a known verifier defect, does the interrogation profile change in a way we can measure cheaply, with no LLM?

Partly yes, and the more useful finding is different. On every unaudited population we ran, model-free interrogation (reference, nop, empty patch, in a fresh container) found materially invalid tasks at 2 to 12 percent: our own 16 Harbor tasks (2), the frozen SWE 20 (1), a random 100 of SWE-bench (2), and TB 2.0 pre-fix (9 of 27 diffable references fail, several fixed in 2.1). One of those (`django__django-10097`, in Verified-500) is a false-accept under the current official image that three human raters marked valid, because tests passing on the base commit is an execution property, not a reading property. Its 15% public solve rate suggests the 2024 environment behaved differently, so this may be image drift; it is invalid on today's image regardless. The instrument is cheap (30 s to 3 min per trial) and grade A.

What it does not do: it does not touch specification invalidity, which is 45 to 68 percent of SWE-bench by the 2024 raters. For that construct the cheap model auditor (doc 34) and the agent solve rate (doc 33) each reach AUROC ~0.8 and together still leave 27.5 percent invalid in the safest fifth. The human sample remains the bound for spec validity; doc 36 tests whether humans can calibrate the judge instead of adjudicating every unit.

## 8. Where this leaves the no-new-ratings constraint

Evan's constraint (2026-09-12): no new human ratings; use existing human labels, extend to machines, build a statistical footprint. What the overnight data say about that:

- **Verifier invalidity needs no ratings at all.** The execution gate is grade A on its own, runs on every population we touched, and its sample bound covers against a known census (doc 41). Certificates on this construct are machine-adjudicated by design. Done.
- **Specification invalidity cannot be bounded on a new population from old labels.** Doc 40 tested it directly: calibrate on four benchmarks, bound the fifth, and the bound misses or goes vacuous in 8 of 10 cells. Static features transfer at 0.6 AUROC. The labels that exist (2024 raters, 2026 repairs, ABA) disagree with each other on what "invalid" means (Jaccard 0.2 to 0.4 between sources), so there is no single construct to calibrate to. This is a finding, not a gap to fill with more modeling.
- **What existing labels do support:** ranking. Solve rate and static features order the review queue at 0.7 to 0.86 AUROC against 2026 labels. A pool can be cleaned, not certified, without fresh labels on it.
- **The honest claim for a new population** is therefore two-part: a machine certificate on verifier invalidity (bound, no humans), plus a spec-invalidity prior from the footprint with its held-out error rates stated (no bound). If a spec bound is required, it needs labels from that population; the size is the SRS table in section 6, and the labels can come from maintainers' repairs and issue trackers over time rather than a rating session.

Next, in order, none requiring ratings:

1. Human review queue from machine flags only: 5 TB 2.1, 2 Harbor-Index, 2 SWE SRS-100, 2 eval_tasks. Confirm upstream or environment. Eleven items.
2. Extend the SWE verifier certificate to n=300 on the frozen design so it can pass at 5% if p is ~2%.
3. Define Part 2 intake as: execution gate (reference twice, nop, environment) plus footprint prior plus quotas. Ship the machine verifier certificate with every pool. Track spec validity through repairs and issues as they accrue, and re-certify from that log.
4. Stop building instruments for the spec construct until a label set with a single protocol exists; ABA-style agent audits are the nearest 2026 thing and are eval-only.

## 9. Transfer test, once step 3 answers

The independent-replication goal: take the calibrated instrument and, without their labels as inputs, reproduce the decisions other labs reached.

- Harbor-Index: does our risk score enrich the 307→100→82 rejections?
- OpenAI Pro: A and B already pass with static evidence. Does interrogation add anything on the top-risk Pro tasks, including `openlibrary-77c16d53`?
- June Kim: does interrogation catch the three golds that fail Pro's own verifier?

Each replication that works is one more population where the calibration held. That is the evidence that the prior transfers and that the fresh sample can be small.

## 10. Do not

- add lexical features or optimize AUROC without the retain-tail
- treat the 2024 label as gold for verifier invalidity
- invent semantic labels for mutations
- train a production model before execution evidence exists
- replace probability sampling with model predictions
- write another ADR before the next experiment runs
- start synthetic generation

## 11. Sources

Motivation: OpenAI SWE-bench Verified (2024); OpenAI "Separating Signal from Noise in Coding Evaluations" (2026-07-08); June Kim determinacy audit of Pro (2026-06-21).
Auditors and funnels: ABA (2605.26079); BenchGuard (2604.24955); Harbor-Index (2609.04298); Terminal-Bench 2.1 / 3.0.
Generators (Part 2 neighbors): SWE-Universe; InfoSynth; CLI-Universe; Endless Terminals; SWE-smith.
Verifier strength: SWE-Mutation; ProgramBench; Reward Hacking Benchmark; GateTruth.
Statistics: FAQ (2601.20251); Noisy but Valid (2601.20913); PRECISE / PPI (2606.05308) and Angelopoulos et al. prediction-powered inference; Berti-Équille progressive sampling (2607.25356); classical acceptance sampling (Dodge-Romig, ANSI Z1.4); model-assisted survey estimation (Särndal).

## 12. Known drift, resolved 2026-09-13 (doc 57)

- Doc 15 tables were regenerated from `pro_reconstruction.json`, which is scored under doc 16's `openai_style_risk`; the doc now notes the scoring change.
- `data/gold/coverage_n100.json` (200 reps) was renamed `coverage_n100_r200.json`; the cited 2,000-rep file is `coverage_n100_r2000.json`.
- `pro_reconstruction.json` now emits `rank_by_openai_style_risk_desc` (the value doc 16 uses) plus a true `rank_by_cheap_risk_desc` (257).


## 13. Operational notes from the overnight run

- Long docker runs must not live inside a grok headless session: the session ends its turn and its children die. Launch runners with `setsid nohup`, resume-aware, and let grok write reports from artifacts afterwards.
- `docker buildx` was missing; Harbor egress-control tasks (network_mode no-network) fail without it. Installed to `~/.docker/cli-plugins`.
- The `terminal-bench-2-1` git checkout and the project `.venv` were deleted from disk mid-run by something outside this session. The Harbor dataset copy at `~/Documents/tb21-dataset/terminal-bench-2-1` is the POST source now. Recreate the venv with `uv venv .venv && uv pip install --python .venv/bin/python -e '.[dev,fit]' swebench datasets huggingface_hub`.
- **Agent and model rules (from Evan, 2026-09-12):** implementation and research agents run through the cursor-agent CLI with the composer 2.5 model (not the fast variant), replacing the grok CLI for all further work; devin CLI when credits are needed. No LLM scoring of tasks inside the pipeline at all: the footprint is execution, static artifacts, public solve rates, and classical statistics only. Do not use api.x.ai or OpenRouter. The doc 34 and 36 audits were run against OpenRouter and api.x.ai without authorization; the results stand as recorded, but any rerun or extension of the auditor must be rewritten to call the grok CLI per item (or batch items per call) instead of an HTTP API. Doc 43 supersedes the agent-and-model parts of this bullet: agent defaults moved to devin CLI on swe-2-max and cmd on deepseek-v4.1-flash, and LLM scoring is now permitted for ordering the review queue only.
- Harbor-Index images are 200+ GB; remove images for finished tasks (`docker rmi`) or the disk fills.

# Prior art and the novelty boundary

Search date: 2026-09-11. Citations were opened and checked. Task Verification Bench (OpenReview `QdDcI0Ftvo`) did **not** resolve to a public PDF, arXiv abstract, or dataset. Do not cite it as a gold source until that is opened.

## What already exists

### Per-task auditors

**ABA** ([arXiv 2605.26079](https://arxiv.org/abs/2605.26079)). Agentic audit of 168 benchmarks. Reports 25.7% of audited tasks with major issues. Filtering those tasks moves SWE-bench Verified and Terminal-Bench 2 averages by +9.9% and +9.6%. Precision checked by expert review and upstream PRs. Not a survey estimator of one benchmark's full population.

**BenchGuard** ([arXiv 2604.24955](https://arxiv.org/abs/2604.24955)). Cross-artifact LLM audit of scientific agent benches. 12 author-confirmed defects on ScienceAgentBench. 83.3% exact match to expert issues on BIXBench Verified-50. Cheap. Human-in-the-loop. Not a CI.

### Construction funnels

**Harbor-Index** ([harbor-index.org](https://harbor-index.org/), [arXiv 2609.04298](https://arxiv.org/abs/2609.04298)). 6,627 → 1,311 (difficulty) → 307 (AI audit) → 100 (human) → 82 (audit-and-fix). This is the strongest operational neighbor. They still reviewed every survivor. The "about a third of the hardest tasks are broken" remark is a funnel observation, not a bound on 6,627.

**Terminal-Bench 2.1 / 3.0.** TB 2.1 fixed 28 of 89 TB 2.0 tasks (the GitHub README says 26; use 28 from the project news page and record the discrepancy). TB 3.0 ships static checks, a 35-criterion rubric, oracle, nop, live trials, and cheat trials, then maintainer sign-off. Census of incoming tasks, not a population CI.

### Generators (Part 2 neighbors, not this study)

SWE-Universe (~807,693 envs), SWE-smith (~50k), SWE-rebench (>21k), R2E-Gym (~8k), CLI-Universe, Endless Terminals, InfoSynth, Code2Bench. They scale training or eval *construction*. They do not certify an existing eval population.

### Verifier probes

SWE-Mutation (2,636 mutants from 800 instances). ProgramBench (200 rebuilds, 248k+ behavioral tests). Reward Hacking Benchmark (planted exploits). EvalPlus and SWE-bench+ (test insufficiency / leakage on coding tasks). These are feature sources, not the estimand.

### Statistics aimed at model scores, not task validity

**FAQ** ([arXiv 2601.20251](https://arxiv.org/abs/2601.20251)). Finite-population inference for *model accuracy*, up to 5× effective sample size, valid coverage under active sampling.

**Noisy but Valid** ([arXiv 2601.20913](https://arxiv.org/abs/2601.20913)). Calibrate judge TPR/FPR on a small human set; finite-sample Type I control for *model failure rates*.

**PRECISE / PPI** ([arXiv 2606.05308](https://arxiv.org/abs/2606.05308)). Prediction-powered inference for ranking metrics.

**Berti-Équille** ([arXiv 2607.25356](https://arxiv.org/abs/2607.25356)). Progressive sampling for *tabular data-quality profiles*. Uniform sometimes beat a bad proxy. Directly relevant to H2.

## OpenAI numbers, with scope

| Source | What was measured | Number | Scope |
| --- | --- | --- | --- |
| Verified 2024 | Filtered of 1,699 random SWE-bench test tasks | 68.3% | Conservative 3-rater ensemble. Not a CI. |
| Verified 2024 | Final set | 500 | Subsample of those that passed the filter, with extra hard items kept. |
| Verified 2026 drop | Material issues among 138 o3-fail tasks | 59.4% | Conditioned on unsolved-by-o3. Not Verified-wide. |
| SWE-Bench Pro 2026 | Auto-flagged | 286 of 731 | Flags, not confirmed. |
| SWE-Bench Pro 2026 | Pipeline / human confirmed broken | 200 (27.4%) / 249 (34.1%) | Targeted review after flags. ~30% of 731 is their summary, still not a designed sample CI. |

## Matrix (short)

| System | Generates | Audits tasks | Population invalidity CI | Probability sample | Gold validity labels |
| --- | --- | --- | --- | --- | --- |
| ABA | no | yes | no | subsample caps | partial |
| BenchGuard | no | yes | no | no | author/expert |
| Harbor-Index | selects | yes | no | no | yes, exhaustive survivors |
| SWE-Universe / SWE-smith | yes | construction-time | no | no | auto |
| SWE-bench Verified 2024 | filters | yes | no (raw 68.3%) | yes, 1,699 of 2,294 | yes, 3 raters |
| OA 2026 Verified/Pro | no | yes | no | no (hard fails / flags) | yes |
| FAQ / NbV / PRECISE | no | no | yes, for *scores/judges* | yes | assumes item labels |
| **This project** | no (Part 1) | signals as predictors | **yes, for task invalidity** | **yes** | **yes, protocol-tagged** |

## What we will not claim

We will not claim automated benchmark QA is new. We will not claim Harbor-Index did not already funnel with AI plus humans. We will claim an end-to-end finite-population certification of *task validity* with coverage-checked bounds and an explicit human-budget / precision tradeoff. The 2026 search did not find that demonstration on agent-eval tasks.

The September 2026 generation, QC, and transfer-statistics frontier and our positioning are in [46-frontier-2026-09.md](46-frontier-2026-09.md).

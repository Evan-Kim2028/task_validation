# Taste and expert-level tasks: 2023 to Sep 2026 sweep

Search date: 2026-09-11. Sources were opened (HTML/site/raw), not abstracts alone. Unverified items are marked. This page is the Part 2 instrument, not Y. Validity stays binary and samplable (docs 02, 23, 24). Taste is graded, needs different instruments, and is certified on the accepted population.

**Claim.** "Expert-level, high-taste" is not a vibe. Labs already operationalize it as a small set of independently measured properties: the evaluator is evidence (validity), difficulty is essential and frontier-unsolved, items discriminate, work is paid-real, time is human-calibrated, and anti-cheat holds under execution. No source certifies taste at population scale with a design-based CI. Funnels and 3-rater filters are the closest.

## A. Rubric matrix

How measured: H = human rubric; M = cheap/frontier model; E = execution (oracle, nop, cheat, F2P); I = IRT/agent-run stats; $ = market or wage.

| Source | Validity / spec | Difficulty | Realism | Discrimination | Diversity | Novelty | Anti-cheat | Time | Economic | Instrument |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TB3 impl rubric (28 named criteria in opened toml; marketing pages say 35) | verifiable, test-instruction alignment, functional verification | difficult, essential_difficulty; undergrad-in-days = too easy | interesting: someone could be paid | not scored | category/tags | novel vs textbook | anti_cheat, environment_hygiene, outcome_verified | expert_time_estimate_hours | paid-work proxy | H+M (`harbor check`) then E (oracle/nop/live/cheat) then maintainer |
| TB proposal rubric | verifiable, well-specified | difficult for a good reason | interesting / paid | no | vs existing TB tasks | vs existing TB | outcome-verified | expert hours, not days of labor | paid | M then Discord then PR |
| Harbor-Index | instruction-verifier alignment | 18-trial pass ≤33%; essential difficulty | insight, not clerical | *not* a goal: max-hard tasks are constants for prediction | 29 of 54 benches, 7 domains | no | audit-and-fix; separate verifier sandbox; 9/1476 gamed (0.6%) | 1.2× fastest runtime or 3h | no | E then M then H (14 reviewers; 1 senior or 2 junior) then fix |
| SWE-bench Verified 2024 | underspec 0-3; FAIL_TO_PASS fairness 0-3; other major issues | 4 buckets; *not* a discard rule | real GitHub issues | no | 12 Python repos; easy kept | contamination noted, not filtered | "easily gamed" in freeform | <15m / 15m-1h / 1-4h / >4h | no | H, 93 Python devs, 3 raters, max-severity ensemble |
| SWE-Bench Pro | human rewrite + requirements + interface; test relevance | drop 1-10 LOC; mean 107 LOC / 4.1 files | copyleft + 18 commercial repos | no | 41 repos, 50-100 each | GPL + private | Docker + human test review | "hours to days" (not timed) | no | H 3-stage: env, augmentation, tests |
| GDPval | 89% well-specified (gold) | expert 1-5; win rate falls with hours | real deliverables, O*NET coverage | pairwise vs expert | 44 occupations, 9 GDP sectors | no | n/a (pairwise) | gold mean 9.5h | wage × hours; gold mean $398 | H, ≥4y (mean 14y), ~5 reviews |
| HCAST / METR horizon | auto scorer + gold + 5× agent QA | logistic vs log human time | "messiness" 16 factors; mean 3.2/16 | β in logistic; 80% horizon ~5× shorter | 78 families | 34% public solutions (HCAST) | transcript reward-hack review | geo mean of successful baselines | no | H timed + E |
| HLE | unambiguous, verifiable, non-searchable | LLM-fail gate then expert | academic, not occupational | calibration error | 100+ subjects | original / non-trivial synthesis | LLM pre-filter | n/a | $500k prizes | M then 2-round H |
| ARC-AGI-2 | pixel-exact | human accuracy index; partitions ≤1pp | fluid reasoning, not jobs | cost/task | unique tasks | unique by design | anti-brute-force | 2 attempts | $0.42/task prize constraint | H: ≥2 solvers in ≤2 tries |
| τ-bench | DB state = annotated goal + policy | pass^k reliability | policy + tools + user sim | pass^k vs pass@k | domains | public domains (leak risk) | state check, not transcript | n/a | no | E (DB) |
| SWE-Lancer | E2E Playwright, 3-rater 0-3 spec/tests | real Upwork $ | Expensify full-stack | earnings | 74% app logic | private holdout | E2E vs unit-test hacks | 26 days to close (issue age) | $50-$32k actual payouts | H 100 engineers + E2E |
| Aider polyglot | unit tests | keep if ≤3 of 7 models solved (of 697) | Exercism katas, not repos | 5-50% target band | 6 languages, 225 | moderate | tests hidden from edit | n/a | no | E + model-hard filter |
| LiveCodeBench / BigCodeBench | hidden tests; GPT-4 tests then human refine | contest / tool-use hardness | contest vs library APIs | live cutoff | rolling / diverse calls | post-cutoff problems | hidden tests | n/a | no | E; LCB/BCB papers not fully opened (via SWE-Lancer table) |
| BetterBench / How2Bench | lifecycle validity, not per-item | n/a | n/a | n/a | n/a | contamination docs | gameability | n/a | n/a | H checklist (46 / 55 criteria) |
| IRT (tinyBench, metabench, Fluid, PSN-IRT) | misfit / mislabel flags | b (difficulty) | no | a (discrimination) | factor structure | no | low-a items often bad | no | no | I from many model runs |

TB3 named criteria opened: verifiable, solvable, difficult, interesting, outcome_verified, anti_cheat_robustness, task_security, functional_verification, deterministic_reproducible, essential_difficulty, test_instruction_alignment, novel, agentic, reviewable, instruction_concision, solution_quality, environment_hygiene, structured_data_schema, typos, difficulty/solution/verification_explanation_quality, category_and_tags, task_name, resource_configuration, task_readme, expert_time_estimate, task_toml_schema. That is 28. Snorkel and tbench.ai say 35. Scale `AGENTS.md` says 28. Use 28 for the opened file; treat 35 as unverified marketing count (later PRs add `binary_reward`).

Harbor-Index funnel (opened site + 2609.04298): 6,627 → 1,311 (≤33% of 18 trials) → 307 (Gemini-3-Flash on alignment + essential difficulty) → 100 (14 humans + 3-person panel) → 82 (audit-and-fix). About one third of the hardest candidates reaching human review were rejected as broken.

SWE-bench Verified: 1,699 of 2,294, 3 raters, discard if any rater puts underspec or test fairness at 2-3 or flags other major issues. 38.3% underspec, 61.1% unfair tests, 68.3% discarded. Final 500 oversamples 1-4h and >4h. Difficulty is *not* Y.

## B. What you can measure without humans

**Execution, no LLM (cheap, Part 1 already).** Oracle pass, nop fail, revert-gold, A/B probes, F2P/P2P, cheat/sandbox isolation, determinism. TB3 oracle/nop/cheat; Harbor separate verifier sandbox; SWE-smith keep only patches that break ≥1 test; Endless Terminals pass@16>0; CLI-Universe fail-to-pass; SWE-Universe buggy-vs-fixed plus in-loop hack detector. Cost: minutes per task. Does not measure realism or essential difficulty.

**IRT / multi-agent runs, no extra humans.** Difficulty = 1 − mean score (Harbor empirical difficulty; U-shaped: 22% easiest bucket, 14.6% hardest). Discrimination = spread across tiers or 2PL `a`. Harbor: frontier gain peaks in the 0.3-0.7 band (+22 to +29 pp), near zero at both ends. PCA: 3 tasks/benchmark recover ranking at mean ρ≈0.923; hard ≠ unique. Fluid Benchmarking (2PL + Fisher selection) raises validity and cuts variance vs random sampling. tinyBenchmarks: ~100 items, ~2% RMSE on MMLU-class suites. PSN-IRT: 11 benches / 41,871 items; difficulty ceiling often below elite θ. IRT-mislabels (2605.30504): 95% precision in top 200. Cost: many model-harness trials. Needs a frozen agent mix; saturates as the mix improves.

**Cheap model.** TB3 `harbor check`; Harbor-Index stage 2 (1,311→307, high-recall); SWE-rebench Qwen-72B quality heads (clarity 79% acc, complexity 81%, test-patch 67% on Verified labels); SWE-Universe quality-judge 78.72% vs human; CLI-Universe rubric lifts human accept 72%→91% and LLM 75%→93%; GDPval auto-grader 66% vs humans (IAA 71%). Use to allocate, not to certify.

**Experts required.** Realism / "someone would be paid" (TB3 interesting; GDPval pairwise; Senior SWE-Bench taste axes: minimality, hygiene, craft. Snorkel blog opened in search only). Spec fairness (SWE-Verified 0-3). Timed baselines (HCAST 563 attempts / 1500h; METR geo mean of *successful* runs). Economic value (GDPval wage×hours; SWE-Lancer actual payouts). Population CI on residual invalidity (this repo, not found elsewhere).

## C. What difficulty, time, and realism predict

| Predictor | Evidence | Predicts |
| --- | --- | --- |
| Log human time | METR: model success vs log human time R²≈0.83, r=0.91, higher than model-model r=0.73. HCAST: 70-80% on <1h, <20% on >4h. GDPval: win rate highest at 0-2h, falls as hours rise. | Agent solve rate. Yes, on these suites. |
| Annotator time buckets | SWE-Verified: scores rise *within* bucket after removing invalids, so time was not just a proxy for brokenness. METR on Verified: exponential horizon still holds, shorter doubling, possibly because annotator times understate easy tasks for contractors. | Weak-to-moderate. Bucket estimates ≠ timed baselines. |
| Expert *forecasts* vs timed baselines | HCAST: forecast vs successful baseline R²=0.51. 79/189 tasks had no successful baseline. | Forecasts are a prior, not a substitute. |
| Whose clock | METR internal PRs: contractors 5-18× slower than maintainers. Horizons match contractor time, not maintainer time. | "Expert time" is a population choice. |
| Empirical agent difficulty | Harbor: 6,627→1,311 at ≤33%. Frontier vs rest: Δ max in mid band. Ofir Press: launch with top model at 0.1-9% (2025 note) or the bench dies. | Headroom. Selecting only max-hard kills discrimination (Harbor says this explicitly). |
| Realism / messiness | METR 16 messiness factors: +1 point ≈ −8.1 pp excess success, R²=0.25. Trend slope similar on high vs low messiness 2023-25. HCAST tasks are well-specified and solitary; authors flag this as the main external-validity hole. | Lower solve rates, not a slower capability trend on this suite. |
| Economic $ | SWE-Lancer: o1 pass@1 rises with reasoning effort especially on expensive buckets. GDPval $ is wage×self-reported hours, not a difficulty oracle. | Weak as a standalone difficulty score; useful as a quota axis. |
| Validity vs hardness | Harbor: ~1/3 of hardest human-reviewed tasks were broken. OpenAI 2026 Verified drop: 59.4% of 138 o3-fail tasks had material issues (conditioned on unsolved, not Verified-wide). | Unsolved ≠ expert-level. Filter validity first. |

No opened source measures "taste" via expert IAA as a population estimand. Closest IAA numbers: GDPval pairwise 71%; Harbor failure-mode κ=0.66 (N=200); Measuring what matters codebook Brennan-Prediger κ=0.524 (N=46 double-coded); SWE-Verified conservative max of 3 (no κ published on the page). None is a CI on a taste rate.

## D. Operational definition (7 properties)

An **expert-level high-taste task** is a task that is already *valid* (Part 1) and then meets these. Do not average them into one score (doc 24).

| # | Property | Type | Instrument | Cost | Builds on |
| --- | --- | --- | --- | --- | --- |
| 1 | **Materially valid evaluator** | binary, samplable | interrogation + human sample UCB | ~3 min/task auto; 200-300 humans per freeze | docs 02/23; TB3 verifiable; Harbor alignment |
| 2 | **Spec-test alignment** | binary, samplable | every assertion traces to instruction; no hidden names | cheap model then expert sample | SWE-Verified Q1/Q2; TB3 test_instruction_alignment; Harbor stage 2 |
| 3 | **Essential difficulty** | binary gate | fail if hardness is format, magic strings, or undergrad-days | TB3/Harbor rubric (M then H) | TB3 essential_difficulty; Harbor "not clerical" |
| 4 | **Frontier-unsolved, not saturated** | graded | pass rate on a frozen N-trial mix; keep if below a cap (Harbor used 33%) *and* above a floor so items still split models | 18 trials × 3 models × 2 harnesses is Harbor's precedent; cheaper mix possible | Harbor stage 1; Ofir Press launch band |
| 5 | **Discrimination** | graded | 2PL `a`, or spread across ≥3 model tiers; drop near-constants | reuse (4)'s matrix | IRT / Fluid / Harbor PCA (hard ≠ informative) |
| 6 | **Human-calibrated time** | graded | TB3 `expert_time_estimate_hours` as prior; METR-style timed success as gold on a sample | cheap self-report; expensive timed (HCAST ~hours/task) | METR/HCAST; SWE-Verified buckets; TB3 |
| 7 | **Paid-realism** | graded ordinal | "a working engineer would be paid to do this" + origin (real repo/issue/Upwork/O*NET). Optional $ = wage×hours or actual bounty | expert rubric; model can allocate | TB3 interesting; GDPval; SWE-Lancer; SWE-Pro commercial |

Population-only (not per-task Y): **diversity** (quotas on family/language/failure mode; Harbor panel; SWE-Pro 50-100/repo cap) and **novelty** (overlap vs existing tasks; TB3 novel; InfoSynth KL/entropy). Anti-cheat is a validity gate (property 1), re-checked with cheat trials after any repair.

## E. Generator QC and survival (Part 2 baseline)

| Generator | QC | Survival / validation | Human |
| --- | --- | --- | --- |
| SWE-smith (50,137 / 128 repos) | env first; keep if ≥1 F2P; 2 min test cap | yield 50.1% overall (Combine 96.9, LM Modify 56.0, Procedural 40.2, LM Rewrite 35.0, PR Mirror 33.8) | ~8 min/repo install parse; ~20h total author labor |
| SWE-Universe (807,693) | iterative buggy/fixed verifier; in-loop hack detector; quality-judge | build success 82.6%→94% with iteration; production non-hack success 75.9% of ~1M candidates | quality-judge 78.72% vs human labels; no census review |
| SWE-rebench (21,336 from 3,468 repos) | issue-PR filters; LLM install recipes; F2P execution; Qwen quality heads | 450k PRs → 153.4k filtered → 21.3k verified (~14% of filtered, ~4.7% of raw); install recipe works in 31% of repos | none at instance scale; labels transferred from Verified |
| R2E-Gym (8,135) | commit heuristics; F2P or generated tests; backtranslation from tests | 2.5× more than issue-only collection; 4,578 decontaminated subset | semi-manual build scripts |
| SWE-Gym (2,438 / 11 repos) | manual deps + SWE-bench F2P script | failed instances dropped (denominator not published) | ~200 annotator hours |
| Endless Terminals (3,255) | container tests; o3 pass@16>0 | ~50% discarded at solvability | none |
| CLI-Universe (6k traj) | rubric-gated tests, hint-conditional (too easy if solved without hint), F2P | ~2/3 of candidates dropped | blueprint IAA high after rubric (72%→91% human accept) |
| InfoSynth | genetic synth + self-verify | 97-98% human-correct on 100-problem samples; filter drops 16-57% depending on split | 13-27 person-hours per 1k generated |
| HCAST (eval, not train gen) | human QA, gold, 5× agent transcripts (945) | iterative rewrite, not a yield rate | 140 people, 563 attempts |
| Harbor-Index (select, not gen) | see A | 82/6,627 = 1.2%; 82/1,311 hard = 6.3% | exhaustive on the 307 |

Training generators optimize F2P and solvability. They do not certify realism, discrimination, or residual invalidity. SWE-smith difficulty rater (trained on Verified labels) is 75.3% acc and is not a human gold.

## F. Build on this, do not rebuild

1. **Keep Y = material invalidity.** Harbor, Verified, and the 2026 o3-fail audit all show unsolved and broken mixed. Certify 1-2, then measure 3-7 on the accepted set (docs 23-24).
2. **Reuse TB3's 28 implementation criteria as the realism/anti-cheat checklist**, plus the 6 proposal criteria for intake. Do not invent a 35th axis until the public toml matches the marketing number.
3. **Reuse Harbor-Index's two-part quality rubric** (alignment + essential difficulty) and its 18-trial difficulty cap as the difficulty stage. Copy the "hard ≠ predictive" warning: a 1,000-task Part 2 needs a mid-band, not only zeros.
4. **Reuse SWE-Verified 0-3 underspec / test-fairness** as the spec instrument, with 3-rater conservative ensemble as one protocol tag, not as the 2026 residual-error label.
5. **Reuse METR's logistic-vs-log-time**, but treat contractor-timed success as gold and self-reported hours as a prior. Budget for R²=0.51 if you only have author estimates.
6. **Reuse GDPval's review depth and IAA** (5 reviews, 71% pairwise) if you need paid-realism; use $ only as a quota, not as difficulty.
7. **Reuse IRT 2PL `a`/`b` on the interrogation/frontier matrix** for discrimination and for dropping misfit items (Fluid, tinyBench, 2605.30504). Fit on agents, not on humans.
8. **Reuse generator F2P + hack-detect as the floor**, not the ceiling: SWE-smith 50% yield, Endless ~50% drop, CLI-Universe 2/3 drop, SWE-Universe 76% non-hack. Expect similar attrition before taste.
9. **Reuse CLI-Universe hint-conditional filtering** to kill tasks a strong model solves without the secret. That is a cheap discrimination pre-filter.
10. **Reuse BetterBench / How2Bench / Measuring-what-matters checklists** for the *benchmark*, not the item: define the phenomenon, sample representatively, report uncertainty, hold out a contamination set. Raji et al. 2021 (cited, not re-opened as PDF) is the construct-validity warning: a score is not "expert software engineering" unless the tasks are.

## G. References (opened)

- Harbor-Index site: https://harbor-index.org/
- Shi et al., Harbor Adapters and Harbor-Index, arXiv:2609.04298, https://arxiv.org/html/2609.04298
- TB3 implementation rubric (28 criteria): https://github.com/scaleapi/terminal-bench-3-public/blob/main/rubrics/task-implementation.toml
- TB3 reviewing / AGENTS (28-criteria wording): https://github.com/scaleapi/terminal-bench-3-public/blob/main/REVIEWING.md
- TB proposal rubric: https://github.com/harbor-framework/terminal-bench/blob/main/docs/prompts/task-proposal.md
- TB3 news: https://www.tbench.ai/news/terminal-bench-3-0
- Snorkel TB3 (claims 35 criteria): https://snorkel.ai/leaderboard/terminal-bench-3-0/
- OpenAI, Introducing SWE-bench Verified (2024): https://openai.com/index/introducing-swe-bench-verified
- Annotation instructions PDF: https://cdn.openai.com/introducing-swe-bench-verified/swe-b-annotation-instructions.pdf
- Deng et al., SWE-Bench Pro, arXiv:2509.16941, https://arxiv.org/html/2509.16941
- Patwardhan et al., GDPval, arXiv:2510.04374, https://arxiv.org/html/2510.04374
- OpenAI GDPval post: https://openai.com/index/gdpval/
- Rein et al., HCAST, arXiv:2503.17354, https://arxiv.org/html/2503.17354v1
- Kwa et al., Measuring AI Ability to Complete Long Tasks, arXiv:2503.14499, https://arxiv.org/html/2503.14499v1
- Phan et al., Humanity's Last Exam, arXiv:2501.14249, https://arxiv.org/html/2501.14249
- Chollet et al., ARC-AGI-2, arXiv:2505.11831 (HTML opened via search fetch): https://arxiv.org/html/2505.11831v2
- Yao et al., τ-bench, arXiv:2406.12045, https://arxiv.org/html/2406.12045
- Miserendino et al., SWE-Lancer, arXiv:2502.12115, https://arxiv.org/html/2502.12115
- Yang et al., SWE-smith, arXiv:2504.21798, https://arxiv.org/html/2504.21798
- Chen et al., SWE-Universe, arXiv:2602.02361, https://arxiv.org/html/2602.02361
- Badertdinov et al., SWE-rebench, arXiv:2505.20411, https://arxiv.org/html/2505.20411
- Jain et al., R2E-Gym, arXiv:2504.07164, https://arxiv.org/html/2504.07164
- Pan et al., SWE-Gym, arXiv:2412.21139, https://arxiv.org/html/2412.21139
- Gandhi et al., Endless Terminals, arXiv:2601.16443, https://arxiv.org/abs/2601.16443 and https://arxiv.org/html/2601.16443v1
- CLI-Universe, arXiv:2606.22883, https://huggingface.co/papers/2606.22883 (PDF snippets opened)
- Garg et al., InfoSynth, arXiv:2601.00575, https://arxiv.org/html/2601.00575v2
- Reuel et al., BetterBench, arXiv:2411.12990, https://arxiv.org/abs/2411.12990 ; site https://betterbench.stanford.edu/
- How2Bench, arXiv:2501.10711, https://arxiv.org/html/2501.10711v3
- Bean et al., Measuring what matters, arXiv:2511.04703, https://arxiv.org/html/2511.04703 (Raji et al. 2021 cited therein; that PDF not re-opened)
- Polo et al., tinyBenchmarks, arXiv:2402.14992
- Kipnis et al., metabench, ICLR 2025, https://openreview.net/forum?id=4T33izzFpK
- Hofmann et al., Fluid Language Model Benchmarking, arXiv:2509.11106, https://arxiv.org/html/2509.11106
- Lost in Benchmarks / PSN-IRT, arXiv:2505.15055, https://arxiv.org/html/2505.15055v3
- Land & Bikel, Auditing LLM Benchmarks with IRT, arXiv:2605.30504
- Ofir Press, How to Build Good Language Modeling Benchmarks: https://ofir.io/How-to-Build-Good-Language-Modeling-Benchmarks/
- Aider polyglot: https://aider.chat/2024/12/21/polyglot.html (secondary; blog not fully fetched)
- LiveCodeBench arXiv:2403.07974 and BigCodeBench arXiv:2406.15877: construction details taken from SWE-Lancer appendix table, not independent full-paper reads
- Senior SWE-Bench taste judge: Snorkel blog search snippet only, **unverified** beyond that page
- τ²-bench: GitHub README opened, paper not fully opened
- TB 2.0 paper arXiv:2601.11868: cited by Harbor; not re-read in full this pass

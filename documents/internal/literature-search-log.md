# Literature search log

Date: 2026-09-11.

Method: web search + arXiv/HTML fetches + OpenAI blog fetch. Not a PRISMA review. Goal was to verify the locked-thesis citation list and find anything that already does population-level *task-validity* CIs.

## Verified IDs

| Claimed | Result |
| --- | --- |
| ABA 2605.26079 | exists |
| BenchGuard 2604.24955 | exists |
| Harbor-Index site + 2609.04298 | exists, 82 tasks |
| SWE-Universe 2602.02361 | exists |
| InfoSynth 2601.00575 | exists |
| Code2Bench 2508.07180 | exists |
| SWE-Mutation ACL 2026 / 2605.22175 | exists (ID in plan was anthology URL; arXiv is 2605.22175) |
| RHB 2605.02964 | exists |
| FAQ 2601.20251 | exists |
| Noisy but Valid 2601.20913 | exists |
| PRECISE 2606.05308 | exists |
| Berti-Équille 2607.25356 | exists |
| ProgramBench 2605.03546 + programbench.com | exists |
| SWE-smith 2504.21798 | exists |
| Endless Terminals 2601.16443 | exists |
| CLI-Universe 2606.22883 | exists |
| SWE-rebench 2505.20411 | exists |
| R2E-Gym 2504.07164 | exists |
| EvalPlus 2305.01210 | exists |
| SWE-bench+ 2410.06992 | exists |
| TB 2.0 paper 2601.11868 | exists |
| OpenAI Verified 2024 / 2026 drop / Pro 2026 posts | exist, numbers match with scope caveats |

## Unverified

Task Verification Bench, OpenReview `QdDcI0Ftvo`. Cloudflare. No arXiv/HF/GitHub under that name.

## Nearby papers not in the original list

- SPICE 2507.09108 (auto-label SWE issue clarity)
- BenchJack 2605.12673 (reward hacks)
- Measuring what Matters 2511.04703 (construct validity of 445 LLM benches, paper-level)
- SWE-Bench Pro Verified (OpenCompass, arXiv 2609.08149)
- Cer-Eval 2505.03814 (certifiable eval of *models*)
- Defective Task Descriptions 2604.24703 (SpecValidator)

None of these is a design-based CI on agent-task invalidity.

## Gold downloads

SWE-bench annotations: https://cdn.openai.com/introducing-swe-bench-verified/swe-bench-annotation-results.zip (fetched, parsed, 1,699 unique).

---

Date: 2026-09-11 (statistical-certification sweep; writeup `documents/30-lit-statistical-certification.md`).

Method: web search + arXiv abs/HTML (and one full HTML: Gema et al. 2406.04127). Not PRISMA. Goal: 2023-Sep 2026 statistical neighbors of a finite-population UCB on residual *task invalidity*, plus classical audit/acceptance sampling.

## Queries run

1. prediction-powered inference Angelopoulos 2023 PPI++ LLM-as-judge Bayesian PPI active PPI stratified PPI
2. "prediction-powered inference" LLM evaluation OR "dataset quality" OR benchmark 2023..2026
3. FAQ "finite-population" LLM evaluation 2601.20251 "How many samples" evaluate LLM tinyBenchmarks metabench "Efficient Benchmarking"
4. "Noisy but Valid" conformal risk control "LLM-as-a-judge" statistical guarantees "auditing with imperfect classifiers" Rogan-Gladen
5. Dodge-Romig LTPD "rule of three" "zero defect" sampling Stringer bound "monetary-unit sampling" SPRT alpha spending audit capture-recapture software inspection
6. "label errors in test sets" Northcutt cleanlab "Are We Done With" benchmark contamination audit SWE-bench Illusion UTBoost "SWE-Bench Pro" Harbor-Index BenchGuard
7. population confidence bound task invalidity OR "benchmark error rate" probability sample LLM evaluation 2023..2026
8. adaptive evaluation LLM IRT tinyBenchmarks "sample-efficient" benchmark 2023 2024 2025 2026 arXiv
9. "How many samples do you need to evaluate an LLM" arXiv
10. metabench Kipnis IRT LLM evaluation arXiv
11. "Efficient Benchmarking" LLM Perlitz arXiv 2307
12. SWE-Bench Illusion UTBoost "Are We Done with MMLU" MMLU-Redux arXiv
13. capture-recapture software inspection Eick Petersson remaining defects estimate
14. "auditing with imperfect classifiers" Chouldechova OR "conformal risk control" Angelopoulos Bates "selective classification" LLM judge guarantees
15. Active statistical inference Zrnic Candes Cross-prediction-powered inference arXiv 2403
16. Dawid-Skene multi-rater consensus LLM evaluation noisy labels 2023 2024 2025
17. PPI++ coverage failure low prevalence binary mean Clopper-Pearson hypergeometric finite population proportion bound
18. "how many samples" "evaluate" LLM OR "language model" confidence interval benchmark site:arxiv.org
19. Berti-Equille progressive sampling data quality 2607.25356 ABA 2605.26079 BenchGuard Harbor-Index 2609.04298
20. SWE-bench+ 2410.06992 "The SWE-Bench Illusion" arXiv contamination audit OpenCompass 2609.08149
21. "auditing with imperfect classifiers" paper arXiv OR "audit" "imperfect classifier" dataset quality bound
22. SPRT sequential probability ratio test alpha spending audit sampling Lan-DeMets O'Brien-Fleming quality control
23. Stringer bound monetary unit sampling MUS audit sampling finite population
24. "rule of three" zero defects Clopper-Pearson "if no events" 3/n upper bound sampling audit
25. "LLM-as-a-judge" "statistical guarantees" Jung conformal arXiv
26. Fluid Benchmarking IRT Allen Institute arXiv
27. The SWE-Bench Illusion arXiv ID Liang Moghaddam

## Opened (new vs prior log)

PPI family: 2301.09633, 2311.01453, 2406.04291, 2405.06034, 2403.03208, 2309.16598, 2502.02363, 2603.19160, 2605.16354, 2605.31278, 2606.05308. Scores/IRT: 2411.00640, 2402.14992, 2308.11696, 2407.12844, 2509.11106, 2505.03814, 2506.07673, 2511.04689, 2606.22826. Judges: 2601.05420, 2511.21140, 2407.18370, 2208.02814, 2602.13110. Audits: 2103.14749, 2406.04127 (full HTML), 2506.12286, 2506.09289, 2410.06992. Classical: ASTM E2334 (secondary), rule-of-three explainers, Stringer/MUS papers, SPRT/Lan-DeMets, Eick/Petersson capture-recapture reviews. Fogliato/Chouldechova AISTATS 2020 (noisy-label fairness).

Already verified in the 2026-09-11 thesis log and re-opened as needed: FAQ, NbV, PRECISE, Berti-Équille, ABA, BenchGuard, Harbor-Index, OpenCompass.

## Rejected as irrelevant to the estimand

- PredictaBoard 2502.14445 (score predictability / rejection, not task-validity CI)
- PiCSAR 2508.21787 (reasoning-chain ranking)
- LifeEval / confidence calibration 2605.23909 (model overconfidence)
- Indeed Engineering bootstrap-CI blog (infinite-pop model eval)
- BenchLM confidence flags (leaderboard provenance)
- UBench 2406.12784 (MCQ uncertainty)
- "Know When You're Wrong" 2603.06604 (self-confidence AUROC)
- Nature MI 2026 confidence-to-behaviour (not sampling)
- Towards Data Science "95% Illusion" (CI pedagogy)
- Inference Scaling Flaws (verifier FPR for resampling)
- Ensembling LLMs for cybersecurity requirements (Dawid-Skene as fusion, not pop CI)
- Shapley-credited Dawid-Skene for AV (multi-label VLM fusion)
- Cost Efficient Fairness Audit 2510.03734 (fairness under partial feedback)
- Cheap Verifiers, Large Blind Spots 2609.01345 (cascade verifier floors; adjacent, not a task-pop UCB)
- Classification with imperfect training labels 1805.11505
- Identifying Mislabeled Instances 1912.05283
- Measuring Five-Nines Reliability 2605.11209 (rare *model* failure on parameterized GSM8K)
- Do Repetitions Matter 2509.24086 (run-to-run, not item sample)
- ReliableEval 2505.22169 (prompt-perturbation moments)
- Benchmark Illusion 2602.11898 (cross-model disagreement, not task defects)
- PRECISE 2601.18777 (duplicate of 2606.05308)
- Doubly-Robust LLM-as-a-Judge 2509.22957 (persona sampling bias, not task Y)
- Conformal Elo 2606.13221 (judge Elo intervals)
- Hierarchical Group-Conditional CRC 2607.24562 (per-group selective risk)
- STABLEVAL 2605.02122 (ranking stability under annotators)
- Calibrate Don't Curate 2605.09702 (judge-panel calibration, not pop invalidity)
- PPI across many tasks 2605.29249 (multi-task recalibration of *model* behaviors)
- FAB-PPI kept as PPI variant, not as a competitor estimand
- Cannings/Fan/Samworth imperfect labels (classifier risk, not audit)
- Sabato/Sarwate/Srebro "Auditing" 1306.2347 (active learning cost, different meaning)
- MMLU-Pro 2406.01574 (harder MMLU; quality not CI)
- Global MMLU 2412.03304 (cultural bias)
- "Are We Done with ImageNet" Beyer 2006.07159 (pre-2023; cited only via Gema)

## Titles that did not resolve

- "How many samples do you need to evaluate an LLM": no paper with that title. Operational stand-in: Miller 2411.00640.
- "Auditing with imperfect classifiers": no paper with that title. Stand-in: Fogliato/Chouldechova 2020 + NbV + Lee et al. 2511.21140.
- Task Verification Bench / OpenReview `QdDcI0Ftvo`: still no public PDF (unchanged from the thesis log).

## Exact-claim result

No opened paper gives a design-based, coverage-checked, one-sided finite-population UCB on residual *agent-task invalidity*. Closest point estimate of sampled benchmark item error: Gema et al. 2406.04127 (6.49%, no UCB).

---

Date: 2026-09-12 (per-task 2026 label-source sweep; writeup `documents/37-labels-2026.md`, catalog `data/gold/label_sources_2026.json`).

Method: web search + opening GitHub/HF/arXiv HTML/data hosts. Goal: 2026 (or still-current live-bench) per-task human labels, repairs, errata, exclusions, or audit verdicts joinable to task IDs. 2024 SWE-bench annotations treated as out of date.

## Queries run

1. Automated Benchmark Auditing ABA arXiv 2605.26079 GitHub HuggingFace per-task audit
2. huggingface auto-bench-audit annotations findings dataset IsThatYou
3. BenchGuard 2604.24955 ScienceAgentBench BIXBench defect list dataset GitHub
4. OpenAI Separating Signal from Noise in Coding Evaluations 2026 SWE-bench Verified audit IDs
5. zai-org terminal-bench-2-verified HuggingFace changelog per-task
6. harbor-framework terminal-bench-2-1 PR 53 task bug issues 2026
7. SWE-Bench Pro Verified OpenCompass scaleai errata GitHub issues 2026
8. "benchmark audit" "task validity" "broken tasks" errata verified subset 2026 arXiv
9. harbor-index.org rejection reasons task list 82 307 100 GitHub huggingface
10. SWE-rebench quality labels 2026 huggingface nebius
11. HLE reviewed errata Humanity's Last Exam dataset corrections 2026 huggingface
12. "BIXBench" Verified-50 huggingface dataset expert revision
13. tau-bench tau2-bench errata broken tasks GitHub 2026
14. LiveCodeBench LiveBench issue tracker errata 2026 per-task
15. BigCodeBench-Hard corrections errata GitHub 2026
16. 2607.02577 tool-calling validity audit dataset github huggingface artifacts per-task
17. harbor-adapters-experiments rejected tasks list GitHub funnel 307
18. Terminal-Bench 3.0 QA rubric outputs published dataset 2026
19. DeepSWE Datacurve SWE-bench Pro audit per-task 2026 github huggingface
20. Task Verification Bench OpenReview QdDcI0Ftvo dataset 2026

Plus GitHub/HF API probes: IsThatYou/auto-bench-audit, XinmingTu/BenchGuard/eval/data/gold, data.autobenchaudit.com, scaleapi/SWE-bench_Pro-os issues, harbor-framework/terminal-bench-2/pulls/53, sierra-research/tau2-bench CHANGELOG, LiveCodeBench/ERRATA.md, kimjune01/program-bench-audit, kimjune01/deepswe-run, benchjack/benchjack/audits, skylenage-ai/HLE-Verified, phylobio/BixBench-Verified-50, openreview.net/forum?id=QdDcI0Ftvo.

## Opened (new vs prior log)

ABA: autobenchaudit.com, data.autobenchaudit.com (index.json, swe_bench_verified/pro/tb2 benchmark.json, trajectory_audits JSON), github.com/IsThatYou/auto-bench-audit, arXiv 2605.26079 HTML.
BenchGuard: github.com/XinmingTu/BenchGuard, sab_gold.json, bixbench_gold.json, arXiv 2604.24955 PDF tables.
OpenAI: openai.com/index/separating-signal-from-noise-coding-evaluations/, openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/.
TB: harbor-framework/terminal-bench-2 PR 53, harbor-framework/terminal-bench-2-1 issues, huggingface.co/datasets/zai-org/terminal-bench-2-verified, tbench.ai/news/terminal-bench-3-0.
Pro: huggingface.co/datasets/opencompass/SWEBench-Pro-Verified, scaleapi/SWE-bench_Pro-os issues (incl. #108).
Harbor-Index: harbor-index.org, arXiv 2609.04298 HTML, github.com/harbor-framework/harbor-index.
Other: nebius/SWE-rebench, skylenage-ai/HLE-Verified, phylobio/BixBench-Verified-50, sierra-research/tau2-bench CHANGELOG.md, LiveCodeBench/ERRATA.md, kimjune01/program-bench-audit, kimjune01/deepswe-run, benchjack/benchjack, arXiv 2607.02577, OpenReview QdDcI0Ftvo (challenge redirect).

## Result for this sweep

Usable new 2026 joinable gold: ABA coding slice (agent audit, IDs public); BenchGuard SAB 12 + BIX 17/24 (human/author); tau2 CHANGELOG 75+ named IDs; TB 2.1 residual issues; LCB ERRATA 17; DeepSWE oracle 4/113; ProgramBench skip 25; HLE-Verified 2500 (QA). OpenAI 138 and 249 IDs not public. Harbor-Index rejects not published. TB3 rubric outputs not published. TVB still no PDF. 2607.02577 artifacts not found.

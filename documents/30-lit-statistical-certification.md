# Statistical certification of residual task invalidity: literature sweep

Search date: 2026-09-11. Scope: 2023 to September 2026, plus classical estimators we reuse. Every numbered paper was opened (arXiv abs/HTML, or a cited standard via a secondary source marked below). This is not a PRISMA review.

The estimand here is the residual rate of *material task invalidity* in a frozen accepted pool, with cheap automated evidence as an auxiliary, certified from a small human probability sample.

## A. What is already established

### 1. Prediction-powered inference and model-assisted survey estimation

| Paper | Shows | Does not | URL |
| --- | --- | --- | --- |
| Angelopoulos et al. 2023 PPI | Valid CIs for means (and more) from scarce gold + abundant ML predictions; rectifier is unbiased even if f is biased. | Finite-pop hypergeometric UCB at low p; task-invalidity estimand. | https://arxiv.org/abs/2301.09633 |
| PPI++ 2311.01453 | Power-tuned λ; CIs that asymptotically never worse than labeled-only. | Coverage of the *normal* UCB when p is near 0 and n is tens to low hundreds. | https://arxiv.org/abs/2311.01453 |
| StratPPI 2406.04291 | Stratification tightens hybrid LLM-eval CIs without assuming the autorater. | Binary rare-event UCB; task validity. | https://arxiv.org/abs/2406.04291 |
| Bayesian PPI 2405.06034 | Stratified and chain-rule proxies for discrete LLM judges. | Frequentist Type I at low p. | https://arxiv.org/abs/2405.06034 |
| Active inference 2403.03208 | Adaptive labeling with valid CIs; PPI is the uniform-sampling special case. | Finite-pop task-invalidity bound. | https://arxiv.org/abs/2403.03208 |
| Cross-PPI 2309.16598 | Train f on the labeled set via cross-fitting; often tighter than split PPI. | Release rule for a frozen pool. | https://arxiv.org/abs/2309.16598 |
| Mozer 2603.19160 | PPI = Cassel difference estimator; PPI++ = GREG (Särndal). | New estimator. | https://arxiv.org/abs/2603.19160 |
| PRECISE 2606.05308 | PPI for ranking metrics (P@K); 21% SE cut at n=30 gold. | Task invalidity. | https://arxiv.org/abs/2606.05308 |
| Kim 2605.16354 | Two-stage design: LLM on all units, humans on a subsample; doubly robust; n from asymptotic variance. Closest design paper to ours. | Agent-task validity; exact low-p UCB. | https://arxiv.org/abs/2605.16354 |
| GLIDE 2605.31278 | Library: PPI++, StratPPI, PTD, active inference; MC validation + method-selection tree. | Does not invent a new estimand. | https://arxiv.org/abs/2605.31278 |

### 2. Finite-population inference for *model scores* (not task validity)

| Paper | Shows | Does not | URL |
| --- | --- | --- | --- |
| FAQ 2601.20251 | Benchmarking as finite-pop inference; up to 5× ESS vs uniform; coverage via Pro-Active Inference. | Item *validity* CI. | https://arxiv.org/abs/2601.20251 |
| Miller 2411.00640 | Super-pop SEs, clustered SEs, n for MDE; report n and SE. Exact title "How many samples do you need to evaluate an LLM" was not found. | Finite-pop UCB; task defects. | https://arxiv.org/abs/2411.00640 |
| tinyBenchmarks 2402.14992 | IRT anchors: ~100 items recover MMLU within ~2%. | Validity of those items. | https://arxiv.org/abs/2402.14992 |
| Efficient Benchmarking 2308.11696 | HELM cost vs ranking reliability; often ×100 compute cut. | Task-invalidity bound. | https://arxiv.org/abs/2308.11696 |
| metabench 2407.12844 | IRT on >5k models; <3% of six benches reconstruct scores. | Item quality CI. | https://arxiv.org/abs/2407.12844 |
| Fluid 2509.11106 | Adaptive 2PL IRT; fewer mislabeled items than random on MMLU-Redux. | Population invalidity UCB. | https://arxiv.org/abs/2509.11106 |
| Cer-Eval 2505.03814 | Adaptive test-sample complexity for *model* accuracy with 95% guarantee. | Task validity. | https://arxiv.org/abs/2505.03814 |
| Zhang et al. 2506.07673 | Random sample + regression beats most "smart" subsets; all methods fail at the evaluation frontier. | Task-invalidity estimand. | https://arxiv.org/abs/2506.07673 |

### 3. Noisy labels and judges with guarantees

| Paper | Shows | Does not | URL |
| --- | --- | --- | --- |
| NbV 2601.20913 | Calibrate judge TPR/FPR on small humans; finite-sample Type I for *model failure rates*. Explicitly not PPI. | Task-invalidity UCB. | https://arxiv.org/abs/2601.20913 |
| Chen et al. 2601.05420 | For binary means, tuned PPI++ = EIF; PPI variance < Rogan-Gladen; RG intervals explode at weak judges. | Finite-pop hypergeometric. | https://arxiv.org/abs/2601.05420 |
| Lee et al. 2511.21140 | Rogan-Gladen plug-in CI for LLM-as-judge; unbiased under calib/test shift; regimes where judge+human beats human-only. | Task validity. | https://arxiv.org/abs/2511.21140 |
| Jung et al. 2407.18370 | Selective LLM-as-judge with guaranteed human agreement (CRC-style); escalate cheap→strong. | Population defect rate. | https://arxiv.org/abs/2407.18370 |
| CRC 2208.02814 | Distribution-free bound on expected risk of a monotone procedure. | Finite-pop proportion. | https://arxiv.org/abs/2208.02814 |
| SCOPE 2602.13110 | Selective pairwise judging with FDR-style risk ≤ α among accepted judgments. | Residual invalidity of a task pool. | https://arxiv.org/abs/2602.13110 |

"Auditing with imperfect classifiers" as a title was not found. Nearest: Fogliato, Chouldechova, G'Sell (AISTATS 2020) on fairness under noisy labels (https://proceedings.mlr.press/v108/fogliato20a.html); NbV and Lee et al. are the LLM versions. Dawid-Skene (1979) is the multi-rater EM consensus model; recent LLM panels use it as an aggregator, not as a population CI.

### 4. Acceptance sampling and audit sampling

Dodge-Romig LTPD tables: consumer risk 0.10 at a stated lot percent defective; hypergeometric Type A OC curves. ANSI/ASQ Z1.4 (ISO 2859): AQL-indexed switching; not a CI. Rule of three: if k=0 in n iid trials, one-sided 95% UCB ≈ 3/n (Hanley & Lippman-Hand 1983; ASTM E2334 for the finite-lot zero-response case). Stringer bound (MUS/PPS): conservative upper bound on total overstatement; too wide for a binary invalidity rate. Wald SPRT: sequential accept/reject with fixed α, β; Lan-DeMets (1983) alpha spending for unplanned looks. Capture-recapture in software inspection (Eick et al. 1992; Petersson et al. 2004 CIs): remaining-defect *count* from overlapping inspectors; needs ≥4 inspectors and underestimates with two. Secondary sources for the books/standards: not the 1959 Dodge-Romig volume itself.

Nearest 2026 statistical neighbour: Kato and Nakagawa, arXiv 2604.06116, *Sequential Audit Sampling for Finite Populations with Exact and Simulation-based Guarantee* (v1 7 Apr 2026, titled *Sequential Audit Sampling with Statistical Guarantees*). It bounds a financial-statement lot deviation rate and the sequential procedure's own error probabilities. Financial auditing, not benchmark auditing; different estimand, same design family.

### 5. Dataset and benchmark quality audits (statistical claims)

| Paper | Shows | Does not | URL |
| --- | --- | --- | --- |
| Northcutt et al. 2103.14749 | Confident learning + crowd: ~3.3% label errors across 10 test sets (ImageNet val ≥6%). Flag-then-review, not SRS of all items. | Design-based CI. | https://arxiv.org/abs/2103.14749 |
| Gema et al. 2406.04127 | Stratified 100/subject (n=5,700): **6.49% of MMLU items erroneous**. Point estimate; two-rater κ 0.64-0.96; auto-detect F2 ≤0.42. Closest published *sampled error rate*. | One-sided UCB; coverage lab; agent tasks. | https://arxiv.org/abs/2406.04127 |
| Berti-Équille 2607.25356 | Progressive sampling for tabular DQ profiles; **uniform beats bad proxies** (DAG 11-49× worse MRE). | Task-invalidity Y. | https://arxiv.org/abs/2607.25356 |
| ABA 2605.26079 | Agentic audit of 168 benches; 25.7% tasks with major issues; filtering moves SWE-Verified / TB2 by +9.9 / +9.6. | Population CI. | https://arxiv.org/abs/2605.26079 |
| BenchGuard 2604.24955 | Cross-artifact LLM audit; 12 confirmed SAB defects; 83.3% match on BIXBench-50. | CI. | https://arxiv.org/abs/2604.24955 |
| SWE-bench+ 2410.06992 | 32.7% "successes" leak solutions; 31.1% weak tests; resolve rate 12.5%→4.0% after filter. | Designed sample CI. | https://arxiv.org/abs/2410.06992 |
| SWE-Bench Illusion 2506.12286 | Up to 76% file-path ID from issue text alone; contamination/memorization, not invalidity CI. | Validity bound. | https://arxiv.org/abs/2506.12286 |
| UTBoost 2506.09289 | 36 insufficient-test instances; 345 false-pass patches; leaderboard rank changes. | Population UCB. | https://arxiv.org/abs/2506.09289 |
| Harbor-Index 2609.04298 | Funnel 6627→82; exhaustive human on survivors. Funnel observation, not a bound on 6627. | CI. | https://arxiv.org/abs/2609.04298 |
| OpenCompass 2609.08149 | Pro Verified: 102/731 repaired (leakage + quality). Census of a targeted repair set. | Probability-sample CI. | https://arxiv.org/abs/2609.08149 |
| Dong et al. 2607.28367 | Wilson interval on the rate of wrong FAIL verdicts over 150 failure trajectories. A real CI on an audit quantity. | Residual task-invalidity bound on an accepted pool. | https://arxiv.org/abs/2607.28367 |

OpenAI Verified 2024 (68.3% of 1,699/2,294 filtered) and Pro 2026 (~30% of 731) are large reviews, not designed CIs. TB 2.1/3.0 is a construction census.

**Exact claim.** Nobody opened here states a *design-based, coverage-checked, one-sided finite-population confidence bound on residual task invalidity of an accepted agent-eval pool*. Closest: Gema et al. (sampled MMLU item-error *point* estimate); FAQ/NbV/PPI/Kim (scores or judges, not task Y); OpenAI/Harbor/ABA (audits without a UCB); Kato & Nakagawa (financial lot deviation rate, accounting); Dong et al. (Wilson CI on wrong-FAIL verdicts among failure trajectories, not a pool bound).

## B. What we can directly reuse

| Piece | Mapping |
| --- | --- |
| Hypergeometric / Clopper-Pearson one-sided UCB; rule of three (n=59 for ε=5%, k=0) | Already the release estimator (`sampling/`). ASTM E2334 is the zero-response finite-lot sibling. |
| Dodge-Romig Type A OC curves | Doc 23 certify-probability table *is* an OC curve at LTPD=ε, c=0. Use those tables rather than inventing OC math. |
| PPI++ / GREG (`ppi_py`, GLIDE) | Already implemented; lab at AUROC 0.70. Keep as research arm, not release. |
| Poststrat-CP (Bonferroni per score bin) | Only assisted bound that covered in `ppi_lab.json`. Use if we must report an assisted interval. |
| Kim 2605.16354 two-stage + DR sample-size | Formalize "LLM/interrogation on N, humans on n". Allocate extra humans where the auxiliary is weak (exactly our AUROC 0.70 case). |
| Lee / Chen Rogan-Gladen vs PPI++ | If the auxiliary is a *binary* interrogation verdict, RG is the misclassification correction; do not use it as the release UCB (too wide / unstable at weak TPR+TPR-1). |
| Two-rater + tiebreak | Matches OpenAI 3-rater ensemble and MMLU-Redux dual review. Dawid-Skene only if we scale past two raters. |
| FAQ Pro-Active Inference | If we later drop SRS for active allocation, borrow their finite-pop coverage fix; do not replace the SRS arm. |
| Berti-Équille uniform | Keep SRS as the inferential arm even when the risk score ranks. |
| Gold corpora | SWE-Verified 1,699 labels; MMLU-Redux 5,700; Harbor-Index 82; OpenCompass 102 repairs. Calibration/eval-only (ADR-0011). |
| GLIDE method tree | Do not rebuild PPI variants; call or copy the tree. |

## C. Agree / disagree

- **PPI gains at weak auxiliaries.** PPI++ theory says λ→0 and you recover classical. Our lab: at AUROC 0.70, n_eff/n ≈ 1.11 on the dirty full set (useless for certification) and the *normal* UCB *undercovers* on thin p=0.009-0.049 (coverage 0.38-0.91). Agrees with Chen: RG/normal intervals misbehave at weak noise; disagrees with the slogan "PPI++ always improves." The failure is the normal tail, not unbiasedness of the point.
- **Uniform vs proxies.** Berti-Équille: uniform beats bad proxies. Zhang 2506.07673: random + regression beats most curated subsets; methods fail when extrapolating. Matches static spec/test AUROC 0.41/0.42 and OOF 0.70 that still leaves 34% invalid in the lowest-risk 5%.
- **Typical test-set error rates.** Northcutt ~3.3% (vision/NLP/audio); MMLU-Redux 6.49%; OpenAI Verified conservative 68.3% *invalid-or-unusable* on SWE-bench test (different construct); ABA 25.7% major issues on agent tasks; Harbor funnel "~1/3 of the hardest are broken." Agent-eval invalidity is an order of magnitude above ImageNet-style label noise. Do not import 3% as the prior for Terminal-Bench-class tasks.
- **Two raters.** Our 0.85 agreement / FNR 0.16 vs majority is in the same band as MMLU-Redux binary κ and OpenAI's 3-rater spread. One rater is not consensus.
- **IRT/tiny benches.** They shrink *score* evaluation, not defect auditing. Fluid even *avoids* mislabeled items, which is the opposite of a validity census.

## D. Novelty boundary

**What nobody has done (that we are doing):** an end-to-end, frozen-pool, design-based one-sided 95% UCB on *material task invalidity* for agent-eval tasks, with a coverage-checked estimator (SRS hypergeometric; stratified-normal rejected), an explicit human-budget table as an OC curve, protocol-tagged gold, and cheap evidence used to *allocate* not to *infer*.

**What we thought was novel that is not:** automated benchmark QA (ABA, BenchGuard, Harbor-Index, TB 3.0); PPI for hybrid eval (Angelopoulos, StratPPI, PRECISE, GLIDE); finite-pop CIs for *model accuracy* (FAQ); sampled *item-error rates* on MCQ benches (MMLU-Redux); acceptance sampling / rule of three; GREG/difference estimation (Särndal; Mozer). Sublinear-in-N human cost is classical sampling, already true without PPI.

## E. Build on this instead of rebuilding

1. Keep SRS-CP / hypergeometric as the release rule; treat PPI++ as optional (Angelopoulos 2311.01453; our `ppi_lab.json`).
2. If assisted inference is required, use poststrat-CP or GLIDE's tree, not a homemade normal UCB (2605.31278).
3. Use Kim's two-stage DR sample-size formula to budget humans where the auxiliary is weak (2605.16354).
4. For a binary interrogation verdict, compare PPI++ vs Rogan-Gladen vs EIF on the same lab (2601.05420, 2511.21140); do not ship RG as the bound.
5. Read OC curves from Dodge-Romig / c=0 plans instead of re-deriving P(certify | p, n, ε).
6. For sequential looks, spend alpha (Lan-DeMets) or freeze the pool; do not peek with a fixed-n UCB.
7. Do not use capture-recapture with two raters (Eick/Petersson: ≥4 inspectors).
8. Calibrate on MMLU-Redux-style *stratified item samples* plus SWE-Verified 1,699; never pool protocols (2406.04127).
9. Treat Harbor-Index / ABA / OpenCompass as transfer tests, not as CIs (2609.04298, 2605.26079, 2609.08149).
10. If we abandon SRS, copy FAQ's finite-pop active-inference coverage, not tinyBenchmarks IRT (2601.20251 vs 2402.14992).

## F. References (opened)

PPI / survey: Angelopoulos et al. https://arxiv.org/abs/2301.09633 ; PPI++ https://arxiv.org/abs/2311.01453 ; StratPPI https://arxiv.org/abs/2406.04291 ; Bayesian PPI https://arxiv.org/abs/2405.06034 ; Active inference https://arxiv.org/abs/2403.03208 ; Cross-PPI https://arxiv.org/abs/2309.16598 ; FAB-PPI https://arxiv.org/abs/2502.02363 ; Mozer https://arxiv.org/abs/2603.19160 ; PRECISE https://arxiv.org/abs/2606.05308 ; Kim https://arxiv.org/abs/2605.16354 ; GLIDE https://arxiv.org/abs/2605.31278 ; ppi_py https://github.com/aangelopoulos/ppi_py ; GLIDE code https://github.com/EmertonData/glide

Scores / IRT: FAQ https://arxiv.org/abs/2601.20251 ; Miller https://arxiv.org/abs/2411.00640 ; tinyBenchmarks https://arxiv.org/abs/2402.14992 ; Efficient Benchmarking https://arxiv.org/abs/2308.11696 ; metabench https://arxiv.org/abs/2407.12844 ; Fluid https://arxiv.org/abs/2509.11106 ; Cer-Eval https://arxiv.org/abs/2505.03814 ; Zhang et al. https://arxiv.org/abs/2506.07673 ; ATLAS https://arxiv.org/abs/2511.04689 ; MINCE https://arxiv.org/abs/2606.22826

Judges / noise: NbV https://arxiv.org/abs/2601.20913 ; Chen et al. https://arxiv.org/abs/2601.05420 ; Lee et al. https://arxiv.org/abs/2511.21140 ; Jung et al. https://arxiv.org/abs/2407.18370 ; CRC https://arxiv.org/abs/2208.02814 ; SCOPE https://arxiv.org/abs/2602.13110 ; Fogliato et al. http://proceedings.mlr.press/v108/fogliato20a.html

Audits: Northcutt https://arxiv.org/abs/2103.14749 ; Gema et al. https://arxiv.org/abs/2406.04127 ; Berti-Équille https://arxiv.org/abs/2607.25356 ; ABA https://arxiv.org/abs/2605.26079 ; BenchGuard https://arxiv.org/abs/2604.24955 ; SWE-bench+ https://arxiv.org/abs/2410.06992 ; Illusion https://arxiv.org/abs/2506.12286 ; UTBoost https://arxiv.org/abs/2506.09289 ; Harbor-Index https://arxiv.org/abs/2609.04298 ; OpenCompass https://arxiv.org/abs/2609.08149 ; Dong et al. https://arxiv.org/abs/2607.28367 ; Kato & Nakagawa https://arxiv.org/abs/2604.06116

Classical (secondary; originals not opened): rule of three / ASTM E2334; Dodge-Romig LTPD; ANSI Z1.4; Stringer/MUS; Wald SPRT; Lan-DeMets 1983; Eick et al. 1992; Petersson et al. 2004; Rogan & Gladen 1978; Dawid & Skene 1979; Clopper & Pearson 1934; Särndal GREG via Mozer.

Unverified: Task Verification Bench (OpenReview `QdDcI0Ftvo`); a paper literally titled "How many samples do you need to evaluate an LLM"; a paper literally titled "auditing with imperfect classifiers".

The September 2026 generation, QC, and transfer-statistics frontier and our positioning are in [46-frontier-2026-09.md](46-frontier-2026-09.md).

# IRT taste vs 2024 validity labels

No humans, no docker. Question: do difficulty and discrimination from public agent submissions relate to the 2024 specification labels?

## Data

SWE-bench experiments `evaluation/test/*/results/results.json` at commit `40f164d5b8f1d249bf95a6df8b74b577fd8e519d` (`data/raw/swe-bench-experiments/CLAIMS.md`). 24 test-split submissions on disk. Matrix restricted to the 1,699 labeled items. Cell = 1 if resolved, missing if `no_generation` or `no_logs`, else 0 among attempted. Keep a submission if it attempted at least 90% of 1,699: **21 survive**. Dropped: `20240402_sweagent_claude3opus`, `20240728_sweagent_gpt4o`, `20240820_honeycomb`. The verified 500-item runs cannot hit 90% of 1,699 and are out of the matrix.

Y from `swe_rater_targets.jsonl`: conservative 1,160/1,699 (68.3%), majority 764 (45.0%), unanimous 390 (23.0%). Severity axes (`underspecified`, `false_negative`) are additional Y, never predictors (ADR-0006). OOF ranker: `oof_openai_2024_conservative.oof.jsonl` field `p_logistic`.

## Method

Per item: solve rate `p_i`; rest-score point-biserial; 2PL joint MLE (MML-free) by alternating ridge logistic Newton on `logit = a_i theta_j + d_i`, `b_i = -d_i/a_i`. Theta standardized each cycle (mean 0, sd 1); `a` clipped to [0.01, 5]; L2 ridge toward 0 (`lambda_a=0.15`). Converged in 20 cycles, NLL 18871 to 7166. Near-constant: `p_i < 0.02` or `> 0.98` (here 649 items, all `p_i=0`). AUROC 1,000-rep bootstrap 95% CI. Mann-Whitney U is stdlib, one-sided `p_less` for invalid < valid. Combination, frozen: retain lowest `z(p_logistic) - z(a_i)`.

Frozen predicate (written before computing): invalid items have lower 2PL discrimination (median `a_i` lower, U-test p < 0.01) and are over-represented among near-constant items.

## a. AUROC for predicting invalid

Higher `a_i` / pbis predict *valid*, so those AUROCs sit below 0.5.

| Y | 1 - p_i | a_i | pbis |
| --- | ---: | ---: | ---: |
| conservative | 0.762 (0.740, 0.786) | 0.251 (0.227, 0.276) | 0.246 (0.222, 0.270) |
| majority | 0.757 (0.735, 0.779) | 0.266 (0.242, 0.287) | 0.258 (0.235, 0.281) |
| unanimous | 0.740 (0.716, 0.764) | 0.280 (0.253, 0.306) | 0.277 (0.251, 0.302) |

`1-p_i` vs underspec>=2: 0.638 (0.614, 0.663). vs FN>=2: 0.759 (0.738, 0.782). Agent failure tracks unfair tests more than underspec.

## b. Valid vs invalid (median, MWU p_less)

| Y | p inv | p val | p U p | a inv | a val | a U p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| conservative | 0.024 | 0.333 | 6.5e-72 | 0.069 | 3.857 | 4.2e-65 |
| majority | 0.000 | 0.286 | 2.5e-79 | 0.014 | 3.408 | 1.0e-65 |
| unanimous | 0.000 | 0.190 | 4.1e-50 | 0.014 | 3.082 | 2.2e-42 |

pbis medians, conservative: 0 vs 0.677. `a` vs pbis r = 0.98; both track `p_i` (spearman `p,a` = 0.85). With 21 systems, 2PL `a` is not a second construct.

## c. Residual invalidity at retain 5/10/20% (conservative; k = 85/170/340)

| Rule | 5% | 10% | 20% |
| --- | ---: | ---: | ---: |
| highest `a_i` | 0.353 | 0.359 | 0.385 |
| mid-band `p_i` (closest to 0.5) | 0.447 | 0.435 | 0.468 |
| OOF `p_logistic` | 0.341 | 0.365 | 0.429 |
| combination `z(OOF)-z(a)` | 0.282 | 0.300 | 0.344 |

All items with `p_i` in [0.2, 0.8]: n=653, residual 0.458 vs base 0.683. OOF 5% residual 0.341 matches the existing cheap-feature curve (doc 23: 34%). Combination is a modest lift, not a certificate.

## d. Frozen predicate

**PASS** on conservative Y. Median `a_i` 0.069 vs 3.857, U p_less = 4.2e-65. Near-constant n=649: invalid rate 0.894 vs 0.552 off-constant; P(near-constant | invalid)=0.50 vs 0.128 given valid.

## What this adds, and what it does not

Psychometrics gives a no-human score for doc 31 properties 4 and 5. `p_i` is the frontier-unsolved / saturation number (property 4). Near-constant flags, and `a_i` when it moves, are the discrimination number (property 5). `1-p_i` even ranks 2024 invalidity a bit better than cheap metadata (AUROC 0.76 vs 0.70), and the FN axis is the reason: broken tests are items agents do not solve.

It does not replace Part 1. The high-`a` 5% tail is still 35% conservative-invalid. The mid-band (the items you would keep for headroom) is 46% invalid. Dropping the 649 never-solved items leaves 55% invalid. Combination with OOF gets to 28% at 5% retain, still far above epsilon=5%. Unsolved is mixed with broken, as Harbor and the 2026 o3-fail audit said.

`a` magnitudes are not portable: J=21, 270 items clip at 5, and `a` restates solve-rate rank. Fit 2PL on a frozen mix after the validity gate, then use `p_i` as a cap-and-floor and drop near-constants. Do not use either as Y.

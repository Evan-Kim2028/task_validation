# Sampling and certification

Code: `src/task_validation/sampling/`.

## Designs

| Name | Role |
| --- | --- |
| Simple random | Cleanest inference |
| Stratified random | Language, benchmark, family, difficulty, source, risk bucket |
| Risk-guided | Oversample the tail. Good for finding defects. Biased as a raw mean unless HT-corrected. |
| Hybrid | 60% SRS / 20% stratified / 15% high-risk / 5% novel. Population estimate from the SRS arm until HT on the union is frozen. |

Every unit records `inclusion_prob`. Without that, unequal-probability samples cannot be estimated.

## Estimators

Simple random, finite population of size N, k invalids in n draws:

- Point estimate: k/n
- One-sided 95% UCB: hypergeometric tail when n < N, else Clopper-Pearson

Stratified: sum_h (N_h / N) p_h, normal UCB with finite-population correction. Small strata make this anti-conservative. The coverage simulation is the check.

Unequal pi: Horvitz-Thompson.

## Release rule

Release an accepted population only when UCB_95%(p) < epsilon.

First operating epsilon: 5%. Later 2% or 1%.

"97% of reviewed tasks were valid" is not the same sentence as "the one-sided 95% bound on population invalidity is 3%."

## Sample size does not track N

Clopper-Pearson, one-sided 95%, **zero** invalids observed (computed in this repo):

| epsilon | n |
| ---: | ---: |
| 0.05 | 59 |
| 0.03 | 99 |
| 0.02 | 149 |
| 0.01 | 299 |

If 1 invalid is observed, n=93 is required for UCB < 5%, n=236 for UCB < 2%. See `data/gold/sample_size_ucb.json`.

Finite-population correction matters when n is a large fraction of N. At 10,000 and 100,000 it is negligible for these n. New strata, new generators, and shift still require extra sample.

## Coverage check (ran)

On the 1,699 SWE-bench 2024 labels, true p = 0.683. 200 replicates.

| n | Design | Mean p-hat | Mean UCB | Coverage |
| ---: | --- | ---: | ---: | ---: |
| 50 | SRS | 0.689 | 0.793 | 0.955 |
| 50 | Stratified by repo | 0.678 | 0.781 | 0.955 |
| 50 | Hybrid (SRS arm) | 0.679 | 0.813 | 0.960 |
| 100 | SRS | 0.683 | 0.758 | 0.970 |
| 100 | Stratified by repo | 0.680 | 0.754 | 0.945 |
| 100 | Hybrid (SRS arm) | 0.685 | 0.781 | 0.985 |

At 2,000 replicates, SRS and hybrid-SRS-arm sit at or above nominal 95% on both the raw 68% population and a constructed 2% population. The stratified normal+FPC bound **undercover** at 2% invalidity (coverage 0.90). That estimator is not a release rule until it is replaced or shown to cover.

Certification of an *accepted* set targets p near 0–5%, where n=100 still yields a wide bound (zero events → UCB ≈ 3%). Sequential stopping lives in `sampling/sequential.py`: release when UCB < epsilon; reject when even a census cannot meet epsilon.

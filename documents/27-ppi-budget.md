# PPI and the human label budget

Code: `src/task_validation/sampling/ppi.py`. Lab: `task_validation.cli ppi-lab` -> `data/gold/ppi_lab.json` (2,000 SRS replicates, seed `ppi-lab-v0`). Auxiliary field: grouped-OOF `p_logistic` (AUROC 0.697 on the conservative 2024 label).

The cheap score is an auxiliary variable. Coverage is a property of the sampling design, not of model quality.

## Estimators

| Name | Point | One-sided 95% UCB |
| --- | --- | --- |
| SRS-CP (baseline) | k/n | Hypergeometric if n < N, else Clopper-Pearson |
| PPI++ | θ = λ mean(f_N) + mean(y − λ f), λ = Cov_n(y,f) / ((1+n/N) Var_N(f)) | Normal: residual var / n plus λ² Var(f_N) / N |
| Difference / GREG | θ = mean(y) + λ (mean(f_N) − mean(f_n)), λ = Cov/Var on the sample | Normal with finite-population correction |
| Poststrat exact | 4 score-quantile bins, weighted stratum means | Clopper-Pearson per stratum at α/4 (Bonferroni) |

PPI++ and GREG remain unbiased if the score is noise. Their *normal* UCB is anti-conservative when n is small and p is near 0. Poststrat-CP is the guaranteed-coverage fallback. An estimator is usable here only if Monte Carlo coverage is at least 0.95.

## Populations

Full N=1,699: conservative p=0.683, majority 0.450, unanimous 0.230.

Lowest-OOF 30% (N=509): p=0.487 / 0.259 / 0.128. Still too dirty to certify.

Thinned: keep every valid, subsample invalids without replacement, keep each unit's OOF score. Conservative: p=0.049 (N=567), 0.020 (550), 0.009 (544).

## Coverage at real AUROC 0.70 (conservative Y)

| Population | n | SRS cover / UCB | PPI++ cover / UCB | GREG cover / UCB | Poststrat cover / UCB |
| --- | ---: | --- | --- | --- | --- |
| full p=0.683 | 100 | 0.954 / 0.758 | 0.958 / 0.756 | 0.952 / 0.754 | 1.00 / 0.856 |
| full p=0.683 | 300 | 0.957 / 0.724 | 0.967 / 0.725 | 0.953 / 0.721 | 1.00 / 0.791 |
| thin p=0.049 | 50 | 1.00 / 0.129 | **0.910 / 0.094** | **0.897 / 0.093** | 1.00 / 0.374 |
| thin p=0.049 | 100 | 0.976 / 0.098 | **0.907 / 0.084** | **0.904 / 0.081** | 1.00 / 0.241 |
| thin p=0.049 | 200 | 0.965 / 0.077 | 0.953 / 0.074 | **0.917 / 0.069** | 1.00 / 0.162 |
| thin p=0.020 | 50 | 1.00 / 0.088 | **0.652 / 0.044** | **0.652 / 0.043** | 1.00 / 0.336 |
| thin p=0.009 | 50 | 1.00 / 0.071 | **0.376 / 0.022** | **0.376 / 0.021** | 1.00 / 0.321 |
| thin p=0.009 | 100 | 1.00 / 0.042 | **0.627 / 0.021** | **0.627 / 0.020** | 1.00 / 0.179 |

Bold cells undercover. Majority and unanimous thinned cells match this pattern. On the full population PPI++ is SRS to two decimals (n_eff/n = 1.11 at n=100). On the certification populations the tighter UCB is the failure mode.

## Label savings (smallest n in {50,100,200,300} with mean UCB < ε and coverage ≥ 0.95)

| Population | ε | n_SRS | n_PPI++ | n_GREG | n_poststrat | n_SRS / n_PPI++ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| thin p=0.049 | 0.05 | none | none | none | none |  |
| thin p=0.049 | 0.10 | 100 | 200 | none | none | 0.5 |
| thin p=0.020 | 0.05 | 200 | none | none | none |  |
| thin p=0.009 | 0.05 | 100 | none | none | none |  |
| thin p=0.009 | 0.10 | 50 | none | none | 300 |  |

PPI++ never beats SRS as a *usable* bound. Raw (ignoring coverage) PPI++ at p=0.049, n=50 has mean UCB 0.094 vs SRS 0.129; that shrink costs 9 points of coverage and is not a release rule. Poststrat-CP always covers and is 2-4x wider.

## AUROC sweep

0.6: mix OOF with Uniform(0,1). 0.7: real OOF. 0.8 and 0.9: mix the score toward the true label (synthetic).

PPI++ n_eff / n on the full conservative population, n=100: 1.04 (AUROC 0.6), 1.11 (0.70), 1.29 (0.8 synthetic), 1.67 (0.9 synthetic). A 2x effective-sample saving is not reached at AUROC 0.9. 3x is not in this sweep.

On thin p=0.049, even synthetic AUROC 0.9 still has PPI++ coverage 0.90 at n=100 (mean UCB 0.081 vs SRS 0.098). Raising AUROC into the 0.9s does not repair the normal bound at low p.

## P(certify at ε=0.05)

Conservative thinned populations. Best valid PPI-type = usable estimator with lowest mean UCB. That is SRS-CP except one cell.

| n | p=0.009 | p=0.020 | p=0.049 | best valid at p=0.049 |
| ---: | ---: | ---: | ---: | --- |
| 59 | 0.53 | 0.28 | 0.042 | SRS (P=0.042) |
| 100 | 0.76 | 0.39 | 0.025 | SRS (P=0.025) |
| 200 | 1.00 | 0.82 | 0.035 | PPI++ (P=0.061) |
| 300 | 1.00 | 1.00 | 0.044 | SRS (P=0.044) |

This is the acceptance-sampling table from doc 23. PPI does not move it.

## Reading

At the real AUROC 0.70 the cheap score is a weak auxiliary. PPI++ saves about 10% of labels on the dirty full population, where we are not certifying, and breaks coverage on the clean populations, where we are. GREG is the same story with an FPC. Poststrat-exact is the only assisted bound that covers, and it costs labels.

Human cost stays the SRS table: 59 to 300 adjudications per frozen accepted pool, constant in N, driven by ε and true p. Sublinear in N was already true without PPI. Smaller than that table is not available from this OOF score.

What would change the budget: an evidence layer with AUROC well above 0.9 *and* a UCB that is exact or conservative at p near 0. Until both exist, SRS hypergeometric / Clopper-Pearson is the release estimator.

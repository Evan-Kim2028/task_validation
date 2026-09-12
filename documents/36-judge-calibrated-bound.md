# Judge-calibrated certification bound

Code: `src/task_validation/sampling/judge_bound.py`. Auditor: `llm_spec_audit.py --full`. Gold: `data/gold/swe_llm_audit_full.jsonl`. Lab: `data/gold/judge_bound_lab.json` (2,000 replicates, seed `judge-bound-lab-v0`). Predicates J1-J3 were written in the module docstring before any full-population AUROC or Monte Carlo cell was computed.

## Setup and spend

Same prompt, model `grok-4.6`, temperature 0, reasoning effort low, concurrency 4. 200 cached n=200 items reused. OpenRouter paid through 1,177 scored items then returned HTTP 402 (in-flight credits, then empty wallet: "can only afford 3983 tokens"). The remaining 522 used `api.x.ai` with the same model and `reasoning_effort=low`. Raw responses live under `data/raw/llm-audit/x-ai/grok-4.6/`. `cost_usd` uses OpenRouter unit prices ($2/$6 per MTok) so the $20 cap is comparable: **$15.37 total** ($9.89 OpenRouter including the original 200, $5.48 xAI-priced, $0.0090/item). Cap not hit. n=200 gold files were not rewritten.

## Frozen predicates

- **J1** judge AUROC (`p_invalid` vs majority) on the full 1,699 >= 0.80
- **J2** at p=0.02 and m=100, at least one calibrated/stratified estimator covers >= 0.95 and has mean UCB below SRS-CP
- **J3** human labels needed for valid mean UCB < 0.05 at p=0.02 drop by at least 2x vs SRS-CP

## Derivations

Rogan-Gladen. Judge census prevalence `p_j`, sensitivity Se, specificity Sp:

`pi = (p_j - (1-Sp)) / (Se + Sp - 1) = (p_j - FPR) / (1 - FPR - FNR)`

Point from the calibration sample. One-sided 95% UCB: parametric bootstrap of Se, Sp (and `p_j` only if the judge is itself sampled). Draws with Youden <= 0 score as 1. If the sample has no Y=1 or no Y=0, Se or Sp is unidentified and UCB=1.

Calibrated finite-pop UCB (NbV-style, not the NbV hypothesis test). `p_j` is known. Humans label an SRS of size m. FPR and FNR get exact binomial CP bounds with a Bonferroni split of alpha: FNR one-sided upper at alpha/2, FPR two-sided at alpha/2 (tails alpha/4). For Youden > 0, `dpi/dFNR >= 0` and `dpi/dFPR` is monotone in FPR, so the max of `pi` at the FPR interval endpoints with FNR at its upper bound is a conservative one-sided UCB. Empty Y-class in the subsample: UCB=1.

PPI with judge. `ppi_mean_ucb` from `ppi.py` with auxiliary `p_invalid`. Normal UCB, same anti-conservative tail as doc 27.

Stratified by judge. Population split into flagged / not flagged. Humans allocated proportional or 70% flag-heavy. Per-stratum one-sided CP at alpha/2, N_h-weighted sum. Empty sample of a nonempty stratum contributes 1. The judge defines strata only.

## Auditor on all 1,699

AUROC, 1,000-rep bootstrap 95% CI:

| Y | s | p_invalid | base rate |
| --- | ---: | ---: | ---: |
| conservative | 0.766 (0.742, 0.788) | 0.792 (0.769, 0.814) | 0.683 |
| majority | 0.777 (0.756, 0.797) | **0.807 (0.786, 0.828)** | 0.450 |
| unanimous | 0.768 (0.747, 0.789) | 0.796 (0.774, 0.818) | 0.230 |

Kappa vs majority **0.470** (agreement 0.735). FN axis 0.758; underspecified 0.662. By repo, `p_invalid` vs majority ranges from 0.66 (psf, n=33) to 0.89 (pydata, n=79); django 0.833 (n=652). pallets n=1 is undefined.

Calibration, `p_invalid` deciles vs majority-invalid rate: 0.05, 0.12, 0.21, 0.28, 0.41, 0.59, 0.56, 0.65, 0.78, 0.85. Rank-order is real. The score is badly scaled (deciles 1-5 sit at p_mean 0.05-0.24, then a jump to 0.77+), so a 0.5 threshold is not a calibrated probability.

## Lab (real judge, no synthetic scores)

Thinning keeps every valid and a random invalid subset, with that unit's real `p_invalid` and `model_material`. After thinning to p=0.02 the judge still flags 29% (majority) / 21% (conservative): FPR on the kept valids does not shrink with prevalence.

Coverage and mean UCB at p=0.02, m=100 (majority; conservative matches to two decimals):

| estimator | cover | mean UCB | usable |
| --- | ---: | ---: | --- |
| SRS-CP | 1.00 | **0.059** | yes |
| RG bootstrap | 0.98 | 0.606 | yes |
| calibrated FPR/FNR | 1.00 | 0.992 | yes |
| strat proportional | 1.00 | 0.104 | yes |
| strat flag-heavy | 1.00 | 0.128 | yes |
| PPI++ judge | 0.88 | 0.041 | no |

Smallest m in {30,50,100,200} with mean UCB < eps and coverage >= 0.95, p=0.02 majority: SRS 200 / 50 / 30 for eps 0.05 / 0.10 / 0.20. No calibrated or stratified estimator reaches 0.05. Strat proportional reaches 0.10 only at m=200 (SRS does it at 50). PPI++ is tighter and undercovers (0.46-0.94).

P(certify at eps=0.05) at p=0.02 majority: SRS 0.00 / 0.37 / 0.81 at m=50/100/200. PPI 0.44 / 0.67 / 0.88 with coverage 0.64 / 0.88 / 0.94. Strat proportional 0 / 0 / 0.06. Calibrated FPR/FNR: 0.

**J1 PASS** (0.807). **J2 FAIL** (every calibrated/stratified UCB at m=100 is wider than SRS 0.059). **J3 FAIL** (no valid estimator beats SRS's m=200 for UCB < 0.05; 2x would need m<=100).

## Reading for doc 23

Section 6 human budget does not move. At the real AUROC 0.81 the judge is a ranking instrument, not a bound. Se/Sp correction is unidentified or huge when p is near 0 and m is tens to low hundreds (expected invalids in the subsample is 1-2; FPR ~0.2-0.3 still flags a fifth of a clean pool). Stratifying on the flag is valid and strictly wider than SRS-CP here because Bonferroni plus a large dirty flagged stratum after thinning. PPI++ repeats doc 27: the normal tail undercovers at low p.

Section 5 design stays: cheap evidence on every task, probability sample of the accepted pool, SRS hypergeometric / Clopper-Pearson as the release UCB. The judge may order the review queue. It does not replace the human sample, and it does not shrink that sample below the table in section 6.

# Risk coverage, label robustness, and the first execution run

The 150-task repo holdout AUROC of 0.76 was a start. This checkpoint asks whether the ranker can make an **accepted tail** clean enough to certify.

## 1. Three targets from the same 1,699 × 3 raters

A rater marks a material problem iff `underspecified>=2` or `false_negative>=2` or `other_major_issues>=1`. That rule matches the public `problematic` field on every row.

| Target | Rule | Invalid | Rate |
| --- | --- | ---: | ---: |
| `openai_2024_conservative` | ≥1 rater (equals `filter_out`) | 1,160 | 0.683 |
| `majority_invalid` | ≥2/3 raters | 764 | 0.450 |
| `unanimous_invalid` | 3/3 raters | 390 | 0.230 |

Inter-rater agreement on the per-rater material bit: **Fleiss κ = 0.39**, pairwise agreement 0.70. The 2024 conservative label is a harsh union of three moderately disagreeing judges. Cheap features may be predicting that union, not a single construct.

Severity axes are still not predictors.

## 2. Grouped 5-fold OOF (12 repositories)

Logistic, cheap artifacts only:

| Y | AUROC (95% boot CI) | Base rate | Calibration slope |
| --- | --- | ---: | ---: |
| conservative | 0.70 (0.67–0.73) | 0.68 | 0.64 |
| majority | 0.70 (0.68–0.73) | 0.45 | 0.76 |
| unanimous | 0.67 (0.65–0.70) | 0.23 | 0.64 |

The lucky 150-task holdout (0.76) overstated grouped-CV AUROC (~0.70). Signal is real and similar across the three Y definitions. Discrimination is **not** the bottleneck.

## 3. Residual invalidity in the lowest-risk tail (logistic OOF)

This is the number that matters.

**Conservative (any rater):**

| Retain lowest-risk | n | Residual invalid |
| ---: | ---: | ---: |
| 1% | 17 | **0.29** |
| 5% | 85 | 0.34 |
| 10% | 170 | 0.36 |
| 20% | 340 | 0.43 |
| 100% | 1,699 | 0.68 |

The tail is better than 68%, not close to 5%. Selective risk control at α=0.20 **refuses to accept anyone**: even the safest calibration prefix cannot put a 20% UCB under 0.20.

**Majority (≥2 raters):**

| Retain | Residual invalid |
| ---: | ---: |
| 1% | 0.12 |
| 5% | 0.15 |
| 10% | 0.19 |
| 20% | 0.22 |
| 100% | 0.45 |

SRC α=0.20 accepts ~7% of a held-out-repo slice with eval residual 0.22 (the bound did not hold on eval). Filter ≠ certificate.

**Unanimous (3/3):**

| Retain | Residual invalid |
| ---: | ---: |
| 1% | **0.00** |
| 5% | 0.059 |
| 10% | 0.065 |
| 20% | 0.091 |
| 100% | 0.23 |

SRC α=0.20 accepts ~24% with eval residual 0.09. This is the first tail that looks like a certification input, and only for the *strictest* Y.

## 4. What this means for the system

Cheap artifact features rank. They do **not** create a 5% residual tail under the 2024 conservative rubric. Execution-grounded evidence (oracle, nop, mutation kill rate) is no longer optional polish. It is the only plausible way to drive conservative residual down.

Do not treat AUROC 0.70 as “the model is ready to filter a 10k population.” Treat the retain table as the product metric.

## 5. Cheap Harbor execution runner (hello-world)

`run-harbor-evidence` on `eval_tasks/tasks/hello-world`:

| Check | Result | Wall clock |
| --- | --- | ---: |
| oracle ×2 | reward 1.0, 1.0 | 32.6s, 31.9s |
| nop | reward 0.0 | 31.1s |
| determinism | true | — |
| wrong-output mutant | killed (reward 0) | 31.9s |
| mutation kill rate | 1.0 | — |

Sources recorded: `static`, `official_verifier`, `oracle_derived`, `mutation`. ~2 minutes for the full cheap stack on a tiny task. Lakehouse will be slower; do not jump to 1,699 SWE-bench Docker evals until lakehouse mutation cost is measured.

## 6. Still not done

- Lakehouse (and the other 15 Harbor tasks) through this runner
- Harbor-Index 82 as external control
- SWE-bench ~50 execution subset
- TB 2.1 maintenance gold
- Six human packets
- Sampling experiment / population certificate
- Synthetic generation

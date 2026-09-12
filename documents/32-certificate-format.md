# Certificate format

A certificate is the release record for one frozen accepted pool. Inputs: a sample manifest (design, N, n, ids, seed) drawn first, then per-unit verdicts with a named label protocol and treatment grade. Output: residual invalidity p-hat, a one-sided 95% UCB, the decision at a stated epsilon, and the flagged units.

Code: `src/task_validation/sampling/certificate.py`. Estimator: hypergeometric UCB when n < N (`estimators.py`); when n = N the UCB is the observed rate (census). Clopper-Pearson is the infinite-population fallback in the estimator module, not the census path.

## Fields

| Field | Meaning |
| --- | --- |
| N, n, k_invalid | Population size, sample size, invalids in the sample |
| p_hat | k / n |
| ucb95, method | One-sided 95% upper bound and how it was computed |
| epsilon, decision | Release iff UCB < epsilon; else reject. Incomplete if any sample unit is unadjudicated |
| p_certify | OC-curve P(UCB < epsilon) if true p equals the observed p-hat |
| label_protocol, grade | Named protocol; assay grade A or B only |
| adjudicator | machine, human, or both |
| replaces_human_sample | Always false for a machine certificate |
| flagged | Invalid unit ids with evidence text |
| unadjudicated | Sample ids with invalid null, missing verdict, or grade not A/B. No imputation |

## Example (synthetic)

Manifest: SRS without replacement, N=80, n=20, seed `synthetic-cert-v0`. Protocol `verifier_invalid.fresh_environment.execution`, grade A, adjudicator machine. One invalid (`t003`). Epsilon 0.05.

```
# Validity certificate

- Decision: REJECT
- N (population): 80
- n (sample): 20
- k invalid: 1
- Point estimate p-hat: 0.050000
- One-sided 95% UCB: 0.200000
- Method: hypergeometric-one-sided
- Epsilon: 0.05
- P(certify | p-hat): 0.000000
- Label protocol: verifier_invalid.fresh_environment.execution
- Grade: A
- Adjudicator: machine
- Replaces human sample: False
- Design: SRS without replacement
- Seed: synthetic-cert-v0

## Flagged units

- `t003`: empty patch resolved (false accept); P2P-break-on-gold: test_maps
```

k=0 is required before this n can fire at epsilon 0.05, and even then the hypergeometric UCB on n=20 from N=80 stays above 0.05, so P(certify | p-hat) is 0.

## Rules

1. Freeze the manifest (ids, N, n, seed, design) before any verdicts. Do not drop units after seeing outcomes.
2. Only grade A or B enters the bound. C/D and null invalid leave the certificate INCOMPLETE.
3. The protocol is a required name. Do not pool protocols into one Y.
4. Machine certificates are labeled machine. They do not replace the human probability sample.

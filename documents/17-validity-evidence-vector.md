# Validity Evidence Vector

The 0.70 OOF AUROC and the OpenAI-Pro recovery used **proxies** (patch size, identifier overlap, literal fractions). Those contain information. They are not the contract.

This layer is a set of **bounded invariants**. A primitive is `not_run | pass | fail | inconclusive` plus `value`, `n`, `d`. Null is not a pass. No production model until these are measured on a labeled subset.

Research question:

> Which model-free validity invariants provide independent information about material task invalidity, and how many are required to produce a clean accepted population?

## The nine primitives

| # | Name | Measurement |
| --- | --- | --- |
| 1 | Specification sufficiency | `n_enforced_ungrounded / n_enforced` on **contract tokens** (literals, error types, numbers, API calls) from **assertion lines** vs the issue prompt |
| 2 | Positive control | reference reward == 1 |
| 3 | Negative control | nop reward == 0, plus wrong impls fail |
| 4 | Implementation invariance | fraction of behavior-preserving alts the verifier **rejects** (narrow tests) |
| 5 | Mutation sensitivity | kill rate on required-behavior removals |
| 6 | Independent behavior | agreement with a check that is not the official tests |
| 7 | Determinism | repeat oracle in a fresh run |
| 8 | Environment integrity | leakage / writable grader / network |
| 9 | Requirement-to-test coverage | `n_stated_untested / n_stated` |

Untrained risk averages measured primitives only.

## Ablation (conservative 2024 Y, n=1699, no new fit)

| Layer | What | Retain 5% residual | Retain 20% residual | AUROC |
| --- | --- | ---: | ---: | ---: |
| A | existing OOF logistic (proxies) | 0.34 | 0.43 | 0.70 |
| B | untrained `spec_gap_contract` | 0.56 | 0.71 | 0.49 |
| C–G | oracle/nop/mutation/invariance/independent | not measured on this labeled set | — | — |

B does **not** beat A on the 5% or 20% tail. The 1% tail is 0.24 vs 0.29 (n=17, not a claim). 1686/1699 still trip a coarse fail threshold: the atomizer is still too wide.

That is not “invariants are impossible.” It is “this construction of (1) and (9) is not yet a verifier.” Proxies still rank better than this untrained gap on the 2024 union label.

## Harbor hello-world (execution subset)

Measured: positive control pass (2/2), negative control pass, mutation kill 1/1, determinism pass, environment integrity pass (separate verifier). Not run: implementation invariance, independent behavior. Spec/coverage on hello-world still mixes pathlib names (`is_file`, `strip`) into contract tokens — primitive (1) needs a tighter assertion grammar before we trust it on tiny tasks.

## Ablation map (status)

| Step | Status |
| --- | --- |
| A current static artifact features | measured |
| B + spec/verifier alignment | measured, untrained; weaker tail than A |
| C + oracle/nop/determinism | hello-world only |
| D + mutation | hello-world file-level wrong output only |
| E + implementation invariance | not run |
| F + independent behavioral evidence | not run |
| G full vector | not run on a labeled population |

Do not train a production risk model on this. Do not generate synthetic tasks. Next measurement is C–E on a **labeled** Harbor or SWE subset small enough to run, then re-do retain-tail. That is the test of whether the evidence layer can become a verifier.
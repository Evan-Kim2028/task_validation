# ADR-0019: Parallel decision tree; 20-task Docker frozen

## Status

Accepted

## Decision

Stop linear one-assay sequencing. The research program is a **decision tree** with five gates. The 20-task SWE interrogation design is **frozen** (`data/gold/swe_2x2_sample.json`, `executed: false`). Do not scale Docker to 50/300/1,699. Do not change those IDs or add treatments.

A failed assay is not a failed thesis. A heuristic that does not name a gate is not allowed.

North star unchanged: certify residual invalidity with a 95% UCB while human effort is sublinear. No synthetic generation until Gate 5.

## Gates

1. Controlled execution reveals evaluator behavior beyond oracle/nop.
2. Execution evidence improves retain-tail vs static proxies.
3. Signal transfers across benchmark lineages.
4. Sampling UCB covers at low prevalence (not stratified-normal).
5. A small human sample certifies or rejects at epsilon.

1K starts only after Gate 5. Part 2 only after 1K→10K→100K.

## Why

Doing A then B then C wasted turns retuning failed constructions. The tree says what happens if A1 is null (do not invent mutations; test orthogonality; switch to natural counterfactuals).

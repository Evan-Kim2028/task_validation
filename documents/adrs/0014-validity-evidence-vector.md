# ADR-0014: Validity Evidence Vector, not more proxy features

## Status

Accepted

## Decision

Stop adding generic ML correlates. Represent each task as nine bounded invariants (spec sufficiency, positive/negative control, invariance, mutation, independent behavior, determinism, environment integrity, coverage). Evaluate with residual invalidity in the accepted tail. No production model until primitives are measured on a labeled subset.

## First measurement

Untrained spec-gap (B) lost to existing OOF logistic (A) at retain 5% and 20% on SWE-bench 2024 conservative labels. Execution primitives exist in schema and are filled on hello-world only. The failure mode is construction of the invariant, not a proof that contract evidence cannot work.

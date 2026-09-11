# ADR-0008: Cite grouped OOF, not the 150-task 0.76

## Status

Accepted (backfill)

## Decision

The first 150-task repository holdout logistic AUROC was 0.76. Grouped 5-fold OOF on all 1,699 is ~0.70 (0.67–0.73). Public numbers use OOF.

## Why

A single holdout of 2–3 repos can luck into 0.76. Twelve-repo GroupKFold is the honest transfer estimate inside SWE-bench 2024.

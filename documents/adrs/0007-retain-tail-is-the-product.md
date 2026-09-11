# ADR-0007: Retain-tail residual is the product metric

## Status

Accepted (backfill of 2026-09-11 risk-coverage run)

## Decision

AUROC answers “can we rank?” The certification system needs “how clean is the accepted tail?” Report residual invalidity among the lowest-risk 1/5/10/20%.

## Evidence

Under the 2024 conservative label, lowest-risk 5% was still 34% invalid. SRC at α=0.20 accepted nobody. Ranking without a clean tail is not enough to start population sampling.

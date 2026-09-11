# ADR-0006: Cheap artifact features only. Never the severity axes.

## Status

Accepted

## Date

2026-09-11

## Context

The 2024 SWE-bench `filter_out` label is defined from underspecification, FAIL_TO_PASS unfairness, and other major issues. Predicting `filter_out` from those axes is circular. H1 needs predictors that could be computed on a new task *before* a human labels it.

## Decision

The frozen predictor list is `CHEAP_FEATURE_NAMES` in `evidence/swe_artifacts.py`. It is computed from problem statement, gold patch, and test patch. Human severity, notes, difficulty, and `filter_out` are forbidden as X.

A later execution feature (oracle, nop, mutation kill rate) may be added to the frozen list in a new protocol version. It still must not be a human annotation.

## Alternatives considered

**Use severity as a proxy risk score.** Used once in an early coverage demo. Not allowed for the risk model.

**Wait for 1,699 Docker evals before any model.** Rejected for this checkpoint. Artifact features are cheap and test whether *any* independent signal exists. Docker evals remain the next evidence layer.

## Consequences

If AUROC is near chance, that is a real negative on this feature set, not a reason to sneak severity back in.

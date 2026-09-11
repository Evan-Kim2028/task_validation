# ADR-0003: ML allocates. Sampling infers.

## Status

Accepted

## Date

2026-09-11

## Context

Risk models will look good on SWE-bench bugs and fail on Terminal-Bench. Harbor-Index already uses AI audit as a funnel stage. If we let the model be the certificate, we have ABA with extra steps.

## Decision

The published bound comes from a probability sample (or HT with recorded pi). The model may oversample the tail. The hybrid design keeps a 60% SRS arm so we can always fall back to a clean estimator.

## Alternatives considered

**Model-predicted prevalence as the bound.** Rejected: no coverage guarantee under shift.

**Pure risk-guided sample with HT only.** Allowed later, after pi estimation is validated in simulation. Not the first production path.

## Consequences

Code in `sampling/designs.py` tags `arm=srs|stratified|high_risk|novel`. Coverage sim for hybrid uses the SRS arm only.

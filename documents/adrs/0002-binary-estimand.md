# ADR-0002: Binary material invalidity is the estimand

## Status

Accepted

## Date

2026-09-11

## Context

TB rubrics have 35 criteria. eval_tasks note 04 has seven quality properties. SWE-bench Verified used two ordinal axes plus a freeform flag. A 20-dimensional score cannot be certified as one bound.

## Decision

Y is binary material invalidity. Other properties are covariates or separate measurements (difficulty, diversity, realism).

## Alternatives considered

**Weighted quality score.** Rejected: no sampling theory for "93% realistic."

**Keep the seven Q1–Q7 as seven estimands.** Too many human questions per packet. Q1–Q3 stay machine-first. Q4–Q6 stay in the checklist as *inputs* to Y, not seven CIs.

## Consequences

Packets force one verdict. Ambiguous is a queue state, not a published class.

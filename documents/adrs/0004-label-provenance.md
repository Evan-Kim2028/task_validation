# ADR-0004: Do not merge label provenances

## Status

Accepted

## Date

2026-09-11

## Context

SWE-bench Verified is three paid engineers per task. TB 2.1 fixes are maintainer acknowledgements. Harbor-Index reviews are a different rubric. Mixing them into one Y trains "whatever some human once disliked."

## Decision

Store `human_label_provenance`. Train and test with provenance as a split, not as extra N. TVB-style author-fix labels, if they appear, stay `AUTHOR_ACKNOWLEDGED_FIX`.

## Alternatives considered

**Pool everything for bigger N.** Rejected until we show the model is stable across provenances.

## Consequences

The 1,699-row table is one provenance. The 16 Harbor packets will be another once labeled.

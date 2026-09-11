# ADR-0011: OpenAI and June Kim labels are evaluation-only

## Status

Accepted

## Context

OpenAI’s July 2026 Pro audit and June Kim’s determinacy audit are the first external targets. Using those IDs as predictors would circularize the reconstruction.

## Decision

Cheap features see only public task artifacts. After scoring, compare overlap / enrichment. OpenAI did not release the 249 IDs; task-level overlap is limited to published examples plus independent audits that did publish IDs (June Kim CLAIMS.md).

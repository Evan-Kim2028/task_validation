# ADR-0017: Agree with interrogation dataset direction; cut the 50–100 multi-benchmark scale

## Status

Accepted

## Decision

The next-step command is right on **measurement**: generalize `interrogate-verifier`, keep the five rates uncollapsed, record observe/unavailable, store raw trials, mine existing human labels without merging provenances, do not train a production model, do not generate tasks, do not revive static rankers.

It is wrong on **scale and estimand**.

- Do **not** run 50–100 tasks spanning SWE-bench / TB / Pro in this phase. ADR-0010 and [19](../19-evaluator-interrogation.md) still forbid 50/731 SWE-bench containers until lakehouse cost is measured.
- Do **not** call this a population-level evaluator-validation dataset yet. ADR-0016: this is not a 2024-label ranker and not a certificate.
- Do **not** treat SWE-bench Verified membership, or the 2024 fairness labels, as ground truth for *evaluator discrimination*. Those labels are issue-vs-F2P fairness (ADR-0004).
- Do **not** ingest Task Verification Bench. It still has no public dump.
- Do **not** invent spec-grounded equivalent/boundary probes by reading tests. Mark them **unavailable**.

This phase’s live pilot is the complete local Harbor packages (16 after excluding `lakehouse-stack-incident` at 1800s verifier timeout), including `lakehouse-publish-recovery` as the ADR-0010 cost measurement.

## Why

A 50–100 mixed-benchmark Docker sweep would violate the cost gate, mix label provenances, and optimize a measurement we have not yet shown is stable on the tasks we can actually run.

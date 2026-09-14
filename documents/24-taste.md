# Taste (Part 2 placeholder)

Validity says the evaluator can be read as evidence. Taste says the task is worth evaluating. They are different estimands and this page exists so taste never leaks into Y.

## What taste means here

| Dimension | Definition | Candidate instrument | Type |
| --- | --- | --- | --- |
| Difficulty | Frontier agents do not trivially solve it | solve rate across N frontier trials | continuous |
| Discrimination | Solve rate separates stronger from weaker agents | spread of solve rate across model tiers | continuous |
| Realism | A working engineer would recognise the task | human rubric, later a calibrated model | ordinal |
| Diversity | Population covers families, languages, failure modes | construction quotas | population property |
| Novelty | Not a paraphrase of an existing task | overlap / similarity | continuous |

None of these is binary. None enters the material-invalidity label. A task can be valid and boring, or invalid and beautiful.

## Rules

- Certify validity first. Taste is measured on the accepted population, never used to define it.
- Taste needs frontier-agent runs. Validity does not. Keep the cost separate.
- Difficulty and discrimination reuse the raw trial schema from the interrogation harness (`data/gold/harbor_interrogate.matrix.jsonl` shape). Realism needs human rubric labels that do not yet exist.
- Do not build a composite taste score. Report the dimensions separately, as the five evaluator rates are.
- Harbor-Index's difficulty stage (6,627 → 1,311) is the nearest precedent. Terminal-Bench 3.0's 28-criterion rubric (the opened toml names 28; 35 is a marketing count, doc 31) is the nearest realism rubric.

## Operational definition

Doc 31 section D gives the literature-grounded version: seven measurable properties (valid evaluator, spec-test alignment, essential difficulty, frontier-unsolved but not saturated, discrimination, human-calibrated time, paid realism), with instrument, cost, and the source each builds on. Properties 1 and 2 are binary and samplable. The rest are graded and measured on the accepted set only. Doc 33 tests whether discrimination and difficulty from public SWE-bench submissions relate to the 2024 validity labels.

## Open questions

- Which of the five dimensions a 1,000-task Part 2 population is actually required to hit, and at what quota.
- Whether a cheap model can grade realism well enough to allocate a human sample, using the same allocate-then-sample design as validity.

Nothing here is scheduled before Part 1's open question (doc 23 section 7) is answered.

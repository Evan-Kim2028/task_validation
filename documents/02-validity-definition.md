# Material invalidity

The primary statistical variable is binary.

A task is **materially invalid** when its evaluation can no longer be interpreted as evidence about the intended capability.

## Positive cases (invalid)

- Impossible under the stated environment
- Prompt and verifier disagree
- Hidden tests require unstated behavior
- Valid implementations fail because of irrelevant constraints
- Invalid implementations pass
- Reference solution is wrong
- Environment is nondeterministic in a way that changes the outcome
- Evaluator can be cheaply gamed
- Benchmark artifacts leak information that changes the intended task

## Not the estimand

These are population-design properties. Measure them. Do not fold them into Y.

| Property | Where it lives |
| --- | --- |
| Realism | Part 2 |
| Diversity | Construction quotas |
| Difficulty | Frontier agent trials |
| Coverage | How the population is sampled |
| Novelty | Overlap / similarity |

## Labels we store

| Label | Meaning |
| --- | --- |
| `valid` | Evaluation is interpretable as evidence about the intended capability |
| `invalid` | Materially invalid under the definition above |
| `ambiguous` | The reviewer cannot decide from the packet. Queue for adjudication. Not a third scientific class. |
| `pending` | No human verdict yet |

Severity axes (underspecification, unfair tests, other) are covariates. They explain *why*. They are not a 20-dimensional quality score.

## Protocol versions

The 2024 OpenAI SWE-bench Verified rule discarded a sample if any of three annotators marked underspecification or FAIL_TO_PASS unfairness at severity 2 or 3, or flagged another major issue. We store that as `protocol = openai-swe-bench-verified-2024-conservative`.

That protocol is **not** the 2026 residual-error label on the 500-task Verified set. Do not mix them.

## Approach A vs Approach B

**Approach A (this phase).** The target is residual invalidity according to the stated audit protocol. Human adjudication is the reference standard. Simple. Does not model judge error.

**Approach B (later).** Treat the reviewer as an imperfect channel. Estimate sensitivity and specificity from multi-rater gold (SWE-bench 3-annotator file). Propagate that into the population bound, following the 2026 Noisy but Valid framework.

This repo ships Approach A packets. Approach B is specified in the implementation plan, not executed.

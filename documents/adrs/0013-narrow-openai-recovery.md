# ADR-0013: The next proof is OpenAI's Pro rejection, not a general validator

## Status

Accepted

## Decision

The research question is only:

> Can cheap, independent evidence recover the result that caused OpenAI to retract SWE-Bench Pro?

Success is A ∧ B ∧ C in [16-narrow-openai-recovery.md](../16-narrow-openai-recovery.md). Matching 30% is forbidden. Building a general validator, a 1,000-task set, or synthetic generation is out of scope until that verdict is written.

## Consequence

Measured YES (rank 38/731 on the named example; 1.56× June Kim in the top 10%; low-risk 20% still 13% dirty). That is a rejection of Pro as a certifiable instrument, not a green light to scale task construction.

# ADR-0016: Interrogate evaluators with controlled behavior, not metadata

## Status

Accepted

## Decision

Evaluator validity is measured by sending the **official verifier** implementations whose intended accept/reject label is known from the spec or the reference solution, then reading the reward.

Metadata (declared FAIL_TO_PASS, file-name witnesses, assertion-payload lookup) is not that measurement. Static assays B/C already failed as 2024-label rankers (ADR-0015). Do not revive them.

Do not collapse the five rates into one score. Observe-only probes (spec-ambiguous behavior) are recorded and kept out of the rates.

This is not a 2024-label ranker and not a population certificate. It answers whether *this evaluator* can be mechanically tested.

SWE-bench Docker remains behind ADR-0010. First live profiles: Harbor tasks we can already run.

## Why

Material invalidity includes "valid implementations fail" and "invalid implementations pass." Those are behavioral claims. File pairing cannot make them.

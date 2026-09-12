# ADR-0018: Grade treatments before any SWE Docker; 2024 Y is a transfer test

## Status

Accepted

## Decision

Agree with the other agent’s approach, with three freezes:

1. **Treatment labels first.** Grade every interrogation treatment A/B/C/D. Only A/B enter an assay. `remove_required` is **C**. A verifier failure does not make it a valid negative. On the 16-task pilot, the only false-accept disappeared when C was dropped.

2. **Do not run 20–30 SWE Docker in this step.** The 2×2 ID list is written (`data/gold/swe_2x2_sample.json`, `executed: false`). Gold vs base is how SWE-bench is *built*; it is likely *not* to separate 2024 fairness labels. n=20 cannot support a decision-grade retain-tail. If that study is run once and is null, **Reconsider** — do not retune treatments.

3. **2024 valid/invalid is a transfer question**, not the definition of evaluator validity (ADR-0016). Natural counterfactuals (base vs gold, TB 2.1 pre/post) are the right next *labels*. Do not invent boundary/equivalent probes. No 50/300/1699. No TVB. No synthetic. No production model.

TB 2.1: 28 public changed-task names stored as `HISTORICAL_MAINTENANCE`. Only `query-optimize` is typed as misspecification in the public post. Do not relabel the other 27 without PR #53.

## Why

The 16-task run established machinery. The bottleneck is whether intended labels are defensible without smuggling in the semantics we want to predict.

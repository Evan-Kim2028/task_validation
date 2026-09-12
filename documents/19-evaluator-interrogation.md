# Evaluator interrogation (controlled behavior)

Question:

> Can evaluator validity be interrogated through controlled behavior, rather than inferred from metadata?

**Yes, as a measurement procedure**, on tasks that have an executable official verifier. Metadata cannot do this. Live profiles: Harbor `hello-world` and `week-hours`. We did **not** start SWE-bench Docker.

## What counts as interrogation

The unit is the task verifier. Treatments are implementations we write. The response is the official Harbor reward. Intended labels come from the **instruction / reference**, not from reverse-engineering the tests.

| Class | Intended | Example |
| --- | --- | --- |
| reference | accept | official `solution/` |
| behavior-preserving | accept | comments; equivalent write of the same output |
| nop | reject | empty agent |
| remove required | reject | omit a gold copy / write nothing |
| revert gold | reject | environment files in place of solution |
| alter output | reject | wrong required string |
| break boundary | reject | required string, wrong case |
| observe | *unlabeled* | spec-ambiguous whitespace; not in the five rates |

Rates, uncollapsed:

* correct acceptance (reference)
* legitimate-variant acceptance
* incorrect rejection (negatives that fail)
* false-accept
* false-reject

`interrogable` is true when at least one positive and one negative probe produced a reward. That is the yes/no on the method. The profile is the finding about *that* evaluator.

## Why metadata is not this

Static change-causality and provenance scored AUROC 0.41 / 0.42 against 2024 conservative labels. Almost every SWE-bench task already declares FAIL_TO_PASS. Author-declared fail-to-pass is a log of one gold vs base pair. It does not test legitimate variants or subtle incorrectness.

2024 labels are mostly "are the F2P tests fair?" A discriminating evaluator can still be an unfair spec. Do not use this profile to predict those labels.

## Live profiles

Official Harbor verifier. No frontier agent. ~32–34s/trial.

| Task | Interrogable | Correct accept | Variant accept | Incorrect reject | False accept | False reject |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| hello-world | yes | 1.0 | 1.0 | 1.0 | 0.0 | 0.0 |
| week-hours | yes | 1.0 | 1.0 | 1.0 | 0.0 | 0.0 |

hello-world negatives: nop, write nothing, `Goodbye, world!`, `hello, world!` (case). Positives: reference, comment-only `solve.sh`, `echo` instead of `printf`.

week-hours negatives: nop, copy only `clock.py`, revert solution files to the broken environment copies. Positive: comment-only `solve.sh`.

**Observe-only (not in the rates).** hello-world `printf ' Hello, world! '` was **accepted**. The instruction names `Hello, world!`; the test uses `.strip()`. That is spec-vs-evaluator slack. It is not a false-accept because we refused to label it.

Artifacts: `data/gold/hello_world_interrogate.json`, `data/gold/week_hours_interrogate.json`, `data/gold/interrogate.summary.json`.

## Freeze

- Interrogate evaluators by running them. Do not infer evaluator validity from artifact metadata.
- Drop a probe class if it cannot be labeled from the spec. Do not retune it into a heuristic score.
- No synthetic tasks. No frontier agents. No 50/731 SWE-bench containers.
- Lakehouse wall-clock is still the ADR-0010 cost gate before SWE-bench Docker.
- Next increment is the Harbor-complete pilot (16 packages), not a 50–100 multi-benchmark population. ADR-0017.

Run:

```sh
PYTHONPATH=src .venv/bin/python -m task_validation.cli interrogate-verifier \
  --task /path/to/eval_tasks/tasks/hello-world \
  --work /tmp/tv-interrogate-hello \
  --out data/gold/hello_world_interrogate.json
```

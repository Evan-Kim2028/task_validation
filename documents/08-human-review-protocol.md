# How to review a packet

## Prerequisites

- This repo checked out
- Sister repo `eval_tasks` checked out next to it if you need the full instruction, environment, and tests
- 5–15 minutes per Harbor packet. SWE-bench calibration items take longer if you open the GitHub issue.

## Steps

1. Open `data/review_queue/README.md` and pick the next **priority** packet, not a random file.
2. Open the packet markdown. Read identity, static evidence, and instruction preview.
3. If the packet is an `eval_tasks` task, open the sister path in `artifacts.path` for the full instruction, `DESIGN.md` if present, and hidden-test names. Do not read `solution/` until you have answered Q4 and Q5.
4. Answer Q1–Q6 with yes / no / cannot tell. Q1–Q3 can be "cannot tell" when logs are missing. That is a packet defect, not a task verdict.
5. Mark exactly one of valid / invalid / ambiguous.
6. If invalid, name the failure using the list in [02-validity-definition.md](02-validity-definition.md).
7. Write minutes spent and your name.
8. Do not edit the task to make it pass. Repair is a different queue.

## Checklist (copied from the packet)

1. Oracle / reference log cited and passing?
2. Nop failed, and a plausible wrong patch would fail a check?
3. Cheat or exploit trial ended at reward 0, or the gap is recorded?
4. Every hidden check is derivable from instruction, env, or readable docs?
5. Two competent engineers would agree on "done"?
6. If evaluation cannot be read as evidence about the intended capability, invalid.

## Known-easy and decoy items

These are in the queue on purpose:

- `tasks/week-hours`, `tasks/shared-limit-si`, `experimental/bootstrap-merge-resume` are below the frontier bar in existing SWE-2 / GLM-flash evidence. They can still be *valid* instruments. Difficulty is not invalidity.
- `experimental/catalog-shift-*` and `warehouse-drift-closure` are decoys in the `eval_tasks` portfolio. Say so if Q5 is "this is the same task with the numbers changed."

## Sealed calibration

`data/review_queue/calibration_sealed.json` holds 10 SWE-bench 2024 protocol labels (5 valid, 5 invalid). Open it **after** you submit those ten packets, if they are added to a later slice. They measure reviewer agreement with the 2024 protocol. They are not 2026 residual truth.

## What not to do

- Do not let an LLM fill the verdict.
- Do not drop a task from the probability sample because it looks boring. That breaks the bound.
- Do not treat a missing cheat log as "passed cheat."
- Do not recode `ambiguous` as `valid`.

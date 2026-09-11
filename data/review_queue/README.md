# Human review queue

Status: **awaiting_human_review**. 16 packets. Verdicts are blank on purpose.

## Read first

[documents/08-human-review-protocol.md](../../documents/08-human-review-protocol.md)

## Priority (do these first)

1. `packets/tasks__lakehouse-publish-recovery.md`
2. `packets/experimental__logged-bandit-ope.md`
3. `packets/experimental__gold-retry-publisher.md`
4. `packets/tasks__durable-prefix-ack.md`
5. `packets/tasks__week-hours.md`
6. `packets/experimental__bootstrap-merge-resume.md`

Then the rest in `manifest.json` order. Decoys (`catalog-shift-*`, `warehouse-drift-closure`) last.

## Sister paths

Packets list `artifacts.path` under `/home/evan/Documents/eval_tasks/...` on the machine that built them. If you cloned both repos side by side, replace that prefix with your `eval_tasks` clone.

## Sealed file

`calibration_sealed.json` is 10 SWE-bench 2024 protocol labels. Do not open it for the Harbor slice. It is for a later agreement check.

## How to return work

Edit the packet in place: tick yes/no/cannot tell, write the verdict, minutes, name. Commit on a branch, or send the six priority files back.

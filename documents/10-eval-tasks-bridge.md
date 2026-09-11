# Sister repo: eval_tasks

`eval_tasks` (https://github.com/Evan-Kim2028/eval_tasks) is a Harbor / Terminal-Bench 3 lab. Public claim: one submission, `tasks/lakehouse-publish-recovery`. `experimental/` is retained design history.

This repo does not own that incident, the OPE generator, or friend-pilot OAuth paths.

## What we reused as process

- Quality bar Q1–Q7 from `eval_tasks/research/notes/04-direction-1000-tasks.md` (local, gitignored there)
- 7-item human checklist from note 05
- Harbor gates: static, oracle, nop, separate verifier, cheat prompt, 35-criterion rubric as a *screen*
- The Q20 residual-rate question: that question is the reason this repo exists

## What stayed in eval_tasks

- Task content and solutions
- Makefile Harbor runners
- Raw `jobs/` (gitignored)
- Vendored TB static checks and planted `fail-*` tasks
- Author-facing TB3 submission checklist

## Inventory we actually queued

Complete Harbor packages with instruction, task.toml, solution, tests, environment. hello-world excluded (harness). Planted `scripts/checks/test-tasks` excluded (checker gold, not human spec review).

From `tasks/`: lakehouse-publish-recovery, durable-prefix-ack, keydir-merge, late-session-gc, shared-limit-si, week-hours.

From `experimental/`: bootstrap-merge-resume, catalog-contention-recovery, catalog-shift-closure, catalog-shift-replay, gold-retry-publisher, lakehouse-stack-incident, logged-bandit-ope, payments-ledger-reconciliation, schema-evolution-cdc, warehouse-drift-closure.

Portfolio docs said contention and stack were "not built out." The tree has full packages and oracle/nop jobs. Packets follow the tree.

## Honesty gaps the reviewer will hit

- Committed `eval_tasks/results/` still marks most TB3 gates pending. Local `jobs/` is richer.
- Cheat logs exist for two tasks.
- SWE-2 Max ran on a handful of repo tasks: week-hours and shared-limit-si pass (below bar), durable-prefix-ack fails, keydir-merge was killed (mechanical).
- Several experimental READMEs still contain `[AUTHOR TODO]`. That is a spec/packaging issue, not automatically material invalidity.

## Scaling story

eval_tasks wants 1 → 1000 tasks in weeks. Terminal-Bench quality process produced 66 TB4 tasks with a paid review team. That does not scale by typing faster. It scales if machine evidence is precomputed and humans read dossiers, then a probability sample certifies the accepted set. This repo is that second system.

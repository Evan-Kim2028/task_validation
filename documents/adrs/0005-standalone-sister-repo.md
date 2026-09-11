# ADR-0005: Standalone public sister repo

## Status

Accepted

## Date

2026-09-11

## Context

eval_tasks is a TB3 submission plus experimental tasks. Putting certification methodology in that tree mixes a hiring task with a research instrument. Research notes there are gitignored.

## Decision

New repo `task_validation`, MIT, public, no runtime dependency on eval_tasks. Harbor ingest takes a filesystem root. Packets point at sister paths. Job traces stay in eval_tasks.

## Alternatives considered

**A `verification/` folder inside eval_tasks.** Rejected: the public story is a general method, not a plugin of one lakehouse task.

**Monorepo.** Rejected for the same reason.

## Consequences

Duplication of the checklist text is acceptable. Vendored TB check scripts stay in eval_tasks unless we later extract a clean subset.

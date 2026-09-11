# ADR-0001: Zero new synthetic tasks in Part 1

## Status

Accepted

## Date

2026-09-11

## Context

eval_tasks wants ~1000 tasks. Generators are the obvious way there. If we generate and certify in one study, two unknowns move at once: the verifier and the generator.

## Decision

Part 1 uses only existing tasks as the experimental population. Part 2 may generate after the certification mechanism is validated.

## Alternatives considered

**Generate now, filter hard.** Rejected: a high yield could mean a good generator or a deaf verifier.

**Generate a small family only as a probe.** Deferred to Part 2. A probe still contaminates the scientific story.

## Consequences

This repo is not a task factory. eval_tasks remains the factory. Certification can later gate eval_tasks families without being judged on their quality in Part 1.

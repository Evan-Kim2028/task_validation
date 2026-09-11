# Automated evidence pipeline

Every task is supposed to receive the same machine vector. This repo defines the vector and implements the cheap, local slice. Docker oracle/nop/cheat and mutation still live in `eval_tasks` Makefile targets. This repo consumes their artifacts.

## Deterministic checks

| Signal | Pass means |
| --- | --- |
| `oracle_pass` | Reference solution reward 1.0 in a clean run |
| `nop_fail` | Empty agent reward 0.0 |
| `environment_builds` | Images build |
| `evaluation_deterministic` | Repeat oracle agrees |
| `reference_changes_behavior` | Tests actually flip under the reference diff |

`eval_tasks` already runs oracle and nop via Harbor. Mutation (re-inject each defect into the oracle, expect ≥1 failing check) is specified in `eval_tasks` research note 04 as Q2a and **is not implemented there yet**. Implementing it is a `task_validation` job, using Harbor tasks first.

## Independent behavioral checks

Do not rerun the same tests. Generate probes from the specification, compare against the oracle. ProgramBench is the reference for scale (200 tasks, 248k+ tests). First cut on Harbor tasks: a second hidden seed if the family already regenerates fixtures.

## Mutation

Plausible wrong solutions must fail. SWE-Mutation shows agentic mutants catch more than conventional mutants. First cut on `eval_tasks`: revert each oracle hunk.

## Adversarial / exploit

Verifier access, test files, reference artifacts, leakage, hardcoding, metadata. RHB is the planted-exploit reference. `eval_tasks` implements `/cheat` with `docs/prompts/hack-trial-prompt.md`. Only two cheat jobs exist today (lakehouse GLM 0.0, OPE Opus 0.0). Codex cheat on lakehouse was a safety refusal and does **not** count.

## LLM audit

Instruction, environment, tests, reference, traces. ABA and BenchGuard show this is practical. LLM output is a *signal*, never the gate.

## Static (implemented here)

Harbor ingest records: instruction, task.toml, solution, tests, environment, canary GUID, separate-verifier mode, test file count, instruction length. That is the only evidence this repo computes without Docker.

## What we will not do in Part 1

We will not generate new synthetic tasks to feed this pipeline. Existing populations only.

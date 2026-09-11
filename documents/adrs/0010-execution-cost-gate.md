# ADR-0010: Harbor cost gate before SWE-bench Docker

## Status

Accepted (backfill)

## Decision

Measure wall-clock on hello-world, then lakehouse, before any 50/300/1,699 SWE-bench container evals. Hello-world was ~32s/trial. 731 Pro tasks × 4 Harbor trials at that rate is about a day of Docker. Do not start it until lakehouse cost is known and static reconstruction is written.

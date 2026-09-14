# Replicating the two Harbor-Index reference failures

Reference. The Harbor-Index control run (doc 28) executed one oracle trial and one nop trial per task, 164 trials over 82 tasks. Two of the 53 tasks with an executable reference returned a zero oracle reward. A single observation per task cannot separate a defect from a flake, and the certificate protocol (doc 32) requires two trials per probe. This document records the replication and the cause.

## Method

Both tasks were re-run on 2026-09-14 from the same dataset copy at `/home/evan/Documents/harbor-index-dataset/harbor-index-1.0`, official verifier, oracle twice and nop twice, one job at a time, fresh container per trial. Artifacts under `data/gold/harbor_index_replicate/`.

## Result

| Task | Oracle rewards | Nop rewards | Exceptions | Verdict |
| --- | --- | --- | --- | --- |
| `featurebench-add-feature-xarray-backend-chunks` | 0.0, 0.0 | 0.0, 0.0 | none | invalid, deterministic |
| `sldbench-discover-vocab-scaling-law` | 0.0, 0.0 | 0.0, 0.0 | none | invalid, deterministic |

With the original control trial, each task now has three oracle observations, all zero, with no infrastructure exception in any of them.

## Cause

The two failures are different, and neither is environment rot.

`featurebench-add-feature-xarray-backend-chunks` executes its test suite with the reference applied and reports `9 failed, 9 passed`. Every failure is a parameterisation of `test_grid_rechunk`. The reference does not satisfy the task's own tests.

`sldbench-discover-vocab-scaling-law` runs its verifier to completion and exits zero. Its own standard output reads `Reward written to /logs/verifier/reward.txt: 0.9663633622783212`. The `reward.txt` file collected from the trial contains `0`. The grader's log and the grader's output disagree. Whether a threshold is applied after the log line or the write is a defect, the shipped task returns zero for its own answer key on every run.

## Consequence

The doc 28 figure of two reference failures among 53 executable Harbor-Index tasks stands, now with replication and a named cause for each. Neither failure is attributable to package rot or to this machine, which distinguishes them from the five unadjudicated RST tasks (doc 53) and from the Terminal-Bench 2.1 census failures, all of which are heavy native builds.

The `sldbench` case adds a defect mode not in the four listed in doc 56: a verifier whose reported score and written reward disagree. A pass on the consistency check cannot detect it, because the check reads only the written reward.

# Terminal-Bench 2.0 vs 2.1: natural counterfactuals

Question (doc 23 section 7): when a maintainer fixes a known task defect, does model-free interrogation of the evaluator change from fail to pass?

Run 2026-09-12. PRE = TB 2.0 task directories at `terminal-bench-2` commit `f5b891c` (worktree `~/Documents/tb2-pre`). POST = TB 2.1 task directories from the Harbor dataset `terminal-bench/terminal-bench-2-1` (`~/Documents/tb21-dataset/terminal-bench-2-1`; the git clone of `harbor-framework/terminal-bench-2-1` was deleted from disk mid-run and the dataset copy is byte-identical for these tasks). 28 maintained task names from `data/gold/tb21_maintenance.jsonl`. Change class per task derived mechanically from which files differ (solution/, tests/, instruction.md, task.toml only, environment/). Official Harbor verifier, `--agent oracle` (reference, intended accept) and `--agent nop` (intended reject), a second oracle run where the first took under 5 minutes. No LLM. Runner: `task_validation.evidence.tb21_pairs`. Artifacts: `data/gold/tb21_pairs.jsonl` (148 trials), `data/gold/tb21_pairs.summary.json`. Wall-clock about 3.6 hours plus a 2-hour rerun of the POST half.

## Results

T = reward 1, F = reward 0, . = not run.

| Task | Change | pre oracle | pre oracle 2 | pre nop | post oracle | post oracle 2 | post nop | Outcome |
| --- | --- | :-: | :-: | :-: | :-: | :-: | :-: | --- |
| build-pmars | solution, misspec | F | . | F | T | T | F | separated |
| caffe-cifar-10 | test, misspec, env | F | . | F | T | . | F | separated |
| hf-model-inference | test, env | F | T | F | T | T | F | separated, pre flaky |
| protein-assembly | solution | F | F | F | T | T | F | separated |
| rstan-to-pystan | solution | F | F | F | T | . | F | separated |
| train-fasttext | test | F | . | F | T | T | F | separated |
| crack-7z-hash | resource | F | . | F | T | . | F | separated (memory 2G to 4G) |
| build-pov-ray | solution | F | F | F | F | F | F | fails both |
| mcmc-sampling-stan | solution | F | . | F | F | . | F | fails both |
| make-doom-for-mips | solution | infra | . | infra | T | T | F | pre not run (image) |
| adaptive-rejection-sampler | solution, misspec | T | T | F | T | T | F | no change |
| configure-git-webserver | solution, test | T | T | F | T | T | F | no change |
| financial-document-processor | solution | T | T | F | T | T | F | no change |
| fix-git | test, env | T | T | F | T | T | F | no change |
| install-windows-3.11 | test, misspec | T | . | F | T | . | F | no change |
| overfull-hbox | env | T | T | F | T | T | F | no change |
| polyglot-c-py | test | T | T | F | T | T | F | no change |
| polyglot-rust-c | test | T | T | F | T | T | F | no change |
| sam-cell-seg | test, misspec | T | . | F | T | T | F | no change |
| extract-moves-from-video | misspec, env | T | T | F | T | T | F | no change |
| filter-js-from-html | resource, misspec | T | . | F | T | T | F | no change |
| mteb-leaderboard | env, misspec, resource | T | . | F | T | T | F | no change |
| mteb-retrieve | env, misspec | T | . | F | T | T | F | no change |
| query-optimize | misspec | T | . | F | T | . | F | no change |
| torch-tensor-parallelism | misspec, resource | T | T | F | T | T | F | no change |
| compile-compcert | env | T | . | F | T | . | F | no change |
| gpt2-codegolf | resource | T | T | F | T | T | F | no change |
| torch-pipeline-parallelism | resource | T | T | F | T | T | F | no change |

Counts:

| Measure | Value |
| --- | ---: |
| Tasks with both versions executed | 27 of 28 |
| Pre-fix reference failures | 9 of 27 |
| Pre fail, post pass (separated) | 7 |
| Pre fail, post fail | 2 (`build-pov-ray`, `mcmc-sampling-stan`) |
| Pre pass, post fail | 0 |
| nop accepted (false accept), any version | 0 of 55 nop trials |
| Pre-fix flaky reference | 1 (`hf-model-inference`: F then T) |
| Post-fix reference determinism | 20 of 20 second runs agree |

## Reading

The answer to the doc 23 question is yes for the defect classes that execution can see. Seven of the nine pre-fix reference failures disappear in 2.1, and every one of the seven corresponds to a maintainer change in the solution, tests, environment, or resource budget. Reference plus nop, no LLM, no mutation heuristics, no reading of tests.

What execution does not see: the six tasks whose only 2.1 change is the instruction (`misspec` without `test_fix` or `solution_fix` in `data/gold/tb21_pairs.summary.json`: torch-tensor-parallelism, mteb-retrieve, mteb-leaderboard, extract-moves-from-video, filter-js-from-html, query-optimize) pass reference and reject nop in both versions. Specification defects are invisible to this instrument, which is consistent with doc 18 and doc 26.

Residual invalidity after the fix: `build-pov-ray` and `mcmc-sampling-stan` references still fail in this environment after the 2.1 repair. Both are apt or package pins; whether they fail upstream or only on this host is not established here. They are flagged for human review, not claimed as 2.1 bugs.

Resource-only changes are counted only when they reproduce: `crack-7z-hash` failed at the 2.0 memory cap and passes at the 2.1 cap on this machine, so it is a real separation. The other resource-only tasks passed under both caps here, which does not show the 2.0 cap was fine elsewhere.

Cost: 148 trials, median about 90 seconds, sequential.

## What this changes in the design

The execution gate (reference passes, nop rejected, in a fresh container, twice) is the Part 1 acceptance test for verifier invalidity. It found 9 of 27 pre-fix TB 2.0 tasks, 2 of 16 of our own, 1 of 20 frozen SWE, and 2 of 100 random SWE. The human sample remains for specification invalidity.

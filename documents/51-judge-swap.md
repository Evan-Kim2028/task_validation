# Judge-swap experiment

Use this to measure rubric robustness: does the verdict of a judge-configured Harbor-Index task change when the judge model changes? The official verifier runs unchanged. Only the model behind its OpenAI-compatible endpoint is swapped, from the shipped judge to `devin --model swe-2-max`.

## What it measures

Each of the 16 judge-stratum tasks (`data/gold/harbor_index_strata.json`) gets k=3 runs of the official verifier on the reference output and k=3 on the nop output, in fresh Harbor containers. The verifier's OpenAI SDK path is pointed at a local shim; the shim answers every completion request by invoking the devin CLI headless. Per run the pipeline records the reward, a sha256 of the verifier's judgment JSON (the judge verdict text hash), the number of shim requests inside the trial window, and wall time. Comparing verdicts across runs, and against the shipped-judge rows from doc 44, shows how much of the verdict is rubric and how much is judge.

Protocol id `verifier_judge_swap.devin_swe2max.fresh_environment.execution`, treatment grade B.

## What it does not measure

It does not measure the shipped verifier. The judge model is deliberately different, so a swapped verdict is not evidence about the task's own judge. Rows carry `verifier_kind=judge_swap` and never pool with execution-verified or shipped-judge runs. `certificate.build_certificate` rejects any verdict tagged `judge_swap` before kind checks, so these rows cannot enter a bound even when presented as `verifier_kind=execution` evidence. Doc 43 applies unchanged: no LLM judgment enters a statistical bound.

## Grade-B rationale

Doc 21 grades a treatment by how much of the scoring path is the shipped one. The swap keeps the shipped verifier code, the shipped rubric, the shipped container, and fresh-environment execution. Only the judge model is substituted. That is more than a reimplementation (C) and less than the shipped judge verbatim (A), so B.

## Shim design

`src/task_validation/evidence/judge_shim.py` is a `ThreadingHTTPServer` bound to `0.0.0.0:8477`. It answers `POST /v1/responses` and `POST /v1/chat/completions`, the two endpoints the tasks' `tests/native_judge.py` call (responses first, chat completions as the SDK fallback). Message lists and response `input` items are flattened to plain text, tagged by role, and passed to `devin --model swe-2-max --respect-workspace-trust false -p --prompt-file prompt.txt` in a fresh scratch directory with no repository. The reply text is returned in the OpenAI response shape. Every request and response is one JSONL row in `data/gold/judge_shim_log.jsonl` with a sha256 of the assembled prompt, so judge inputs are auditable without storing prompt text.

Verifier containers run on per-trial bridge networks. The shim is reached at `172.17.0.1:8477`, a local host address reachable from any bridge-networked container; this was verified by POSTing from a probe container on a fresh bridge network. The runner injects `JUDGE_MODELS=devin-swe2max` (routes to the openai provider in `native_judge.judge_provider_for_model`), `JUDGE_REPEATS=1`, `JUDGE_CONCURRENCY=1`, `OPENAI_API_KEY=sk-judge-shim` (dummy), and `OPENAI_BASE_URL=http://172.17.0.1:8477/v1` via `harbor run --verifier-env`. No task files are edited.

Failure handling is loud: a devin non-zero exit, timeout, or empty reply returns HTTP 502 to the verifier, which the official code logs as a judge failure. If a verifier produced LLM-judged detail (reasoning fields or model-matched pairs) while the shim saw zero requests, the row is marked `status=shim_bypassed` and never counts as an executed swap run.

## Runner

`src/task_validation/evidence/judge_swap.py`, exposed as `task-validation judge-swap`. Sequential over tasks; each trial is `harbor run` with `-n 1`, so harbor concurrency is 1 while the gate-A workload occupies the machine. `--verifier-timeout-multiplier 6` gives the devin backend headroom inside the verifier's own timeout. Output: `data/gold/harbor_index_judge_swap.jsonl` and `data/gold/harbor_index_judge_swap.summary.json`. Resume is by `(task_id, probe, rep)` against the JSONL; rerunning skips completed trials.

## Smoke result

2026-09-13, two tasks in the foreground, one reference and one nop trial each.

| Task | Probe | Reward | Shim requests | Status |
| --- | --- | --- | --- | --- |
| hle-identify-city-from-photo | oracle | 1.0 | 1 | executed |
| hle-identify-city-from-photo | nop | 0.0 | 0 | executed |
| gaia2-adapt-hard-1 | oracle | 0.0 | 0 | executed |
| gaia2-adapt-hard-1 | nop | 0.0 | 0 | executed |

The hle oracle trial proves the path end to end: the verifier container POSTed `/v1/responses` to `172.17.0.1:8477` from its own bridge subnet, devin answered, and the verifier accepted the reference (reward 1.0). The hle nop rejects deterministically: no agent output means no judge call, matching the task's short-circuit. gaia2-adapt-hard-1 scores `tool_call_count_mismatch` with zero agent actions, so no LLM call is made there either; that matches the control run's 0.0 for the same probe (`data/gold/harbor_index_control.jsonl`).

## Collect and summarize

The full run is detached under `setsid nohup`, logging to `logs/judge_swap.log`. While it runs:

```
tail -f logs/judge_swap.log
wc -l data/gold/harbor_index_judge_swap.jsonl data/gold/judge_shim_log.jsonl
```

When it finishes (96 trials planned; 4 were completed by the smoke):

```
PYTHONPATH=src .venv/bin/python - <<'PY'
import json
from pathlib import Path
s = json.loads(Path("data/gold/harbor_index_judge_swap.summary.json").read_text())
print(s["n_runs"], "runs;", s["n_tasks_with_rows"], "tasks;",
      s["n_shim_bypassed"], "bypassed;", s["shim"]["n_requests"], "shim requests")
for tid, t in s["tasks"].items():
    print(tid, t["reference"]["rewards"], t["nop"]["rewards"], t["statuses"])
PY
```

Per-verdict comparison against the shipped judge needs the doc-44 shipped-judge run (`data/gold/harbor_index_judge.jsonl`), which requires real provider keys and has not run. Until then the swap rows stand alone as rubric-robustness evidence under their own protocol.

## Results

2026-09-13. All 96 rows in `data/gold/harbor_index_judge_swap.jsonl` are `status=executed`; `data/gold/harbor_index_judge_swap.summary.json` reports `n_runs=96`, `n_shim_bypassed=0`, and `shim.n_requests=36` (also `wc -l data/gold/judge_shim_log.jsonl` = 36). Rewards below are per-rep lists from the JSONL; shim counts are `shim_requests` per run, oracle then nop.

| Task | Oracle rewards | Nop rewards | Shim requests per run (oracle / nop) | Verdict |
| --- | --- | --- | --- | --- |
| gaia2-adapt-hard-1 | 0, 0, 0 | 0, 0, 0 | 0,0,0 / 0,0,0 | short-circuit |
| gaia2-adapt-hard-2 | 0, 0, 0 | 0, 0, 0 | 0,0,0 / 0,0,0 | short-circuit |
| gaia2-ambiguous | 0, 0, 0 | 0, 0, 0 | 0,0,0 / 0,0,0 | short-circuit |
| gaia2-timed-1 | 0, 0, 0 | 0, 0, 0 | 0,0,0 / 0,0,0 | short-circuit |
| gaia2-timed-2 | 0, 0, 0 | 0, 0, 0 | 0,0,0 / 0,0,0 | short-circuit |
| hle-dirac-fermion-tunneling | 1, 1, 1 | 0, 0, 0 | 1,1,1 / 0,0,0 | consistent |
| hle-fibered-category-schemes | 1, 1, 1 | 0, 0, 0 | 1,1,1 / 0,0,0 | consistent |
| hle-identify-city-from-photo | 1, 1, 1 | 0, 0, 0 | 1,1,1 / 0,0,0 | consistent |
| hle-identify-ingvar-runestone | 1, 1, 1 | 0, 0, 0 | 1,1,1 / 0,0,0 | consistent |
| hle-interval-coverage-bound | 1, 1, 1 | 0, 0, 0 | 1,1,1 / 0,0,0 | consistent |
| hle-name-alkaloid-compound | 1, 1, 1 | 0, 0, 0 | 1,1,1 / 0,0,0 | consistent |
| hle-shock-wave-density-profile | 1, 1, 1 | 0, 0, 0 | 1,1,1 / 0,0,0 | consistent |
| hle-vowel-marking-system | 1, 1, 1 | 0, 0, 0 | 1,1,1 / 0,0,0 | consistent |
| omnimath-find-perfect-square-functions | 1, 1, 1 | 0, 0, 0 | 1,1,1 / 0,0,0 | consistent |
| omnimath-maximize-gf-sum | 1, 1, 1 | 0, 0, 0 | 0,0,0 / 0,0,0 | short-circuit |
| widesearch-list-bri-projects-2025 | 1, 1, 1 | 0, 0, 0 | 3,3,3 / 0,0,0 | consistent |

Ten tasks are consistent under the swapped judge: oracle accepted 3/3, nop rejected 3/3, and the judge was actually called (1 shim request per oracle run for the hle and omnimath-find tasks, 3 per oracle run for widesearch, which judges per-item). Six tasks short-circuit: the verifier never reaches the model on either probe, so the swap is vacuous for them. For the five gaia2 tasks the action-mode verifier gates on tool-call count first: `gaia2_cli_result.json` under `/tmp/tv-hindex/judge-swap-jobs/jswap-*/verifier/` records `result_type=tool_call_count_mismatch` with `agent_action_count=0` even on the oracle probe (the oracle replay emits no counted actions), so reward 0.0 is decided before any LLM call. For omnimath-maximize-gf-sum, `reward_detail.json` records `mode=str_verifier, matched=true` on the oracle: the judge entry point is a plain string equality, not an LLM call. Separately, all 48 nop trials made zero shim requests: nop output is empty and every task's verifier rejects before judging. No task is inconsistent; none remains infra.

Verdict text varies run to run without flipping the accept bit: judged tasks carry 2 to 4 distinct `verdict_sha256` values across their 6 rows (summary `tasks.<id>.verdict_sha256`), while deterministic tasks carry 1 or 2.

### Agreement with the control run

`data/gold/harbor_index_control.jsonl` holds one row per probe per task. On nop, all 16 control rows are reward 0.0 and all 48 swap nop rows are 0.0: full agreement, though for gaia2 and widesearch the control 0.0 is a `JudgeConfigurationError` crash (`JUDGE_MODELS must be set` in each row's `test_stdout_tail`) rather than a verifier decision, since the control run injects no judge env. On oracle the control run has no usable verdict for any judge task: 10 rows are `status=infra` (the eight hle and two omnimath tasks) and 6 rows are judge-config crashes (the five gaia2 tasks and widesearch). The one cell that looks divergent, widesearch oracle (control 0.0 vs swap 1, 1, 1), is therefore not a judge disagreement: the control 0.0 came from the missing-`JUDGE_MODELS` crash, not a shipped-judge rejection. Where the control verdict is real it agrees, and no shipped-judge oracle verdict exists yet to disagree with; that comparison still needs the doc-44 run.

### What this does and does not show

Per the grade-B framing above: the shipped verifier code, rubric, container, and fresh-environment execution ran unchanged; only the model behind the OpenAI-compatible endpoint was devin-swe2max. The result shows that on the 10 tasks where the rubric actually consults the judge, a different model accepts the reference and that the accept bit is stable across reps even though the written verdict text varies. It also shows the judge stratum is thinner than it looks: 6 of 16 tasks never exercise the judge on either probe, so their rows say something about the rubric's deterministic gate and nothing about judge robustness. It does not show that the shipped judge accepts or rejects anything: no shipped-judge oracle row exists yet, and these rows (`verifier_kind=judge_swap`) can never enter a certificate bound regardless.

### Operator note, 2026-09-13: prune incident and rerun

The first full pass (job stamps ~19:45-19:50 UTC, 15:45-15:50 local) landed 30 `status=infra` rows for the five tasks then in flight, each failing in about 10 s with "no container found for service main" during artifact copy (row `stderr_tail`). The operator ran `docker image prune -a` in that window, which did remove the verifier images for these tasks (for example `crystalxyz/harbor-index-batch1:gaia2-timed-1-verifier-20260623` re-pulled on the first rerun trial). The recorded root cause in the trial logs is however network exhaustion, not the missing image: `/tmp/tv-hindex/judge-swap-jobs/jswap-*/**/trial.log` shows `compose up --detach --wait` failing with `all predefined address pools have been fully subnetted`: enough stale per-trial bridge networks had accumulated from earlier runs to exhaust docker's default IPAM pools. Not a task defect either way.

The runner's resume keys on `(task_id, probe, rep)`, so infra rows are skipped forever; `judge_swap.py` gained `--redo-infra`, which rewrites `--out` dropping `status=infra` rows for the `--task` ids before the run. Two passes ran detached under `setsid nohup` logging to `logs/judge_swap.log`: at 20:23 UTC the first pass dropped 30 rows, its first 16 retried trials hit the same subnet error, and after the stale `*__env_default` / `*__verifier__trial_default` networks were removed with `docker network rm` (~20:26 UTC; the command refuses networks with attached containers, so the concurrent lot-001 and iceberg-spike networks were untouched) the remaining 14 trials of that pass executed; at 20:48 UTC a second pass dropped the 16 leftover infra rows and completed the set by ~21:11 UTC, about 48 minutes of rerun wall time inside the 90-minute budget. No docker prune ran during the reruns. The runner serves the shim in-process on `0.0.0.0:8477` (`serve_in_thread`), so no detached shim was started; a second bind would have collided, and `/health` answered on `172.17.0.1:8477` during both passes.

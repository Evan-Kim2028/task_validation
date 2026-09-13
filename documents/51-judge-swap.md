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

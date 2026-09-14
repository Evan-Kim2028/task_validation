# Judge-verifier and no-reference protocol

Use this when a pool under certification contains tasks whose verifier is an LLM-judge ensemble, or tasks that ship no reference solution. Harbor-Index 1.0 has 16 of the first (hle 8, gaia2 5, omnimath 2, widesearch 1) and 13 of the second (algotune 5, gso 7, codepde 1): doc 28, `data/gold/harbor_index_strata.json`.

## Judge-verified tasks

1. Run the official judge exactly as the task configures it. Supply the `JUDGE_MODELS` / `JUDGE_REPEATS` environment the task declares (doc 28). Do not substitute a different judge.
2. Run it k=3 times on the reference output and k=3 times on the nop output.
3. Record judge agreement per output: all 3 verdicts, not just the majority. Judge nondeterminism is a verifier property. A judge that flips on identical output is evidence about the verifier, not noise to average away.
4. Record the judge model id and version for every run.
5. Keep judge-verified tasks in their own stratum with their own bound. Never pool them with execution-verified tasks (doc 32: do not pool protocols into one Y).

## No-reference tasks

Pick one per task:

1. Obtain or write a reference solution, then grade it as a treatment A/B/C/D per doc 21. Only A/B references enter the assay.
2. Or hold the task out of the certified population and report it as uncovered. A nop probe alone measures incorrect_reject only; correct acceptance stays unmeasured (doc 28).

## Certificate fields

Per doc 32, every per-lot certificate that contains non-execution verifiers adds:

| Field | Values | Meaning |
| --- | --- | --- |
| verifier_kind | execution, judge, none | How the task's verifier reaches a verdict |
| judge_model | model id and version | Required when verifier_kind is judge |
| judge_agreement | counts out of 3 | Reference agreement and nop agreement, recorded separately |

## What is not claimed

A judge-verified stratum has no grade-A machine certificate. Running the judge measures verifier behavior; it does not adjudicate Y. The bound on a judge stratum is human-adjudicated, drawn under the same probability-sample design as every other stratum (doc 23 section 5, doc 32). A task with verifier_kind none contributes no execution evidence at all.

## Implementation

Runner: `src/task_validation/evidence/judge_verifier.py`, exposed as `task-validation interrogate-judge`. Detection is static: a task is judge-verified when `JUDGE_MODELS` or `JUDGE_REPEATS` appears in its `tests/` files or `task.toml`. The runner passes the declared judge env through `harbor run --verifier-env` and pulls the verifier's own detail JSON with `--verifier-include-logs *.json`, so per-model, per-repeat rewards land in `data/gold/harbor_index_judge.jsonl` next to the k=3 oracle and k=3 nop run rows. Missing keys produce `missing_judge_env` rows; nothing is run or imputed.

Strata map: `data/gold/harbor_index_strata.json` assigns each of the 82 task ids a `verifier_kind` stratum from `data/gold/harbor_index_control.summary.json` plus detection. Counts: 53 execution, 16 judge, 13 none. The judge stratum is 16, not 15: `hle-shock-wave-density-profile` is judge-configured (same `native_judge.py` as the other hle tasks) but its control oracle went infra, so doc 28 counts it under infra, not under the judge outcome row.

Certificate: `src/task_validation/sampling/certificate.py` now carries `verifier_kind`, `judge_model`, and `judge_agreement`, plus a `strata` count over the sample. A verdict that declares a different `verifier_kind` is unadjudicated in this certificate, so judge-verified units cannot pool into an execution bound. A judge certificate also requires `judge_model` on every counted unit and rejects `adjudicator=machine`, matching the no-machine-certificate rule above.

Environment the 16 judge-configured tasks require, per task: `JUDGE_MODELS`, `JUDGE_REPEATS`, `JUDGE_CONCURRENCY`, and the provider key for each chosen model (`OPENAI_API_KEY` by default; `claude*` needs `ANTHROPIC_API_KEY`, `gemini*` needs `GEMINI_API_KEY` or `GOOGLE_API_KEY`, `deepseek*` needs `DEEPSEEK_API_KEY`). `omnimath-find-perfect-square-functions` defaults `JUDGE_MODELS` to `gpt-5` in its verifier code, so it needs `OPENAI_API_KEY` even unconfigured. `task-validation interrogate-judge --list` prints this audit per task.

What ran (2026-09-13): detection, strata enumeration, and the env audit only. No `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`, or `DEEPSEEK_API_KEY` is present in the environment, so no judge task was interrogated and `data/gold/harbor_index_judge.jsonl` does not exist until keys are supplied.

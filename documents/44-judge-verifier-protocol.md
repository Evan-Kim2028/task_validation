# Judge-verifier and no-reference protocol

Use this when a pool under certification contains tasks whose verifier is an LLM-judge ensemble, or tasks that ship no reference solution. Harbor-Index 1.0 has 15 of the first (hle 7, gaia2 5, omnimath 2, widesearch 1) and 13 of the second (algotune 5, gso 7, codepde 1): doc 28, `data/gold/harbor_index_control.summary.json`.

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

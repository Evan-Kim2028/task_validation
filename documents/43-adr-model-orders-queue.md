# ADR: a model orders the queue, never the bound

Status: accepted 2026-09-13.

## Context

The sentence "No LLM scoring inside the pipeline" (doc 42 Rules in force, doc 23 section 13) was written while the open question was whether a model could produce or shrink the published bound. Doc 36 answered that. On the full SWE-bench 1,699 the judge reaches AUROC 0.81 against the majority label, and every judge-calibrated bound is still wider than SRS-CP or undercovers at p = 0.02:

| Estimator at p = 0.02, m = 100 | Coverage | Mean UCB |
| --- | ---: | ---: |
| SRS-CP | 1.00 | 0.059 |
| Rogan-Gladen bootstrap | 0.98 | 0.606 |
| Calibrated FPR/FNR | 1.00 | 0.992 |
| Stratified proportional | 1.00 | 0.104 |
| Stratified flag-heavy | 1.00 | 0.128 |
| PPI++ with judge | 0.88 | 0.041 |

Source: doc 36, `data/gold/judge_bound_lab.json`. A model at AUROC 0.81 is a ranking instrument, not an estimator.

Meanwhile every 2026 frontier filter uses a model at admission:

| Filter | Model use | Recorded effect |
| --- | --- | --- |
| Harbor-Index stage 2 (arXiv 2609.04298) | Gemini-3-Flash broken-task screen | 1,311 to 307 candidates |
| T1 audit over RST (arXiv 2609.11042) | model audit before training | RL lift 59.9 to 64.0 on TB 2.1 |
| CalibForge (arXiv 2608.06352) | model at admission | calibration filtering |
| FrogNano / TaskPilot (arXiv 2609.07925) | model at admission | task screening |

Refusing all model use gives up the queue-ordering signal and buys no statistical safety the design does not already have.

## Decision

LLM scoring is permitted inside the pipeline for one purpose: ordering the review and reject queue over candidate tasks. It never enters the published bound. The bound remains the design-based hypergeometric one-sided 95% UCB from a probability sample, with the SRS arm always present, adjudicated by humans or by grade-A machine execution (doc 23 section 5, doc 32, doc 35, doc 41).

## Consequences

- Model verdicts are stored as a ranking feature with model id and prompt hash, never as a label. Labels still carry protocol and treatment grade (doc 21, doc 32).
- A model-flagged task outside the probability sample does not change the estimate. Ordering decides which units humans see first, not what the sample says.
- Each per-lot certificate states that a model was used for ordering only (doc 32).
- Doc 36 stands unchanged: no Rogan-Gladen bound, no calibrated FPR/FNR bound, no judge-stratified bound, no PPI bound. Each was tested and lost to SRS-CP.
- The doc 23 section 4 rule "No model in the published bound. ML allocates and assists; sampling infers." is unchanged. This ADR is that rule made precise.

## Rules replaced

- The sentence "No LLM scoring inside the pipeline." in doc 42 Rules in force.
- The same sentence inside the agent-and-model bullet of doc 23 section 13.

Agent and model rules, recorded here because they changed in the same decision: implementation and research agents now run through the devin CLI on swe-2-max and through Command Code (cmd) on deepseek-v4.1-flash. cursor-agent composer 2.5 is no longer the default. The bans on api.x.ai and OpenRouter still stand. The grok CLI is for web and X research only.

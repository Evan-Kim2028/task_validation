# LLM specification-invalidity instrument

Cheap LLM auditor vs the 2024 3-rater labels on a frozen SRS. Eval of an instrument, not training. Human labels, votes, and OOF scores never enter the prompt. One pass; no prompt retune after seeing Y.

## Setup

Model `x-ai/grok-4.6` on OpenRouter. Prompt $0.000002 / token ($2.00 / MTok), completion $0.000006 / token ($6.00 / MTok). Reasoning is mandatory; calls used `effort=low`. Spend **$1.65** ($0.0082 / item) of the $10 cap. Pre-run projection $5.68 at 4,000 assumed completion tokens; actual means 2,792 prompt + 444 completion. Wall-clock ~10 min at concurrency 4 (one socket timeout retried). Sample stayed at n=200.

Sample: SRS without replacement, n=200 of 1,699, seed `swe-llm-audit-v0` hashed sha256 to an int, drawn from the sorted `task_id` list (`data/gold/swe_llm_audit_sample.json`). Conservative base rate 0.665 in sample vs 0.683 in the population.

Prompt: issue text, FAIL_TO_PASS names, test patch, gold patch; truncated to ~24k tokens with issue and test patch first. JSON only. Rubric mirrors the 2024 questions (underspecified 0-3, false_negative 0-3, other_major_issue 0/1 plus a one-line reason, confidence 0-1, two-sentence rationale) and asks for `p_invalid` = P(the conservative rule would discard). Frozen ranker: `s = max(underspecified, false_negative) + 0.25*other`.

Combination, written before results: retain lowest `z(s) + z(1-p_i)`.

## Frozen predicates (written before the run)

- **F1** AUROC(s, conservative) >= 0.75 with 1,000-rep bootstrap CI lower bound > 0.70
- **F2** Cohen's kappa of the model material bit vs majority_invalid >= 0.39 (human Fleiss kappa)
- **F3** retain-20% residual under the combination <= 0.20 on conservative Y (versus 0.43 for metadata alone on the full 1,699)

## Results

AUROC, 1,000-rep bootstrap 95% CI:

| Y | s | p_invalid |
| --- | ---: | ---: |
| conservative | 0.776 (0.708, 0.840) | 0.814 (0.746, 0.871) |
| majority | 0.801 (0.737, 0.857) | 0.839 (0.779, 0.889) |
| unanimous | 0.787 (0.724, 0.842) | 0.792 (0.727, 0.855) |

Per-axis: model underspecified vs human underspecified>=2: 0.649 (0.570, 0.719). Model false_negative vs human FN>=2: 0.781 (0.719, 0.844).

Agreement, model as a fourth rater: pairwise vs the three human material bits 0.707 (human-human pairwise on the full dump is 0.70). Vs majority: agreement 0.75, Cohen's kappa **0.495**.

Retain-tail residual invalidity, conservative Y (k = 10 / 20 / 40):

| Rule | 5% | 10% | 20% |
| --- | ---: | ---: | ---: |
| s | 0.400 | 0.300 | 0.275 |
| 1-p_i | 0.300 | 0.250 | 0.350 |
| p_logistic | 0.200 | 0.200 | 0.375 |
| z(s)+z(1-p_i) | 0.400 | 0.300 | 0.275 |

**F1 PASS** (0.776, CI lo 0.708). **F2 PASS** (kappa 0.495). **F3 FAIL** (retain-20% combo residual 0.275 > 0.20).

## Reading

A cheap auditor ranks the 2024 specification label and agrees with majority at about the human kappa. That is new: nothing model-based had been tried, and static spec/test structure was chance (AUROC 0.41). It is not a usable allocator for what PPI needs. Doc 27 wanted AUROC well above 0.9; 0.78 on s and 0.81 on p_invalid sit in the cheap-metadata band (OOF 0.70, solve-rate 0.76), not that band. The product number still fails: keep the safest 20% by the frozen combination and 27.5% are conservative-invalid (11/40). Metadata alone on this sample is 37.5% at 20%; the combo beats that and beats the published 0.43 on the full 1,699, and still misses 0.20. n=10 at 5% is too small to prefer p_logistic's 0.20 there.

The FN axis is where the model (and solve-rate) have signal; underspecification is weaker. Same split as the IRT note. p_invalid outranked discrete s; the frozen score stays s.

What remains for the human sample: this instrument can order a review queue. It cannot certify. Residual 27.5% at retain 20% still needs the SRS adjudication budget in doc 23 (two raters plus tiebreak). Do not put the model in the bound. Do not retune the prompt on this sample.

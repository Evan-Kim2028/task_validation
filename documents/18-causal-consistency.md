# Causal consistency (pause the nine-invariant expansion)

I agree with the other agent’s command. The nine-invariant list was still being filled with lexical stand-ins. Validity, as we defined it, is **whether independent artifacts agree under counterfactuals**.

Question:

> Does a task contain enough internally redundant, executable evidence to test whether its specification, gold change, and evaluator agree?

Not: can we invent another feature that predicts the 2024 label?

## Three assays (defined, then measured once)

| Assay | What we implemented | Executed? |
| --- | --- | --- |
| **Change causality** | Gold hunks vs test-file / F2P name witnesses; declared F2P nonempty | **No** fail-before / pass-after Docker |
| **Contract provenance** | Each assertion payload grounded in prompt / requirements / gold added-lines / nowhere | No control-flow trace |
| **Verifier discrimination** | Profile only: revert-mutant menu, gold-only asserts; rates null until execution | Harbor hello-world only |

No new ML. No token-Jaccard as the primary method. If an assay fails as a ranker, drop that *construction* — do not retune.

## 150-task stratified sample

48 valid / 102 invalid (matches 32/68 of the 1,699). Same conservative Y as before.

Primary metric: residual invalidity in the lowest-risk tail.

| Ranker | Retain 5% residual | Retain 20% residual | AUROC |
| --- | ---: | ---: | ---: |
| **A** OOF logistic (proxies) | 0.38 | 0.43 | 0.72 |
| **B** change causality (static) | 0.38 | 0.70 | **0.41** |
| **C** contract provenance | 0.63 | 0.73 | **0.42** |
| **D** discrimination profile (static) | 0.25 | 0.63 | **0.46** |
| **E** mean(B,C,D) | 0.75 | 0.80 | **0.37** |

B, C, and E are worse than chance as rankers of the 2024 label. **Drop them as label predictors.** Do not keep tuning file-pairing or assertion-string lookup.

D’s 5% tail (0.25 vs A’s 0.38) is n=8. Not enough to keep.

## What this means

The 2024 human label is mostly “are the F2P tests fair?” Almost every SWE-bench task already *declares* FAIL_TO_PASS. Static “does a test file mention the gold module?” is true for too many tasks, valid and invalid. So it cannot recover that label — and we should not force it to.

The *actual* causality assay is executable: tests fail on base, pass after gold, that hunk is necessary. That was **not** run (`executed_gold_eval: false`). The other agent asked for that assay. The static stand-in is not it. **Drop the stand-in. Keep the executable definition for a small later slice, or stop.**

Same for provenance: “payload string in the prompt” is still lookup, not tracing. Drop this construction. A later version has to start from a failing assertion and walk to the gold hunk with execution or AST, or we drop the assay.

## Decision

- Pause nine-invariant expansion. VEV schema can stay as a folder; it is not the research front.
- Do not train a production model on B/C/D/E.
- Do not generate tasks.
- Executable **evaluator interrogation** (assay 3, Harbor official verifier) ran on hello-world and week-hours. See [19-evaluator-interrogation.md](19-evaluator-interrogation.md). That is not a 2024 retain-tail result.
- SWE-bench fail-before/pass-after on a labeled slice is still behind ADR-0010. If that trial does not move the retain-tail, drop assay 1. Do not retune static B/C.

Artifacts: `data/gold/causal_ablation.summary.json` (profiles in `causal_ablation.json`).

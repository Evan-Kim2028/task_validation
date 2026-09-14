# Decision tree (source of truth for sequence)

Supersedes the linear list in [13-next-directives.md](13-next-directives.md). North star: certify a large accepted population with a 95% UCB while human review grows sublinearly.

```
candidate population
  → cheap evidence → risk
  → probability sample (inclusion probs recorded)
  → human audit
  → 95% UCB
  → certify / reject
```

No synthetic generation until Part 1 works. No 1K until Gate 5.

## Frozen 20-task run (Track A1)

IDs and suite locked in `data/gold/swe_2x2_sample.json`. Treatments: reference / nop / revert (A/B only). `executed: false`. **Do not scale Docker.** Interpret as evaluator *behavior*, not as a 2024-label recovery.

After it runs:

| Result | Next |
| --- | --- |
| Clear separation of evaluator behavior | A2: 50–100 selected tasks |
| Null vs 2024 Y | Do not invent mutations. Test orthogonality. |
| Weak treatment labels | A3 natural counterfactuals only |

## Tracks

| Track | Now | Blocked on |
| --- | --- | --- |
| **A** evaluator validity | Harbor 16 done; treatments graded; 20 IDs frozen | Docker for A1 |
| **B** certification | B1 rater-noise + B2 coverage lab (5000 reps done, `data/gold/coverage_lab_r5000.json`) | nothing |
| **C** evidence → risk | Static OOF retain-tail exists | execution on *labeled* SWE (A1) |
| **D** transfer | Pro reconstruction YES (reject, not 30%) | Gate 2 |

## Gates (current)

| Gate | Status |
| --- | --- |
| **1** behavior beyond oracle/nop | **Partial.** Harbor: preserve_comments adds 0 bits vs reference; nop/revert discriminate; 2/16 references fail. Not 2024 Y. |
| **2** retain-tail vs static | **Open.** Conservative 5% tail still ~34% invalid on static OOF. No labeled execution ablation. |
| **3** transfer | **Partial.** Cheap prompt-vs-test recovered OpenAI’s *decision* to distrust Pro. Interrogation not transferred. |
| **4** UCB coverage at low p | **Closed.** 5000-rep lab n=100, `data/gold/coverage_lab_r5000.json` (seed `coverage-lab-v0`). SRS-hypergeometric coverage 0.972–1.00 at p ≤ 5%. Stratified-normal **0.91 at 5%, 0.89 at 2%, 0.63 at 1%, 0.47 at 0.5%** — not a release rule. Release estimator: SRS hypergeometric one-sided UCB (docs 32, 35, 41). |
| **5** small-n certify | **Closed for now.** Tail is not clean. Human packets deferred. |

## Do not

- Merge label provenances (A3 corpus is an index).
- Use ML as the population estimator.
- Tune to OpenAI ~30% or June Kim 15%.
- Use stratified-normal UCB as a release rule.
- Add heuristics that do not name a gate.

If we cannot get (1) validity evidence, (2) valid inference, and (3) a human-budget tradeoff, stop and reassess the north star.

## B1 rater-noise floor (done)

One rater vs 3-rater **majority**: agree **0.85**, FPR **0.14**, FNR **0.16**.

One rater vs **conservative (union)**: FPR 0 (by construction), FNR **0.34**. A single human audit systematically misses invalids the other two caught. Gate 5 human minutes must not assume one rater = consensus.

Pairwise agreement 0.70, Fleiss κ 0.39 (already).

## B2 coverage lab (5000 reps, `data/gold/coverage_lab_r5000.json`; 500-rep draft kept at `data/gold/coverage_lab.json`)

| true p | SRS-HG cover | Stratified-normal cover |
| ---: | ---: | ---: |
| 0.68 | 0.95 | 0.95 |
| 0.20 | 0.97 | 0.93 |
| 0.10 | 0.96 | 0.91 |
| 0.05 | 0.97 | 0.91 |
| 0.02 | 1.00 | **0.89** |
| 0.009 | 1.00 | **0.63** |
| 0.006 | 1.00 | **0.47** |

Risk-guided is discovery-only (no UCB). Hybrid certifies from the SRS arm only.

## A3 corpus

Indexed, not merged: SWE 2024 (1699×3 protocols), Pro 731 (eval-only), June Kim 109, TB 2.1 28, Harbor packets 82 PENDING, Harbor interrogation 16, TVB hole. `data/gold/validity_corpus.json`.

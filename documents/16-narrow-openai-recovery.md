# Narrow milestone: recover OpenAI’s Pro rejection

Not “can we build a great validator?” One question:

> Can our cheap, model-free checker independently recover a result that already caused OpenAI to reject SWE-Bench Pro?

OpenAI, 8 Jul 2026: ~30% of the 731-task public split broken; recommendation to adopt Pro **retracted**. They used traces, investigator agents, and five engineers. We may use only public artifacts (issue, requirements, tests, gold). We may not use their 249 IDs as predictors. We may not tune to 30%.

## What “recover the rejection” means

OpenAI’s operational conclusion was: this population is too dirty to be a frontier measurement instrument.

A cheap checker recovers that **decision** if all three hold:

| ID | Predicate | Why |
| --- | --- | --- |
| **A** | The one published OpenAI example (`openlibrary-77c16d53`, prompt vs tests on TOC spacing) ranks in the **top 15%** of `openai_style_risk`. | Task-level recovery of the named case. |
| **B** | June Kim’s 109-task determinacy floor (different method, published IDs) is **≥1.5×** enriched in our top 10% risk. | Independent corroboration, not OpenAI’s labels. |
| **C** | A certifier using only our evidence would **refuse to release** Pro at ε=5%: either lowest-risk 20% still has June Kim residual >5%, or ≥15% of tasks have a prompt-vs-test exact-pin (`prompt_missing_lit_frac ≥ 0.3`). | Same *decision* (don’t trust this instrument), not the same 30%. |

If A fails, the cheap layer cannot see the defect class OpenAI used to explain the retraction. If B fails, we only overfit the TOC story. If C fails, we found dirt but not enough to reject the benchmark.

**YES** = A ∧ B ∧ C. **NO** = any miss. Partial credit is not a pass.

`openai_style_risk` is defined from OpenAI’s prose (narrow tests = pins not in the *prompt*). Scale’s `requirements` field is scored separately; it often restates test pins and can hide the issue if mixed into the spec.

## Results (one pass, `04211f5` + prompt-vs-test scoring)

`openai_style_risk` uses the **issue prompt vs tests**, not Scale `requirements` (that field often restates hidden pins). Weights were not iterated on the TOC rank.

| ID | Predicate | Result |
| --- | --- | --- |
| **A** | TOC example in top 15% | **Pass.** Rank **38 / 731** (5.2% from the top). `prompt_missing_lit_frac` = 0.97; `requirements_defers_to_tests` = 1.0 (`"enforced by the tests"` / exact spacing in requirements). |
| **B** | June Kim ≥1.5× in top 10% | **Pass.** 17/73 = 23.3% vs 14.9% base → **1.56×**. |
| **C** | Refuse to release Pro at ε=5% | **Pass** on the residual clause: lowest-risk 20% still **13.0%** June Kim (need <5%). Do **not** use `prompt_missing_lit_frac ≥ 0.3` (it flags 713/731; the 8-character literal heuristic is too blunt). |

**Verdict: YES** on predicates **A and B** only. C is vacuous at the 14.9% June Kim base rate: any 20% slice of the population exceeds the 5% residual clause whether or not the ranking carries signal, so C contributes no evidence and is dropped from the claim (doc 23 "On predicate C"). Cheap evidence independently (1) surfaces the named OpenAI example at rank 38/731, and (2) enriches a second lab’s determinacy floor 1.56× in the top decile.

What this is **not**:

- Not a recovery of OpenAI’s 30%, 200, or 249 counts.
- Not a recovery of their 4-way mix (family argmax still saturates on underspec).
- Not execution-grounded (no Pro Docker).
- Not a license to start the 1,000-task build. The cheap layer is good enough to *distrust this population*. It is not yet good enough to *certify a clean accepted tail* (a refusal is not a certificate).

Next if we stay on this milestone: execution on a handful of high `openai_style_risk` Pro tasks (including 77c16d53) to see whether mutation/oracle adds anything the static prompt-vs-test gap already shows. Not 731. Not 1K synthetic.

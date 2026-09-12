# Harbor interrogation pilot (not a population)

The other agent’s next-step list is the right **measurement program** and the wrong **scale**. ADR-0017.

## Agreement

Keep: generalize the harness; five uncollapsed rates; observe vs unavailable vs tested; raw trials; existing human labels with provenance; no synthetic tasks; no official-verifier replacement; no composite score; no static ranker revival; no production model this phase.

## Cuts

| Proposed | Frozen instead |
| --- | --- |
| 50–100 tasks across SWE-bench / TB / Pro | 16 complete local Harbor packages, including lakehouse |
| Population-level evaluator-validation dataset | Task-level behavioral evidence on tasks we can actually run |
| SWE-bench Verified membership as GT | 2024 labels stored as a **separate** fairness protocol, not evaluator Y |
| TVB / TB maintenance as gold | Documented holes (TVB still unopenable) |
| Spec-equivalent / boundary for every task | **Unavailable** unless the instruction/reference labels it |

Static AUROC 0.41 / 0.42 stays the negative baseline. Not rerun.

## What interrogation establishes

The official verifier’s accept/reject on implementations whose intended label is known from the spec or the reference. That is evaluator *behavior*.

## What it does not establish

Material task invalidity in the 2024 sense (hidden tests, underspec). A discriminating verifier can still be an unfair spec. Population residual invalidity. A certificate.

## Pilot results

16 complete Harbor packages. Official verifier only. `--agent oracle` / `--agent nop`. **No LLM.** Wall-clock **2859s** (~48 min), mean **179s/task**. 0 infrastructure failures (every trial returned a reward).

| Question | Result |
| --- | --- |
| How often can evaluator validity be interrogated? | **16/16** (at least one labeled positive and one labeled negative executed) |
| Cost per task | **~3 min** (4–8 Docker trials × ~32–40s). Not tokens. |
| Accept known-correct (mean correct_accept) | **0.875** (14/16 references accepted) |
| Reject known-incorrect (mean incorrect_reject) | **0.979** |
| Accept reasonable alternatives (mean variant_accept) | **0.875** (tracks reference: comment-only `solve.sh`) |
| Accept known-incorrect (mean false_accept) | **0.021** (1 task) |
| Semantic labels ambiguous / unavailable | equivalent/alter/boundary **1/16** (hello-world only). revert **12/16**. observe **1/16**. |
| Static metadata baseline | AUROC **0.41 / 0.42** on 2024 labels. Not rerun. Different estimand. |

13/16 tasks: accept reference+variant, reject all labeled negatives.

Outliers (do not collapse into a score):

| Task | What happened |
| --- | --- |
| `experimental/bootstrap-merge-resume` | Reference reward 0. False-reject 1.0. Negatives still 0. |
| `experimental/logged-bandit-ope` | Same. Slowest task (~327s). |
| `experimental/schema-evolution-cdc` | Reference 1.0. `remove_required` (drop last `install`) still accepted → false-accept 0.33. |
| `tasks/hello-world` `strip_spaces` | Observe-only. Accepted. Instruction vs `.strip()`. Not in the rates. |

**Lakehouse** (`tasks/lakehouse-publish-recovery`): 189s, rates 1/1/1/0/0. ADR-0010 cost number: ~38s/trial, same order as hello-world.

Failure taxonomy:

| Class | n | Notes |
| --- | --- | --- |
| harness/infra (no reward) | 0 | |
| reference rejected | 2 | oracle does not pass in this run; not debug-chased |
| partial gold still accepted | 1 | drop-last-apply too weak as “incorrect” |
| spec-equivalent unavailable | 15 | would require reading tests |
| planted `scripts/checks/test-tasks` | excluded | not real tasks |

No production model. Harbor packets still `PENDING`. SWE 2024 labels were **not** joined as Y.

Artifacts: `data/gold/harbor_interrogate.jsonl`, `.summary.json`, `.matrix.jsonl`; `data/gold/human_labels.jsonl`.

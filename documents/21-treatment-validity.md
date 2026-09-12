# Treatment validity (the 16-task signal, graded)

Agree with the approach. The 16-task pilot is machinery. The bottleneck is **whether intended labels are A/B**, not more treatments and not 50 Docker tasks.

## Treatment grades

| Family | Grade | In assay? | Provenance |
| --- | --- | --- | --- |
| nop | **A** | yes | empty agent |
| preserve (comment) | **A** | yes, but 0 extra bits | no-op vs reference script |
| reference | **B** | yes | author solution (2/16 failed) |
| revert_gold | **B** | yes | constructed pre-fix env |
| hello-world echo / goodbye / case | **B** | yes | instruction literals |
| **remove_required** | **C** | **no** | heuristic last-apply drop |
| strip_spaces | **D** | no | spec-ambiguous |

`remove_required` must not count as a valid negative because the verifier failed. On `schema-evolution-cdc` it **passed**.

## Rates, uncollapsed

| | All executed | **A/B only** |
| --- | ---: | ---: |
| correct_accept | 0.875 | 0.875 |
| variant_accept | 0.875 | 0.875 |
| incorrect_reject | 0.979 | **1.0** |
| false_accept | 0.021 | **0.0** |
| false_reject | 0.125 | 0.125 |

The pilot’s only false-accept was a C treatment. preserve_comments tracked reference **16/16**. Minimum battery: **reference, nop, revert_gold**.

## 2×2 SWE list — not executed

20 run IDs + 8 spare in `data/gold/swe_2x2_sample.json`. Within-class median split on OOF logistic. Cells ~270/269 valid, ~581/579 invalid.

Gold vs base will probably **not** beat the static 0.41/0.42 baseline on 2024 Y: SWE-bench already requires fail-before/pass-after. A null is the **Reconsider** gate, not a reason to invent treatments.

## TB 2.1

28 changed tasks from the public post. `HISTORICAL_MAINTENANCE`. Named misspec: `query-optimize`. TVB still unused.

## Decision gate (unchanged)

**Continue** only if A/B executable interrogation separates independently established validity better than static proxies.

**Reconsider** if it adds little, or if treatment labels require the semantics we are trying to predict.

No 1K. No 731 Docker. No production model. No new treatment types.

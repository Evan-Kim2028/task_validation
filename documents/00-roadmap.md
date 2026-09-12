# Roadmap

Frozen 2026-09-11 after the empirical bridge. Do not start the 1,000-task build. Do not generate synthetic tasks.

```
CURRENT
1,699 human labels
        │
        ▼
cheap artifact model ✓  grouped-CV AUROC ~.70
        │                 (150-task holdout was .76; do not cite that as the OOF number)
        ▼
────────────────────────────────
NOW: decision tree (gates 1–5)   ← you are here
────────────────────────────────
        │
        ├── SWE-Bench Pro 731
        ├── OpenAI failure taxonomy (strict / underspec / low-coverage / misleading)
        └── independent determinacy audit (June Kim, 109/728 floor)
        │
        ▼
execution evidence               (hello-world done; lakehouse next; not 731 Docker yet)
        │
        ▼
better risk / risk-coverage
        │
        ▼
cross-benchmark transfer
        │
        ▼
population sampling
        │
        ▼
first statistical certificate
        │
        ▼
Harbor-scale population
        │
        ▼
1K / 10K / 100K
        │
        ▼
PART 2: synthetic generation
```

## Milestone status

| Milestone | Status |
| --- | --- |
| Thesis + estimand + sister repo | done |
| SWE-bench 2024 gold ingest | done |
| Cheap artifacts + first ranker | done |
| Grouped OOF + retain-tail | done |
| Hello-world Harbor runner | done |
| **Narrow: recover OpenAI's Pro rejection** | **YES (A∧B∧C).** Named example rank 38/731; June Kim 1.56×; would not certify at 5%. Not a 30% match. |
| **Validity Evidence Vector (invariants, not proxies)** | **Paused.** Spec-gap lost to proxies. Do not expand the nine list. |
| **Causal consistency (3 assays)** | **Static B/C dropped** (AUROC 0.41/0.42). |
| **Evaluator interrogation (controlled behavior)** | **Harbor 16-package pilot done.** 16/16 interrogable. Mean ~179s/task. 13/16 clean discrimination. No LLM. Not 50–100 SWE Docker. ADR-0017. |
| **Treatment grades A/B/C/D** | **Done on the 16.** `remove_required` is C. A/B-only false_accept **0**. SWE 2×2 IDs listed, **not executed**. ADR-0018. |
| **Decision tree (gates 1–5)** | **Frozen.** 20-task Docker not scaled. B1 rater-noise + B2 coverage lab + A3 corpus index. ADR-0019. |
| Lakehouse cost (ADR-0010) | **measured:** lakehouse-publish-recovery 189s / 5 trials (~38s/trial). |
| SWE-bench ~50 execution | blocked on cost gate |
| TB 2.1 maintenance gold | not started |
| Six human packets | deferred |
| Population certificate | not started |
| Synthetic generation | Part 2 |

Progress decisions: [adrs/](adrs/). Sequence freeze: [13-next-directives.md](13-next-directives.md).

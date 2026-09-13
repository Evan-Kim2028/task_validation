# Documents

One mode per file. Explanation files argue. Reference files describe. How-to files tell you what to do.

| File | Mode | Read when |
| --- | --- | --- |
| [01-thesis.md](01-thesis.md) | Explanation | You need the locked claim |
| [02-validity-definition.md](02-validity-definition.md) | Reference | You need the estimand |
| [03-prior-art.md](03-prior-art.md) | Explanation | You need the novelty boundary |
| [04-evalqa-gold.md](04-evalqa-gold.md) | Reference | You need the dataset schema |
| [05-evidence-pipeline.md](05-evidence-pipeline.md) | Reference | You need the machine signals |
| [06-risk-model.md](06-risk-model.md) | Explanation | You need what ML is allowed to do |
| [07-sampling-and-certification.md](07-sampling-and-certification.md) | Reference | You need estimators and UCBs |
| [08-human-review-protocol.md](08-human-review-protocol.md) | How-to | You are reviewing packets |
| [09-implementation-plan.md](09-implementation-plan.md) | Explanation | You need phases, stop line, and notes |
| [10-eval-tasks-bridge.md](10-eval-tasks-bridge.md) | Explanation | You need how this repo relates to `eval_tasks` |
| [11-stop-line.md](11-stop-line.md) | How-to | You need what is ready vs deferred |
| [12-empirical-bridge.md](12-empirical-bridge.md) | Explanation | You need the first evidence→label experiment |
| [13-next-directives.md](13-next-directives.md) | How-to | Frozen sequence after the bridge |
| [14-risk-coverage-and-labels.md](14-risk-coverage-and-labels.md) | Explanation | Retain-tail numbers and hello-world execution |
| [00-roadmap.md](00-roadmap.md) | Explanation | Where we are on the 1K→100K path |
| [15-openai-reconstruction.md](15-openai-reconstruction.md) | Explanation | SWE-Bench Pro / OpenAI / June Kim reconstruction |
| [16-narrow-openai-recovery.md](16-narrow-openai-recovery.md) | Explanation | Yes/no: recover OpenAI's Pro rejection |
| [17-validity-evidence-vector.md](17-validity-evidence-vector.md) | Reference | Nine invariants and A–G ablation |
| [18-causal-consistency.md](18-causal-consistency.md) | Explanation | Three assays; drop failed static constructions |
| [19-evaluator-interrogation.md](19-evaluator-interrogation.md) | Explanation | Official verifier vs controlled implementations |
| [20-harbor-pilot.md](20-harbor-pilot.md) | Explanation | Agree on measurement; cut 50–100 multi-bench scale |
| [21-treatment-validity.md](21-treatment-validity.md) | Explanation | A/B/C/D grades; A/B-only rates; SWE 2×2 listed not run |
| [22-decision-tree.md](22-decision-tree.md) | How-to | North star, tracks A–D, gates 1–5 |
| [23-handoff.md](23-handoff.md) | Explanation | **Start here.** Operating story, honest budget, next four experiments |
| [24-taste.md](24-taste.md) | Reference | Taste dimensions kept out of Y; Part 2 placeholder |
| [25-tb21-pairs.md](25-tb21-pairs.md) | Explanation | TB 2.0 vs 2.1 natural counterfactuals: 9/27 pre-fix reference failures, 7 separated, 0 false accepts |
| [28-harbor-index-control.md](28-harbor-index-control.md) | Explanation | Harbor-Index 82 as external control: 2/53 reference failures, 15 LLM-judge verifiers, 13 no reference |
| [26-swe-2x2-exec.md](26-swe-2x2-exec.md) | Explanation | Frozen 20 SWE under the official harness: 19/20 gold pass, 1 env-dependent reference failure, null vs 2024 label |
| [27-ppi-budget.md](27-ppi-budget.md) | Explanation | PPI / GREG / poststrat vs SRS: cheap score saves ~10% labels, breaks coverage at low p |
| [29-pro-verified-transfer.md](29-pro-verified-transfer.md) | Explanation | OpenCompass 102 repaired Pro tasks as eval-only label: AUROC 0.51, P1/P2 fail |
| [30-lit-statistical-certification.md](30-lit-statistical-certification.md) | Explanation | Statistical prior art sweep: PPI, FAQ, acceptance sampling, audits; novelty boundary |
| [31-lit-taste-and-expert-tasks.md](31-lit-taste-and-expert-tasks.md) | Explanation | Rubric matrix, 7-property operational definition of expert-level tasks, generator QC baselines |
| [32-certificate-format.md](32-certificate-format.md) | Reference | Certificate fields, census and coverage-check modes, machine vs human adjudication |
| [33-irt-taste-vs-validity.md](33-irt-taste-vs-validity.md) | Explanation | 2PL IRT on public SWE-bench submissions vs 2024 labels |
| [34-llm-spec-audit.md](34-llm-spec-audit.md) | Explanation | Cheap-model spec audit on a frozen SRS-200 vs 3-rater labels; F1/F2 pass, F3 fail |
| [35-swe-srs100-certificate.md](35-swe-srs100-certificate.md) | Reference | First machine certificate: SRS-100 of 1,699, verifier invalidity in a fresh environment |
| [36-judge-calibrated-bound.md](36-judge-calibrated-bound.md) | Explanation | Full-1,699 judge audit; Rogan-Gladen / calibrated / stratified / PPI bounds vs SRS-CP |
| [37-labels-2026.md](37-labels-2026.md) | Reference | 2026-era per-task label sources: ABA audit data, BenchGuard gold, tau2 changelog, TB 2.1 issues; what does not exist |
| [38-aba-transfer.md](38-aba-transfer.md) | Explanation | 2026 labels ingested (ABA, BenchGuard, tau2, Z.ai); transfer tests T1 to T5 |
| [40-footprint-holdout.md](40-footprint-holdout.md) | Explanation | Non-LLM validity footprint with leave-one-population-out error rates and transfer-bound coverage |
| [41-tb21-census-certificate.md](41-tb21-census-certificate.md) | Reference | TB 2.1 89-task census certificate and SRS-30 coverage check |
| [42-progress-v0.1.md](42-progress-v0.1.md) | Explanation | Release record for v0.1: what is established, rejected, open |
| [43-adr-model-orders-queue.md](43-adr-model-orders-queue.md) | Explanation | ADR: a model orders the review queue, never the bound; current agent and model rules |
| [44-judge-verifier-protocol.md](44-judge-verifier-protocol.md) | How-to | You are certifying a pool with LLM-judge or no-reference tasks |
| [45-harbor-index-funnel-footprint.md](45-harbor-index-funnel-footprint.md) | Explanation | Harbor-Index funnel reconstruction plan, labels, and footprint feasibility |
| [46-frontier-2026-09.md](46-frontier-2026-09.md) | Explanation | September 2026 generation and QC frontier, transfer statistics, positioning table, decontamination and difficulty rules |
| [47-swe-srs300-certificate.md](47-swe-srs300-certificate.md) | Reference | SWE-bench SRS-300 verifier certificate (partial prefix n=190, UCB 4.65%, release) and the 11-item machine-flag human queue |
| [48-harbor-index-funnel-run.md](48-harbor-index-funnel-run.md) | Reference | Harbor-Index funnel reconstruction: manifest verified at 6,627, fetch plan and byte estimate |
| [49-decontamination.md](49-decontamination.md) | Reference | 13-gram and Jaccard decontamination index over TB4, Harbor-Index, TB 2.1, SWE-bench Verified |
| [50-part2-intake-spec.md](50-part2-intake-spec.md) | Reference | Part 2 intake: lot freeze, gates A to C, model-ordered queue, strata, SRS certificate, dossier, operator checklist |
| [51-judge-swap.md](51-judge-swap.md) | Explanation | Judge-swap experiment: devin swe-2-max behind an OpenAI-compatible shim as a grade-B rubric-robustness treatment on the 16 Harbor-Index judge tasks |
| [adrs/](adrs/) | Decisions | You need why a choice was frozen |
| [internal/](internal/) | Working notes | You need search logs and open questions |

Do not merge Part 2 (synthetic generation) into these files. That work has its own later documents.

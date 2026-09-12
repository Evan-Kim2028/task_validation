# ABA 2026 labels, eval-only transfer

Search date 2026-09-12. Labels are evaluation-only ([ADR-0011](adrs/0011-external-audits-are-eval-only.md)). They are not features and were not used to tune weights. ABA is an agent audit (Opus 4.7) with a sampled expert check, not a human census of the benches. Module: `task_validation.evidence.labels_2026`. Artifacts: `data/gold/labels_2026.jsonl`, `labels_2026.summary.json`, `labels_2026.transfer.json`.

## Sources ingested

| Source | n rows | Join | Label mix |
| --- | ---: | --- | --- |
| ABA coding slice | 1320 | see below | 297 major, 207 minor, 816 none |
| OpenCompass Pro Verified | 102 | Pro instance_id | repaired |
| June Kim Pro determinacy | 109 | instance_* prefix | major_issue |
| TB 2.1 maintenance | 28 | TB directory name | repaired |
| Z.ai TB2-verified named fixes | 20 | TB directory name | repaired (not the 89 Dockerfile rows) |
| BenchGuard SAB | 12 | integer task key | repaired |
| BenchGuard Bix | 17 | bix-N-qM | repaired |
| tau2 CHANGELOG v1.0.0/1.0.1 | 78 | domain+number | errata |

ABA slice (matches the opened site): Verified 500 (39 major, 21 static-major, 36 traj-major); Pro 731 (242 any-major, 85 static-major, 220 traj-major); TB2 89 (16 major, 5 static-major, 16 traj-major). License: paper 2605.26079 is CC BY 4.0; `data.autobenchaudit.com` has no LICENSE file. 44 Pro ids join by casefold (`nodebb` vs `NodeBB`). The ABA `task_file` suffix is an audit hash, not a Scale hash.

**Join rules.** TB: directory name (`build-pmars`). SWE Verified: `instance_id` (`astropy__astropy-12907`). Pro: full `instance_{org}__{repo}-{sha}[-v...]`, casefold org/repo. tau2: `airline-2`, `retail-0`, `banking_knowledge-074`.

Overlap of non-none labels on a shared join key: June Kim vs OpenCompass Jaccard 0.884 (99/112); ABA-any vs those 102/109 is 0.21/0.23; TB 2.1 vs Z.ai 0.50; ABA-any vs TB 2.1 0.42.

## Predicates (frozen before any transfer count)

**T1 (TB2, verifier).** Among the 27 maintained TB tasks with a pre-fix execution result, tasks whose pre-fix reference failed (9) have a higher rate of ABA major findings on tb2 than tasks that passed (18). Report the 2x2 and Fisher exact p (stdlib).

**T2 (TB2 census, verifier).** Once the census has rows, the TB 2.1 tasks whose reference fails or whose nop passes are enriched in ABA tb2 major findings versus the rest. Report counts; if the census is incomplete, report on the rows available and say so.

**T3 (SWE Verified, spec).** The ABA Verified major-finding set (39) versus our judge `p_invalid` and solve rate `1-p_i` on the ~500 Verified items that are also in the 1,699: AUROC with 1,000-rep bootstrap CI for each, and versus the 2024 conservative label as the old baseline. Predicate: judge AUROC vs ABA-major >= 0.70.

**T4 (Pro, spec).** ABA Pro major findings (static 85, trajectory 220) versus `openai_style_risk` and `cheap_risk`: AUROC and top-decile enrichment, plus overlap with OpenCompass 102 and June Kim 109 (Jaccard). No frozen pass/fail; descriptive.

**T5 (SWE random 100, verifier).** Do our two execution flags (`django__django-10097`, `django__django-12503`) appear in ABA Verified / any findings? Report what ABA says about them.

## Results

| ID | Result |
| --- | --- |
| **T1** | **Fail.** 2x2 (ABA major / not): pre-fail 1/8, pre-pass 8/10. Rates 0.11 vs 0.44. Fisher two-sided p = 0.193 (greater p = 0.990). Skipped `make-doom-for-mips` (infra). |
| **T2** | **Not enriched.** Census is incomplete (76 of 89). Flagged: `build-cython-ext`, `build-pov-ray` (reference fail, nop ok). 2x2: 0/2 vs 12/62. Rate 0 vs 0.16. |
| **T3** | **Pass.** Judge AUROC 0.876 (0.828 to 0.924). Solve-rate `1-p_i` 0.859 (0.784 to 0.923). 2024 conservative is constant 0 on Verified-500 (all 500 were kept), so AUROC 0.50; it is not a baseline on this slice. |
| **T4** | Chance. `openai_style_risk` AUROC 0.51 (static) / 0.55 (traj); top-decile 1.06x / 0.96x. `cheap_risk` similar or worse. Jaccard vs OpenCompass: static 0.18 (28), traj 0.22 (57); vs June Kim: 0.18 (29) / 0.24 (63). |
| **T5** | `django__django-10097` is in ABA Verified with major static and trajectory findings (F2P list misaligned; unrelated auth template tests). `django__django-12503` is not in the ABA 500 (it is in the 1,699, 2024-invalid). |

T1 fail ids with an ABA major: only `protein-assembly`. Pre-pass ABA majors: `configure-git-webserver`, `extract-moves-from-video`, `filter-js-from-html`, `install-windows-3.11`, `mteb-leaderboard`, `mteb-retrieve`, `polyglot-c-py`, `sam-cell-seg`.

## Reading

A 2026 agent-audit label agrees with our spec-side instruments on SWE Verified: the cheap judge and the public solve rate both rank the 39 ABA majors well above 0.70. That is the same neighborhood the judge was already good at (2024 issue-vs-F2P fairness). It does not agree with verifier execution. Pre-fix TB reference failures and the two live census reference failures are not ABA majors; several instruction-level ABA majors pass reference and reject nop. `django-10097` is the overlap instance (we saw an empty-patch false accept; ABA saw a contaminated F2P list). `django-12503` is outside ABA's Verified sample.

ABA cannot serve as the allocator gold going forward. It labels every Verified, Pro, and TB2 task with a downloadable id, which no other 2026 source does, but it is not a human census. Expert confirmation in the paper is a sample across benches. Construct is mixed (instruction, env, evaluation) and protocol-incompatible with TB maintenance and with the 2024 raters. Use it as a 2026 ranking Y for spec-side transfer tests. Keep the human SRS as the bound. Cheap Pro prompt-vs-test scores do not recover ABA Pro majors, and those majors are mostly not the OpenCompass / June Kim 102/109.

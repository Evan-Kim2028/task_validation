# OpenCompass Pro Verified transfer

Third independent transfer test of cheap prompt-vs-test evidence on SWE-Bench Pro. OpenCompass repaired 102 of 731 public tasks (arXiv 2609.08149; HF `opencompass/SWEBench-Pro-Verified`, Apache 2.0). Those 102 IDs are eval-only ([ADR-0011](adrs/0011-external-audits-are-eval-only.md)). They are not features and were not used to tune weights ([ADR-0012](adrs/0012-do-not-fit-the-thirty-percent.md)).

Field names on `data/gold/swe_pro_features.jsonl`: `task_id`, `features.openai_style_risk`, `features.cheap_risk`. June Kim is not a per-row flag in that file; 109 prefixes live in `data/raw/swe-bench-pro/CLAIMS.md` and match via `match_prefixes`.

## Predicates (frozen before any Pro Verified count)

Population: 731 public Pro rows. Primary score: existing `openai_style_risk` (prompt vs tests). Top 10% k = round(0.10 * n). Lowest-risk 20% k = round(0.20 * n). Enrichment = (positives in head / k) / (n_positive / n). Ties keep input order.

**P1.** The 102 repaired IDs are enriched >= 1.5x in the top 10% of `openai_style_risk` versus the 102/731 base rate.

**P2.** The overly-narrow-tests subset (75) is enriched more than the misleading-prompts subset (22) in that same top 10%. The score was built for prompt-vs-test pins, so narrow tests should be the stronger cell. If P2 fails, the score is not category-specific.

**P3.** The lowest-risk 20% by `openai_style_risk` still contains > 5% repaired IDs. A certifier would refuse to release Pro at eps = 5% on this lineage. The 102/731 base rate is already ~14%, so a random 20% slice is expected above 5%. P3 is a release-refusal check, not proof that the score found the dirt.

YES = P1 and P2 and P3. No retune on fail.

Also report: Jaccard of the 102 with June Kim's 109; enrichment of the union and of the intersection in the same top 10%; the same three numbers on `cheap_risk`; AUROC of `openai_style_risk` for repaired vs not, 1,000-rep bootstrap 95% CI.

## Mapping

HF revision `ae466f824cdee69d2c010b6c954b7418c411b6e4`, Apache 2.0. README Part II lists 102 IDs (22 misleading, 75 narrow, 3 broad, 2 other). `swebench_pro_verified.jsonl` has 731 `instance_id`s; all 731 equal the public Pro `task_id`s. All 102 repaired IDs matched by exact string equality. No hashing, no prefix fallback. 102 >= 90, so the run continued.

## Results

| ID | Predicate | Result |
| --- | --- | --- |
| **P1** | 102 IDs >= 1.5x in top 10% `openai_style_risk` | **Fail.** 14/73 = 19.2% vs 14.0% base (102/731) → **1.37x** |
| **P2** | narrow (75) enriched more than misleading (22) | **Fail.** narrow 10/73 → 1.34x; misleading 4/73 → 1.82x. The score is not category-specific. |
| **P3** | lowest-risk 20% still > 5% repaired | **Pass.** 17/146 = **11.6%** |
| **YES** | P1 and P2 and P3 | **NO** |

AUROC of `openai_style_risk` for repaired vs not: **0.509** (1,000-rep bootstrap 95% CI 0.453 to 0.569). Chance.

| Category | n | in top 73 | enrichment |
| --- | ---: | ---: | ---: |
| misleading_prompts | 22 | 4 | 1.82x |
| overly_narrow_tests | 75 | 10 | 1.34x |
| overly_broad_tests | 3 | 0 | 0 |
| other | 2 | 0 | 0 |
| all repaired | 102 | 14 | 1.37x |

June Kim 109 vs OpenCompass 102: intersection 99, union 112, **Jaccard 0.884**. Same top 10% of `openai_style_risk`: intersection 14/73 → 1.42x; union 17/73 → 1.52x.

`cheap_risk` comparison (not the frozen score): P1 **pass** 17/73 → **1.67x**; P2 **fail** (narrow 1.74x vs misleading 1.82x); P3 **pass** 16/146 = 11.0%.

## Reading

The frozen predicates fail. Weights were not retuned.

`openai_style_risk` does not rank this Y. 1.37x is below the 1.5x bar, and the AUROC CI includes 0.5. P2 fails in the wrong direction: misleading prompts concentrate more than overly narrow tests, so the score is not category-specific. P3 is a refusal (11.6% > 5%) but the base rate is already 14%, the same vacuous structure as predicate C in the handoff.

The 102 are not a new population. They overlap June Kim's 109 on 99 IDs (Jaccard 0.88). Independent provenance, nearly the same label set. `cheap_risk` happens to clear 1.5x here; that is a comparison, not a reason to swap the frozen score.

Artifacts: `data/gold/pro_verified_transfer.json`, `data/gold/pro_verified_labels.jsonl` (eval_only true, provenance `opencompass_swebench_pro_verified_2026`), `data/raw/swe-bench-pro-verified/CLAIMS.md`.

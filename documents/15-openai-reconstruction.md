# OpenAI signal-to-noise reconstruction (SWE-Bench Pro public 731)

Milestone, not a certificate. Audit labels were **not** used as predictors. We did **not** fit the ~30% number.

Sources: ScaleAI/SWE-bench_Pro public split (731); OpenAI, *Separating signal from noise in coding evaluations* (8 Jul 2026); June Kim, swebench-pro-audit CLAIMS.md (109 claimable / 728, 15% floor).

## What OpenAI published

| Step | n | Rate of 731 |
| --- | ---: | ---: |
| Public population | 731 | 1.00 |
| Automated filter | 286 | 0.39 |
| Pipeline broken | 200 | 0.274 |
| Human (5 engineers) broken | 249 | 0.341 |

Families (share of *dataset*, from the OpenAI post): overly strict 14.4% agent / 17.8% human; underspec 6.3 / 7.5; low coverage 4.1 / 9.4; misleading 1.9 / 1.2. They did **not** release the 249 IDs.

That ~30% is a targeted-audit summary. It is not a probability-sample prevalence. Do not treat matching it as validation ([ADR-0012](adrs/0012-do-not-fit-the-thirty-percent.md)).

## Workstream 1: ingest

`data/gold/swe_pro_features.jsonl` — 731 rows.

Available **without** an agent: instruction, requirements, interface, gold patch, test patch, fail_to_pass, dockerhub_tag, language, repo, base_commit. Hidden tests still need the official image to *execute*. Languages: go 280, python 266, js 165, ts 20.

## Workstream 2: cheap static (four families)

Visible spec = problem_statement + requirements + interface. Signals: exact string literals in tests not in spec, `match=`, whitespace asserts, test-only identifiers, gold files unmentioned in spec/tests, instruction/test token conflicts (e.g. “single space” vs `"  "`).

**Family argmax is not a reconstruction of OpenAI’s mix.** Mean family scores: underspec 0.71, low-coverage 0.57, strict 0.33, misleading 0.04. Almost every row’s argmax is underspec. Do not quote 622/731 underspec as an OpenAI-taxonomy recovery. The ranking `cheap_risk` is the object we evaluate.

## Workstream 3–4: execution / mutation

Not run on 731. Hello-world Harbor stack is ~32s/trial; 731 × 4 trials is about a day of Docker ([ADR-0010](adrs/0010-execution-cost-gate.md)). Mutation *menus* (hunk counts) are stored per Pro task with `executed: false`.

## Workstream 5–6: external comparison

**Exact task-level overlap with OpenAI:** they published one worked example (OpenLibrary TOC, one vs two spaces). We matched `instance_internetarchive__openlibrary-77c16d53…`. It ranks **257 / 731** by `cheap_risk` (35th percentile from the top), family argmax underspec, risk 0.47. We **did not** independently put that example in an extreme tail. That is not a task-level reproduction.

**Independent audit with IDs (June Kim):** 109 prefixes in CLAIMS.md matched 109/731 Pro IDs (base rate 14.9%).

| Slice | June Kim rate | Enrichment vs 14.9% |
| --- | ---: | ---: |
| Top 10% `cheap_risk` | 24.7% (18/73) | **1.65×** |
| Top 15% | 22.7% | 1.52× |
| Top 20% | 20.5% | 1.38× |
| Lowest-risk 5% retained | 8.1% | 0.54× |
| Lowest-risk 10% retained | 6.8% | 0.46× |
| All 731 | 14.9% | 1.00× |

That is **enrichment**, not validation. We did not use those 109 IDs as X. Aggregate agreement with OpenAI’s 30% is not reported as a win.

## Workstream 7: retain-tail (June Kim floor as eval Y only)

| Retain lowest `cheap_risk` | n | Residual June Kim rate |
| ---: | ---: | ---: |
| 1% | 7 | 0.00 |
| 5% | 37 | 0.081 |
| 10% | 73 | 0.068 |
| 20% | 146 | 0.103 |
| 100% | 731 | 0.149 |

The tail is cleaner than 15%. It is not a 5% residual on a 15% floor except at tiny n.

## Workstream 8: decision gate

| # | Question | Answer |
| --- | --- | --- |
| 1 | Do cheap signals reproduce known defect *structure*? | **Partial.** Ranking enriches June Kim’s determinacy floor 1.65× in the top 10%. Four-way family mix does **not** match OpenAI (underspec saturates). The one published OpenAI example is mid-pack. |
| 2 | Does execution-grounded evidence materially improve separation? | **Unknown.** Not run on Pro. Hello-world only. |
| 3 | Does the signal transfer beyond SWE-bench 2024? | **Weak yes** on June Kim IDs (independent of OpenAI’s method). Not a trained transfer AUROC. |
| 4 | Is there a sufficiently clean low-risk tail for economical certification? | **No** for a 5% residual on this 15% floor at a useful retain fraction (5–20% retain still 7–10% June Kim). |

Per the frozen rule: if #4 is negative, **stop and investigate the evidence layer** before any 1,000-task work. Next evidence step is lakehouse mutation cost, then a **small** Pro execution subset (not 731), not population sampling.

## Artifacts

- `data/gold/swe_pro_features.jsonl`
- `data/gold/pro_reconstruction.json`
- `data/raw/swe-bench-pro/CLAIMS.md` (June Kim, eval-only)

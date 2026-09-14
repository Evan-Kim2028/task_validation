# Harbor-Index funnel footprint: plan and feasibility

Status: executed 2026-09-13. This page is the dated plan; results are in doc 52 (`data/gold/harbor_funnel_stage1.summary.json`, `harbor_funnel_labels.jsonl`, `harbor_funnel_traj_eval.json`).

## The funnel and what is public

Harbor-Index (arXiv 2609.04298, doc 28) cut 6,627 candidates to 82 tasks:

| Stage | Filter | In | Out |
| --- | --- | ---: | ---: |
| 1 | solve rate at most 33% over 18 frontier trials | 6,627 | 1,311 |
| 2 | Gemini-3-Flash broken-task screen | 1,311 | 307 |
| 3 | 14 human reviewers | 307 | 100 |
| 4 | audit-and-fix | 100 | 82 |

Rejected IDs for stages 2 to 4 are not published (doc 28, `data/gold/label_sources_2026.json`).

The Hugging Face dataset `kendx/Harbor-Adapter` (paper appendix E.1) ships two pieces:

| Artifact | Size | Rows | Contents |
| --- | --- | ---: | --- |
| `harbor_adapters.manifest.parquet` | 16 MB | 178,647 | benchmark, task_name, agent, model, trial_ids; no reward |
| trajectories split | about 340 GB | 793,698 trials | per-task archives, each containing result.json with reward |

On the 54 adapters named in the paper, the manifest holds exactly 6,627 (benchmark, task_name) pairs: the stage-1 input. Of these, 5,684 have at least 3 trials on all 6 frontier cells. Stage 1 used 3 trials times 6 cells drawn from a private database, so the public dump approximates the official solve-rate input rather than reproducing it exactly.

## Plan

1. Reconstruct the candidate population and stage-1 solve rates from the manifest plus result.json only. Estimate bytes per archive first, then fetch selectively. Never pull the full 340 GB.
2. Build three labels:

| Label | Positives | Negatives | Reading |
| --- | ---: | ---: | --- |
| survived_stage1 | about 1,311 | 5,316 | difficulty: at most 33% solve over 18 frontier trials |
| survived_funnel | 82 | 6,545 | survival of the whole funnel |
| survived_2_to_4 | 82 | about 1,229 | AI screen plus human audit, conditional on stage-1 survival |

This is the only label set anywhere with more than 1,000 hard candidates judged by AI plus human audit (`data/gold/label_sources_2026.json` catalogs the smaller sources).

3. Caveat on survived_2_to_4: it conflates broken, too-easy-on-inspection, diversity quota, and panel taste. It is a curation label, not an invalidity label. Evaluate it leave-one-benchmark-out: 82 positives across 29 benchmarks leak benchmark identity, so a pooled AUROC would read source recognition as signal.
4. Apply the existing extractor `src/task_validation/evidence/footprint.py` to all candidates. Report held-out AUROC per stage label. Compare against the 0.71 curated-vs-generated held-out number on Harbor-Index in doc 40.
5. Run exploratory Mapper (topological data analysis) over the footprint features, with stage-1 solve rate as the lens, colored by survival. Use it only to find regions with zero survivors and generator-specific flares. Mapper output is parameter-sensitive, carries no inference, and never enters a gate or a bound.

## Stop rule

If leave-one-benchmark-out AUROC for survived_2_to_4 is under 0.65, the funnel footprint is benchmark identity and the plan stops.

## Cost

The manifest is 16 MB. Beyond that, result.json for about 6,627 tasks times up to 18 trials each, fetched selectively after a per-archive byte estimate.

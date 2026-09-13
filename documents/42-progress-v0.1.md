# Progress note: v0.1 (2026-09-12)

Where the program stands after the first execution night. Start at [23-handoff.md](23-handoff.md) for the operating story; this note is the release record.

## What v0.1 establishes

1. **Verifier invalidity is a machine measurement.** Run the official verifier against the reference and an empty solution in a fresh container, twice. Grade A, no humans, no models, 30 s to 3 min per trial. It found invalid tasks on every unaudited population and ordered populations by their audit history: TB 2.0 pre-fix 33%, our own tasks 12.5%, TB 2.1 post-fix 5.6%, Harbor-Index 3.8%, SWE-bench random sample 2%.
2. **The certification machinery works end to end and covers.** Frozen manifest, machine verdicts, hypergeometric one-sided 95% UCB. SWE-bench SRS-100: p-hat 2%, UCB 6.1%, reject at 5% (doc 35). TB 2.1 census of 89: 5.6% (doc 41); a frozen SRS-30 bound covered the census and Monte Carlo coverage is 0.985 to 1.00.
3. **Natural counterfactuals confirm the instrument.** TB 2.0 to 2.1: 9 of 27 pre-fix references fail; 7 pass after the maintainer fix; 0 false accepts in 55 nop trials (doc 25).
4. **The human budget is what simple random sampling says, and models do not shrink it.** PPI with the metadata score (doc 27) and Rogan-Gladen, calibrated, stratified, and PPI bounds with a judge at AUROC 0.81 (doc 36) all undercover or are wider than SRS at low prevalence. 200 to 300 adjudications per frozen pool at epsilon 5% and true p near 2%.
5. **Specification invalidity does not transfer across benchmarks without labels from the population itself.** Leave-one-population-out calibration misses or is vacuous in 8 of 10 cells (doc 40). The 2026 label sources disagree with each other (Jaccard 0.2 to 0.4). Existing labels support ranking (solve rate 0.86 AUROC vs ABA 2026 majors on SWE-Verified), not bounding.
6. **Model-free interrogation has two coverage boundaries:** LLM-judge verifiers (18% of Harbor-Index) and tasks without a reference (16% of Harbor-Index) (doc 28).
7. **Expert-level task quality has a measurable definition** (doc 31, seven properties) and a non-LLM footprint separates curated from generated tasks at 0.71 to 0.75 held-out AUROC, which is distribution membership, not taste (doc 40).

## What v0.1 rejects

- Static specification/test structure as a validity ranker (docs 18, 29): chance.
- Model-assisted bounds at current signal quality (docs 27, 36).
- Cross-benchmark calibration transfer for the spec construct (doc 40).
- Grade-C heuristic mutations as negatives (doc 21, outlier 3 in doc 23).
- The 2024 SWE-bench annotations as a 2026 target (doc 37).

## Artifacts

Code under `src/task_validation/` (evidence, sampling, model), 130+ tests, gold and manifests under `data/gold/`, raw downloads with `CLAIMS.md` provenance under `data/raw/`, harness logs under `logs/run_evaluation/`, human review packets under `data/review_queue/`. Every number in the documents reproduces from `data/gold/`.

## Rules in force

Agent and model rules are set by doc 43: implementation and research agents run through the devin CLI on swe-2-max and cmd on deepseek-v4.1-flash, and LLM scoring is permitted for ordering the review queue only. No api.x.ai, no OpenRouter. Docs 34 and 36 used an LLM judge before that rule and remain as a record only. Long docker runs live outside agent sessions. Model access history and infrastructure fixes are in doc 23 section 13.

## Open at v0.1

- 11 machine-flagged tasks await a human look: 5 TB 2.1, 2 Harbor-Index, 2 SWE-bench, 2 eval_tasks.
- SWE verifier certificate extension to n=300 running (`data/gold/swe_srs300_sample.json`).
- Part 2 intake definition: execution gate plus footprint prior plus quotas, machine verifier certificate per pool, spec validity tracked through repairs and issues over time.

# Validity certificate

- Decision: RELEASE
- N (population): 1699
- n (sample): 190
- k invalid: 4
- Point estimate p-hat: 0.021053
- One-sided 95% UCB: 0.046498
- Method: hypergeometric-one-sided
- Epsilon: 0.05
- P(certify | p-hat): 0.623894
- Label protocol: verifier_invalid.fresh_environment.execution
- Grade: A
- Adjudicator: machine
- Replaces human sample: False
- Design: SRS without replacement, completed prefix of the frozen sequential SRS-300 draw
- Seed: swe-srs-v0 (sha256 -> int) + swe-srs-v0-extend-200 (sha256 -> int)
- Partial: true. Frozen manifest `data/gold/swe_srs300_sample.json` is n=300; 297 of 300 executed both treatments (`data/gold/swe_srs300_exec.summary.json`); the bound is computed on the completed prefix of the frozen draw order, n=190 (`data/gold/swe_srs300.certificate.json`).
- Complete: true **in the artifact** is scoped to the certificate's own manifest, the 190-unit completed prefix, where every in-bound unit is adjudicated. It does not describe the frozen 300-unit draw, for which `partial` is true. This is the `build_certificate` semantics in `src/task_validation/sampling/certificate.py`; the two fields are not contradictory.

## Flagged units

- `django__django-10097`: empty patch resolved (false accept). Evidence: `logs/run_evaluation/tv100-empty/tv-empty/django__django-10097`
- `django__django-12503`: reference fails own verifier. Evidence: `logs/run_evaluation/tv100-gold/tv-gold/django__django-12503`
- `django__django-10426`: empty patch resolved (false accept). Evidence: `logs/run_evaluation/tv300-empty/tv-empty/django__django-10426`
- `django__django-15521`: reference fails own verifier. Evidence: `logs/run_evaluation/tv300-gold/tv-gold/django__django-15521`

## Reading (added by hand)

This is the extension doc 35 called for: the same frozen design extended to n=300 by adding 200 units drawn without replacement from the 1,599 not in the first 100 (`data/gold/swe_srs300_sample.json`, seeds `swe-srs-v0` and `swe-srs-v0-extend-200`). The first 100 reuse the tv100 runs from doc 35; the 200 new units ran under run_ids `tv300-gold` and `tv300-empty`.

The run is incomplete. 297 of 300 executed both treatments. Three matplotlib units produced no `report.json` on the gold run, so they are unadjudicated: `matplotlib__matplotlib-22926`, `matplotlib__matplotlib-24849`, `matplotlib__matplotlib-25442` (`infra_ids` in `data/gold/swe_srs300_exec.summary.json`). Their empty runs executed and did not resolve.

Because the manifest is a sequential draw, the completed prefix is itself an SRS. The bound uses the first 190 ids of the frozen order, the longest prefix with every unit adjudicated. The 107 units that executed but sit after the first unadjudicated unit are reported here, not in the bound, so no unit is dropped on its own outcome. Four of those 107 are also flagged: `mwaskom__seaborn-2766` and `pydata__xarray-7089` (reference fails own verifier), `psf__requests-774` and `sphinx-doc__sphinx-9467` (empty patch resolved). Evidence: `logs/run_evaluation/tv300-gold/tv-gold/` and `logs/run_evaluation/tv300-empty/tv-empty/` under each id; verdicts in `data/gold/swe_srs300_verdicts.jsonl`. They enter the bound when the run completes. For scale only: a bound over all 297 executed units (k=8) would also be 0.046498. The certified number is the prefix one, since it does not condition on execution.

Decision RELEASE at epsilon 0.05: the one-sided 95% UCB is 4.65% against a point estimate of 2.1%. This is the first pool to clear the bar, at partial sample size. What it says: with 95% confidence, at most 4.7% of the 1,699 SWE-bench test instances have a reference that fails its own verifier or a verifier that accepts an empty patch, in this execution environment. What it does not say is unchanged from doc 35: nothing about specification invalidity, and no replacement for the human sample. `replaces_human_sample` is false by construction.

When the three remaining gold runs land, the certificate recomputes on the next completed prefix or the full n=300. If k stays at 8 of 300, the UCB is 0.0459 and the decision still releases.

Artifacts: `data/gold/swe_srs300_sample.json` (frozen manifest), `data/gold/swe_srs300_exec.jsonl`, `data/gold/swe_srs300_exec.summary.json`, `data/gold/swe_srs300_verdicts.jsonl`, `data/gold/swe_srs300.certificate.json`, harness logs under `logs/run_evaluation/tv100-*` and `logs/run_evaluation/tv300-*`.

## Human queue

The 11 machine-flagged tasks from doc 23 section 8 are assembled as review packets under `data/review_queue/machine_flags_2026-09/` with `manifest.json` as the index. Each packet carries the verifier output, the failing command, and the environment fingerprint. Verdict fields are empty; humans own the call.

| Task | Source | Protocol | Evidence |
| --- | --- | --- | --- |
| `build-cython-ext` | TB 2.1 census (doc 41) | verifier_invalid.fresh_environment.execution | `data/gold/tb21_census_verdicts.jsonl`; `data/gold/tb21_census.jsonl` |
| `build-pov-ray` | TB 2.1 census (doc 41) | verifier_invalid.fresh_environment.execution | `data/gold/tb21_census_verdicts.jsonl`; `data/gold/tb21_census.jsonl` |
| `mcmc-sampling-stan` | TB 2.1 census (doc 41) | verifier_invalid.fresh_environment.execution | `data/gold/tb21_census_verdicts.jsonl`; `data/gold/tb21_census.jsonl` |
| `qemu-alpine-ssh` | TB 2.1 census (doc 41) | verifier_invalid.fresh_environment.execution | `data/gold/tb21_census_verdicts.jsonl`; `data/gold/tb21_census.jsonl` |
| `qemu-startup` | TB 2.1 census (doc 41) | verifier_invalid.fresh_environment.execution | `data/gold/tb21_census_verdicts.jsonl`; `data/gold/tb21_census.jsonl` |
| `featurebench-add-feature-xarray-backend-chunks` | Harbor-Index control (doc 28) | verifier_invalid.fresh_environment.execution | `data/gold/harbor_index_control.jsonl` |
| `sldbench-discover-vocab-scaling-law` | Harbor-Index control (doc 28) | verifier_invalid.fresh_environment.execution | `data/gold/harbor_index_control.jsonl` |
| `django__django-10097` | SWE SRS-100 certificate (doc 35) | verifier_invalid.fresh_environment.execution | `data/gold/swe_srs100.certificate.json`; `data/gold/swe_srs100_verdicts.jsonl` |
| `django__django-12503` | SWE SRS-100 certificate (doc 35) | verifier_invalid.fresh_environment.execution | `data/gold/swe_srs100.certificate.json`; `data/gold/swe_srs100_verdicts.jsonl` |
| `experimental/bootstrap-merge-resume` | eval_tasks diagnosis (doc 20) | verifier_invalid.fresh_environment.execution | `data/gold/harbor_outlier_diagnosis.json`; `data/gold/harbor_interrogate.jsonl` |
| `experimental/logged-bandit-ope` | eval_tasks diagnosis (doc 20) | verifier_invalid.fresh_environment.execution | `data/gold/harbor_outlier_diagnosis.json`; `data/gold/harbor_interrogate.jsonl` |

All 11 flags are grade A, adjudicator machine. The review question for each is whether the failure reproduces upstream or is an environment defect on this host.

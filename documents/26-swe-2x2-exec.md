# SWE-bench 2x2: gold vs empty under the official harness

Run 2026-09-11 with `swebench==5.0.2`, dataset `SWE-bench/SWE-bench` test split, images from the `swebench` namespace, 4 workers, 1800 s timeout. IDs are the frozen 20 in `data/gold/swe_2x2_sample.json` (5 per cell of valid/invalid x low/high OOF risk). Treatments: gold patch (intended accept), empty patch (intended reject), gold again on the 5 fastest (determinism). Parser: `task_validation.evidence.swe_exec`. Artifacts: `data/gold/swe_2x2_exec.jsonl`, `data/gold/swe_2x2_exec.summary.json`, raw harness logs under `logs/run_evaluation/`.

## Results

| Measure | Value |
| --- | ---: |
| Instances run | 20 / 20 (0 infra, 0 timeout) |
| Gold resolved | 19 |
| Empty resolved | 0 |
| Reference fails its own verifier | 1 (`astropy__astropy-7973`) |
| Determinism (5 repeats) | 5 / 5 agree |
| Flaky | 0 |
| Gold wall-clock per instance | 73 s mean |
| Empty wall-clock | ~9 min for 20 |

Cross-tab of the executable signal (gold passes and empty fails) against the 2024 conservative label:

| | invalid (2024) | valid (2024) |
| --- | ---: | ---: |
| signal present | 9 | 10 |
| signal absent | 1 | 0 |

phi = -0.23 on n=20. `correlates_with_2024_label: false`. This is the expected null: SWE-bench is constructed so that gold passes and base fails, and the 2024 label is about specification fairness, not verifier behavior. It is not a retune signal.

## The one failure

`astropy__astropy-7973` (2024 label: invalid, high OOF risk). The single FAIL_TO_PASS test behaves correctly: fails on empty, passes on gold. Four PASS_TO_PASS tests in `astropy/wcs/tests/test_wcs.py` (`TestMaps::test_consistency`, `TestMaps::test_maps`, `TestSpectra::test_consistency`, `TestSpectra::test_spectra`) fail under both treatments. The harness therefore reports gold as not resolved. Those tests depend on data files or network at test time, so this is an environment-integrity defect: in a fresh container the reference cannot pass its own verifier. Class: `verifier_invalid.environment_dependent_p2p`. Grade A (mechanical, same failure under both treatments).

## Reading

- Gold-pass / empty-fail is a construction invariant of SWE-bench and carries no information about the 2024 specification label. Doc 21 predicted this. Assay 1 (change causality by execution) is dropped for SWE-bench as a predictor of that label.
- The instrument still finds something the static layer cannot: 1 of 20 references fails in a fresh environment. On our own 16 Harbor tasks it was 2 of 16. Both are verifier/environment invalidity, which is the construct the instrument measures.
- Cost is low: about 73 s per gold run and under 30 s per empty run with 4 workers. A probability sample of the 1,699 is affordable (doc 32).
- Determinism held on all 5 repeats. No flake observed at this scale.

## Not established

- Any relation between executable evidence and the 2024 label (n=20, and the null was expected).
- Whether the astropy failure is present in the official SWE-bench validation environment or only here. It is recorded as environment-dependent, not as a benchmark bug claim.

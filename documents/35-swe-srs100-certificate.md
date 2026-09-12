# Validity certificate

- Decision: REJECT
- N (population): 1699
- n (sample): 100
- k invalid: 2
- Point estimate p-hat: 0.020000
- One-sided 95% UCB: 0.060624
- Method: hypergeometric-one-sided
- Epsilon: 0.05
- P(certify | p-hat): 0.394817
- Label protocol: verifier_invalid.fresh_environment.execution
- Grade: A
- Adjudicator: machine
- Replaces human sample: False
- Design: SRS without replacement
- Seed: swe-srs-v0 (sha256 -> int)

## Flagged units

- `django__django-10097`: empty patch resolved (false accept)
- `django__django-12503`: reference fails own verifier

## Reading (added by hand)

This is the first end-to-end run of the certification design on a real population: frozen SRS manifest first, then machine adjudication of every sampled unit with grade-A mechanical labels under the official SWE-bench harness, then a design-based bound. No model is in the bound. Wall-clock about 3 hours on one machine, roughly 50 s per gold run and 30 s per empty run with 4 workers, plus registry retries.

What the two flagged units are:

- `django__django-10097`: all 438 FAIL_TO_PASS tests pass with no patch applied, under the current official `swebench` 5.0.2 image. The evaluation cannot distinguish a fix from nothing in that environment. The 2024 three-rater label is valid (0/0/0) and the task is in Verified-500. Only 15% of public submissions resolved it, which suggests the tests did fail on base in the 2024 environment; the defect may be image drift rather than an original construction error. Either way the task is materially invalid for anyone evaluating on today's image. Execution finds this; reading cannot. Prior public flags: SWE-bench issues #267 ("5 instances in Verified fail for gold patch") and #487 (Oct 2025) report the gold patch as unresolved on this instance; no maintainer fix is recorded. Our run shows a different symptom (everything passes), consistent with an image or test-runner drift over time. `django__django-12503` has no prior public flag we could find.
- `django__django-12503`: the reference patch fails `test_no_option (i18n.test_extraction.BasicExtractorTests)` in a fresh container. Environment-dependent (gettext tooling). Same class as `astropy__astropy-7973` in doc 26. The 2024 raters had already marked this task invalid (underspecified 2), for a different reason.

What the certificate says and does not say:

- It says: with 95% confidence, at most 6.1% of the 1,699 SWE-bench test instances have a reference that fails its own verifier or a verifier that accepts an empty patch, in this execution environment. The point estimate is 2%.
- It does not say anything about specification invalidity (the 2024 construct, 68% conservative). That estimand needs the human sample or the judge-calibrated path in doc 36.
- It is a machine certificate. `replaces_human_sample` is false by construction. A human spot check of the flagged units and a random subset is the next step (packets in `data/review_queue/`).

Why REJECT at 5% with p-hat 2%: the OC curve. With 2 of 100 the hypergeometric UCB is 6.1%; P(certify | p = 0.02, n = 100) is 0.39. Doc 23 section 6 already said n = 200 to 300 is the realistic budget at this prevalence. The next draw should extend the same frozen design to n = 300 (add 200 new units, no reselection).

Artifacts: `data/gold/swe_srs100_sample.json` (manifest), `data/gold/swe_srs100_exec.jsonl`, `data/gold/swe_srs100_verdicts.jsonl`, `data/gold/swe_srs100.certificate.json`, harness logs under `logs/run_evaluation/tv100-*`.

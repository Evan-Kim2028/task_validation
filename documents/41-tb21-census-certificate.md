# Validity certificate

- Decision: REJECT
- N (population): 89
- n (sample): 89
- k invalid: 5
- Point estimate p-hat: 0.056180
- One-sided 95% UCB: 0.056180
- Method: census
- Epsilon: 0.05
- P(certify | p-hat): 0.000000
- Label protocol: verifier_invalid.fresh_environment.execution
- Grade: A
- Adjudicator: machine
- Replaces human sample: False
- Design: census
- Seed: None

## Flagged units

- `build-cython-ext`: reference fails own verifier
- `build-pov-ray`: reference fails own verifier
- `mcmc-sampling-stan`: reference fails own verifier
- `qemu-alpine-ssh`: reference fails own verifier
- `qemu-startup`: reference fails own verifier

## Reading (added by hand)

Census of Terminal-Bench 2.1 (89 tasks, Harbor dataset `terminal-bench/terminal-bench-2-1`), official verifier, reference and nop, one docker job at a time, no LLM. Five references fail their own verifier in a fresh container on this host: `build-cython-ext`, `build-pov-ray`, `mcmc-sampling-stan`, `qemu-alpine-ssh`, `qemu-startup`. nop was rejected on all 89. Two of the five (`build-pov-ray`, `mcmc-sampling-stan`) also failed in the 2.0 version and were not repaired by the 2.1 maintenance (doc 25). Whether the five fail upstream or only on this host is not established; they are the human review queue for TB 2.1, with logs under `/tmp/tv-tb21census/jobs`.

Census rate 5.6%, so TB 2.1 does not clear epsilon = 5% on the verifier construct in this environment. It would clear 10%.

## Coverage check of the sample bound against the census

The census is a known truth, so it validates the sampling machinery on a benchmark built by someone else. A frozen SRS of 30 (`data/gold/tb21_srs30_manifest.json`, seed `tb21-srs30-v0`) drew 0 of the 5 invalid units; its one-sided 95% hypergeometric UCB is 7.9%, which covers the census 5.6%. Monte Carlo over 4,000 SRS draws from the census (`data/gold/tb21_census_montecarlo.json`; `simple_random` with seed scheme `tb21-census-mc:n{n}:r{r}`, `srs_estimate` hypergeometric UCB):

| n | coverage of 5.6% | mean UCB | P(UCB < 5%) |
| ---: | ---: | ---: | ---: |
| 20 | 1.000 | 0.208 | 0.000 |
| 30 | 1.000 | 0.163 | 0.000 |
| 50 | 0.9875 | 0.120 | 0.0125 |

The bound covers at or above nominal. It also almost never certifies at 5% when the true rate is 5.6%, which is the correct behavior. Artifacts: `data/gold/tb21_census_verdicts.jsonl`, `tb21_census.certificate.json`, `tb21_srs30.certificate.json`, `tb21_census_montecarlo.json`.

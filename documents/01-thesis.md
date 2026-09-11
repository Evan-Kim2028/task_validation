# Locked thesis

Working title: **Statistical Certification of Agent Evaluation Benchmarks Under Limited Human Review**

## The problem

Agent benchmarks are noisy measurement instruments. A task can look executable and difficult while being invalid because the specification, environment, reference solution, or verifier is inconsistent.

Current practice is still task-centric:

> inspect task → diagnose problem → repair or drop task.

2026 systems make that cheaper. They still do not support a statement of the form:

> Among the N accepted tasks, the residual rate of materially invalid tasks is below X% with 95% confidence.

That is the claim this project is built to make.

## Why the claim matters

OpenAI's 2024 SWE-bench Verified campaign reviewed 1,699 randomly sampled test tasks, three annotators each, and discarded 68.3% under a conservative rule, leaving 500. In 2026 they audited 138 of those 500 that o3 failed across 64 runs and found material issues in 59.4% of *that hard subset*. That 59.4% is not a Verified-wide rate. It is still enough to retire the benchmark as a frontier coding measure.

Their SWE-Bench Pro public split (731 tasks) was auto-flagged at 286 potentially broken tasks. Deeper review put the broken share around 30% of 731. They retracted the recommendation to use Pro as the successor.

The question is not "can humans find bad tasks?" It is "how do we know a large accepted population is trustworthy without reviewing every task?"

## Hypotheses

**H1. Automated evidence is predictive.** Features such as oracle/nop behavior, independent tests, mutation score, determinism, exploit probes, environment integrity, and LLM audit scores predict human material-invalidity labels.

**H2. Risk stratification reduces human cost.** For a fixed review budget, a hybrid of random, stratified, and risk-guided sampling finds defects and estimates prevalence more efficiently than simple random sampling. This is an experiment, not an assumption. Berti-Équille 2026 found that naive representative sampling can beat a bad proxy.

**H3. Population validity can be statistically certified.** After machine filtering and probability sampling, we estimate the finite-population invalidity rate and report a one-sided 95% upper confidence bound.

Example claim:

> The observed invalid rate was 1.2%. The one-sided 95% upper confidence bound is 3.1%.

## One-sentence version

Benchmark validity is a finite-population quality-control problem: independent execution-based evidence identifies high-risk tasks, probability sampling estimates residual invalidity, and a small human audit budget supplies a defensible confidence bound without reviewing every task.

## What this is not

It is not a generator. It is not a 20-dimensional quality score. It is not a claim that nobody has audited benchmarks. It is not Harbor-Index with a new name. Harbor-Index funnels 6,627 candidates to 82 tasks by difficulty, AI audit, and exhaustive human review of survivors. We replace the exhaustive survivor audit with a probability sample and a coverage-checked bound.

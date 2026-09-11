# Next directives (frozen after the empirical bridge)

Written 2026-09-11. This sequence supersedes the “future work” tone in [09-implementation-plan.md](09-implementation-plan.md) for anything after the cheap-feature AUROC.

Do **not** start the 1,000-task build. Do **not** generate synthetic tasks. Part 1 certifies **validity** only.

## Locked claim

> We can certify the residual material-invalidity rate of a large agent-evaluation task population to a predefined statistical bound using a small, explicitly budgeted human audit, rather than exhaustively reviewing every task.

ML may say “I trust this task.” It may not make the population-validity claim. That claim still comes from probability sampling.

## Execution order

1. Label-robustness analysis on the 1,699 three-rater annotations
2. Out-of-fold / risk-coverage / calibration analysis
3. Cheap execution evidence runner
4. Mutation execution (`reference → mutate → verifier`)
5. SWE-bench subset (~50), then maybe 300–500, then maybe 1,699
6. Harbor-Index 82 as external control; 16 `eval_tasks`; 6,627 only if the manifest exists
7. Second gold source: Terminal-Bench 2.1 maintenance (`HISTORICAL_MAINTENANCE`)
8. Six human packets, as a 1–2 minute usability/calibration experiment
9. Sampling experiment (SRS vs stratified vs risk-guided vs hybrid)
10. Population certification on 5k–10k existing tasks
11. Synthetic expansion (Part 2)

Human packets are **after** full evidence vectors, not before.

## Two parallel bottlenecks

**Statistical.** Does the ranker create a *clean accepted tail*? Report residual invalidity among the lowest-risk 1%, 5%, 10%, 20%. That number decides whether certification is economical.

**Engineering.** Cheap Harbor execution + deterministic mutation kill rate, with wall-clock and flake rates, before spending Docker on 1,699 SWE-bench instances.

## Estimator rule already known

Do not use the stratified-normal UCB as a release rule. It undercover at ~2% prevalence. SRS / hypergeometric, or a repaired stratified interval, only.

## Four Part 1 deliverables

1. Evidence: which cheap signals predict material invalidity, and under which label definition
2. Selective risk: how much residual invalidity drops as we reject the tail
3. Sampling: fixed human budgets 10/25/50/100/200
4. Certification: N, n, estimate, 95% UCB, human minutes

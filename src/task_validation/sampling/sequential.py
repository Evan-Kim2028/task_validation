"""Sequential certification. Stop when UCB < epsilon, or when it cannot be met."""

from __future__ import annotations

from dataclasses import dataclass

from task_validation.sampling.estimators import srs_estimate


@dataclass(frozen=True)
class SequentialState:
    n_population: int
    n_sampled: int
    n_invalid: int
    p_hat: float
    ucb95: float
    epsilon: float
    decision: str  # continue | release | reject
    reason: str


def step(
    *,
    N: int,
    n: int,
    k: int,
    epsilon: float,
    alpha: float = 0.05,
) -> SequentialState:
    if n <= 0:
        return SequentialState(N, 0, 0, 0.0, 1.0, epsilon, "continue", "no sample yet")
    est = srs_estimate(k, n, N, alpha)
    if est.ucb95 < epsilon:
        return SequentialState(
            N, n, k, est.p_hat, est.ucb95, epsilon, "release", "ucb below epsilon"
        )
    # Best case remaining: all future draws valid. If even k invalids in N
    # still has UCB >= epsilon at full census, we can only reject if k/N >= epsilon
    # at census. Before census, if k/N already >= epsilon the point estimate
    # cannot recover. If remaining slots cannot dilute k/N below epsilon, reject.
    if N > 0 and (k / N) >= epsilon:
        return SequentialState(
            N, n, k, est.p_hat, est.ucb95, epsilon, "reject", "even a census cannot meet epsilon"
        )
    remaining = N - n
    # If we sample the rest and find zero more invalids, p_hat_final = k/N.
    # UCB at n=N is just k/N. Release is possible iff k/N < epsilon.
    if remaining == 0:
        decision = "release" if est.ucb95 < epsilon else "reject"
        return SequentialState(N, n, k, est.p_hat, est.ucb95, epsilon, decision, "census")
    return SequentialState(N, n, k, est.p_hat, est.ucb95, epsilon, "continue", "ucb still above epsilon")

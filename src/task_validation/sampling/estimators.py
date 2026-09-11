"""Design-based estimators and one-sided upper confidence bounds.

The certification claim is not "we observed 97% valid." It is
"UCB_95%(p) < epsilon" for residual material-invalidity in a finite
accepted population.

Clopper-Pearson is the default binomial UCB because it is conservative.
When the population size N is known and sampling is without replacement,
the hypergeometric tail is tighter and is preferred.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def _binom_sf(k: int, n: int, p: float) -> float:
    """P(X >= k) for X ~ Binomial(n, p)."""
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    # Recurrence on terms to avoid giant factorials.
    q = 1.0 - p
    term = q**n
    total = 0.0
    for i in range(0, k):
        total += term
        if i == n:
            break
        term *= (n - i) * p / ((i + 1) * q) if q > 0 else 0.0
    return max(0.0, min(1.0, 1.0 - total))


def _hypergeom_sf(k: int, N: int, K: int, n: int) -> float:
    """P(X >= k) for X ~ Hypergeometric(N, K, n)."""
    if k <= 0:
        return 1.0
    lo = max(0, n - (N - K))
    hi = min(n, K)
    if k > hi:
        return 0.0
    if k <= lo:
        return 1.0
    total = 0.0
    # Sum the upper tail via log-gamma.
    log_den = math.lgamma(N + 1) - math.lgamma(n + 1) - math.lgamma(N - n + 1)
    for x in range(k, hi + 1):
        log_num = (
            math.lgamma(K + 1)
            - math.lgamma(x + 1)
            - math.lgamma(K - x + 1)
            + math.lgamma(N - K + 1)
            - math.lgamma(n - x + 1)
            - math.lgamma((N - K) - (n - x) + 1)
        )
        total += math.exp(log_num - log_den)
    return max(0.0, min(1.0, total))


def clopper_pearson_upper(k: int, n: int, alpha: float = 0.05) -> float:
    """One-sided Clopper-Pearson upper bound for a binomial proportion.

    Solves for p such that P(X <= k | n, p) = alpha, i.e. the largest p
    still compatible with seeing at most k invalids.
    """
    if n <= 0:
        raise ValueError("n must be positive")
    if k < 0 or k > n:
        raise ValueError("k must be in [0, n]")
    if not 0 < alpha < 1:
        raise ValueError("alpha must be in (0, 1)")
    if k == n:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        # P(X <= k) = 1 - P(X >= k+1)
        cdf = 1.0 - _binom_sf(k + 1, n, mid)
        if cdf > alpha:
            lo = mid
        else:
            hi = mid
    return hi


def hypergeometric_upper(k: int, n: int, N: int, alpha: float = 0.05) -> float:
    """One-sided UCB on K/N given k invalids in an SRS of n from N."""
    if not (0 < n <= N):
        raise ValueError("need 0 < n <= N")
    if k < 0 or k > n:
        raise ValueError("k must be in [0, n]")
    if k == n:
        return 1.0
    # Smallest K such that P(X <= k | N, K, n) < alpha, then K-1 is the bound.
    lo, hi = k, N - (n - k)
    answer = hi
    while lo <= hi:
        mid = (lo + hi) // 2
        cdf = 1.0 - _hypergeom_sf(k + 1, N, mid, n)
        if cdf > alpha:
            lo = mid + 1
        else:
            answer = mid
            hi = mid - 1
    return answer / N


@dataclass(frozen=True)
class PrevalenceEstimate:
    n_population: int
    n_sampled: int
    n_invalid: int
    p_hat: float
    ucb95: float
    method: str
    inclusion_probs_recorded: bool


def srs_estimate(k: int, n: int, N: int, alpha: float = 0.05) -> PrevalenceEstimate:
    if n <= 0:
        raise ValueError("n must be positive")
    p_hat = k / n
    if n < N:
        ucb = hypergeometric_upper(k, n, N, alpha)
        method = "hypergeometric-one-sided"
    else:
        ucb = clopper_pearson_upper(k, n, alpha)
        method = "clopper-pearson-one-sided"
    return PrevalenceEstimate(
        n_population=N,
        n_sampled=n,
        n_invalid=k,
        p_hat=p_hat,
        ucb95=ucb,
        method=method,
        inclusion_probs_recorded=True,
    )


def horvitz_thompson(
    labels: list[int],
    inclusion_probs: list[float],
    N: int,
) -> float:
    """HT estimator of the population mean of a 0/1 label."""
    if len(labels) != len(inclusion_probs):
        raise ValueError("labels and inclusion_probs must align")
    if any(p <= 0 or p > 1 for p in inclusion_probs):
        raise ValueError("inclusion probabilities must be in (0, 1]")
    return (1.0 / N) * sum(y / pi for y, pi in zip(labels, inclusion_probs))


def stratified_estimate(
    strata: list[tuple[int, int, int]],
    N: int,
    alpha: float = 0.05,
) -> PrevalenceEstimate:
    """Strata are (N_h, n_h, k_h). Normal UCB with finite-population correction.

    The point estimate is unbiased. The UCB uses a design-based variance plus
    a z_{1-alpha} quantile. For small n_h this is anti-conservative; the
    coverage simulation in `simulate.py` is the check, not this formula.
    """
    if N <= 0:
        raise ValueError("N must be positive")
    p_hat = 0.0
    var = 0.0
    n_total = 0
    k_total = 0
    z = _z_one_sided(alpha)
    for N_h, n_h, k_h in strata:
        if n_h <= 0 or N_h <= 0:
            continue
        p_h = k_h / n_h
        w = N_h / N
        p_hat += w * p_h
        n_total += n_h
        k_total += k_h
        if n_h > 1:
            fpc = 1.0 - (n_h / N_h)
            s2 = p_h * (1.0 - p_h) * n_h / (n_h - 1)
            var += (w**2) * fpc * (s2 / n_h)
    ucb = min(1.0, p_hat + z * math.sqrt(max(var, 0.0)))
    return PrevalenceEstimate(
        n_population=N,
        n_sampled=n_total,
        n_invalid=k_total,
        p_hat=p_hat,
        ucb95=ucb,
        method="stratified-normal-fpc",
        inclusion_probs_recorded=True,
    )


def _z_one_sided(alpha: float) -> float:
    # Acklam inverse-normal approximation at 1-alpha.
    # Accurate to ~1e-4, enough for an operating UCB.
    p = 1.0 - alpha
    a1, a2, a3, a4, a5, a6 = (
        -3.969683028665376e01,
        2.209460984351125e02,
        -2.759285104469687e02,
        1.383577459574091e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    )
    b1, b2, b3, b4, b5 = (
        -5.447609739541277e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    )
    c1, c2, c3, c4, c5, c6 = (
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    )
    d1, d2, d3, d4 = (
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996e00,
        3.754408661907416e00,
    )
    plow = 0.02425
    phigh = 1 - plow
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c1 * q + c2) * q + c3) * q + c4) * q + c5) * q + c6) / (
            (((d1 * q + d2) * q + d3) * q + d4) * q + 1
        )
    if p <= phigh:
        q = p - 0.5
        r = q * q
        return (
            (((((a1 * r + a2) * r + a3) * r + a4) * r + a5) * r + a6)
            * q
            / (((((b1 * r + b2) * r + b3) * r + b4) * r + b5) * r + 1)
        )
    q = math.sqrt(-2 * math.log(1 - p))
    return -(
        (((((c1 * q + c2) * q + c3) * q + c4) * q + c5) * q + c6)
        / ((((d1 * q + d2) * q + d3) * q + d4) * q + 1)
    )

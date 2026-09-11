"""Coverage and cost simulations on a labeled finite population.

This is the check that a nominal 95% UCB actually covers. Run it on
SWE-bench Verified ensemble labels before trusting the bound on a new
population.
"""

from __future__ import annotations

from dataclasses import dataclass

from task_validation.sampling.designs import hybrid, simple_random, stratified_random
from task_validation.sampling.estimators import srs_estimate, stratified_estimate


@dataclass
class CoverageResult:
    design: str
    n: int
    replicates: int
    true_p: float
    mean_p_hat: float
    mean_ucb: float
    coverage: float
    mean_invalids_found: float


def _labels(population: dict[str, int]) -> tuple[list[str], float]:
    ids = list(population)
    true_p = sum(population[i] for i in ids) / len(ids)
    return ids, true_p


def simulate_srs(
    population: dict[str, int],
    n: int,
    replicates: int,
    seed: str,
) -> CoverageResult:
    ids, true_p = _labels(population)
    N = len(ids)
    hits = 0
    p_sum = 0.0
    ucb_sum = 0.0
    found = 0
    for r in range(replicates):
        draw = simple_random(ids, n, f"{seed}:srs:{r}")
        k = sum(population[i] for i in draw.ids())
        est = srs_estimate(k, n, N)
        p_sum += est.p_hat
        ucb_sum += est.ucb95
        found += k
        if true_p <= est.ucb95 + 1e-12:
            hits += 1
    return CoverageResult(
        design="srs",
        n=n,
        replicates=replicates,
        true_p=true_p,
        mean_p_hat=p_sum / replicates,
        mean_ucb=ucb_sum / replicates,
        coverage=hits / replicates,
        mean_invalids_found=found / replicates,
    )


def simulate_stratified(
    population: dict[str, int],
    strata: dict[str, str],
    n: int,
    replicates: int,
    seed: str,
) -> CoverageResult:
    ids, true_p = _labels(population)
    N = len(ids)
    hits = 0
    p_sum = 0.0
    ucb_sum = 0.0
    found = 0
    for r in range(replicates):
        draw = stratified_random(ids, n, f"{seed}:st:{r}", strata)
        by: dict[str, list[str]] = {}
        for u in draw.units:
            by.setdefault(u.stratum, []).append(u.task_id)
        Nh: dict[str, int] = {}
        for i in ids:
            Nh[strata.get(i, "all")] = Nh.get(strata.get(i, "all"), 0) + 1
        packed = []
        k_total = 0
        for h, members in by.items():
            k_h = sum(population[i] for i in members)
            k_total += k_h
            packed.append((Nh[h], len(members), k_h))
        est = stratified_estimate(packed, N)
        p_sum += est.p_hat
        ucb_sum += est.ucb95
        found += k_total
        if true_p <= est.ucb95 + 1e-12:
            hits += 1
    return CoverageResult(
        design="stratified",
        n=n,
        replicates=replicates,
        true_p=true_p,
        mean_p_hat=p_sum / replicates,
        mean_ucb=ucb_sum / replicates,
        coverage=hits / replicates,
        mean_invalids_found=found / replicates,
    )


def subsample_low_prevalence(
    population: dict[str, int],
    target_p: float,
    seed: str,
) -> dict[str, int]:
    """Build a rarer-invalid population from a labeled set, for QC-style coverage."""
    from task_validation.sampling.designs import _rng

    valid = [i for i, y in population.items() if y == 0]
    invalid = [i for i, y in population.items() if y == 1]
    if not valid:
        return dict(population)
    n_inv = int(round(target_p * len(valid) / max(1.0 - target_p, 1e-9)))
    n_inv = max(1, min(n_inv, len(invalid)))
    rng = _rng(seed + ":lowp")
    keep_inv = rng.sample(invalid, n_inv)
    return {i: 0 for i in valid} | {i: 1 for i in keep_inv}


def simulate_hybrid_discovery(
    population: dict[str, int],
    strata: dict[str, str],
    risks: dict[str, float],
    n: int,
    replicates: int,
    seed: str,
) -> CoverageResult:
    """Hybrid is scored on defect discovery. The UCB is computed from the SRS arm only."""
    ids, true_p = _labels(population)
    N = len(ids)
    hits = 0
    p_sum = 0.0
    ucb_sum = 0.0
    found = 0
    for r in range(replicates):
        draw = hybrid(ids, n, f"{seed}:hy:{r}", strata, risks)
        srs_units = [u for u in draw.units if u.arm == "srs"]
        k_srs = sum(population[u.task_id] for u in srs_units)
        n_srs = max(len(srs_units), 1)
        est = srs_estimate(k_srs, n_srs, N)
        p_sum += est.p_hat
        ucb_sum += est.ucb95
        found += sum(population[u.task_id] for u in draw.units)
        if true_p <= est.ucb95 + 1e-12:
            hits += 1
    return CoverageResult(
        design="hybrid-srs-arm",
        n=n,
        replicates=replicates,
        true_p=true_p,
        mean_p_hat=p_sum / replicates,
        mean_ucb=ucb_sum / replicates,
        coverage=hits / replicates,
        mean_invalids_found=found / replicates,
    )

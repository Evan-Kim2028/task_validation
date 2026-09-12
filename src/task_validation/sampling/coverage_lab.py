"""Coverage laboratory. Does not pick a release estimator until 5000-rep runs.

Stratified-normal UCB is scored here so we can see it fail. It is not the
release rule. SRS uses hypergeometric. Risk-guided is discovery-only.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from task_validation.sampling.designs import hybrid, risk_guided, simple_random, stratified_random
from task_validation.sampling.estimators import srs_estimate, stratified_estimate
from task_validation.sampling.simulate import subsample_low_prevalence
from task_validation.sampling.sequential import step

PREVALENCES = (0.68, 0.20, 0.10, 0.05, 0.02, 0.01, 0.005)
EPSILONS = (0.05, 0.02)


@dataclass
class LabRow:
    design: str
    n: int
    replicates: int
    true_p: float
    mean_p_hat: float
    bias: float
    mean_ucb: float
    mean_width: float
    coverage: float
    mean_invalids_found: float
    n_release: dict
    n_false_certify: dict
    notes: str


def _pack(design: str, n: int, reps: int, true_p: float, p_hats, ucbs, found, notes: str) -> LabRow:
    hits = sum(1 for u in ucbs if true_p <= u + 1e-12)
    release = {}
    false_c = {}
    for eps in EPSILONS:
        n_rel = sum(1 for u in ucbs if u < eps)
        release[str(eps)] = n_rel / reps
        # False certify: we would release at eps while the population is worse than eps.
        if true_p >= eps:
            false_c[str(eps)] = n_rel / reps
        else:
            false_c[str(eps)] = 0.0
    mean_p = sum(p_hats) / reps
    mean_u = sum(ucbs) / reps
    return LabRow(
        design=design,
        n=n,
        replicates=reps,
        true_p=true_p,
        mean_p_hat=mean_p,
        bias=mean_p - true_p,
        mean_ucb=mean_u,
        mean_width=mean_u - mean_p,
        coverage=hits / reps,
        mean_invalids_found=sum(found) / reps,
        n_release={k: v for k, v in release.items()},
        n_false_certify={k: v for k, v in false_c.items()},
        notes=notes,
    )


def simulate_srs_lab(population: dict[str, int], n: int, reps: int, seed: str) -> LabRow:
    ids = list(population)
    N = len(ids)
    true_p = sum(population.values()) / N
    p_hats, ucbs, found = [], [], []
    for r in range(reps):
        draw = simple_random(ids, n, f"{seed}:srs:{r}")
        k = sum(population[i] for i in draw.ids())
        est = srs_estimate(k, n, N)
        p_hats.append(est.p_hat)
        ucbs.append(est.ucb95)
        found.append(k)
    return _pack("srs-hypergeometric", n, reps, true_p, p_hats, ucbs, found, "certificate arm")


def simulate_stratified_normal_lab(
    population: dict[str, int],
    strata: dict[str, str],
    n: int,
    reps: int,
    seed: str,
) -> LabRow:
    ids = list(population)
    N = len(ids)
    true_p = sum(population.values()) / N
    p_hats, ucbs, found = [], [], []
    for r in range(reps):
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
        p_hats.append(est.p_hat)
        ucbs.append(est.ucb95)
        found.append(k_total)
    return _pack(
        "stratified-normal-fpc",
        n,
        reps,
        true_p,
        p_hats,
        ucbs,
        found,
        "NOT a release rule; known to undercover at low p",
    )


def simulate_hybrid_lab(
    population: dict[str, int],
    strata: dict[str, str],
    risks: dict[str, float],
    n: int,
    reps: int,
    seed: str,
) -> LabRow:
    ids = list(population)
    N = len(ids)
    true_p = sum(population.values()) / N
    p_hats, ucbs, found = [], [], []
    for r in range(reps):
        draw = hybrid(ids, n, f"{seed}:hy:{r}", strata, risks)
        srs_units = [u for u in draw.units if u.arm == "srs"]
        k_srs = sum(population[u.task_id] for u in srs_units)
        n_srs = max(len(srs_units), 1)
        est = srs_estimate(k_srs, n_srs, N)
        p_hats.append(est.p_hat)
        ucbs.append(est.ucb95)
        found.append(sum(population[u.task_id] for u in draw.units))
    return _pack(
        "hybrid-srs-arm-certificate",
        n,
        reps,
        true_p,
        p_hats,
        ucbs,
        found,
        "UCB from SRS arm only; other arms are discovery",
    )


def simulate_risk_discovery(
    population: dict[str, int],
    risks: dict[str, float],
    n: int,
    reps: int,
    seed: str,
) -> LabRow:
    ids = list(population)
    N = len(ids)
    true_p = sum(population.values()) / N
    p_hats, ucbs, found = [], [], []
    for r in range(reps):
        draw = risk_guided(ids, n, f"{seed}:rg:{r}", risks)
        k = sum(population[i] for i in draw.ids())
        # Discovery arm: do not certify. Record a dummy UCB=1 so release rate is 0.
        p_hats.append(k / n)
        ucbs.append(1.0)
        found.append(k)
    row = _pack("risk-guided-discovery-only", n, reps, true_p, p_hats, ucbs, found, "no certificate")
    return row


def simulate_sequential_srs(
    population: dict[str, int],
    n_max: int,
    batch: int,
    reps: int,
    seed: str,
    epsilon: float = 0.05,
) -> dict:
    ids = list(population)
    N = len(ids)
    true_p = sum(population.values()) / N
    n_rel = n_rej = n_open = 0
    n_false = 0
    ns = []
    for r in range(reps):
        rng_ids = simple_random(ids, min(n_max, N), f"{seed}:seq:{r}").ids()
        k = 0
        decision = "continue"
        n_used = 0
        for n in range(batch, min(n_max, N) + 1, batch):
            k = sum(population[i] for i in rng_ids[:n])
            st = step(N=N, n=n, k=k, epsilon=epsilon)
            n_used = n
            decision = st.decision
            if decision != "continue":
                break
        ns.append(n_used)
        if decision == "release":
            n_rel += 1
            if true_p >= epsilon:
                n_false += 1
        elif decision == "reject":
            n_rej += 1
        else:
            n_open += 1
    return {
        "design": "sequential-srs",
        "n_max": n_max,
        "batch": batch,
        "replicates": reps,
        "true_p": true_p,
        "epsilon": epsilon,
        "p_release": n_rel / reps,
        "p_reject": n_rej / reps,
        "p_open_at_nmax": n_open / reps,
        "p_false_release": n_false / reps,
        "mean_n_at_stop": sum(ns) / reps,
    }


def load_population(gold: Path, oof: Path | None) -> tuple[dict[str, int], dict[str, str], dict[str, float]]:
    population: dict[str, int] = {}
    strata: dict[str, str] = {}
    risks: dict[str, float] = {}
    with gold.open(encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            tid = rec["task_id"]
            population[tid] = 1 if rec.get("human_validity_label") == "invalid" else 0
            strata[tid] = rec.get("repository") or "unknown"
            sev = rec.get("human_severity") or {}
            risks[tid] = float(sev.get("false_negative") or 0.0) / 3.0
    if oof and oof.is_file():
        with oof.open(encoding="utf-8") as fh:
            for line in fh:
                rec = json.loads(line)
                risks[rec["task_id"]] = float(rec["p_logistic"])
    return population, strata, risks


def run_lab(
    gold: Path,
    oof: Path | None,
    *,
    n: int = 100,
    replicates: int = 500,
    seed: str = "coverage-lab-v0",
    prevalences: tuple[float, ...] = PREVALENCES,
) -> dict:
    base_pop, strata, risks = load_population(gold, oof)
    rows = []
    seq = []
    for p in prevalences:
        if abs(p - 0.68) < 0.02:
            pop = dict(base_pop)
            tag = f"{seed}:p68"
        else:
            pop = subsample_low_prevalence(base_pop, p, f"{seed}:p{p}")
            tag = f"{seed}:p{p}"
        st = {i: strata[i] for i in pop}
        rk = {i: risks.get(i, 0.0) for i in pop}
        true_p = sum(pop.values()) / len(pop)
        nn = min(n, len(pop))
        rows.append(asdict(simulate_srs_lab(pop, nn, replicates, tag)))
        rows.append(asdict(simulate_stratified_normal_lab(pop, st, nn, replicates, tag)))
        rows.append(asdict(simulate_hybrid_lab(pop, st, rk, nn, replicates, tag)))
        rows.append(asdict(simulate_risk_discovery(pop, rk, nn, replicates, tag)))
        if true_p <= 0.06:
            seq.append(simulate_sequential_srs(pop, nn, 20, replicates, tag, epsilon=0.05))
    return {
        "n": n,
        "replicates": replicates,
        "seed": seed,
        "epsilon_grid": list(EPSILONS),
        "final_estimator_requires_replicates": 5000,
        "stratified_normal_is_release_rule": False,
        "rows": rows,
        "sequential": seq,
        "gate": "B2 / Gate 4",
    }

"""Sampling designs. Inclusion probabilities are first-class.

ML risk scores may oversample the high-risk tail. They do not replace
the probability sample that carries the population estimate.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SampleUnit:
    task_id: str
    stratum: str
    risk: float
    inclusion_prob: float
    arm: str  # srs | stratified | high_risk | novel | hybrid


@dataclass
class SampleDraw:
    design: str
    n: int
    seed: str
    units: list[SampleUnit] = field(default_factory=list)

    def ids(self) -> list[str]:
        return [u.task_id for u in self.units]


def _rng(seed: str) -> random.Random:
    digest = hashlib.sha256(seed.encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def simple_random(
    task_ids: list[str],
    n: int,
    seed: str,
    strata: dict[str, str] | None = None,
    risks: dict[str, float] | None = None,
) -> SampleDraw:
    if n > len(task_ids):
        raise ValueError("n larger than population")
    rng = _rng(seed)
    chosen = rng.sample(list(task_ids), n)
    N = len(task_ids)
    pi = n / N
    units = [
        SampleUnit(
            task_id=i,
            stratum=(strata or {}).get(i, "all"),
            risk=(risks or {}).get(i, 0.0),
            inclusion_prob=pi,
            arm="srs",
        )
        for i in chosen
    ]
    return SampleDraw(design="srs", n=n, seed=seed, units=units)


def stratified_random(
    task_ids: list[str],
    n: int,
    seed: str,
    strata: dict[str, str],
    risks: dict[str, float] | None = None,
) -> SampleDraw:
    """Proportional allocation, at least one per nonempty stratum when n allows."""
    rng = _rng(seed)
    buckets: dict[str, list[str]] = {}
    for i in task_ids:
        buckets.setdefault(strata.get(i, "all"), []).append(i)
    N = len(task_ids)
    alloc: dict[str, int] = {}
    remaining = n
    names = sorted(buckets)
    for h in names:
        take = int(round(n * len(buckets[h]) / N))
        take = min(take, len(buckets[h]))
        alloc[h] = take
        remaining -= take
    # Fix rounding so we hit n without exceeding stratum size.
    while remaining > 0:
        progressed = False
        for h in names:
            if remaining <= 0:
                break
            if alloc[h] < len(buckets[h]):
                alloc[h] += 1
                remaining -= 1
                progressed = True
        if not progressed:
            break
    while remaining < 0:
        progressed = False
        for h in reversed(names):
            if remaining >= 0:
                break
            if alloc[h] > 0:
                alloc[h] -= 1
                remaining += 1
                progressed = True
        if not progressed:
            break
    units: list[SampleUnit] = []
    for h in names:
        chosen = rng.sample(buckets[h], alloc[h]) if alloc[h] else []
        Nh = len(buckets[h])
        pi = alloc[h] / Nh if Nh else 0.0
        for i in chosen:
            units.append(
                SampleUnit(
                    task_id=i,
                    stratum=h,
                    risk=(risks or {}).get(i, 0.0),
                    inclusion_prob=pi,
                    arm="stratified",
                )
            )
    return SampleDraw(design="stratified", n=len(units), seed=seed, units=units)


def risk_guided(
    task_ids: list[str],
    n: int,
    seed: str,
    risks: dict[str, float],
    strata: dict[str, str] | None = None,
    floor: float = 0.05,
) -> SampleDraw:
    """Oversample the high-risk tail. Inclusion probs are recorded so HT works.

    Sampling probability is proportional to max(risk, floor), without
    replacement, via sequential weighted draws.
    """
    rng = _rng(seed)
    remaining = list(task_ids)
    chosen: list[str] = []
    # Approximate pi_i via the first-order inclusion of a draw-by-draw scheme.
    # Exact without-replacement pi is expensive; we record the realized
    # sequential probability product as a conservative known-pi design.
    pi: dict[str, float] = {i: 0.0 for i in task_ids}
    for draw_i in range(n):
        weights = [max(risks.get(i, 0.0), floor) for i in remaining]
        total = sum(weights)
        if total <= 0:
            pick = rng.choice(remaining)
            p = 1.0 / len(remaining)
        else:
            u = rng.random() * total
            acc = 0.0
            pick = remaining[-1]
            p = weights[-1] / total
            for i, w in zip(remaining, weights):
                acc += w
                if acc >= u:
                    pick = i
                    p = w / total
                    break
        # Survival probability of still being in the pool times this draw p.
        # For units not yet chosen, accumulate.
        for i, w in zip(remaining, weights):
            pi[i] += (1.0 - pi[i]) * ((w / total) if total else 1.0 / len(remaining))
        chosen.append(pick)
        remaining.remove(pick)
        if not remaining:
            break
        _ = draw_i
    units = [
        SampleUnit(
            task_id=i,
            stratum=(strata or {}).get(i, "all"),
            risk=risks.get(i, 0.0),
            inclusion_prob=min(1.0, max(pi[i], 1e-12)),
            arm="high_risk",
        )
        for i in chosen
    ]
    return SampleDraw(design="risk_guided", n=len(units), seed=seed, units=units)


def hybrid(
    task_ids: list[str],
    n: int,
    seed: str,
    strata: dict[str, str],
    risks: dict[str, float],
    fractions: tuple[float, float, float, float] = (0.60, 0.20, 0.15, 0.05),
) -> SampleDraw:
    """Production mix: probability + stratified + high-risk + novel.

    The probability arm is the one that certifies. Targeted arms find defects.
    Overlap is dropped from later arms so a task is reviewed once; the
    surviving inclusion probability is the probability it entered through
    any arm, approximated as 1 - product(1 - pi_arm) for arms that could
    have selected it. For the first cut we record the arm it actually
    entered and that arm's pi, and we keep the srs arm large enough that
    the population estimate can be computed from srs units alone.
    """
    n_srs, n_str, n_risk, n_novel = [
        max(0, int(round(n * f))) for f in fractions
    ]
    # Fix rounding to n.
    while n_srs + n_str + n_risk + n_novel > n and n_srs > 0:
        n_srs -= 1
    while n_srs + n_str + n_risk + n_novel < n:
        n_srs += 1
    used: set[str] = set()
    units: list[SampleUnit] = []

    srs = simple_random(task_ids, min(n_srs, len(task_ids)), seed + ":srs", strata, risks)
    units.extend(srs.units)
    used.update(srs.ids())

    rest = [i for i in task_ids if i not in used]
    if n_str and rest:
        st = stratified_random(rest, min(n_str, len(rest)), seed + ":str", strata, risks)
        units.extend(st.units)
        used.update(st.ids())

    rest = [i for i in task_ids if i not in used]
    if n_risk and rest:
        rg = risk_guided(rest, min(n_risk, len(rest)), seed + ":risk", risks, strata)
        units.extend(rg.units)
        used.update(rg.ids())

    rest = [i for i in task_ids if i not in used]
    if n_novel and rest:
        # "Novel" here is the lowest-risk remainder: regime-change placeholder
        # until generator-version metadata exists.
        ranked = sorted(rest, key=lambda i: risks.get(i, 0.0))
        take = ranked[: min(n_novel, len(ranked))]
        pi = n_novel / max(len(rest), 1)
        for i in take:
            units.append(
                SampleUnit(
                    task_id=i,
                    stratum=strata.get(i, "all"),
                    risk=risks.get(i, 0.0),
                    inclusion_prob=pi,
                    arm="novel",
                )
            )

    return SampleDraw(design="hybrid", n=len(units), seed=seed, units=units)

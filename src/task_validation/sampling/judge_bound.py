"""Judge-calibrated finite-population invalidity bounds.

A cheap auditor labels every unit. Humans label a calibration subsample.
Coverage is a property of the bound, not of judge quality.

Frozen predicates, written before any full-population AUROC or Monte
Carlo cell was computed:

J1. Judge AUROC (p_invalid vs majority_invalid) on the full 1,699 >= 0.80.
J2. At true p=0.02 and m=100, at least one calibrated or stratified
    estimator has Monte Carlo coverage >= 0.95 and mean UCB strictly
    below SRS-CP at the same m.
J3. For true p=0.02, the smallest m in {30,50,100,200} at which a valid
    (coverage >= 0.95) estimator has mean UCB < 0.05 is at most half the
    corresponding SRS-CP m (a 2x drop in human labels).
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

from task_validation.sampling.estimators import clopper_pearson_upper, srs_estimate
from task_validation.sampling.ppi import (
    AssistedEstimate,
    auroc_binary,
    ppi_mean_ucb,
    poststrat_exact_ucb,
)

REPO_ROOT = Path(__file__).resolve().parents[3]

# Written before computing. Do not retune after seeing cells.
FROZEN_PREDICATES = {
    "J1": "judge AUROC vs majority on the full 1,699 >= 0.80",
    "J2": (
        "at p=0.02 and m=100 at least one calibrated/stratified estimator "
        "covers >= 0.95 AND has mean UCB below SRS-CP"
    ),
    "J3": (
        "the human labels needed for UCB < 0.05 at p=0.02 drop by at least "
        "2x versus SRS-CP for some valid estimator"
    ),
}

N_GRID = (30, 50, 100, 200)
OC_N_GRID = (50, 100, 200)
EPS_GRID = (0.05, 0.10, 0.20)
THIN_P = (0.05, 0.02)
Y_FIELDS = (
    ("majority", "majority_invalid"),
    ("conservative", "openai_2024_conservative"),
)
USABLE_COVERAGE = 0.95
FLAG_HEAVY_FRAC = 0.70
N_BOOT_DEFAULT = 2000
N_BOOT_LAB = 400
CALIBRATED_ESTIMATORS = (
    "rogan-gladen-boot",
    "calibrated-fnr-fpr",
    "strat-judge-proportional",
    "strat-judge-flag-heavy",
)
ALL_ESTIMATORS = ("srs-hypergeometric",) + CALIBRATED_ESTIMATORS + ("ppi++-judge",)


@dataclass(frozen=True)
class JudgeEstimate:
    p_hat: float
    ucb95: float
    method: str
    sens: float | None
    spec: float | None
    fpr: float | None
    fnr: float | None
    n_sampled: int
    n_population: int
    n_boot: int = 0
    details: dict = field(default_factory=dict)


def _clip01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _rng(seed: str) -> random.Random:
    digest = hashlib.sha256(seed.encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def _binomial(rng: random.Random, n: int, p: float) -> int:
    n = int(n)
    if n <= 0:
        return 0
    if p <= 0.0:
        return 0
    if p >= 1.0:
        return n
    mean = n * p
    nq = n - mean
    # Exact Bernoulli sum in the small-count regime; rounded normal
    # otherwise. The lab bootstrap spends most of its time here.
    if mean >= 10.0 and nq >= 10.0:
        x = int(round(rng.gauss(mean, math.sqrt(mean * (1.0 - p)))))
        if x < 0:
            return 0
        if x > n:
            return n
        return x
    return sum(1 for _ in range(n) if rng.random() < p)


def _quantile(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    ys = sorted(xs)
    i = p * (len(ys) - 1)
    lo = int(i)
    hi = min(lo + 1, len(ys) - 1)
    w = i - lo
    return ys[lo] * (1.0 - w) + ys[hi] * w


def clopper_pearson_lower(k: int, n: int, alpha: float = 0.05) -> float:
    """One-sided Clopper-Pearson lower bound for a binomial proportion.

    Equal to 1 - clopper_pearson_upper(n - k, n, alpha). k=0 returns 0.
    """
    if n <= 0:
        raise ValueError("n must be positive")
    if k < 0 or k > n:
        raise ValueError("k must be in [0, n]")
    if not 0 < alpha < 1:
        raise ValueError("alpha must be in (0, 1)")
    if k == 0:
        return 0.0
    return 1.0 - clopper_pearson_upper(n - k, n, alpha)


def rogan_gladen_point(prev_judge: float, sens: float, spec: float) -> float | None:
    """pi = (p_j - (1-spec)) / (sens + spec - 1). None if Youden <= 0."""

    den = float(sens) + float(spec) - 1.0
    if den <= 1e-12:
        return None
    return (float(prev_judge) - (1.0 - float(spec))) / den


def _pi_from_fpr_fnr(prev_judge: float, fpr: float, fnr: float) -> float:
    """Rogan-Gladen in (FPR, FNR) form. Denominator <= 0 yields 1 (vacuous)."""

    den = 1.0 - float(fpr) - float(fnr)
    if den <= 1e-12:
        return 1.0
    return _clip01((float(prev_judge) - float(fpr)) / den)


def rogan_gladen(
    prev_judge: float,
    sens: float,
    spec: float,
    *,
    alpha: float = 0.05,
    n_boot: int = N_BOOT_DEFAULT,
    n_judge: int | None = None,
    n_sens: int | None = None,
    n_spec: int | None = None,
    seed: str | None = None,
) -> JudgeEstimate:
    """Rogan-Gladen prevalence point and one-sided UCB.

    Point: (prev_judge - (1-spec)) / (sens + spec - 1).

    One-sided (1-alpha) UCB is the (1-alpha) quantile of a parametric
    bootstrap: Se* ~ Bin(n_sens, sens)/n_sens, Sp* ~ Bin(n_spec, spec)/n_spec,
    and if n_judge is set, p_j* ~ Bin(n_judge, prev_judge)/n_judge. Draws with
    Youden* <= 0 are scored as 1. If n_sens or n_spec is omitted, that rate is
    treated as known. Census judge labels: omit n_judge (p_j fixed).
    """
    if not 0 < alpha < 1:
        raise ValueError("alpha must be in (0, 1)")
    point = rogan_gladen_point(prev_judge, sens, spec)
    p_hat = _clip01(point) if point is not None else 1.0
    fpr = 1.0 - float(spec)
    fnr = 1.0 - float(sens)
    if n_sens is not None and int(n_sens) <= 0:
        return JudgeEstimate(
            p_hat=p_hat,
            ucb95=1.0,
            method="rogan-gladen-boot",
            sens=float(sens),
            spec=float(spec),
            fpr=fpr,
            fnr=fnr,
            n_sampled=int(n_sens or 0) + int(n_spec or 0),
            n_population=int(n_judge or 0),
            n_boot=0,
            details={"reason": "n_sens<=0; Se unidentified"},
        )
    if n_spec is not None and int(n_spec) <= 0:
        return JudgeEstimate(
            p_hat=p_hat,
            ucb95=1.0,
            method="rogan-gladen-boot",
            sens=float(sens),
            spec=float(spec),
            fpr=fpr,
            fnr=fnr,
            n_sampled=int(n_sens or 0) + int(n_spec or 0),
            n_population=int(n_judge or 0),
            n_boot=0,
            details={"reason": "n_spec<=0; Sp unidentified"},
        )
    if n_boot <= 0 or (n_sens is None and n_spec is None and n_judge is None):
        ucb = p_hat if point is not None else 1.0
        return JudgeEstimate(
            p_hat=p_hat,
            ucb95=ucb,
            method="rogan-gladen-oracle" if point is not None else "rogan-gladen-undefined",
            sens=float(sens),
            spec=float(spec),
            fpr=fpr,
            fnr=fnr,
            n_sampled=int(n_sens or 0) + int(n_spec or 0),
            n_population=int(n_judge or 0),
            n_boot=0,
            details={"youden": float(sens) + float(spec) - 1.0},
        )
    rng = _rng(seed or "rogan-gladen")
    draws: list[float] = []
    for _ in range(n_boot):
        se_s = float(sens)
        sp_s = float(spec)
        pj_s = float(prev_judge)
        if n_sens is not None:
            se_s = _binomial(rng, int(n_sens), float(sens)) / float(n_sens)
        if n_spec is not None:
            sp_s = _binomial(rng, int(n_spec), float(spec)) / float(n_spec)
        if n_judge is not None and int(n_judge) > 0:
            pj_s = _binomial(rng, int(n_judge), float(prev_judge)) / float(n_judge)
        star = rogan_gladen_point(pj_s, se_s, sp_s)
        draws.append(1.0 if star is None else _clip01(star))
    ucb = _quantile(draws, 1.0 - alpha)
    if ucb is None:
        ucb = 1.0
    return JudgeEstimate(
        p_hat=p_hat,
        ucb95=_clip01(ucb),
        method="rogan-gladen-boot",
        sens=float(sens),
        spec=float(spec),
        fpr=fpr,
        fnr=fnr,
        n_sampled=int(n_sens or 0) + int(n_spec or 0),
        n_population=int(n_judge or 0),
        n_boot=n_boot,
        details={"youden": float(sens) + float(spec) - 1.0},
    )


def calibrated_prevalence_ucb(
    judge_labels_pop: list[int],
    human_labels_cal: list[int],
    judge_labels_cal: list[int],
    alpha: float = 0.05,
) -> JudgeEstimate:
    """NbV-style finite-population UCB from a judge census plus human subsample.

    Derivation
    ----------
    Let Y_i be true invalidity, J_i the binary judge label, N the population
    size, pi = mean(Y). The judge is observed on every unit, so
    p_j = mean(J) is known. With FPR = P(J=1|Y=0) and FNR = P(J=0|Y=1),

        p_j = pi * (1 - FNR) + (1 - pi) * FPR
        pi  = (p_j - FPR) / (1 - FPR - FNR)

    provided Youden = 1 - FPR - FNR > 0. Humans label an SRS of size m.
    Among the m0 calibration valids, fp ~ Binomial(m0, FPR); among the m1
    calibration invalids, fn ~ Binomial(m1, FNR). (Binomial, not
    hypergeometric, as specified; this is slightly conservative for a
    finite lot.)

    Sign of the map: for Youden > 0 and p_j >= FPR (always true in the
    population), dpi/dFNR >= 0. dpi/dFPR has the sign of (p_j + FNR - 1)
    and is typically negative. A conservative one-sided UCB therefore uses
    an *upper* bound on FNR and the worse endpoint of an FPR interval.

    Alpha split (Bonferroni): FNR gets a one-sided CP upper at alpha/2.
    FPR gets a two-sided CP interval with total mass alpha/2 (each tail
    alpha/4). Evaluate pi at (FPR_lo, FNR_hi) and (FPR_hi, FNR_hi); the
    UCB is the max, or 1 if a corner has Youden <= 0. If m0=0 or m1=0 a
    rate is unidentified and the UCB is 1.

    This is not a hypothesis test from Feng et al. (NbV 2601.20913); it is
    the finite-population prevalence analogue: judge census, Se/Sp
    calibrated on m humans, exact binomial rate bounds, union bound.
    """
    if not 0 < alpha < 1:
        raise ValueError("alpha must be in (0, 1)")
    if len(human_labels_cal) != len(judge_labels_cal):
        raise ValueError("human_labels_cal and judge_labels_cal must align")
    if not judge_labels_pop:
        raise ValueError("judge_labels_pop must be nonempty")
    n_pop = len(judge_labels_pop)
    m = len(human_labels_cal)
    p_j = _mean([float(v) for v in judge_labels_pop])
    m0 = m1 = fp = fn = 0
    for y, j in zip(human_labels_cal, judge_labels_cal):
        yi = int(y)
        ji = int(j)
        if yi == 0:
            m0 += 1
            if ji == 1:
                fp += 1
        else:
            m1 += 1
            if ji == 0:
                fn += 1
    fpr_hat = (fp / m0) if m0 else None
    fnr_hat = (fn / m1) if m1 else None
    sens_hat = (1.0 - fnr_hat) if fnr_hat is not None else None
    spec_hat = (1.0 - fpr_hat) if fpr_hat is not None else None
    if fpr_hat is not None and fnr_hat is not None:
        p_hat = _pi_from_fpr_fnr(p_j, fpr_hat, fnr_hat)
    else:
        p_hat = _mean([float(v) for v in human_labels_cal])
    details = {
        "p_j": p_j,
        "m": m,
        "m0": m0,
        "m1": m1,
        "fp": fp,
        "fn": fn,
        "alpha_fnr": alpha / 2.0,
        "alpha_fpr_tail": alpha / 4.0,
    }
    if m0 <= 0 or m1 <= 0:
        return JudgeEstimate(
            p_hat=_clip01(p_hat),
            ucb95=1.0,
            method="calibrated-fnr-fpr",
            sens=sens_hat,
            spec=spec_hat,
            fpr=fpr_hat,
            fnr=fnr_hat,
            n_sampled=m,
            n_population=n_pop,
            details={**details, "reason": "FPR or FNR unidentified"},
        )
    fnr_hi = clopper_pearson_upper(fn, m1, alpha / 2.0)
    fpr_lo = clopper_pearson_lower(fp, m0, alpha / 4.0)
    fpr_hi = clopper_pearson_upper(fp, m0, alpha / 4.0)
    u1 = _pi_from_fpr_fnr(p_j, fpr_lo, fnr_hi)
    u2 = _pi_from_fpr_fnr(p_j, fpr_hi, fnr_hi)
    ucb = max(u1, u2)
    details.update(
        {
            "fnr_hi": fnr_hi,
            "fpr_lo": fpr_lo,
            "fpr_hi": fpr_hi,
            "ucb_at_fpr_lo": u1,
            "ucb_at_fpr_hi": u2,
        }
    )
    return JudgeEstimate(
        p_hat=_clip01(p_hat),
        ucb95=_clip01(ucb),
        method="calibrated-fnr-fpr",
        sens=sens_hat,
        spec=spec_hat,
        fpr=fpr_hat,
        fnr=fnr_hat,
        n_sampled=m,
        n_population=n_pop,
        details=details,
    )


def ppi_with_judge(
    y_labeled: list[int] | list[float],
    p_invalid_labeled: list[float],
    p_invalid_population: list[float],
    alpha: float = 0.05,
) -> AssistedEstimate:
    """PPI++ with the judge probability p_invalid as the auxiliary."""

    est = ppi_mean_ucb(
        y_labeled, p_invalid_labeled, p_invalid_population, alpha=alpha
    )
    method = "ppi++-judge" if est.method == "ppi++-normal" else est.method + "-judge"
    return AssistedEstimate(
        p_hat=est.p_hat,
        ucb95=est.ucb95,
        method=method,
        lam=est.lam,
        n_effective=est.n_effective,
        se=est.se,
        n_sampled=est.n_sampled,
        n_population=est.n_population,
    )


def stratified_by_judge_ucb(
    y_flagged: list[int],
    y_unflagged: list[int],
    n_flagged_pop: int,
    n_unflagged_pop: int,
    alpha: float = 0.05,
) -> AssistedEstimate:
    """Design-based UCB: stratify the population by the binary judge.

    Humans are sampled inside each stratum (flagged / not flagged). Each
    stratum gets a one-sided Clopper-Pearson bound at alpha/2 (Bonferroni).
    The population UCB is the N_h-weighted sum. An empty sample of a
    nonempty population stratum contributes UCB_h = 1. Does not trust the
    judge: J only defines strata.
    """
    est = poststrat_exact_ucb(
        [y_flagged, y_unflagged],
        [int(n_flagged_pop), int(n_unflagged_pop)],
        alpha=alpha,
    )
    return AssistedEstimate(
        p_hat=est.p_hat,
        ucb95=est.ucb95,
        method="stratified-judge-cp-bonferroni",
        lam=est.lam,
        n_effective=est.n_effective,
        se=est.se,
        n_sampled=est.n_sampled,
        n_population=est.n_population,
    )


def allocate_judge_strata(
    n: int,
    n_unflagged_pop: int,
    n_flagged_pop: int,
    mode: str,
    flag_frac: float = FLAG_HEAVY_FRAC,
) -> tuple[int, int]:
    """Return (n_unflagged, n_flagged). mode is proportional or flag-heavy."""

    n0, n1 = int(n_unflagged_pop), int(n_flagged_pop)
    n = min(int(n), n0 + n1)
    if n <= 0 or n0 + n1 <= 0:
        return 0, 0
    if mode == "proportional":
        take1 = int(round(n * n1 / (n0 + n1))) if (n0 + n1) else 0
    elif mode == "flag-heavy":
        take1 = int(round(n * float(flag_frac)))
    else:
        raise ValueError(f"unknown allocation {mode}")
    take1 = max(0, min(n1, take1))
    take0 = n - take1
    if take0 > n0:
        extra = take0 - n0
        take0 = n0
        take1 = min(n1, take1 + extra)
    if take1 > n1:
        extra = take1 - n1
        take1 = n1
        take0 = min(n0, take0 + extra)
    leftover = n - take0 - take1
    if leftover > 0:
        room1 = n1 - take1
        add1 = min(room1, leftover)
        take1 += add1
        leftover -= add1
        take0 += min(n0 - take0, leftover)
    if n >= 2:
        if n1 > 0 and take1 == 0 and take0 > 1:
            take1, take0 = 1, take0 - 1
        if n0 > 0 and take0 == 0 and take1 > 1:
            take0, take1 = 1, take1 - 1
    return take0, take1


def _thin_idx(y: list[int], target_p: float, rng: random.Random) -> tuple[list[int], dict]:
    valid = [i for i, yi in enumerate(y) if yi == 0]
    invalid = [i for i, yi in enumerate(y) if yi == 1]
    if not valid:
        idx = list(range(len(y)))
        return idx, {"method": "no valids; kept full population", "target_p": target_p}
    n_inv = int(round(target_p * len(valid) / max(1.0 - target_p, 1e-9)))
    n_inv = max(1, min(n_inv, len(invalid)))
    keep_inv = rng.sample(invalid, n_inv)
    idx = sorted(valid + keep_inv)
    return idx, {
        "method": (
            "keep all valids; subsample invalids without replacement; "
            "retain each unit's real judge p_invalid and model_material"
        ),
        "n_valid_kept": len(valid),
        "n_invalid_available": len(invalid),
        "n_invalid_kept": n_inv,
        "target_p": target_p,
    }


def load_audit_rows(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("s") is None or rec.get("p_invalid") is None:
                continue
            if rec.get("majority_invalid") is None:
                continue
            if rec.get("model_material") is None:
                rec["model_material"] = int(
                    int(rec.get("underspecified") or 0) >= 2
                    or int(rec.get("false_negative") or 0) >= 2
                    or int(rec.get("other_major_issue") or 0) >= 1
                )
            rows.append(rec)
    rows.sort(key=lambda r: r["task_id"])
    return rows


def build_populations(rows: list[dict], seed: str) -> list[dict]:
    pops: list[dict] = []
    f_all = [float(r["p_invalid"]) for r in rows]
    j_all = [int(r["model_material"]) for r in rows]
    ids = [r["task_id"] for r in rows]
    for y_name, field in Y_FIELDS:
        y_all = [int(r[field] or 0) for r in rows]
        pops.append(
            {
                "pop_id": f"full-{y_name}",
                "y_name": y_name,
                "kind": "full",
                "N": len(y_all),
                "true_p": _mean([float(v) for v in y_all]),
                "auroc": auroc_binary(y_all, f_all),
                "y": y_all,
                "f": f_all,
                "j": j_all,
                "task_ids": ids,
                "construction": {"method": "full 1699 with real judge outputs"},
            }
        )
        for tp in THIN_P:
            rng = _rng(f"{seed}:thin:{y_name}:{tp}")
            idx, how = _thin_idx(y_all, tp, rng)
            yt = [y_all[i] for i in idx]
            ft = [f_all[i] for i in idx]
            jt = [j_all[i] for i in idx]
            idt = [ids[i] for i in idx]
            tag = f"{tp:.2f}".replace("0.", "p")
            pops.append(
                {
                    "pop_id": f"thin-{tag}-{y_name}",
                    "y_name": y_name,
                    "kind": "thinned",
                    "N": len(yt),
                    "true_p": _mean([float(v) for v in yt]),
                    "auroc": auroc_binary(yt, ft),
                    "y": yt,
                    "f": ft,
                    "j": jt,
                    "task_ids": idt,
                    "construction": how,
                }
            )
    return pops


def _sens_spec_from_sample(y: list[int], j: list[int]) -> tuple[float | None, float | None, int, int]:
    tp = fn = tn = fp = 0
    for yi, ji in zip(y, j):
        if yi == 1:
            if ji == 1:
                tp += 1
            else:
                fn += 1
        else:
            if ji == 1:
                fp += 1
            else:
                tn += 1
    n_pos = tp + fn
    n_neg = tn + fp
    se = (tp / n_pos) if n_pos else None
    sp = (tn / n_neg) if n_neg else None
    return se, sp, n_pos, n_neg


def simulate_cell(
    y: list[int],
    j: list[int],
    f: list[float],
    n: int,
    reps: int,
    seed: str,
    *,
    alpha: float = 0.05,
    n_boot: int = N_BOOT_LAB,
    eps_grid: tuple[float, ...] = EPS_GRID,
) -> list[dict]:
    """SRS for SRS-CP, RG, calibrated, PPI; two allocations for stratified."""

    N = len(y)
    n = min(n, N)
    idx0 = [i for i, ji in enumerate(j) if int(ji) == 0]
    idx1 = [i for i, ji in enumerate(j) if int(ji) == 1]
    n0_pop, n1_pop = len(idx0), len(idx1)
    p_j = (n1_pop / N) if N else 0.0
    rng = _rng(seed)
    names = ALL_ESTIMATORS
    acc = {name: {"p": [], "u": []} for name in names}
    hg_cache: dict[tuple[int, int, int], tuple[float, float]] = {}

    def hg(k: int, nn: int) -> tuple[float, float]:
        key = (k, nn, N)
        if key not in hg_cache:
            est = srs_estimate(k, nn, N, alpha)
            hg_cache[key] = (est.p_hat, est.ucb95)
        return hg_cache[key]

    for r in range(reps):
        srs_idx = rng.sample(range(N), n)
        y_s = [y[i] for i in srs_idx]
        j_s = [j[i] for i in srs_idx]
        f_s = [f[i] for i in srs_idx]
        k = int(sum(y_s))
        p_srs, u_srs = hg(k, n)
        acc["srs-hypergeometric"]["p"].append(p_srs)
        acc["srs-hypergeometric"]["u"].append(u_srs)

        se, sp, n_pos, n_neg = _sens_spec_from_sample(y_s, j_s)
        if se is None or sp is None:
            acc["rogan-gladen-boot"]["p"].append(p_srs)
            acc["rogan-gladen-boot"]["u"].append(1.0)
        else:
            rg = rogan_gladen(
                p_j,
                se,
                sp,
                alpha=alpha,
                n_boot=n_boot,
                n_sens=n_pos,
                n_spec=n_neg,
                seed=f"{seed}:rg:{r}",
            )
            acc["rogan-gladen-boot"]["p"].append(rg.p_hat)
            acc["rogan-gladen-boot"]["u"].append(rg.ucb95)

        cal = calibrated_prevalence_ucb(j, y_s, j_s, alpha=alpha)
        acc["calibrated-fnr-fpr"]["p"].append(cal.p_hat)
        acc["calibrated-fnr-fpr"]["u"].append(cal.ucb95)

        ppi = ppi_with_judge(y_s, f_s, f, alpha=alpha)
        acc["ppi++-judge"]["p"].append(ppi.p_hat)
        acc["ppi++-judge"]["u"].append(ppi.ucb95)

        for mode, est_name in (
            ("proportional", "strat-judge-proportional"),
            ("flag-heavy", "strat-judge-flag-heavy"),
        ):
            a0, a1 = allocate_judge_strata(n, n0_pop, n1_pop, mode)
            y0 = [y[i] for i in rng.sample(idx0, a0)] if a0 else []
            y1 = [y[i] for i in rng.sample(idx1, a1)] if a1 else []
            st = stratified_by_judge_ucb(y1, y0, n1_pop, n0_pop, alpha=alpha)
            acc[est_name]["p"].append(st.p_hat)
            acc[est_name]["u"].append(st.ucb95)

    true_p = sum(y) / N if N else 0.0
    rows = []
    for name in names:
        us = acc[name]["u"]
        ps = acc[name]["p"]
        mean_u = sum(us) / reps
        mean_p = sum(ps) / reps
        hits = sum(1 for u in us if true_p <= u + 1e-12)
        certify = {str(eps): sum(1 for u in us if u < eps) / reps for eps in eps_grid}
        rows.append(
            {
                "estimator": name,
                "n": n,
                "N": N,
                "replicates": reps,
                "true_p": true_p,
                "mean_p_hat": mean_p,
                "mean_ucb": mean_u,
                "excess_width": mean_u - true_p,
                "coverage": hits / reps,
                "usable": (hits / reps) >= USABLE_COVERAGE,
                "p_certify": certify,
                "p_j": p_j,
                "n_flagged": n1_pop,
                "n_unflagged": n0_pop,
            }
        )
    return rows


def _savings_table(cells: list[dict], n_grid: tuple[int, ...]) -> list[dict]:
    by: dict[tuple[str, str], dict[int, dict]] = {}
    for c in cells:
        by.setdefault((c["pop_id"], c["estimator"]), {})[c["n"]] = c
    out = []
    pop_ids = sorted({c["pop_id"] for c in cells})
    for pop_id in pop_ids:
        true_p = next(c["true_p"] for c in cells if c["pop_id"] == pop_id)
        for eps in EPS_GRID:
            row: dict = {"pop_id": pop_id, "true_p": true_p, "eps": eps, "n_valid": {}, "n_raw": {}}
            for est in ALL_ESTIMATORS:
                grid = by.get((pop_id, est), {})
                n_raw = n_valid = None
                for n in n_grid:
                    c = grid.get(n)
                    if c is None:
                        continue
                    if n_raw is None and c["mean_ucb"] < eps:
                        n_raw = n
                    if n_valid is None and c["mean_ucb"] < eps and c["usable"]:
                        n_valid = n
                row["n_raw"][est] = n_raw
                row["n_valid"][est] = n_valid
            srs = row["n_valid"].get("srs-hypergeometric")
            ratios = {}
            for est in ALL_ESTIMATORS:
                other = row["n_valid"].get(est)
                ratios[est] = (srs / other) if (srs and other) else None
            row["ratio_n_srs_n_est_valid"] = ratios
            out.append(row)
    return out


def evaluate_predicates(report: dict) -> dict:
    """Apply J1/J2/J3. Predicates were frozen before the lab ran."""

    auroc_maj = report["meta"].get("auroc_p_invalid_majority")
    j1 = bool(auroc_maj is not None and auroc_maj >= 0.80)
    cells = report["cells"]

    def cell(pop_id: str, n: int, est: str) -> dict | None:
        for c in cells:
            if c["pop_id"] == pop_id and c["n"] == n and c["estimator"] == est:
                return c
        return None

    j2_hits = []
    for pop_id in ("thin-p02-majority", "thin-p02-conservative"):
        srs = cell(pop_id, 100, "srs-hypergeometric")
        if srs is None:
            continue
        for est in CALIBRATED_ESTIMATORS:
            c = cell(pop_id, 100, est)
            if c is None:
                continue
            if c["coverage"] >= USABLE_COVERAGE and c["mean_ucb"] < srs["mean_ucb"]:
                j2_hits.append(
                    {
                        "pop_id": pop_id,
                        "estimator": est,
                        "coverage": c["coverage"],
                        "mean_ucb": c["mean_ucb"],
                        "srs_mean_ucb": srs["mean_ucb"],
                    }
                )
    j2 = bool(j2_hits)

    j3_hits = []
    savings = report.get("savings") or []
    for pop_id in ("thin-p02-majority", "thin-p02-conservative"):
        row = next((s for s in savings if s["pop_id"] == pop_id and s["eps"] == 0.05), None)
        if row is None:
            continue
        n_srs = row["n_valid"].get("srs-hypergeometric")
        for est in ALL_ESTIMATORS:
            if est == "srs-hypergeometric":
                continue
            n_est = row["n_valid"].get(est)
            if n_est is None:
                continue
            if n_srs is None:
                # SRS never reached UCB < 0.05 on the grid; half of >200 is 100.
                if n_est <= 100:
                    j3_hits.append(
                        {
                            "pop_id": pop_id,
                            "estimator": est,
                            "n_est": n_est,
                            "n_srs": None,
                            "ratio": None,
                        }
                    )
            elif n_srs / n_est >= 2.0 - 1e-12:
                j3_hits.append(
                    {
                        "pop_id": pop_id,
                        "estimator": est,
                        "n_est": n_est,
                        "n_srs": n_srs,
                        "ratio": n_srs / n_est,
                    }
                )
    j3 = bool(j3_hits)
    return {
        "J1": {
            "text": FROZEN_PREDICATES["J1"],
            "pass": j1,
            "auroc_p_invalid_majority": auroc_maj,
            "threshold": 0.80,
        },
        "J2": {
            "text": FROZEN_PREDICATES["J2"],
            "pass": j2,
            "hits": j2_hits,
        },
        "J3": {
            "text": FROZEN_PREDICATES["J3"],
            "pass": j3,
            "hits": j3_hits,
        },
        "all_pass": bool(j1 and j2 and j3),
        "written_before_computing": True,
    }


def run_judge_lab(
    gold: Path,
    *,
    replicates: int = 2000,
    seed: str = "judge-bound-lab-v0",
    n_grid: tuple[int, ...] = N_GRID,
    n_boot: int = N_BOOT_LAB,
    progress: bool = True,
) -> dict:
    rows = load_audit_rows(gold)
    if len(rows) < 1699:
        raise SystemExit(f"expected 1699 scored audit rows, got {len(rows)}")
    y_maj = [int(r["majority_invalid"] or 0) for r in rows]
    f_all = [float(r["p_invalid"]) for r in rows]
    auroc_maj = auroc_binary(y_maj, f_all)
    # Record J1 inputs before the Monte Carlo; do not peek at coverage cells.
    pops = build_populations(rows, seed)
    cells: list[dict] = []
    n_pops = len(pops)
    for pi, pop in enumerate(pops):
        if progress:
            print(
                f"[judge-lab] {pi + 1}/{n_pops} {pop['pop_id']} "
                f"N={pop['N']} p={pop['true_p']:.4f} auroc={pop['auroc']}",
                file=sys.stderr,
            )
        for n in n_grid:
            nn = min(n, pop["N"])
            block = simulate_cell(
                pop["y"],
                pop["j"],
                pop["f"],
                nn,
                replicates,
                f"{seed}:main:{pop['pop_id']}:{n}",
                n_boot=n_boot,
            )
            for row in block:
                row["pop_id"] = pop["pop_id"]
                row["y_name"] = pop["y_name"]
                row["kind"] = pop["kind"]
                row["auroc"] = pop["auroc"]
                cells.append(row)
    savings = _savings_table(cells, n_grid)
    oc = []
    for c in cells:
        if c["kind"] != "thinned" or c["n"] not in OC_N_GRID:
            continue
        if not c["pop_id"].endswith("-majority") and not c["pop_id"].endswith(
            "-conservative"
        ):
            continue
        oc.append(
            {
                "pop_id": c["pop_id"],
                "estimator": c["estimator"],
                "n": c["n"],
                "true_p": c["true_p"],
                "coverage": c["coverage"],
                "mean_ucb": c["mean_ucb"],
                "p_certify_eps05": c["p_certify"].get("0.05"),
                "usable": c["usable"],
            }
        )
    pop_meta = [{k: v for k, v in p.items() if k not in ("y", "f", "j", "task_ids")} for p in pops]
    report = {
        "meta": {
            "seed": seed,
            "replicates": replicates,
            "n_grid": list(n_grid),
            "eps_grid": list(EPS_GRID),
            "alpha": 0.05,
            "n_boot_rg": n_boot,
            "n_joined": len(rows),
            "auroc_p_invalid_majority": auroc_maj,
            "usable_coverage_threshold": USABLE_COVERAGE,
            "flag_heavy_frac": FLAG_HEAVY_FRAC,
            "frozen_predicate_text": FROZEN_PREDICATES,
            "notes": (
                "SRS-CP is the release baseline. Rogan-Gladen uses a parametric "
                "bootstrap UCB. calibrated-fnr-fpr is the Bonferroni CP rectangle "
                "on FPR/FNR. Stratified-by-judge is design-based CP. PPI++ uses "
                "the judge p_invalid as auxiliary (normal UCB)."
            ),
        },
        "populations": pop_meta,
        "cells": cells,
        "savings": savings,
        "operating_characteristic": oc,
    }
    report["frozen_predicates"] = evaluate_predicates(report)
    return report


def compact_summary(report: dict) -> dict:
    keep_cell = (
        "pop_id",
        "estimator",
        "n",
        "N",
        "true_p",
        "mean_p_hat",
        "mean_ucb",
        "excess_width",
        "coverage",
        "usable",
        "p_certify",
        "auroc",
        "kind",
        "y_name",
        "p_j",
    )
    return {
        "meta": report["meta"],
        "populations": report["populations"],
        "coverage": [{k: c[k] for k in keep_cell if k in c} for c in report["cells"]],
        "savings": report["savings"],
        "operating_characteristic": report["operating_characteristic"],
        "frozen_predicates": report["frozen_predicates"],
    }


def _fmt_table(headers: list[str], rows: list[list[object]]) -> str:
    srows = [headers] + [
        [
            ""
            if x is None
            else f"{x:.4f}"
            if isinstance(x, float)
            else str(x)
            for x in r
        ]
        for r in rows
    ]
    widths = [max(len(srows[i][j]) for i in range(len(srows))) for j in range(len(headers))]
    lines = []
    for i, r in enumerate(srows):
        line = " | ".join(
            val.ljust(widths[j]) if j == 0 else val.rjust(widths[j])
            for j, val in enumerate(r)
        )
        lines.append(line)
        if i == 0:
            lines.append("-+-".join("-" * w for w in widths))
    return "\n".join(lines)


def format_key_tables(report: dict) -> str:
    chunks = []
    meta = report["meta"]
    pred = report.get("frozen_predicates") or {}
    chunks.append(
        f"judge-lab seed={meta['seed']} reps={meta['replicates']} "
        f"joined={meta['n_joined']} auroc_majority={meta['auroc_p_invalid_majority']}"
    )
    chunks.append("populations")
    chunks.append(
        _fmt_table(
            ["pop_id", "N", "true_p", "auroc"],
            [
                [p["pop_id"], p["N"], p["true_p"], p["auroc"]]
                for p in report["populations"]
            ],
        )
    )
    chunks.append("coverage (usable iff coverage >= 0.95)")
    cov_rows = []
    for c in report["cells"]:
        if c["n"] not in N_GRID:
            continue
        cov_rows.append(
            [
                c["pop_id"],
                c["n"],
                c["estimator"],
                c["coverage"],
                c["mean_ucb"],
                c["usable"],
            ]
        )
    chunks.append(
        _fmt_table(
            ["pop", "n", "est", "cover", "mean_ucb", "usable"],
            cov_rows,
        )
    )
    chunks.append("smallest n with mean UCB < eps AND coverage >= 0.95")
    sav_rows = []
    for s in report["savings"]:
        if s["eps"] not in EPS_GRID:
            continue
        nv = s["n_valid"]
        sav_rows.append(
            [
                s["pop_id"],
                s["eps"],
                nv.get("srs-hypergeometric"),
                nv.get("rogan-gladen-boot"),
                nv.get("calibrated-fnr-fpr"),
                nv.get("ppi++-judge"),
                nv.get("strat-judge-proportional"),
                nv.get("strat-judge-flag-heavy"),
            ]
        )
    chunks.append(
        _fmt_table(
            ["pop", "eps", "n_srs", "n_rg", "n_cal", "n_ppi", "n_prop", "n_heavy"],
            sav_rows,
        )
    )
    chunks.append("P(certify at eps=0.05) on p=0.02 populations")
    oc_rows = []
    for r in report.get("operating_characteristic") or []:
        if "p02" not in r["pop_id"]:
            continue
        if r["n"] not in OC_N_GRID:
            continue
        oc_rows.append(
            [
                r["pop_id"],
                r["n"],
                r["estimator"],
                r["true_p"],
                r["coverage"],
                r["mean_ucb"],
                r["p_certify_eps05"],
            ]
        )
    chunks.append(
        _fmt_table(
            ["pop", "n", "est", "true_p", "cover", "mean_ucb", "P_cert"],
            oc_rows,
        )
    )
    chunks.append("Frozen predicates")
    for key in ("J1", "J2", "J3"):
        block = pred.get(key) or {}
        chunks.append(
            f"  {key} {'PASS' if block.get('pass') else 'FAIL'}: {block.get('text')}"
        )
    chunks.append(f"all_pass={pred.get('all_pass')}")
    return "\n".join(chunks)


def main(argv: list[str] | None = None) -> int:
    gold = REPO_ROOT / "data/gold/swe_llm_audit_full.jsonl"
    out = REPO_ROOT / "data/gold/judge_bound_lab.json"
    summary_path = REPO_ROOT / "data/gold/judge_bound_lab.summary.json"
    if argv:
        # Keep the module runnable without argparse flags in the default path.
        pass
    if not gold.is_file():
        raise SystemExit(f"missing {gold}")
    report = run_judge_lab(gold)
    out.write_text(json.dumps(report) + "\n", encoding="utf-8")
    summary_path.write_text(
        json.dumps(compact_summary(report), indent=2) + "\n", encoding="utf-8"
    )
    print(format_key_tables(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Prediction-powered / model-assisted finite-population invalidity bounds.

The cheap OOF score is an auxiliary variable. Coverage comes from the
sampling design, not from model quality. PPI++ and the difference
estimator use a normal approximation that is anti-conservative when n
is small and p is near 0; post-stratified exact CP is the fallback.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path

from task_validation.sampling.estimators import (
    _z_one_sided,
    clopper_pearson_upper,
    srs_estimate,
)

N_GRID = (50, 100, 200, 300)
OC_N_GRID = (59, 100, 200, 300)
EPS_GRID = (0.05, 0.10, 0.20, 0.30)
THIN_P = (0.05, 0.02, 0.01)
Y_FIELDS = (
    ("conservative", "openai_2024_conservative"),
    ("majority", "majority_invalid"),
    ("unanimous", "unanimous_invalid"),
)
OOF_FIELD = "p_logistic"
N_BINS = 4
USABLE_COVERAGE = 0.95


@dataclass(frozen=True)
class AssistedEstimate:
    p_hat: float
    ucb95: float
    method: str
    lam: float
    n_effective: float
    se: float
    n_sampled: int
    n_population: int


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _var(xs: list[float], ddof: int = 1) -> float:
    n = len(xs)
    if n <= ddof:
        return 0.0
    m = _mean(xs)
    return sum((x - m) ** 2 for x in xs) / (n - ddof)


def _cov(xs: list[float], ys: list[float], ddof: int = 1) -> float:
    n = len(xs)
    if n != len(ys) or n <= ddof:
        return 0.0
    mx, my = _mean(xs), _mean(ys)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (n - ddof)


def _clip01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def _n_eff(var_y: float, var_hat: float, n: int, N: int) -> float:
    if var_hat <= 0.0:
        return float(N)
    if var_y <= 0.0:
        return float(n)
    return max(1.0, min(float(N), var_y / var_hat))


def auroc_binary(y: list[int], scores: list[float]) -> float | None:
    """Mann-Whitney AUROC with average ranks for ties. Stdlib only."""
    n_pos = sum(1 for v in y if v == 1)
    n_neg = len(y) - n_pos
    if n_pos == 0 or n_neg == 0:
        return None
    order = sorted(range(len(y)), key=lambda i: scores[i])
    rank_sum_pos = 0.0
    i = 0
    n = len(y)
    while i < n:
        j = i + 1
        while j < n and scores[order[j]] == scores[order[i]]:
            j += 1
        avg_rank = 0.5 * ((i + 1) + j)
        for k in range(i, j):
            if y[order[k]] == 1:
                rank_sum_pos += avg_rank
        i = j
    u = rank_sum_pos - n_pos * (n_pos + 1) / 2.0
    return u / (n_pos * n_neg)


def quantile_cuts(values: list[float], n_bins: int = N_BINS) -> list[float]:
    if n_bins < 1:
        raise ValueError("n_bins must be positive")
    xs = sorted(values)
    n = len(xs)
    if n == 0 or n_bins == 1:
        return []
    cuts = []
    for b in range(1, n_bins):
        i = min(n - 1, max(0, (b * n) // n_bins))
        cuts.append(xs[i])
    return cuts


def bin_of(v: float, cuts: list[float]) -> int:
    for i, c in enumerate(cuts):
        if v < c:
            return i
    return len(cuts)


def srs_cp_ucb(y_labeled: list[int], N: int, alpha: float = 0.05) -> AssistedEstimate:
    """Hypergeometric (n < N) or Clopper-Pearson (census) one-sided UCB."""
    n = len(y_labeled)
    if n <= 0:
        raise ValueError("labeled sample must be nonempty")
    k = int(sum(y_labeled))
    est = srs_estimate(k, n, N, alpha)
    return AssistedEstimate(
        p_hat=est.p_hat,
        ucb95=est.ucb95,
        method=est.method,
        lam=0.0,
        n_effective=float(n),
        se=max(0.0, est.ucb95 - est.p_hat),
        n_sampled=n,
        n_population=N,
    )


def _tune_lam_mean(
    y_labeled: list[float],
    f_labeled: list[float],
    f_population: list[float],
    *,
    power_tune: bool,
) -> float:
    n = len(y_labeled)
    N = len(f_population)
    cov = _cov(y_labeled, f_labeled, ddof=1)
    if power_tune:
        var_f = _var(f_population, ddof=1) if N > 1 else _var(f_labeled, ddof=1)
        if var_f <= 1e-18:
            return 0.0
        r = n / N if N else 0.0
        lam = cov / ((1.0 + r) * var_f)
    else:
        var_f = _var(f_labeled, ddof=1)
        if var_f <= 1e-18:
            return 0.0
        lam = cov / var_f
    if lam > 5.0:
        return 5.0
    if lam < -5.0:
        return -5.0
    return lam


def ppi_mean_ucb(
    y_labeled: list[int] | list[float],
    f_labeled: list[float],
    f_population: list[float],
    alpha: float = 0.05,
    lam: float | None = None,
) -> AssistedEstimate:
    """PPI++ mean (Angelopoulos, Duchi, Zrnic 2023).

    theta = lam * mean(f_pop) + mean(y_lab - lam * f_lab)

    Closed-form power-tuning for the mean:
    lam = Cov_n(y, f) / ((1 + n/N) Var_N(f)).

    One-sided normal UCB uses labeled residual variance plus the
    population-prediction term lam^2 Var(f_pop) / N. Not a release rule
    when n is small and p is near 0 (normal approximation).
    """
    n = len(y_labeled)
    N = len(f_population)
    if n == 0 or N == 0:
        raise ValueError("labeled sample and f_population must be nonempty")
    if n != len(f_labeled):
        raise ValueError("y_labeled and f_labeled must align")
    yf = [float(v) for v in y_labeled]
    if lam is None:
        lam_hat = _tune_lam_mean(yf, f_labeled, f_population, power_tune=True)
    else:
        lam_hat = float(lam)
    mean_f = _mean(f_population)
    resid = [yi - lam_hat * fi for yi, fi in zip(yf, f_labeled)]
    theta = lam_hat * mean_f + _mean(resid)
    z = _z_one_sided(alpha)
    if n < 2:
        fb = srs_cp_ucb([int(round(v)) for v in yf], N, alpha)
        return AssistedEstimate(
            p_hat=_clip01(theta),
            ucb95=fb.ucb95,
            method="ppi++-fallback-srs",
            lam=lam_hat,
            n_effective=float(n),
            se=fb.se,
            n_sampled=n,
            n_population=N,
        )
    var_rect = _var(resid, ddof=1) / n
    var_pred = (lam_hat**2) * _var(f_population, ddof=1) / N
    var_hat = max(0.0, var_rect + var_pred)
    se = math.sqrt(var_hat)
    ucb = _clip01(theta + z * se)
    return AssistedEstimate(
        p_hat=_clip01(theta),
        ucb95=ucb,
        method="ppi++-normal",
        lam=lam_hat,
        n_effective=_n_eff(_var(yf, ddof=1), var_hat, n, N),
        se=se,
        n_sampled=n,
        n_population=N,
    )


def difference_estimator_ucb(
    y_labeled: list[int] | list[float],
    f_labeled: list[float],
    f_population: list[float],
    alpha: float = 0.05,
    lam: float | None = None,
) -> AssistedEstimate:
    """Model-assisted difference / GREG mean with finite-population correction.

    theta = mean(y_lab) + lam * (mean(f_pop) - mean(f_lab))
    lam defaults to the sample regression coefficient Cov(y,f)/Var(f)
    (no PPI++ n/N shrinkage). Variance is (1-n/N) s_e^2 / n.
    """
    n = len(y_labeled)
    N = len(f_population)
    if n == 0 or N == 0:
        raise ValueError("labeled sample and f_population must be nonempty")
    if n != len(f_labeled):
        raise ValueError("y_labeled and f_labeled must align")
    yf = [float(v) for v in y_labeled]
    if lam is None:
        lam_hat = _tune_lam_mean(yf, f_labeled, f_population, power_tune=False)
    else:
        lam_hat = float(lam)
    mean_y = _mean(yf)
    mean_f_lab = _mean(f_labeled)
    mean_f_pop = _mean(f_population)
    theta = mean_y + lam_hat * (mean_f_pop - mean_f_lab)
    z = _z_one_sided(alpha)
    if n < 2 or n > N:
        fb = srs_cp_ucb([int(round(v)) for v in yf], N, alpha)
        return AssistedEstimate(
            p_hat=_clip01(theta),
            ucb95=fb.ucb95,
            method="difference-fallback-srs",
            lam=lam_hat,
            n_effective=float(n),
            se=fb.se,
            n_sampled=n,
            n_population=N,
        )
    resid = [yi - lam_hat * fi for yi, fi in zip(yf, f_labeled)]
    fpc = 1.0 - (n / N)
    # n-2 when the slope is estimated from the same sample (GREG).
    ddof = 2 if lam is None else 1
    var_e = _var(resid, ddof=ddof) if n > ddof else _var(resid, ddof=1)
    var_hat = fpc * var_e / n
    se = math.sqrt(max(0.0, var_hat))
    ucb = _clip01(theta + z * se)
    return AssistedEstimate(
        p_hat=_clip01(theta),
        ucb95=ucb,
        method="difference-greg-fpc",
        lam=lam_hat,
        n_effective=_n_eff(_var(yf, ddof=1), var_hat if var_hat > 0 else 1e-18, n, N),
        se=se,
        n_sampled=n,
        n_population=N,
    )


def poststrat_exact_ucb(
    y_labeled_by_stratum: list[list[int]],
    N_h: list[int],
    alpha: float = 0.05,
) -> AssistedEstimate:
    """Post-stratified exact CP UCB, Bonferroni across strata.

    Each stratum gets a one-sided Clopper-Pearson bound at alpha/H.
    The population UCB is the N_h-weighted sum. Empty sample strata
    contribute UCB_h = 1. Valid regardless of the score quality.
    """
    if len(y_labeled_by_stratum) != len(N_h):
        raise ValueError("y_labeled_by_stratum and N_h must align")
    N = sum(N_h)
    if N <= 0:
        raise ValueError("N_h must sum to a positive population size")
    H = sum(1 for nh in N_h if nh > 0)
    if H <= 0:
        raise ValueError("no nonempty population strata")
    alpha_h = alpha / H
    p_hat = 0.0
    ucb = 0.0
    n_total = 0
    k_total = 0
    for ys, Nh in zip(y_labeled_by_stratum, N_h):
        if Nh <= 0:
            continue
        w = Nh / N
        n_h = len(ys)
        n_total += n_h
        k_h = int(sum(ys))
        k_total += k_h
        if n_h <= 0:
            p_hat += w * 0.0
            ucb += w * 1.0
            continue
        if n_h > Nh:
            raise ValueError("stratum sample larger than stratum population")
        p_hat += w * (k_h / n_h)
        ucb += w * clopper_pearson_upper(k_h, n_h, alpha_h)
    return AssistedEstimate(
        p_hat=_clip01(p_hat),
        ucb95=_clip01(ucb),
        method="poststrat-cp-bonferroni",
        lam=0.0,
        n_effective=float(n_total),
        se=max(0.0, ucb - p_hat),
        n_sampled=n_total,
        n_population=N,
    )


def mix_scores_to_auroc(
    y: list[int],
    f: list[float],
    target: float,
    rng: random.Random,
    *,
    toward_label: bool,
) -> tuple[list[float], float | None, float]:
    """Mix f with uniform noise (degrade) or with Y (synthetic improve)."""
    n = len(y)
    if toward_label:
        extra = [float(yi) for yi in y]
    else:
        extra = [rng.random() for _ in range(n)]

    def mix(a: float) -> list[float]:
        return [(1.0 - a) * fi + a * ei for fi, ei in zip(f, extra)]

    lo, hi = 0.0, 1.0
    best_a = 0.0
    best = f
    best_au = auroc_binary(y, f)
    for _ in range(36):
        mid = 0.5 * (lo + hi)
        fm = mix(mid)
        au = auroc_binary(y, fm)
        if au is None:
            break
        best, best_a, best_au = fm, mid, au
        if toward_label:
            if au < target:
                lo = mid
            else:
                hi = mid
        else:
            if au > target:
                lo = mid
            else:
                hi = mid
    return best, best_au, best_a


def _rng(seed: str) -> random.Random:
    digest = hashlib.sha256(seed.encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def load_joined(gold: Path, targets: Path, oof: Path) -> list[dict]:
    oof_p: dict[str, float] = {}
    with oof.open(encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            oof_p[rec["task_id"]] = float(rec[OOF_FIELD])
    tgt: dict[str, dict] = {}
    with targets.open(encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            tgt[rec["task_id"]] = rec
    rows: list[dict] = []
    with gold.open(encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            tid = rec["task_id"]
            if tid not in oof_p or tid not in tgt:
                continue
            t = tgt[tid]
            rows.append(
                {
                    "task_id": tid,
                    "openai_2024_conservative": int(t["openai_2024_conservative"]),
                    "majority_invalid": int(t["majority_invalid"]),
                    "unanimous_invalid": int(t["unanimous_invalid"]),
                    "f": oof_p[tid],
                }
            )
    rows.sort(key=lambda r: r["task_id"])
    return rows


def _subset(y: list[int], f: list[float], idx: list[int]) -> tuple[list[int], list[float]]:
    return [y[i] for i in idx], [f[i] for i in idx]


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
            "retain each unit's OOF p_logistic"
        ),
        "n_valid_kept": len(valid),
        "n_invalid_available": len(invalid),
        "n_invalid_kept": n_inv,
        "target_p": target_p,
    }


def _low30_idx(f: list[float]) -> list[int]:
    order = sorted(range(len(f)), key=lambda i: (f[i], i))
    n_keep = max(1, int(0.3 * len(f)))
    return sorted(order[:n_keep])


def _pop_record(
    pop_id: str,
    y_name: str,
    kind: str,
    y: list[int],
    f: list[float],
    construction: dict,
    *,
    synthetic_scores: bool = False,
    auroc_target: float | None = None,
) -> dict:
    n = len(y)
    true_p = (sum(y) / n) if n else 0.0
    au = auroc_binary(y, f)
    rec = {
        "pop_id": pop_id,
        "y_name": y_name,
        "kind": kind,
        "N": n,
        "true_p": true_p,
        "auroc": au,
        "auroc_target": auroc_target,
        "synthetic_scores": synthetic_scores,
        "construction": construction,
        "y": y,
        "f": f,
    }
    return rec


def build_populations(rows: list[dict], seed: str) -> list[dict]:
    pops: list[dict] = []
    f_all = [float(r["f"]) for r in rows]
    for y_name, field in Y_FIELDS:
        y_all = [int(r[field]) for r in rows]
        pops.append(
            _pop_record(
                f"full-{y_name}",
                y_name,
                "full",
                y_all,
                f_all,
                {"method": "full 1699-row SWE-bench 2024 join", "n": len(rows)},
            )
        )
        idx30 = _low30_idx(f_all)
        y30, f30 = _subset(y_all, f_all, idx30)
        pops.append(
            _pop_record(
                f"low30-{y_name}",
                y_name,
                "low30",
                y30,
                f30,
                {
                    "method": "lowest 30% by OOF p_logistic (ties broken by index)",
                    "fraction": 0.3,
                    "n_source": len(rows),
                    "n_kept": len(idx30),
                },
            )
        )
        for tp in THIN_P:
            rng = _rng(f"{seed}:thin:{y_name}:{tp}")
            idx, how = _thin_idx(y_all, tp, rng)
            yt, ft = _subset(y_all, f_all, idx)
            tag = f"{tp:.2f}".replace("0.", "p")
            pops.append(
                _pop_record(
                    f"thin-{tag}-{y_name}",
                    y_name,
                    "thinned",
                    yt,
                    ft,
                    how,
                )
            )
    return pops


def simulate_cell(
    y: list[int],
    f: list[float],
    n: int,
    reps: int,
    seed: str,
    *,
    n_bins: int = N_BINS,
    alpha: float = 0.05,
    eps_grid: tuple[float, ...] = EPS_GRID,
) -> list[dict]:
    """SRS replicates for the four UCBs. Returns one row per estimator."""
    N = len(y)
    if n > N:
        n = N
    cuts = quantile_cuts(f, n_bins)
    H = len(cuts) + 1
    N_h = [0] * H
    for fi in f:
        N_h[bin_of(fi, cuts)] += 1
    rng = _rng(seed)
    names = ("srs-hypergeometric", "ppi++-normal", "difference-greg-fpc", "poststrat-cp-bonferroni")
    acc = {
        name: {"p": [], "u": [], "lam": [], "neff": []}
        for name in names
    }
    hg_cache: dict[tuple[int, int, int], float] = {}
    p_cache: dict[tuple[int, int, int], float] = {}
    cp_cache: dict[tuple[int, int, float], float] = {}

    def hg_ucb(k: int, nn: int) -> tuple[float, float]:
        key = (k, nn, N)
        if key not in p_cache:
            est = srs_estimate(k, nn, N, alpha)
            p_cache[key] = est.p_hat
            hg_cache[key] = est.ucb95
        return p_cache[key], hg_cache[key]

    def cp_cached(k: int, nn: int, a: float) -> float:
        key = (k, nn, round(a, 12))
        if key not in cp_cache:
            cp_cache[key] = clopper_pearson_upper(k, nn, a)
        return cp_cache[key]

    H_pos = sum(1 for nh in N_h if nh > 0)
    alpha_h = alpha / max(H_pos, 1)

    for _ in range(reps):
        idx = rng.sample(range(N), n)
        y_s = [y[i] for i in idx]
        f_s = [f[i] for i in idx]
        k = int(sum(y_s))
        p_srs, u_srs = hg_ucb(k, n)
        acc["srs-hypergeometric"]["p"].append(p_srs)
        acc["srs-hypergeometric"]["u"].append(u_srs)
        acc["srs-hypergeometric"]["lam"].append(0.0)
        acc["srs-hypergeometric"]["neff"].append(float(n))

        ppi = ppi_mean_ucb(y_s, f_s, f, alpha)
        acc["ppi++-normal"]["p"].append(ppi.p_hat)
        acc["ppi++-normal"]["u"].append(ppi.ucb95)
        acc["ppi++-normal"]["lam"].append(ppi.lam)
        acc["ppi++-normal"]["neff"].append(ppi.n_effective)

        dif = difference_estimator_ucb(y_s, f_s, f, alpha)
        acc["difference-greg-fpc"]["p"].append(dif.p_hat)
        acc["difference-greg-fpc"]["u"].append(dif.ucb95)
        acc["difference-greg-fpc"]["lam"].append(dif.lam)
        acc["difference-greg-fpc"]["neff"].append(dif.n_effective)

        by = [[] for _ in range(H)]
        for i in idx:
            by[bin_of(f[i], cuts)].append(y[i])
        p_ps = 0.0
        u_ps = 0.0
        for ys_h, Nh in zip(by, N_h):
            if Nh <= 0:
                continue
            w = Nh / N
            n_h = len(ys_h)
            if n_h <= 0:
                u_ps += w * 1.0
                continue
            k_h = int(sum(ys_h))
            p_ps += w * (k_h / n_h)
            u_ps += w * cp_cached(k_h, n_h, alpha_h)
        acc["poststrat-cp-bonferroni"]["p"].append(_clip01(p_ps))
        acc["poststrat-cp-bonferroni"]["u"].append(_clip01(u_ps))
        acc["poststrat-cp-bonferroni"]["lam"].append(0.0)
        acc["poststrat-cp-bonferroni"]["neff"].append(float(n))

    true_p = sum(y) / N
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
                "mean_lam": sum(acc[name]["lam"]) / reps,
                "mean_n_effective": sum(acc[name]["neff"]) / reps,
                "p_certify": certify,
            }
        )
    return rows


def _savings_table(cells: list[dict], pops: list[dict], n_grid: tuple[int, ...]) -> list[dict]:
    by: dict[tuple[str, str], dict[int, dict]] = {}
    pop_p = {p["pop_id"]: p["true_p"] for p in pops}
    for c in cells:
        by.setdefault((c["pop_id"], c["estimator"]), {})[c["n"]] = c
    estimators = (
        "srs-hypergeometric",
        "ppi++-normal",
        "difference-greg-fpc",
        "poststrat-cp-bonferroni",
    )
    out = []
    for pop_id in {c["pop_id"] for c in cells}:
        for eps in EPS_GRID:
            row = {
                "pop_id": pop_id,
                "true_p": pop_p.get(pop_id),
                "eps": eps,
            }
            ns_raw = {}
            ns_valid = {}
            for est in estimators:
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
                ns_raw[est] = n_raw
                ns_valid[est] = n_valid
            row["n_raw"] = ns_raw
            row["n_valid"] = ns_valid
            srs = ns_valid.get("srs-hypergeometric")
            ppi = ns_valid.get("ppi++-normal")
            dif = ns_valid.get("difference-greg-fpc")
            ratio_ppi = (srs / ppi) if (srs and ppi) else None
            ratio_dif = (srs / dif) if (srs and dif) else None
            row["ratio_n_srs_n_ppi_valid"] = ratio_ppi
            row["ratio_n_srs_n_diff_valid"] = ratio_dif
            srs_r = ns_raw.get("srs-hypergeometric")
            ppi_r = ns_raw.get("ppi++-normal")
            row["ratio_n_srs_n_ppi_raw"] = (srs_r / ppi_r) if (srs_r and ppi_r) else None
            out.append(row)
    out.sort(key=lambda r: (r["pop_id"], r["eps"]))
    return out


def _best_valid_name(cell_group: list[dict]) -> str | None:
    """Lowest mean UCB among estimators with coverage >= 0.95, excluding none."""
    valid = [c for c in cell_group if c["usable"]]
    if not valid:
        return None
    valid.sort(key=lambda c: (c["mean_ucb"], c["estimator"]))
    return valid[0]["estimator"]


def run_ppi_lab(
    gold: Path,
    targets: Path,
    oof: Path,
    *,
    replicates: int = 2000,
    seed: str = "ppi-lab-v0",
    n_grid: tuple[int, ...] = N_GRID,
    include_sweep: bool = True,
    include_oc: bool = True,
    progress: bool = True,
) -> dict:
    rows = load_joined(gold, targets, oof)
    pops = build_populations(rows, seed)
    y_cons = [int(r["openai_2024_conservative"]) for r in rows]
    f_all = [float(r["f"]) for r in rows]
    auroc_actual = auroc_binary(y_cons, f_all)

    cells: list[dict] = []
    n_pops = len(pops)
    for pi, pop in enumerate(pops):
        if progress:
            print(
                f"[ppi-lab] {pi + 1}/{n_pops} {pop['pop_id']} N={pop['N']} p={pop['true_p']:.4f}",
                file=sys.stderr,
            )
        for n in n_grid:
            nn = min(n, pop["N"])
            block = simulate_cell(
                pop["y"], pop["f"], nn, replicates, f"{seed}:main:{pop['pop_id']}:{n}"
            )
            for row in block:
                row["pop_id"] = pop["pop_id"]
                row["y_name"] = pop["y_name"]
                row["kind"] = pop["kind"]
                row["auroc"] = pop["auroc"]
                row["synthetic_scores"] = False
                cells.append(row)

    oc_cells: list[dict] = []
    if include_oc:
        extra_n = [n for n in OC_N_GRID if n not in n_grid]
        oc_pops = [p for p in pops if p["kind"] == "thinned" or p["kind"] == "low30"]
        if extra_n:
            if progress:
                print(f"[ppi-lab] OC extra n={extra_n} on {len(oc_pops)} pops", file=sys.stderr)
            for pop in oc_pops:
                for n in extra_n:
                    nn = min(n, pop["N"])
                    block = simulate_cell(
                        pop["y"], pop["f"], nn, replicates, f"{seed}:oc:{pop['pop_id']}:{n}"
                    )
                    for row in block:
                        row["pop_id"] = pop["pop_id"]
                        row["y_name"] = pop["y_name"]
                        row["kind"] = pop["kind"]
                        row["auroc"] = pop["auroc"]
                        row["synthetic_scores"] = False
                        oc_cells.append(row)

    sweep_cells: list[dict] = []
    sweep_pops_meta: list[dict] = []
    if include_sweep:
        base_specs = []
        for pop in pops:
            if pop["pop_id"] in ("full-conservative", "thin-p05-conservative"):
                base_specs.append(pop)
        targets_au = (
            (0.6, False, "noise"),
            (0.7, False, "actual"),
            (0.8, True, "synthetic-toward-label"),
            (0.9, True, "synthetic-toward-label"),
        )
        for base in base_specs:
            for target_au, toward, tag in targets_au:
                if tag == "actual":
                    f_use = list(base["f"])
                    au = auroc_binary(base["y"], f_use)
                    mix_a = 0.0
                    synthetic = False
                else:
                    rng = _rng(f"{seed}:mix:{base['pop_id']}:{target_au}:{tag}")
                    f_use, au, mix_a = mix_scores_to_auroc(
                        base["y"], base["f"], target_au, rng, toward_label=toward
                    )
                    synthetic = toward
                sp = _pop_record(
                    f"sweep-{base['pop_id']}-auroc{target_au:.1f}",
                    base["y_name"],
                    f"sweep-{base['kind']}",
                    list(base["y"]),
                    f_use,
                    {
                        "base_pop": base["pop_id"],
                        "mix": tag,
                        "mix_weight": mix_a,
                        "auroc_target": target_au,
                        "synthetic_scores": synthetic,
                        "note": (
                            "0.8/0.9 mix the OOF score toward the true label (synthetic)"
                            if synthetic
                            else "0.6 mixes OOF with Uniform(0,1); 0.7 is the real OOF score"
                        ),
                    },
                    synthetic_scores=synthetic,
                    auroc_target=target_au,
                )
                sweep_pops_meta.append({k: v for k, v in sp.items() if k not in ("y", "f")})
                if progress:
                    print(
                        f"[ppi-lab] sweep {sp['pop_id']} auroc={sp['auroc']}",
                        file=sys.stderr,
                    )
                for n in n_grid:
                    nn = min(n, sp["N"])
                    block = simulate_cell(
                        sp["y"], sp["f"], nn, replicates, f"{seed}:sweep:{sp['pop_id']}:{n}"
                    )
                    for row in block:
                        row["pop_id"] = sp["pop_id"]
                        row["y_name"] = sp["y_name"]
                        row["kind"] = sp["kind"]
                        row["auroc"] = sp["auroc"]
                        row["auroc_target"] = target_au
                        row["synthetic_scores"] = synthetic
                        row["base_pop"] = base["pop_id"]
                        sweep_cells.append(row)

    all_for_savings = cells + oc_cells
    savings = _savings_table(all_for_savings, pops, tuple(sorted(set(n_grid) | set(OC_N_GRID))))
    sweep_pops_as_pops = []
    for meta in sweep_pops_meta:
        sweep_pops_as_pops.append(
            {
                "pop_id": meta["pop_id"],
                "true_p": meta["true_p"],
                "y_name": meta["y_name"],
                "kind": meta["kind"],
            }
        )
    sweep_savings = _savings_table(sweep_cells, sweep_pops_as_pops, n_grid) if sweep_cells else []

    oc_table = []
    oc_source = cells + oc_cells
    by_pop_n: dict[tuple[str, int], list[dict]] = {}
    for c in oc_source:
        if c["n"] in OC_N_GRID:
            by_pop_n.setdefault((c["pop_id"], c["n"]), []).append(c)
    for (pop_id, n), grp in sorted(by_pop_n.items()):
        best = _best_valid_name(grp)
        srs = next(c for c in grp if c["estimator"] == "srs-hypergeometric")
        best_row = next((c for c in grp if c["estimator"] == best), None) if best else None
        oc_table.append(
            {
                "pop_id": pop_id,
                "n": n,
                "true_p": srs["true_p"],
                "p_certify_srs": srs["p_certify"].get("0.05"),
                "best_valid_estimator": best,
                "p_certify_best_valid": (
                    best_row["p_certify"].get("0.05") if best_row else None
                ),
                "coverage_srs": srs["coverage"],
                "coverage_best_valid": best_row["coverage"] if best_row else None,
                "mean_ucb_srs": srs["mean_ucb"],
                "mean_ucb_best_valid": best_row["mean_ucb"] if best_row else None,
            }
        )

    pop_meta = [{k: v for k, v in p.items() if k not in ("y", "f")} for p in pops]
    return {
        "meta": {
            "seed": seed,
            "replicates": replicates,
            "n_grid": list(n_grid),
            "oc_n_grid": list(OC_N_GRID),
            "eps_grid": list(EPS_GRID),
            "alpha": 0.05,
            "oof_field": OOF_FIELD,
            "n_joined": len(rows),
            "n_bins_poststrat": N_BINS,
            "auroc_actual_conservative": auroc_actual,
            "usable_coverage_threshold": USABLE_COVERAGE,
            "notes": (
                "PPI++ and difference use a normal UCB (anti-conservative at small n "
                "and p near 0). Poststrat-CP Bonferroni is the guaranteed-coverage "
                "fallback. 0.8/0.9 AUROC scores are synthetic (mix toward the label). "
                "An estimator is usable only if Monte Carlo coverage is >= 0.95."
            ),
        },
        "populations": pop_meta,
        "cells": cells,
        "oc_extra_cells": oc_cells,
        "savings": savings,
        "auroc_sweep_populations": sweep_pops_meta,
        "auroc_sweep_cells": sweep_cells,
        "auroc_sweep_savings": sweep_savings,
        "operating_characteristic": oc_table,
    }


def compact_summary(report: dict) -> dict:
    def slim_cell(c: dict) -> dict:
        keep = (
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
            "mean_lam",
            "mean_n_effective",
            "p_certify",
            "auroc",
            "auroc_target",
            "synthetic_scores",
            "kind",
            "y_name",
            "base_pop",
        )
        return {k: c[k] for k in keep if k in c}

    def slim_pop(p: dict) -> dict:
        keep = (
            "pop_id",
            "y_name",
            "kind",
            "N",
            "true_p",
            "auroc",
            "auroc_target",
            "synthetic_scores",
            "construction",
        )
        return {k: p[k] for k in keep if k in p}

    return {
        "meta": report["meta"],
        "populations": [slim_pop(p) for p in report["populations"]],
        "coverage": [slim_cell(c) for c in report["cells"]],
        "savings": report["savings"],
        "auroc_sweep_populations": report["auroc_sweep_populations"],
        "auroc_sweep_coverage": [slim_cell(c) for c in report["auroc_sweep_cells"]],
        "auroc_sweep_savings": report["auroc_sweep_savings"],
        "operating_characteristic": report["operating_characteristic"],
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
        line = " | ".join(val.ljust(widths[j]) if j == 0 else val.rjust(widths[j]) for j, val in enumerate(r))
        lines.append(line)
        if i == 0:
            lines.append("-+-".join("-" * w for w in widths))
    return "\n".join(lines)


def format_key_tables(report: dict) -> str:
    """Compact text tables for the CLI and the closing printout."""
    chunks = []
    meta = report["meta"]
    chunks.append(
        f"ppi-lab seed={meta['seed']} reps={meta['replicates']} "
        f"joined={meta['n_joined']} auroc_actual={meta['auroc_actual_conservative']:.3f}"
    )
    pops = report["populations"]
    chunks.append("populations")
    chunks.append(
        _fmt_table(
            ["pop_id", "N", "true_p", "auroc"],
            [[p["pop_id"], p["N"], p["true_p"], p["auroc"]] for p in pops],
        )
    )

    focus = [c for c in report["cells"] if c["kind"] in ("thinned", "full", "low30")]
    # Coverage at n=100, 300 for thinned conservative + full conservative + low30 unanimous
    interesting = {
        "full-conservative",
        "full-majority",
        "full-unanimous",
        "low30-conservative",
        "low30-majority",
        "low30-unanimous",
        "thin-p05-conservative",
        "thin-p02-conservative",
        "thin-p01-conservative",
    }
    cov_rows = []
    for c in focus:
        if c["pop_id"] not in interesting:
            continue
        if c["n"] not in (50, 100, 200, 300):
            continue
        cov_rows.append(
            [
                c["pop_id"],
                c["n"],
                c["estimator"].replace("-hypergeometric", "").replace("-normal", "").replace("-greg-fpc", "").replace("-cp-bonferroni", ""),
                c["coverage"],
                c["mean_ucb"],
                c["excess_width"],
                c["usable"],
            ]
        )
    chunks.append("coverage (usable iff coverage >= 0.95)")
    chunks.append(
        _fmt_table(
            ["pop", "n", "est", "cover", "mean_ucb", "excess", "usable"],
            cov_rows,
        )
    )

    sav = [
        s
        for s in report["savings"]
        if s["pop_id"] in interesting and s["eps"] in (0.05, 0.10, 0.20)
    ]
    sav_rows = []
    for s in sav:
        nv = s["n_valid"]
        sav_rows.append(
            [
                s["pop_id"],
                s["eps"],
                nv.get("srs-hypergeometric"),
                nv.get("ppi++-normal"),
                nv.get("difference-greg-fpc"),
                nv.get("poststrat-cp-bonferroni"),
                s["ratio_n_srs_n_ppi_valid"],
            ]
        )
    chunks.append("label savings: smallest n with mean UCB < eps AND coverage >= 0.95")
    chunks.append(
        _fmt_table(
            ["pop", "eps", "n_srs", "n_ppi", "n_diff", "n_ps", "n_srs/n_ppi"],
            sav_rows,
        )
    )

    sw = report.get("auroc_sweep_savings") or []
    sw_rows = []
    for s in sw:
        if s["eps"] not in (0.05, 0.10):
            continue
        nv = s["n_valid"]
        sw_rows.append(
            [
                s["pop_id"],
                s["eps"],
                nv.get("srs-hypergeometric"),
                nv.get("ppi++-normal"),
                nv.get("difference-greg-fpc"),
                s["ratio_n_srs_n_ppi_valid"],
            ]
        )
    chunks.append("AUROC sweep savings (0.8/0.9 are synthetic)")
    chunks.append(
        _fmt_table(
            ["pop", "eps", "n_srs", "n_ppi", "n_diff", "n_srs/n_ppi"],
            sw_rows,
        )
    )

    oc = report.get("operating_characteristic") or []
    oc_focus = [
        r
        for r in oc
        if r["pop_id"].startswith("thin-") and "conservative" in r["pop_id"]
    ]
    chunks.append("P(certify at eps=0.05): SRS-CP vs best valid PPI-type")
    chunks.append(
        _fmt_table(
            ["pop", "n", "true_p", "P_srs", "best", "P_best"],
            [
                [
                    r["pop_id"],
                    r["n"],
                    r["true_p"],
                    r["p_certify_srs"],
                    r["best_valid_estimator"],
                    r["p_certify_best_valid"],
                ]
                for r in oc_focus
            ],
        )
    )
    return "\n\n".join(chunks) + "\n"


def write_ppi_lab(report: dict, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report) + "\n", encoding="utf-8")
    summary = compact_summary(report)
    out.with_name(out.stem + ".summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )

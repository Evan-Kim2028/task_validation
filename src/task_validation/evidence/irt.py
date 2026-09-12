"""2PL IRT and agent-solve taste vs 2024 SWE-bench validity labels.

Stdlib only. Joint MLE (no marginal likelihood): alternate ridge logistic
Newton steps for item (a, d) and person theta, then standardize theta to
mean 0, sd 1 and rescale a, d. Missing cells (no_generation, no_logs) are
skipped. Discrimination a is constrained positive.

Frozen before any label comparison (section D):
invalid items have lower 2PL discrimination (median a_i lower, U-test p < 0.01)
and are over-represented among near-constant items.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

# Written before computing associations with Y.
FROZEN_PREDICATE = (
    "invalid items have lower 2PL discrimination (median a_i lower, "
    "U-test p < 0.01) and are over-represented among near-constant items"
)
COMBINATION_RULE = (
    "retain lowest z(p_logistic) - z(a_i): low OOF invalidity risk and "
    "high 2PL discrimination"
)

MIN_ATTEMPT_FRAC = 0.90
NEAR_CONSTANT_LO = 0.02
NEAR_CONSTANT_HI = 0.98
N_BOOTSTRAP = 1000
BOOTSTRAP_SEED = 20260911
RETAIN_FRACS = (0.05, 0.10, 0.20)
MID_BAND = (0.20, 0.80)
RIDGE_A = 0.15
RIDGE_D = 0.05
RIDGE_THETA = 0.05
MAX_ITER = 60
INNER_NEWTON = 3
TOL = 1e-4
A_MIN, A_MAX = 0.01, 5.0
Y_KEYS = (
    ("conservative", "openai_2024_conservative"),
    ("majority", "majority_invalid"),
    ("unanimous", "unanimous_invalid"),
)


def sigmoid(z: float) -> float:
    if z >= 0:
        e = math.exp(-min(z, 60.0))
        return 1.0 / (1.0 + e)
    e = math.exp(max(z, -60.0))
    return e / (1.0 + e)


def logit(p: float) -> float:
    p = min(1.0 - 1e-6, max(1e-6, p))
    return math.log(p / (1.0 - p))


def mean(xs: list[float]) -> float:
    return sum(xs) / max(len(xs), 1)


def pop_sd(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))


def median(xs: list[float]) -> float | None:
    if not xs:
        return None
    ys = sorted(xs)
    n = len(ys)
    mid = n // 2
    if n % 2:
        return float(ys[mid])
    return 0.5 * (ys[mid - 1] + ys[mid])


def pearson(x: list[float], y: list[float]) -> float | None:
    n = len(x)
    if n < 3 or n != len(y):
        return None
    mx, my = mean(x), mean(y)
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    dx = math.sqrt(sum((xi - mx) ** 2 for xi in x))
    dy = math.sqrt(sum((yi - my) ** 2 for yi in y))
    if dx < 1e-12 or dy < 1e-12:
        return None
    return num / (dx * dy)


def _average_ranks(values: list[float]) -> tuple[list[float], float]:
    n = len(values)
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    tie_term = 0.0
    i = 0
    while i < n:
        j = i
        while j < n and values[order[j]] == values[order[i]]:
            j += 1
        t = j - i
        if t > 1:
            tie_term += t * t * t - t
        avg = 0.5 * (i + 1 + j)
        for k in range(i, j):
            ranks[order[k]] = avg
        i = j
    return ranks, tie_term


def _norm_cdf(z: float) -> float:
    return 0.5 * math.erfc(-z / math.sqrt(2.0))


def auroc(y: list[int], scores: list[float]) -> float | None:
    n_pos = sum(1 for t in y if t == 1)
    n_neg = len(y) - n_pos
    if n_pos == 0 or n_neg == 0 or len(y) != len(scores):
        return None
    ranks, _ = _average_ranks(scores)
    sum_pos = sum(ranks[i] for i, t in enumerate(y) if t == 1)
    u = sum_pos - n_pos * (n_pos + 1) / 2.0
    return u / (n_pos * n_neg)


def _percentile(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    ys = sorted(xs)
    i = p * (len(ys) - 1)
    lo = int(i)
    hi = min(lo + 1, len(ys) - 1)
    w = i - lo
    return ys[lo] * (1.0 - w) + ys[hi] * w


def bootstrap_auroc(
    y: list[int],
    scores: list[float],
    n_reps: int = N_BOOTSTRAP,
    seed: int = BOOTSTRAP_SEED,
) -> dict:
    point = auroc(y, scores)
    rng = random.Random(seed)
    n = len(y)
    boots: list[float] = []
    for _ in range(n_reps):
        idx = [rng.randrange(n) for _ in range(n)] if n else []
        val = auroc([y[i] for i in idx], [scores[i] for i in idx])
        if val is not None:
            boots.append(val)
    lo = _percentile(boots, 0.025)
    hi = _percentile(boots, 0.975)
    return {
        "value": point,
        "n_bootstrap": n_reps,
        "n_defined": len(boots),
        "seed": seed,
        "ci95": [lo, hi] if lo is not None and hi is not None else None,
    }


def mann_whitney_u(x: list[float], y: list[float]) -> dict:
    """MWU. U is pairwise wins for x (higher ranks). p_less tests x stochastically < y."""

    n1, n2 = len(x), len(y)
    out = {
        "n_x": n1,
        "n_y": n2,
        "median_x": median(x),
        "median_y": median(y),
        "U": None,
        "p_two_sided": None,
        "p_less": None,
        "p_greater": None,
    }
    if n1 == 0 or n2 == 0:
        return out
    ranks, tie_term = _average_ranks(list(x) + list(y))
    r1 = sum(ranks[:n1])
    u1 = r1 - n1 * (n1 + 1) / 2.0
    n = n1 + n2
    mu = n1 * n2 / 2.0
    if n > 1:
        sigma2 = n1 * n2 / 12.0 * ((n + 1) - tie_term / (n * (n - 1)))
    else:
        sigma2 = 0.0
    sigma = math.sqrt(max(sigma2, 0.0))
    out["U"] = u1
    if sigma < 1e-12:
        out["p_two_sided"] = 1.0
        out["p_less"] = 1.0
        out["p_greater"] = 1.0
        return out
    z_less = (u1 - mu + 0.5) / sigma
    z_greater = (u1 - mu - 0.5) / sigma
    p_less = _norm_cdf(z_less)
    p_greater = 1.0 - _norm_cdf(z_greater)
    z_two = (u1 - mu - math.copysign(0.5, u1 - mu)) / sigma if u1 != mu else 0.0
    p_two = min(1.0, 2.0 * (1.0 - _norm_cdf(abs(z_two))))
    out["p_less"] = p_less
    out["p_greater"] = p_greater
    out["p_two_sided"] = p_two
    return out


def zscore(xs: list[float]) -> list[float]:
    m = mean(xs)
    sd = pop_sd(xs)
    if sd < 1e-12:
        return [0.0] * len(xs)
    return [(x - m) / sd for x in xs]


def _id_set(raw) -> set[str]:
    if not raw:
        return set()
    if isinstance(raw, dict):
        return {str(k) for k, v in raw.items() if v}
    out: set[str] = set()
    for x in raw:
        if x is None:
            continue
        out.add(str(x))
    return out


def parse_results(data: dict) -> dict[str, set[str]]:
    """Map a results.json object to resolved / missing / generated id sets."""

    resolved = _id_set(data.get("resolved") or data.get("resolved_ids"))
    no_gen = _id_set(data.get("no_generation"))
    no_logs = _id_set(data.get("no_logs"))
    generated = (
        _id_set(data.get("generated"))
        | _id_set(data.get("with_logs"))
        | _id_set(data.get("applied"))
        | _id_set(data.get("completed_ids"))
        | _id_set(data.get("unresolved") or data.get("unresolved_ids"))
    )
    missing = no_gen | no_logs
    return {
        "resolved": resolved,
        "missing": missing,
        "no_generation": no_gen,
        "no_logs": no_logs,
        "generated": generated,
    }


def cell_value(parsed: dict[str, set[str]], item_id: str, assume_full: bool) -> int | None:
    """resolved=1, no_generation/no_logs=missing, else 0 if attempted."""

    if item_id in parsed["missing"]:
        return None
    if item_id in parsed["resolved"]:
        return 1
    if parsed["generated"]:
        if item_id in parsed["generated"] or assume_full:
            return 0
        return None
    if assume_full:
        return 0
    return None


def load_jsonl(path: Path, key: str = "task_id") -> dict[str, dict]:
    out: dict[str, dict] = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            out[rec[key]] = rec
    return out


def list_results_json(experiments_dir: Path) -> list[Path]:
    root = experiments_dir / "evaluation" / "test"
    if not root.is_dir():
        return []
    found: list[Path] = []
    for sub in sorted(root.iterdir()):
        p = sub / "results" / "results.json"
        if p.is_file():
            found.append(p)
    return found


def git_commit(experiments_dir: Path) -> str | None:
    head = experiments_dir / ".git" / "HEAD"
    if not head.is_file():
        return None
    text = head.read_text(encoding="utf-8").strip()
    if text.startswith("ref:"):
        ref = experiments_dir / ".git" / text.split(" ", 1)[1].strip()
        if ref.is_file():
            return ref.read_text(encoding="utf-8").strip()
        return None
    return text or None


def build_matrix(
    item_ids: list[str],
    result_paths: list[Path],
    min_attempt_frac: float = MIN_ATTEMPT_FRAC,
) -> dict:
    """Item x submission binary matrix. Missing = None. 90% attempt filter."""

    n_items = len(item_ids)
    threshold = min_attempt_frac * n_items
    submissions: list[dict] = []
    for path in result_paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        parsed = parse_results(data)
        assume_full = not parsed["generated"]
        col: list[int | None] = [
            cell_value(parsed, iid, assume_full) for iid in item_ids
        ]
        n_attempted = sum(1 for v in col if v is not None)
        n_resolved = sum(1 for v in col if v == 1)
        rec = {
            "name": path.parent.parent.name,
            "path": str(path),
            "n_attempted": n_attempted,
            "n_resolved": n_resolved,
            "attempt_frac": n_attempted / n_items if n_items else 0.0,
            "survived": n_attempted >= threshold,
            "assume_full_split": assume_full,
            "column": col,
        }
        submissions.append(rec)

    kept = [s for s in submissions if s["survived"]]
    matrix = [[s["column"][i] for s in kept] for i in range(n_items)]
    return {
        "item_ids": item_ids,
        "n_items": n_items,
        "n_submissions_listed": len(submissions),
        "n_submissions_used": len(kept),
        "min_attempt_frac": min_attempt_frac,
        "threshold_attempted": threshold,
        "submissions": [
            {k: v for k, v in s.items() if k != "column"} for s in submissions
        ],
        "used_names": [s["name"] for s in kept],
        "matrix": matrix,
    }


def solve_rate(row: list[int | None]) -> tuple[float | None, int, int]:
    obs = [v for v in row if v is not None]
    n = len(obs)
    n_res = sum(obs)
    if n == 0:
        return None, 0, 0
    return n_res / n, n, n_res


def near_constant(p: float | None, lo: float = NEAR_CONSTANT_LO, hi: float = NEAR_CONSTANT_HI) -> bool:
    if p is None:
        return True
    return p < lo or p > hi


def point_biserial_row(row: list[int | None], rest_scores: list[float | None]) -> float | None:
    xs: list[float] = []
    ts: list[float] = []
    for y, t in zip(row, rest_scores):
        if y is None or t is None:
            continue
        xs.append(float(y))
        ts.append(float(t))
    if len(xs) < 3 or len(set(xs)) < 2:
        return None
    return pearson(xs, ts)


def submission_totals(matrix: list[list[int | None]]) -> list[float | None]:
    if not matrix:
        return []
    n_items = len(matrix)
    n_sub = len(matrix[0])
    out: list[float | None] = []
    for j in range(n_sub):
        obs = [matrix[i][j] for i in range(n_items) if matrix[i][j] is not None]
        out.append(sum(obs) / len(obs) if obs else None)
    return out


def rest_scores_for_item(
    matrix: list[list[int | None]],
    item_index: int,
    totals: list[float | None],
) -> list[float | None]:
    n_items = len(matrix)
    n_sub = len(matrix[0]) if matrix else 0
    out: list[float | None] = []
    for j in range(n_sub):
        y = matrix[item_index][j]
        tot = totals[j]
        if y is None or tot is None:
            out.append(None)
            continue
        n_obs = sum(1 for i in range(n_items) if matrix[i][j] is not None)
        if n_obs <= 1:
            out.append(None)
            continue
        rest = (tot * n_obs - y) / (n_obs - 1)
        out.append(rest)
    return out


def item_point_biserial(matrix: list[list[int | None]]) -> list[float | None]:
    totals = submission_totals(matrix)
    return [
        point_biserial_row(matrix[i], rest_scores_for_item(matrix, i, totals))
        for i in range(len(matrix))
    ]


def _nll(
    matrix: list[list[int | None]],
    a: list[float],
    d: list[float],
    theta: list[float],
    ridge_a: float,
    ridge_d: float,
    ridge_th: float,
) -> float:
    s = 0.0
    n_items = len(matrix)
    n_sub = len(theta)
    for i in range(n_items):
        ai, di = a[i], d[i]
        row = matrix[i]
        for j in range(n_sub):
            y = row[j]
            if y is None:
                continue
            p = min(1.0 - 1e-12, max(1e-12, sigmoid(ai * theta[j] + di)))
            s += -(y * math.log(p) + (1 - y) * math.log(1 - p))
    s += 0.5 * ridge_a * sum(x * x for x in a)
    s += 0.5 * ridge_d * sum(x * x for x in d)
    s += 0.5 * ridge_th * sum(x * x for x in theta)
    return s


def _standardize_theta(a: list[float], d: list[float], theta: list[float]) -> float:
    n = len(theta)
    m = mean(theta)
    sd = pop_sd(theta)
    if sd < 1e-8:
        sd = 1.0
    for j in range(n):
        theta[j] = (theta[j] - m) / sd
    for i in range(len(a)):
        d[i] = d[i] + a[i] * m
        a[i] = min(A_MAX, max(A_MIN, a[i] * sd))
    return sd


def fit_2pl(
    matrix: list[list[int | None]],
    *,
    ridge_a: float = RIDGE_A,
    ridge_d: float = RIDGE_D,
    ridge_th: float = RIDGE_THETA,
    max_iter: int = MAX_ITER,
    inner: int = INNER_NEWTON,
    tol: float = TOL,
) -> dict:
    """Joint MLE 2PL by alternating ridge logistic Newton. MML-free.

    logit P(y_ij=1) = a_i * theta_j + d_i, with b_i = -d_i / a_i.
    After each cycle, theta is standardized (mean 0, sd 1) and (a, d) rescaled.
    a is clipped to [A_MIN, A_MAX]. Convergence: max |delta a| < tol after
    at least 8 cycles, or max_iter. Ridge is L2 on a, d, theta (toward 0).
    """

    n_items = len(matrix)
    n_sub = len(matrix[0]) if matrix else 0
    if n_items == 0 or n_sub == 0:
        return {
            "a": [],
            "d": [],
            "b": [],
            "theta": [],
            "n_iter": 0,
            "converged": True,
            "nll": [],
            "ridge_a": ridge_a,
            "ridge_d": ridge_d,
            "ridge_th": ridge_th,
            "max_iter": max_iter,
            "tol": tol,
        }

    p_item: list[float] = []
    for i in range(n_items):
        p, n_obs, _ = solve_rate(matrix[i])
        p_item.append(0.5 if p is None or n_obs == 0 else p)
    p_sub: list[float] = []
    for j in range(n_sub):
        obs = [matrix[i][j] for i in range(n_items) if matrix[i][j] is not None]
        p_sub.append(sum(obs) / len(obs) if obs else 0.5)

    pbis = item_point_biserial(matrix)
    a = [
        max(A_MIN, min(2.5, 0.5 + 2.0 * max(0.0, pbis[i] or 0.0)))
        for i in range(n_items)
    ]
    d = [logit(p) for p in p_item]
    theta = [logit(p) for p in p_sub]
    _standardize_theta(a, d, theta)

    history = [_nll(matrix, a, d, theta, ridge_a, ridge_d, ridge_th)]
    last_a: list[float] | None = None
    n_iter = 0
    converged = False
    for it in range(max_iter):
        n_iter = it + 1
        for i in range(n_items):
            row = matrix[i]
            for _ in range(inner):
                ga = gd = haa = had = hdd = 0.0
                for j in range(n_sub):
                    y = row[j]
                    if y is None:
                        continue
                    p = sigmoid(a[i] * theta[j] + d[i])
                    w = max(p * (1.0 - p), 1e-8)
                    r = p - y
                    tj = theta[j]
                    ga += r * tj
                    gd += r
                    haa += w * tj * tj
                    had += w * tj
                    hdd += w
                ga += ridge_a * a[i]
                gd += ridge_d * d[i]
                haa += ridge_a
                hdd += ridge_d
                det = haa * hdd - had * had
                if abs(det) < 1e-12:
                    haa += 0.5
                    hdd += 0.5
                    det = haa * hdd - had * had
                da = (hdd * ga - had * gd) / det
                dd = (haa * gd - had * ga) / det
                da = max(-0.4, min(0.4, da))
                dd = max(-0.4, min(0.4, dd))
                a[i] = min(A_MAX, max(A_MIN, a[i] - da))
                d[i] = min(8.0, max(-8.0, d[i] - dd))
        for j in range(n_sub):
            for _ in range(inner):
                g = h = 0.0
                tj = theta[j]
                for i in range(n_items):
                    y = matrix[i][j]
                    if y is None:
                        continue
                    ai = a[i]
                    p = sigmoid(ai * tj + d[i])
                    w = max(p * (1.0 - p), 1e-8)
                    g += (p - y) * ai
                    h += w * ai * ai
                g += ridge_th * tj
                h += ridge_th
                dt = max(-0.4, min(0.4, g / max(h, 1e-8)))
                tj -= dt
                theta[j] = tj
        _standardize_theta(a, d, theta)
        history.append(_nll(matrix, a, d, theta, ridge_a, ridge_d, ridge_th))
        if last_a is not None:
            delta = max(abs(a[i] - last_a[i]) for i in range(n_items))
            if delta < tol and it >= 8:
                converged = True
                break
        last_a = list(a)

    b: list[float | None] = []
    for i in range(n_items):
        if abs(a[i]) < 1e-3:
            b.append(None)
        else:
            b.append(-d[i] / a[i])
    return {
        "a": a,
        "d": d,
        "b": b,
        "theta": list(theta),
        "n_iter": n_iter,
        "converged": converged,
        "nll": history,
        "nll_start": history[0] if history else None,
        "nll_end": history[-1] if history else None,
        "ridge_a": ridge_a,
        "ridge_d": ridge_d,
        "ridge_th": ridge_th,
        "max_iter": max_iter,
        "inner_newton": inner,
        "tol": tol,
        "identifiability": (
            "theta standardized each cycle (mean 0, sd 1); a and d rescaled; "
            "a clipped to [0.01, 5]; L2 ridge toward 0"
        ),
    }


def mid_band_score(p: float | None, lo: float = MID_BAND[0], hi: float = MID_BAND[1]) -> float:
    if p is None:
        return 1e9
    if lo <= p <= hi:
        return abs(p - 0.5)
    return 1.0 + abs(p - 0.5)


def head_size(n: int, frac: float) -> int:
    if n <= 0:
        return 0
    return min(n, max(1, int(round(frac * n))))


def retain_by_score(
    y: list[int],
    scores: list[float],
    fracs: tuple[float, ...] = RETAIN_FRACS,
    *,
    higher_kept: bool,
) -> list[dict]:
    n = len(y)
    order = sorted(range(n), key=lambda i: (scores[i], i), reverse=higher_kept)
    out = []
    for frac in fracs:
        k = head_size(n, frac)
        kept = order[:k]
        n_inv = sum(y[i] for i in kept)
        out.append(
            {
                "retain_frac": frac,
                "n_retained": k,
                "n_invalid": n_inv,
                "residual_invalid": n_inv / k if k else None,
            }
        )
    return out


def group_stats(values: list[float], y: list[int]) -> dict:
    inv = [v for v, t in zip(values, y) if t == 1]
    val = [v for v, t in zip(values, y) if t == 0]
    mw = mann_whitney_u(inv, val)
    return {
        "n_invalid": len(inv),
        "n_valid": len(val),
        "median_invalid": median(inv),
        "median_valid": median(val),
        "mean_invalid": mean(inv) if inv else None,
        "mean_valid": mean(val) if val else None,
        "mann_whitney": mw,
    }


def evaluate_frozen_predicate(
    a: list[float],
    y: list[int],
    near: list[bool],
    *,
    p_threshold: float = 0.01,
) -> dict:
    """Apply the frozen predicate. Do not retune on fail."""

    inv_a = [ai for ai, t in zip(a, y) if t == 1]
    val_a = [ai for ai, t in zip(a, y) if t == 0]
    mw = mann_whitney_u(inv_a, val_a)
    med_inv = median(inv_a)
    med_val = median(val_a)
    lower_median = (
        med_inv is not None and med_val is not None and med_inv < med_val
    )
    u_pass = mw["p_less"] is not None and mw["p_less"] < p_threshold
    n_nc = sum(1 for f in near if f)
    n_nc_inv = sum(1 for f, t in zip(near, y) if f and t == 1)
    n_not = sum(1 for f in near if not f)
    n_not_inv = sum(1 for f, t in zip(near, y) if (not f) and t == 1)
    rate_nc = n_nc_inv / n_nc if n_nc else None
    rate_not = n_not_inv / n_not if n_not else None
    rate_inv_nc = (
        sum(1 for f, t in zip(near, y) if t == 1 and f) / sum(1 for t in y if t == 1)
        if sum(y)
        else None
    )
    rate_val_nc = (
        sum(1 for f, t in zip(near, y) if t == 0 and f) / sum(1 for t in y if t == 0)
        if sum(1 for t in y if t == 0)
        else None
    )
    over = (
        rate_nc is not None
        and rate_not is not None
        and rate_nc > rate_not
        and rate_inv_nc is not None
        and rate_val_nc is not None
        and rate_inv_nc > rate_val_nc
    )
    passed = bool(lower_median and u_pass and over)
    return {
        "text": FROZEN_PREDICATE,
        "pass": passed,
        "lower_median_a": lower_median,
        "u_test_p_less": mw["p_less"],
        "u_test_pass": u_pass,
        "p_threshold": p_threshold,
        "median_a_invalid": med_inv,
        "median_a_valid": med_val,
        "near_constant_invalid_rate": rate_nc,
        "non_constant_invalid_rate": rate_not,
        "p_near_constant_given_invalid": rate_inv_nc,
        "p_near_constant_given_valid": rate_val_nc,
        "over_represented": over,
        "n_near_constant": n_nc,
        "mann_whitney": mw,
    }


def json_float(x) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


def _label_block(compact: dict, raters: dict) -> dict:
    sev = compact.get("human_severity") or {}
    return {
        "human_validity_label": compact.get("human_validity_label"),
        "openai_2024_conservative": raters.get("openai_2024_conservative"),
        "majority_invalid": raters.get("majority_invalid"),
        "unanimous_invalid": raters.get("unanimous_invalid"),
        "underspecified": sev.get("underspecified"),
        "false_negative": sev.get("false_negative"),
        "other_major_issues": sev.get("other_major_issues"),
        "n_raters": raters.get("n_raters", compact.get("n_raters")),
        "n_material_votes": raters.get("n_material_votes"),
    }


def analyze_against_y(
    items: list[dict],
    y_name: str,
    y: list[int],
    *,
    n_bootstrap: int,
    seed: int,
) -> dict:
    p = [float(it["p_i"]) for it in items]
    a = [float(it["a_i"]) for it in items]
    pbis = [float(it["pbis"] if it["pbis"] is not None else 0.0) for it in items]
    one_minus_p = [1.0 - pi for pi in p]
    near = [bool(it["near_constant"]) for it in items]
    aurocs = {
        "one_minus_p": bootstrap_auroc(y, one_minus_p, n_reps=n_bootstrap, seed=seed),
        "a_i": bootstrap_auroc(y, a, n_reps=n_bootstrap, seed=seed + 1),
        "pbis": bootstrap_auroc(y, pbis, n_reps=n_bootstrap, seed=seed + 2),
    }
    dist = {
        "solve_rate": group_stats(p, y),
        "a_i": group_stats(a, y),
        "pbis": group_stats(pbis, y),
        "one_minus_p": group_stats(one_minus_p, y),
    }
    pred = evaluate_frozen_predicate(a, y, near)
    oof = [float(it["p_logistic"]) if it.get("p_logistic") is not None else 0.5 for it in items]
    za = zscore(a)
    zo = zscore(oof)
    combo = [zo[i] - za[i] for i in range(len(items))]
    mid = [mid_band_score(it["p_i"]) for it in items]
    in_band = [MID_BAND[0] <= it["p_i"] <= MID_BAND[1] for it in items]
    n_band = sum(in_band)
    n_band_inv = sum(1 for b, t in zip(in_band, y) if b and t == 1)
    retain = {
        "high_a": retain_by_score(y, a, RETAIN_FRACS, higher_kept=True),
        "high_pbis": retain_by_score(y, pbis, RETAIN_FRACS, higher_kept=True),
        "mid_band": retain_by_score(y, mid, RETAIN_FRACS, higher_kept=False),
        "oof_p_logistic": retain_by_score(y, oof, RETAIN_FRACS, higher_kept=False),
        "combination": retain_by_score(y, combo, RETAIN_FRACS, higher_kept=False),
        "mid_band_all": {
            "n": n_band,
            "n_invalid": n_band_inv,
            "residual_invalid": n_band_inv / n_band if n_band else None,
            "band": list(MID_BAND),
        },
        "base_rate": mean([float(t) for t in y]),
        "combination_rule": COMBINATION_RULE,
    }
    return {
        "y": y_name,
        "n": len(y),
        "n_invalid": sum(y),
        "base_rate": mean([float(t) for t in y]),
        "auroc": aurocs,
        "distributions": dist,
        "frozen_predicate": pred,
        "retain": retain,
    }


def severity_covariates(items: list[dict], *, n_bootstrap: int, seed: int) -> dict:
    """IRT stats vs underspecified / false_negative axes. Not features for Y."""

    p = [float(it["p_i"]) for it in items]
    a = [float(it["a_i"]) for it in items]
    pbis = [float(it["pbis"] if it["pbis"] is not None else 0.0) for it in items]
    u = [float((it["labels"] or {}).get("underspecified") or 0.0) for it in items]
    fn = [float((it["labels"] or {}).get("false_negative") or 0.0) for it in items]
    y_u = [1 if v >= 2 else 0 for v in u]
    y_fn = [1 if v >= 2 else 0 for v in fn]
    one_minus_p = [1.0 - pi for pi in p]
    return {
        "note": (
            "severity axes are labels, never predictors (ADR-0006). "
            "Reported as additional Y, not as covariates in a model of conservative Y."
        ),
        "underspecified_ge2": {
            "n": sum(y_u),
            "base_rate": mean([float(t) for t in y_u]),
            "auroc": {
                "one_minus_p": bootstrap_auroc(y_u, one_minus_p, n_reps=n_bootstrap, seed=seed),
                "a_i": bootstrap_auroc(y_u, a, n_reps=n_bootstrap, seed=seed + 3),
                "pbis": bootstrap_auroc(y_u, pbis, n_reps=n_bootstrap, seed=seed + 4),
            },
            "distributions": {
                "solve_rate": group_stats(p, y_u),
                "a_i": group_stats(a, y_u),
            },
            "spearman_p_i": pearson(
                _average_ranks(p)[0], _average_ranks(u)[0]
            ),
            "spearman_a_i": pearson(
                _average_ranks(a)[0], _average_ranks(u)[0]
            ),
        },
        "false_negative_ge2": {
            "n": sum(y_fn),
            "base_rate": mean([float(t) for t in y_fn]),
            "auroc": {
                "one_minus_p": bootstrap_auroc(y_fn, one_minus_p, n_reps=n_bootstrap, seed=seed + 5),
                "a_i": bootstrap_auroc(y_fn, a, n_reps=n_bootstrap, seed=seed + 6),
                "pbis": bootstrap_auroc(y_fn, pbis, n_reps=n_bootstrap, seed=seed + 7),
            },
            "distributions": {
                "solve_rate": group_stats(p, y_fn),
                "a_i": group_stats(a, y_fn),
            },
            "spearman_p_i": pearson(
                _average_ranks(p)[0], _average_ranks(fn)[0]
            ),
            "spearman_a_i": pearson(
                _average_ranks(a)[0], _average_ranks(fn)[0]
            ),
        },
    }


def format_auroc_row(block: dict) -> str:
    ci = block.get("ci95") or [None, None]
    v = block.get("value")
    if v is None:
        return "NA"
    lo, hi = ci
    if lo is None or hi is None:
        return f"{v:.3f}"
    return f"{v:.3f} ({lo:.3f}, {hi:.3f})"


def print_tables(summary: dict) -> None:
    print(f"submissions listed: {summary['data']['n_submissions_listed']}")
    print(f"submissions used (>=90% of 1699): {summary['data']['n_submissions_used']}")
    print(f"commit: {summary['data'].get('experiments_commit')}")
    print(f"2PL converged: {summary['fit']['converged']} in {summary['fit']['n_iter']} cycles")
    nll = summary["fit"].get("nll") or []
    if len(nll) >= 2:
        print(f"NLL {nll[0]:.1f} -> {nll[-1]:.1f}")
    print()
    print("a. AUROC for predicting invalid (1,000-rep bootstrap 95% CI)")
    print(f"{'Y':<14} {'1-p_i':<28} {'a_i':<28} {'pbis':<28}")
    for name, block in summary["by_y"].items():
        a = block["auroc"]
        print(
            f"{name:<14} {format_auroc_row(a['one_minus_p']):<28} "
            f"{format_auroc_row(a['a_i']):<28} {format_auroc_row(a['pbis']):<28}"
        )
    print()
    print("b. Solve rate and a_i, valid vs invalid (median, MWU p_less for invalid < valid)")
    print(
        f"{'Y':<14} {'p med inv':>10} {'p med val':>10} {'p U p':>10} "
        f"{'a med inv':>10} {'a med val':>10} {'a U p':>10}"
    )
    for name, block in summary["by_y"].items():
        sp = block["distributions"]["solve_rate"]
        sa = block["distributions"]["a_i"]
        print(
            f"{name:<14} {sp['median_invalid'] or 0:10.3f} {sp['median_valid'] or 0:10.3f} "
            f"{sp['mann_whitney']['p_less'] or 0:10.4g} "
            f"{sa['median_invalid'] or 0:10.3f} {sa['median_valid'] or 0:10.3f} "
            f"{sa['mann_whitney']['p_less'] or 0:10.4g}"
        )
    print()
    print("c. Residual invalidity at retain 5/10/20%")
    cons = summary["by_y"]["conservative"]["retain"]
    print(f"{'rule':<22} {'5%':>8} {'10%':>8} {'20%':>8}")
    for key, label in (
        ("high_a", "high a_i"),
        ("mid_band", "mid-band p"),
        ("oof_p_logistic", "OOF p_logistic"),
        ("combination", "OOF + a combo"),
    ):
        rows = cons[key]
        vals = {r["retain_frac"]: r["residual_invalid"] for r in rows}
        print(
            f"{label:<22} {vals[0.05]:8.3f} {vals[0.10]:8.3f} {vals[0.20]:8.3f}"
        )
    mb = cons["mid_band_all"]
    print(
        f"mid-band all p in {MID_BAND}: n={mb['n']} residual={mb['residual_invalid']:.3f} "
        f"base={cons['base_rate']:.3f}"
    )
    print()
    pred = summary["by_y"]["conservative"]["frozen_predicate"]
    print("d. Frozen predicate (conservative Y):", "PASS" if pred["pass"] else "FAIL")
    print("  ", pred["text"])
    print(
        f"   median a invalid={pred['median_a_invalid']:.3f} valid={pred['median_a_valid']:.3f} "
        f"p_less={pred['u_test_p_less']:.4g} over_rep={pred['over_represented']}"
    )


def run(
    *,
    experiments_dir: Path,
    compact_path: Path,
    raters_path: Path,
    oof_path: Path,
    out_path: Path,
    summary_path: Path,
    claims_path: Path | None = None,
    n_bootstrap: int = N_BOOTSTRAP,
    seed: int = BOOTSTRAP_SEED,
) -> dict:
    compact = load_jsonl(compact_path)
    raters = load_jsonl(raters_path)
    oof = load_jsonl(oof_path)
    item_ids = sorted(compact.keys())
    if len(item_ids) != 1699:
        raise SystemExit(f"expected 1699 labeled items, got {len(item_ids)}")
    result_paths = list_results_json(experiments_dir)
    commit = git_commit(experiments_dir)
    packed = build_matrix(item_ids, result_paths)
    matrix = packed["matrix"]
    pbis = item_point_biserial(matrix)
    fit = fit_2pl(matrix)
    items: list[dict] = []
    for i, tid in enumerate(item_ids):
        p, n_att, n_res = solve_rate(matrix[i])
        rec = {
            "task_id": tid,
            "repository": compact[tid].get("repository"),
            "p_i": p,
            "a_i": fit["a"][i],
            "b_i": fit["b"][i],
            "d_i": fit["d"][i],
            "pbis": pbis[i],
            "near_constant": near_constant(p),
            "n_attempted": n_att,
            "n_resolved": n_res,
            "p_logistic": (oof.get(tid) or {}).get("p_logistic"),
            "labels": _label_block(compact[tid], raters.get(tid) or {}),
        }
        items.append(rec)

    by_y = {}
    for name, field in Y_KEYS:
        y = [int((it["labels"] or {}).get(field) or 0) for it in items]
        by_y[name] = analyze_against_y(
            items, name, y, n_bootstrap=n_bootstrap, seed=seed
        )
    sev = severity_covariates(items, n_bootstrap=n_bootstrap, seed=seed)

    payload = {
        "schema": "swe_irt.v1",
        "n_items": len(items),
        "n_submissions_used": packed["n_submissions_used"],
        "used_names": packed["used_names"],
        "items": items,
    }
    nll = fit.get("nll") or []
    summary = {
        "schema": "swe_irt.summary.v1",
        "frozen_predicate": FROZEN_PREDICATE,
        "combination_rule": COMBINATION_RULE,
        "data": {
            "experiments_dir": str(experiments_dir),
            "experiments_commit": commit,
            "source": "https://github.com/SWE-bench/experiments",
            "split": "evaluation/test",
            "n_items": packed["n_items"],
            "n_submissions_listed": packed["n_submissions_listed"],
            "n_submissions_used": packed["n_submissions_used"],
            "min_attempt_frac": packed["min_attempt_frac"],
            "used_names": packed["used_names"],
            "dropped": [
                s["name"] for s in packed["submissions"] if not s["survived"]
            ],
            "submissions": packed["submissions"],
        },
        "fit": {
            "method": "joint MLE, alternating ridge logistic Newton, MML-free",
            "n_iter": fit["n_iter"],
            "converged": fit["converged"],
            "nll": nll,
            "nll_start": fit.get("nll_start"),
            "nll_end": fit.get("nll_end"),
            "ridge_a": fit["ridge_a"],
            "ridge_d": fit["ridge_d"],
            "ridge_th": fit["ridge_th"],
            "max_iter": fit["max_iter"],
            "inner_newton": fit.get("inner_newton"),
            "tol": fit["tol"],
            "identifiability": fit.get("identifiability"),
            "n_near_constant": sum(1 for it in items if it["near_constant"]),
            "median_p": median([it["p_i"] for it in items if it["p_i"] is not None]),
            "median_a": median([it["a_i"] for it in items]),
        },
        "by_y": by_y,
        "severity": sev,
        "constraints": {
            "stdlib_only": True,
            "no_docker": True,
            "severity_not_used_as_features": True,
            "no_humans_for_taste_dims": True,
        },
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    if claims_path is not None:
        dropped = ", ".join(summary["data"]["dropped"]) or "(none)"
        used = "\n".join(f"- {n}" for n in packed["used_names"])
        claims_path.parent.mkdir(parents=True, exist_ok=True)
        claims_path.write_text(
            "# SWE-bench experiments (results.json only)\n\n"
            "Eval-only agent submissions. Never used as features that define Y. "
            "Taste dimensions (solve rate, 2PL a/b, point-biserial) are estimated "
            "from public resolved lists.\n\n"
            f"- Repo: https://github.com/SWE-bench/experiments\n"
            f"- Commit: `{commit}`\n"
            f"- Sparse path: `evaluation/test/*/results/results.json` "
            f"(no logs, no trajectories)\n"
            f"- Submissions listed on the test split: {packed['n_submissions_listed']}\n"
            f"- Submissions used (attempted >= 90% of the 1,699 labeled items): "
            f"{packed['n_submissions_used']}\n"
            f"- Dropped: {dropped}\n"
            "- `evaluation/verified/` is the 500-item split; those runs cannot "
            "hit 90% of 1,699 and are not in the matrix.\n\n"
            "Used:\n"
            f"{used}\n",
            encoding="utf-8",
        )
    return summary


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="2PL IRT taste vs 2024 validity labels")
    p.add_argument(
        "--experiments-dir",
        type=Path,
        default=REPO_ROOT / "data/raw/swe-bench-experiments",
    )
    p.add_argument(
        "--compact",
        type=Path,
        default=REPO_ROOT / "data/gold/swe_verified_compact.jsonl",
    )
    p.add_argument(
        "--raters",
        type=Path,
        default=REPO_ROOT / "data/gold/swe_rater_targets.jsonl",
    )
    p.add_argument(
        "--oof",
        type=Path,
        default=REPO_ROOT / "data/gold/oof_openai_2024_conservative.oof.jsonl",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "data/gold/swe_irt.json",
    )
    p.add_argument(
        "--summary",
        type=Path,
        default=REPO_ROOT / "data/gold/swe_irt.summary.json",
    )
    p.add_argument(
        "--claims",
        type=Path,
        default=REPO_ROOT / "data/raw/swe-bench-experiments/CLAIMS.md",
    )
    p.add_argument("--n-bootstrap", type=int, default=N_BOOTSTRAP)
    p.add_argument("--seed", type=int, default=BOOTSTRAP_SEED)
    args = p.parse_args(argv)
    summary = run(
        experiments_dir=args.experiments_dir,
        compact_path=args.compact,
        raters_path=args.raters,
        oof_path=args.oof,
        out_path=args.out,
        summary_path=args.summary,
        claims_path=args.claims,
        n_bootstrap=args.n_bootstrap,
        seed=args.seed,
    )
    print_tables(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

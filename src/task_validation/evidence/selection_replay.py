"""Selection rules as measuring instruments: rank recovery on TB4 (doc 65).

Docs 52/59/63 settled the label-prediction question (features do not
predict which tasks humans kept; all at chance). This module asks the
different question: does a selection RULE produce a better measuring
instrument than random selection of the same size? The instrument is a
k-task subset of the 66 TB4 tasks; the target is the full-66 ranking of
the 13 submissions by mean reward; the score is Kendall tau / Spearman
rho / mean rank distance between the subset ranking and the full
ranking.

Rules compared at k in {8, 16, 24, 32}:
  random          - uniform draw of k tasks
  band_lo_hi      - pooled solve rate in [lo, hi], then uniform draw of k
  irt_2pl         - top-k Fisher information at mean ability, joint-MLE
                    2PL on the 66x13 fractional response matrix (cell =
                    mean of the 5 scored trials; a fractional y is a
                    valid binomial-proportion likelihood term)
  pbis            - top-k point-biserial of item score vs rest score

Two uncertainty statements are reported per cell:
  - seed distribution over >=N_SEEDS draws for the sampling rules
  - a cell-level trial bootstrap (resample each task x submission cell's
    5 trials with replacement, refit the rule, rescore tau), which also
    gives a paired interval on tau_rule - E_seed[tau_random]

An in-sample greedy oracle (forward selection maximizing tau against the
full ranking) gives the ceiling any selection rule could reach on this
matrix.

Durability confound check (task 2): agent_name and model_name are
separate fields, so the submission = model x harness fusion can be
inspected directly. The design's crossed-ness decides whether model and
harness variance are separable.

Cost accounting (task 3): cost_usd and token counts are per-trial
fields; the artifact prices a k=3-per-task difficulty gate on 1,000 new
tasks per submission.

No model output enters a bound; nothing here is a bound (doc 43).
"""

from __future__ import annotations

import json
import math
import random
from collections import defaultdict
from pathlib import Path

from task_validation.evidence.durability import split_tiers
from task_validation.evidence.irt import (
    A_MIN,
    _average_ranks,
    _percentile,
    fit_2pl,
    item_point_biserial,
    pearson,
    sigmoid,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
GOLD = REPO_ROOT / "data" / "gold"

TB4_RAW = Path("/home/evan/Documents/eval_tasks/analysis/tb4/raw")
OUT_PATH = GOLD / "selection_replay_tb4.json"

PROTOCOL = "selection_replay.tb4.2026-09-15"

K_VALUES = (8, 16, 24, 32)
BANDS = ((0.10, 0.70), (0.25, 0.75), (0.30, 0.70))
N_SEEDS = 400  # >=200 required; seed draws per sampling rule per k
N_SEEDS_BOOT = 16  # seed draws per sampling rule inside each bootstrap rep
N_BOOT = 300  # cell-level trial bootstrap reps
N_POWER = 300  # parametric reps per m for the trials-per-cell power curve
POWER_M = (1, 2, 5, 20, 50)
POWER_K = 16
SEED = 20260915
IRT_MAX_ITER = 40


# ---------------------------------------------------------------- loading


def load_tb4(raw_dir: Path = TB4_RAW) -> dict:
    """One row per scored trial; cells keyed (task, submission_index).

    reward None is scored as failure (success = reward > 0), matching the
    doc 63 convention. Trial rows keep cost_usd / tokens for task 3.
    """
    subs: list[dict] = []
    cells: dict[tuple[str, int], list[int]] = defaultdict(list)
    trials: list[dict] = []
    n_null = 0
    for path in sorted(raw_dir.glob("*.trials.json")):
        j = len(subs)
        entries = json.loads(path.read_text())
        agent = model = provider = version = None
        for e in entries:
            if e.get("is_scored") is False:
                continue
            agent = e.get("agent_name")
            model = e.get("model_name")
            provider = e.get("model_provider")
            version = e.get("agent_version")
            r = e.get("reward")
            if r is None:
                n_null += 1
            cells[(e["task_name"], j)].append(1 if (r is not None and r > 0) else 0)
            trials.append(
                {
                    "task_name": e["task_name"],
                    "sub": j,
                    "cost_usd": e.get("cost_usd"),
                    "input_tokens": e.get("input_tokens"),
                    "output_tokens": e.get("output_tokens"),
                    "cache_tokens": e.get("cache_tokens"),
                }
            )
        subs.append(
            {
                "agent_name": agent,
                "model_name": model,
                "model_provider": provider,
                "agent_version": version,
                "file": path.name,
            }
        )
    tasks = sorted({t for (t, _j) in cells})
    return {
        "tasks": tasks,
        "subs": subs,
        "cells": dict(cells),
        "trials": trials,
        "n_null_rewards": n_null,
    }


def cell_matrix(tasks: list[str], n_sub: int, cells: dict) -> list[list[float]]:
    """66x13 matrix of cell mean rewards (fractional, in [0,1])."""
    return [
        [sum(cells[(t, j)]) / len(cells[(t, j)]) for j in range(n_sub)]
        for t in tasks
    ]


def task_solve_rates(matrix: list[list[float]]) -> list[float]:
    """Pooled per-task solve rate over all submissions and trials."""
    return [sum(row) / len(row) for row in matrix]


# ---------------------------------------------------------------- ranking


def submission_means(matrix: list[list[float]], items: list[int]) -> list[float]:
    n_sub = len(matrix[0])
    return [sum(matrix[i][j] for i in items) / len(items) for j in range(n_sub)]


def ranks_desc(values: list[float]) -> list[float]:
    """Average ranks, rank 1 = highest value."""
    asc, _ = _average_ranks([-v for v in values])
    return asc


def kendall_tau(x: list[float], y: list[float]) -> float | None:
    """Kendall tau-b (tie-corrected)."""
    n = len(x)
    if n < 2:
        return None
    conc = disc = tx = ty = 0
    for i in range(n):
        for j in range(i + 1, n):
            dx = (x[i] > x[j]) - (x[i] < x[j])
            dy = (y[i] > y[j]) - (y[i] < y[j])
            if dx == 0 and dy == 0:
                continue
            if dx == 0:
                tx += 1
            elif dy == 0:
                ty += 1
            elif dx == dy:
                conc += 1
            else:
                disc += 1
    n0 = n * (n - 1) / 2.0
    den = math.sqrt((n0 - tx) * (n0 - ty))
    if den < 1e-12:
        return None
    return (conc - disc) / den


def rank_agreement(matrix: list[list[float]], items: list[int], full_ranks: list[float]) -> dict:
    sub_ranks = ranks_desc(submission_means(matrix, items))
    tau = kendall_tau(sub_ranks, full_ranks)
    rho = pearson(sub_ranks, full_ranks)
    dist = sum(abs(a - b) for a, b in zip(sub_ranks, full_ranks)) / len(sub_ranks)
    return {"tau": tau, "rho": rho, "mean_rank_dist": dist}


# ---------------------------------------------------------------- rules


def select_random(n_items: int, k: int, rng: random.Random) -> list[int]:
    return sorted(rng.sample(range(n_items), min(k, n_items)))


def band_members(rates: list[float], lo: float, hi: float) -> list[int]:
    return [i for i, p in enumerate(rates) if lo <= p <= hi]


def select_band(rates: list[float], lo: float, hi: float, k: int, rng: random.Random) -> list[int]:
    members = band_members(rates, lo, hi)
    return sorted(rng.sample(members, min(k, len(members))))


def irt_item_params(matrix: list[list[float]], max_iter: int = IRT_MAX_ITER) -> dict:
    """2PL on the fractional 66x13 matrix; Fisher info at theta = mean = 0."""
    fit = fit_2pl(matrix, max_iter=max_iter)
    a, d = fit["a"], fit["d"]
    pbis = item_point_biserial(matrix)
    info = []
    for i in range(len(matrix)):
        p = sigmoid(d[i])
        info.append(a[i] * a[i] * p * (1.0 - p))
    # a is clipped to [A_MIN, A_MAX] inside fit_2pl, so "a <= 0" surfaces
    # as a pinned at the A_MIN floor; the point-biserial is the sign check.
    dropped = [
        i for i in range(len(matrix)) if a[i] <= A_MIN + 1e-9 or (pbis[i] or 0.0) <= 0.0
    ]
    return {"a": a, "d": d, "info": info, "pbis": pbis, "dropped": dropped,
            "converged": fit["converged"], "n_iter": fit["n_iter"]}


def select_irt(matrix: list[list[float]], k: int) -> tuple[list[int], dict]:
    par = irt_item_params(matrix)
    order = sorted(range(len(matrix)), key=lambda i: (-par["info"][i], i))
    kept = [i for i in order if i not in set(par["dropped"])]
    return sorted(kept[:k]), par


def select_pbis(matrix: list[list[float]], k: int) -> tuple[list[int], list[float | None]]:
    pbis = item_point_biserial(matrix)
    order = sorted(range(len(matrix)), key=lambda i: (-(pbis[i] or -1e9), i))
    kept = [i for i in order if (pbis[i] or 0.0) > 0.0]
    return sorted(kept[:k]), pbis


def oracle_select(matrix: list[list[float]], k: int, full_ranks: list[float]) -> dict:
    """Greedy forward selection maximizing tau vs the full ranking."""
    selected: list[int] = []
    remaining = set(range(len(matrix)))
    best_tau = None
    while len(selected) < k and remaining:
        cand, cand_tau = None, None
        for i in sorted(remaining):
            t = rank_agreement(matrix, selected + [i], full_ranks)["tau"]
            if t is not None and (cand_tau is None or t > cand_tau):
                cand, cand_tau = i, t
        if cand is None:
            break
        selected.append(cand)
        remaining.discard(cand)
        best_tau = cand_tau
    return {"items": sorted(selected), "tau": best_tau}


# ---------------------------------------------------------------- resampling


def resample_cells(cells: dict, rng: random.Random) -> dict:
    """Empirical bootstrap: redraw each cell's trials with replacement."""
    out = {}
    for key, vals in cells.items():
        n = len(vals)
        out[key] = [vals[rng.randrange(n)] for _ in range(n)]
    return out


def parametric_cells(cells: dict, m: int, rng: random.Random) -> dict:
    """Binomial(m, observed cell rate): the m-trials-per-cell design."""
    out = {}
    for key, vals in cells.items():
        p = sum(vals) / len(vals)
        out[key] = [1 if rng.random() < p else 0 for _ in range(m)]
    return out


def _mean_tau_over_seeds(
    matrix: list[list[float]],
    full_ranks: list[float],
    pick,
    n_seeds: int,
    rng: random.Random,
) -> list[float]:
    """pick(rng) -> item list; returns per-seed tau list."""
    taus = []
    for _ in range(n_seeds):
        items = pick(rng)
        if not items:
            continue
        t = rank_agreement(matrix, items, full_ranks)["tau"]
        if t is not None:
            taus.append(t)
    return taus


def _seed_summary(taus: list[float]) -> dict:
    return {
        "mean": sum(taus) / len(taus) if taus else None,
        "p025": _percentile(taus, 0.025),
        "p975": _percentile(taus, 0.975),
        "n_seeds": len(taus),
    }


# ---------------------------------------------------------------- task 1


def run_selection(data: dict) -> dict:
    tasks, subs, cells = data["tasks"], data["subs"], data["cells"]
    n_sub = len(subs)
    matrix = cell_matrix(tasks, n_sub, cells)
    rates = task_solve_rates(matrix)
    full_ranks = ranks_desc(submission_means(matrix, list(range(len(tasks)))))
    rng = random.Random(SEED)

    band_sizes = {
        f"{lo:.2f}_{hi:.2f}": len(band_members(rates, lo, hi)) for lo, hi in BANDS
    }

    rules: dict[str, dict] = {}
    rules["random"] = {
        "kind": "sampling",
        "pick": lambda r, k: select_random(len(tasks), k, r),
    }
    for lo, hi in BANDS:
        name = f"band_{lo:.2f}_{hi:.2f}"
        members = band_members(rates, lo, hi)
        rules[name] = {
            "kind": "sampling",
            "band_size": len(members),
            "pick": lambda r, k, m=members: sorted(r.sample(m, min(k, len(m)))),
        }
    rules["irt_2pl"] = {
        "kind": "deterministic",
        "pick": lambda r, k: select_irt(matrix, k)[0],
    }
    rules["pbis"] = {
        "kind": "deterministic",
        "pick": lambda r, k: select_pbis(matrix, k)[0],
    }

    # Observed-data evaluation ------------------------------------------------
    results: dict[str, dict] = {}
    for name, rule in rules.items():
        per_k = {}
        for k in K_VALUES:
            if rule["kind"] == "sampling":
                taus, rhos, dists, sizes = [], [], [], []
                for _ in range(N_SEEDS):
                    items = rule["pick"](rng, k)
                    ag = rank_agreement(matrix, items, full_ranks)
                    if ag["tau"] is None:
                        continue
                    taus.append(ag["tau"])
                    rhos.append(ag["rho"])
                    dists.append(ag["mean_rank_dist"])
                    sizes.append(len(items))
                per_k[str(k)] = {
                    "n_selected_mean": sum(sizes) / len(sizes) if sizes else 0,
                    "tau": _seed_summary(taus),
                    "rho": _seed_summary(rhos),
                    "mean_rank_dist": _seed_summary(dists),
                }
            else:
                items = rule["pick"](rng, k)
                ag = rank_agreement(matrix, items, full_ranks)
                per_k[str(k)] = {
                    "n_selected": len(items),
                    "tau": ag["tau"],
                    "rho": ag["rho"],
                    "mean_rank_dist": ag["mean_rank_dist"],
                }
        results[name] = per_k

    oracle = {
        str(k): oracle_select(matrix, k, full_ranks) for k in K_VALUES
    }

    # Cell-level trial bootstrap ----------------------------------------------
    # Resample each cell's 5 trials; recompute the full ranking and every
    # rule (bands and item params refit on the resampled matrix). Sampling
    # rules are averaged over N_SEEDS_BOOT seeds per rep so the quantity
    # bootstrapped is E_seed[tau], comparable across rules.
    boot_tau: dict[str, dict[str, list[float]]] = {
        name: {str(k): [] for k in K_VALUES} for name in rules
    }
    boot_delta: dict[str, dict[str, list[float]]] = {
        name: {str(k): [] for k in K_VALUES} for name in rules if name != "random"
    }
    for _rep in range(N_BOOT):
        cells_b = resample_cells(cells, rng)
        matrix_b = cell_matrix(tasks, n_sub, cells_b)
        rates_b = task_solve_rates(matrix_b)
        full_b = ranks_desc(submission_means(matrix_b, list(range(len(tasks)))))
        rep_tau: dict[str, dict[str, float | None]] = {}
        for name, rule in rules.items():
            rep_tau[name] = {}
            for k in K_VALUES:
                if name == "random":
                    pick = lambda r, kk=k: select_random(len(tasks), kk, r)
                elif rule["kind"] == "sampling":
                    lo, hi = (float(x) for x in name.split("_")[1:3])
                    pick = lambda r, kk=k, lo=lo, hi=hi: select_band(rates_b, lo, hi, kk, r)
                elif name == "irt_2pl":
                    pick = lambda r, kk=k: select_irt(matrix_b, kk)[0]
                else:
                    pick = lambda r, kk=k: select_pbis(matrix_b, kk)[0]
                if rule["kind"] == "sampling":
                    taus = _mean_tau_over_seeds(matrix_b, full_b, pick, N_SEEDS_BOOT, rng)
                    v = sum(taus) / len(taus) if taus else None
                else:
                    items = pick(rng)
                    v = rank_agreement(matrix_b, items, full_b)["tau"] if items else None
                rep_tau[name][str(k)] = v
                if v is not None:
                    boot_tau[name][str(k)].append(v)
        for name in boot_delta:
            for k in K_VALUES:
                v, vr = rep_tau[name][str(k)], rep_tau["random"][str(k)]
                if v is not None and vr is not None:
                    boot_delta[name][str(k)].append(v - vr)

    for name in rules:
        for k in K_VALUES:
            xs = boot_tau[name][str(k)]
            results[name][str(k)]["boot_mean_tau"] = {
                "mean": sum(xs) / len(xs) if xs else None,
                "ci95": [_percentile(xs, 0.025), _percentile(xs, 0.975)] if xs else None,
                "n_defined": len(xs),
            }
            if name in boot_delta:
                ds = boot_delta[name][str(k)]
                results[name][str(k)]["delta_vs_random_boot"] = {
                    "mean": sum(ds) / len(ds) if ds else None,
                    "ci95": [_percentile(ds, 0.025), _percentile(ds, 0.975)] if ds else None,
                    "p_delta_gt_0": (
                        sum(1 for x in ds if x > 0) / len(ds) if ds else None
                    ),
                    "n_defined": len(ds),
                }

    # Trials-per-cell power curve ---------------------------------------------
    # Parametric bootstrap at m trials per cell. The ranking noise in a
    # k-subset comes from cell means over m trials; m is the design knob a
    # real gate controls. Reports SE of E_seed[tau_random], SE of the pbis
    # rule's tau, and SE of the paired difference at k=POWER_K.
    power = {}
    for m in POWER_M:
        taus_r, taus_p, deltas = [], [], []
        for _ in range(N_POWER):
            cells_m = parametric_cells(cells, m, rng)
            matrix_m = cell_matrix(tasks, n_sub, cells_m)
            full_m = ranks_desc(submission_means(matrix_m, list(range(len(tasks)))))
            tr = _mean_tau_over_seeds(
                matrix_m, full_m,
                lambda r: select_random(len(tasks), POWER_K, r),
                8, rng,
            )
            items_p = select_pbis(matrix_m, POWER_K)[0]
            tp = rank_agreement(matrix_m, items_p, full_m)["tau"] if items_p else None
            if tr and tp is not None:
                mr = sum(tr) / len(tr)
                taus_r.append(mr)
                taus_p.append(tp)
                deltas.append(tp - mr)
        power[str(m)] = {
            "k": POWER_K,
            "se_random_mean_tau": _sd(taus_r),
            "se_pbis_tau": _sd(taus_p),
            "se_delta_pbis_minus_random": _sd(deltas),
            "mean_delta": sum(deltas) / len(deltas) if deltas else None,
            "n_defined": len(deltas),
        }

    full_means = submission_means(matrix, list(range(len(tasks))))
    return {
        "n_tasks": len(tasks),
        "n_submissions": n_sub,
        "band_sizes": band_sizes,
        "full_ranking": [
            {
                "submission": f"{subs[j]['model_name']} / {subs[j]['agent_name']}",
                "mean_reward": full_means[j],
                "rank": full_ranks[j],
            }
            for j in sorted(range(n_sub), key=lambda j: full_ranks[j])
        ],
        "rules": results,
        "oracle": oracle,
        "power_trials_per_cell": power,
        "tau_pair_note": (
            "13 submissions give C(13,2)=78 pairs; tau-b moves in quanta "
            "of ~2/78 = 0.026, so advantages smaller than ~0.03 tau are "
            "below the ranking resolution regardless of trials per cell."
        ),
    }


def _sd(xs: list[float]) -> float | None:
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


# ---------------------------------------------------------------- task 2


def run_confound(data: dict) -> dict:
    """agent_name x model_name crossed-ness and nested variance split."""
    subs = data["subs"]
    tasks, cells = data["tasks"], data["cells"]
    n_sub = len(subs)

    agents = sorted({s["agent_name"] for s in subs})
    models = sorted({s["model_name"] for s in subs})
    populated = {(s["agent_name"], s["model_name"]) for s in subs}
    models_per_agent = {a: sorted(s["model_name"] for s in subs if s["agent_name"] == a) for a in agents}
    agents_per_model = {m: sorted(s["agent_name"] for s in subs if s["model_name"] == m) for m in models}
    shared_models = [m for m, a in agents_per_model.items() if len(a) > 1]

    matrix = cell_matrix(tasks, n_sub, cells)

    # Nested decomposition of per-task submission means:
    #   total variance across the 13 submissions
    #   = between-harness (confounded model+harness)
    #   + within-harness across models (pure model axis, harness fixed)
    # The additive model ~ model + harness is NOT identifiable here: no
    # model appears under two harnesses, so between-harness differences
    # cannot be attributed. The nested split is the identifiable version.
    def decompose(means: list[float]) -> dict:
        grand = sum(means) / n_sub
        groups = defaultdict(list)
        for j, s in enumerate(subs):
            groups[s["agent_name"]].append(means[j])
        ss_between = sum(len(v) * (sum(v) / len(v) - grand) ** 2 for v in groups.values())
        ss_within = sum(
            (x - sum(v) / len(v)) ** 2 for v in groups.values() for x in v
        )
        total = ss_between + ss_within
        return {
            "total": total,
            "between_harness": ss_between,
            "within_harness_models": ss_within,
            "share_between": ss_between / total if total > 0 else None,
        }

    overall = decompose(submission_means(matrix, list(range(len(tasks)))))
    per_task = [decompose(matrix[i]) for i in range(len(tasks))]
    share_between_tasks = [d["share_between"] for d in per_task if d["share_between"] is not None]

    # Durability slope with the harness held fixed: order each harness's
    # models by that harness's overall solve rate, take top-third minus
    # bottom-third within the harness (2/2/2 for claude-code's 6 models,
    # 1/1/1 for codex's 3). The naive slope fuses harness into the axis by
    # ordering all 13 submissions (doc 63, 5/4/4 tiers).
    naive = _naive_slopes(matrix, subs)
    fixed = {}
    for a in agents:
        idx = [j for j, s in enumerate(subs) if s["agent_name"] == a]
        if len(idx) < 3:
            fixed[a] = {"n_models": len(idx), "note": "fewer than 3 models; no top/bottom third"}
            continue
        rates = {
            j: sum(matrix[i][j] for i in range(len(tasks))) / len(tasks) for j in idx
        }
        ordered = sorted(idx, key=lambda j: (rates[j], subs[j]["model_name"]))
        tiers = split_tiers(ordered, 3)
        lo_set, hi_set = set(tiers[0]), set(tiers[2])
        slopes = []
        for i in range(len(tasks)):
            b = sum(matrix[i][j] for j in lo_set) / len(lo_set)
            t = sum(matrix[i][j] for j in hi_set) / len(hi_set)
            slopes.append(t - b)
        fixed[a] = {
            "n_models": len(idx),
            "bottom": [subs[j]["model_name"] for j in tiers[0]],
            "top": [subs[j]["model_name"] for j in tiers[2]],
            "slope_median": _percentile(slopes, 0.5),
            "slope_p25": _percentile(slopes, 0.25),
            "slope_p75": _percentile(slopes, 0.75),
            "slopes": slopes,
        }

    return {
        "n_agents": len(agents),
        "n_models": len(models),
        "n_cells_possible": len(agents) * len(models),
        "n_cells_populated": len(populated),
        "models_per_agent": models_per_agent,
        "n_models_shared_across_agents": len(shared_models),
        "crossed": bool(shared_models),
        "variance_overall_submission_means": overall,
        "variance_per_task_share_between_median": _percentile(share_between_tasks, 0.5),
        "slope_naive_13sub_544": {
            "median": _percentile(naive, 0.5),
            "p25": _percentile(naive, 0.25),
            "p75": _percentile(naive, 0.75),
        },
        "slope_harness_fixed": {
            a: {k: v for k, v in d.items() if k != "slopes"} for a, d in fixed.items()
        },
    }


def _naive_slopes(matrix: list[list[float]], subs: list[dict]) -> list[float]:
    n_sub = len(subs)
    n_tasks = len(matrix)
    means = submission_means(matrix, list(range(n_tasks)))
    ordered = sorted(range(n_sub), key=lambda j: (means[j], subs[j]["model_name"]))
    tiers = split_tiers(ordered, 3)
    lo_set, hi_set = set(tiers[0]), set(tiers[2])
    return [
        sum(matrix[i][j] for j in hi_set) / len(hi_set)
        - sum(matrix[i][j] for j in lo_set) / len(lo_set)
        for i in range(n_tasks)
    ]


# ---------------------------------------------------------------- task 3


def run_costs(data: dict) -> dict:
    subs, trials = data["subs"], data["trials"]
    costs = [t["cost_usd"] for t in trials if t["cost_usd"] is not None]

    def _agg(group_key) -> list[dict]:
        by = defaultdict(list)
        for t in trials:
            if t["cost_usd"] is not None:
                by[group_key(t)].append(t["cost_usd"])
        rows = []
        for name, xs in sorted(by.items()):
            rows.append(
                {
                    "name": name,
                    "n_trials": len(xs),
                    "mean_cost": sum(xs) / len(xs),
                    "median_cost": _percentile(xs, 0.5),
                    "total_cost": sum(xs),
                    "cost_k3_x_1000_tasks": 3 * 1000 * (sum(xs) / len(xs)),
                }
            )
        return rows

    by_agent = _agg(lambda t: subs[t["sub"]]["agent_name"])
    by_model = _agg(lambda t: subs[t["sub"]]["model_name"])
    cheapest = min(by_model, key=lambda r: r["mean_cost"])
    return {
        "n_trials_with_cost": len(costs),
        "n_trials_missing_cost": len(trials) - len(costs),
        "overall": {
            "mean_cost_per_trial": sum(costs) / len(costs),
            "median_cost_per_trial": _percentile(costs, 0.5),
            "total_cost_grid": sum(costs),
        },
        "by_agent": by_agent,
        "by_model": by_model,
        "cheapest_model": cheapest,
        "gate_price_note": (
            "cost_k3_x_1000_tasks = mean per-trial cost x 3 trials x 1000 "
            "tasks: the price of running one submission through a "
            "difficulty gate over 1,000 candidate tasks."
        ),
    }


# ---------------------------------------------------------------- driver


def run() -> dict:
    print("[selection_replay] loading tb4 raw", flush=True)
    data = load_tb4()
    selection = run_selection(data)
    print("[selection_replay] rank recovery done; confound + costs", flush=True)
    confound = run_confound(data)
    costs = run_costs(data)
    out = {
        "protocol": PROTOCOL,
        "source": str(TB4_RAW),
        "n_trial_rows": len(data["trials"]),
        "n_null_rewards_scored_0": data["n_null_rewards"],
        "k_values": list(K_VALUES),
        "n_seeds_sampling": N_SEEDS,
        "n_seeds_in_bootstrap": N_SEEDS_BOOT,
        "n_bootstrap": N_BOOT,
        "n_power_reps": N_POWER,
        "seed": SEED,
        "selection": selection,
        "confound": confound,
        "costs": costs,
    }
    OUT_PATH.write_text(json.dumps(out, indent=1) + "\n")
    print(f"[selection_replay] wrote {OUT_PATH}", flush=True)
    return out


if __name__ == "__main__":
    run()

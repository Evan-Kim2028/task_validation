"""Task durability: capability curves over model tiers (doc 63).

A good task today that the next model generation solves is not a good
task. Every in-scope task in the Harbor-Adapter dump carries trials from
16 models spanning weak to frontier, so each task has a capability curve:
how much its solve rate rises as model capability rises. A steep curve
saturates soon. A flat curve at moderate difficulty endures. A flat curve
at zero is usually a broken task, which the execution certificate already
catches (doc 32, doc 35).

Capability ordering is derived from the data, not asserted: each model's
overall solve rate across all in-scope tasks orders the 16 models, and the
ordered list splits into three tiers of roughly equal size (6/5/5).
Ordering models by their own aggregate performance and then measuring
per-task slope against that ordering is circular at the population level:
a model ranks high because it solves many tasks, so the top tier is
guaranteed a higher pooled rate than the bottom tier and the population
median slope is positive by construction. It is not circular at the task
level: the ordering only says which models are stronger on average, and a
single task's slope is an honest estimate of how much its own solve rate
changes between the weaker and stronger halves of that ordering. The
population median slope is licensed as a descriptive statistic of the
dump, not as evidence that tasks in general rise; a per-task slope and
its bootstrap interval are licensed as measurements of that task.

External labels (the 82 published Harbor-Index survivors) are eval-only
(doc 43). No model output enters a bound; nothing here is a bound.
"""

from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path

from task_validation.evidence.harbor_funnel import (
    EXEC_FEATURES,
    INDEX_TO_MANIFEST,
    SHORTCUT_FEATURES,
    TRAJ_FEATURES,
    _fit_logit_fast,
    _FRONTIER_BUNDLE_MAP,
    _oof_predict,
    eval_label,
    load_in_scope_trials,
    within_benchmark_eval,
)
from task_validation.evidence.irt import mann_whitney_u

REPO_ROOT = Path(__file__).resolve().parents[3]
GOLD = REPO_ROOT / "data" / "gold"

TRIALS_PATH = GOLD / "harbor_adapter_trials.jsonl"
STAGE1_PATH = GOLD / "harbor_funnel_stage1.jsonl"
TASK_TRAJ_PATH = GOLD / "harbor_adapter_task_traj.jsonl"
TIERS_PATH = GOLD / "model_tiers.json"
CURVES_PATH = GOLD / "task_capability_curves.jsonl"
CURVES_SUMMARY_PATH = GOLD / "task_capability_curves.summary.json"
PREDICTION_PATH = GOLD / "durability_prediction.json"
BENCH_PATH = GOLD / "durability_benchmarks.json"
TB4_PATH = GOLD / "durability_tb4.json"
LOT001_PATH = GOLD / "durability_lot001.json"

TB4_RAW = Path("/home/evan/Documents/eval_tasks/analysis/tb4/raw")
LOT001_GATE_C = Path(
    "/home/evan/Documents/eval_tasks/lots/lot-001/gate_c/gate_c.summary.json"
)

PROTOCOL = "durability.capability_curve.2026-09-14"

MIN_TIER_TRIALS = 3  # eligibility: >=3 trials in bottom and top tiers
LEVEL_EPS = 0.05  # floored: every tier rate <= eps; ceilinged: every >= 1-eps
SLOPE_SATURATING = 0.40  # preliminary-pass "steep" cutoff
SLOPE_DURABLE = 0.10  # "low slope" cutoff for the durable class
N_BOOT_SLOPE = 400
BOOT_SEED = 20260914

# Feature set for the durability model (doc 40 model class: median
# imputation, missingness indicators, standardized design, L2 logit).
# EXEC_FEATURES + TRAJ + verifier + shortcut, all readable from
# harbor_funnel_stage1.jsonl and harbor_adapter_task_traj.jsonl alone.
# The two failed-test-signature features (ver_top_failed_share,
# ver_n_distinct_failed_tests) live only in the per-trial trajectory
# extract, not in the two joined inputs named for this analysis, and are
# excluded.
VERIFIER_FEATURES = (
    "ver_has_report_json_rate",
    "ver_n_tests_total_mean",
    "ver_n_tests_failed_mean",
    "ver_reward_partial_rate",
)
PREDICTION_FEATURES = EXEC_FEATURES + TRAJ_FEATURES + VERIFIER_FEATURES + SHORTCUT_FEATURES
# Reward-derived stage-1 fields (frontier_solve_rate, cell_rate_*) are a
# near-deterministic function of the same trials the label is built from,
# so they are excluded from the eval matrix, matching the doc 52/54 rule.


def model_overall_rates(rows: list[dict]) -> dict:
    """Overall in-scope solve rate per model across all tasks."""
    stats: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in rows:
        m = r.get("model")
        if m is None:
            continue
        stats[m][0] += 1
        stats[m][1] += 1 if (r.get("reward") is not None and r["reward"] > 0) else 0
    return {
        m: {"n_trials": n, "n_succ": s, "solve_rate": s / n}
        for m, (n, s) in stats.items()
    }


def split_tiers(ordered: list, n_tiers: int = 3) -> list[list]:
    """Contiguous tiers over an ordered list, first tiers get the remainder.

    Same convention as numpy.array_split: 16 -> sizes 6, 5, 5;
    13 -> 5, 4, 4; 7 -> 3, 2, 2.
    """
    n = len(ordered)
    base, rem = divmod(n, n_tiers)
    out, i = [], 0
    for k in range(n_tiers):
        size = base + (1 if k < rem else 0)
        out.append(ordered[i : i + size])
        i += size
    return out


def assign_tiers(rates: dict) -> dict:
    """Order models by overall solve rate; split into bottom/mid/top tiers."""
    ordered = sorted(rates, key=lambda m: (rates[m]["solve_rate"], m))
    tiers = split_tiers(ordered, 3)
    model_entries = []
    tier_of = {}
    tier_name = {}
    for name, members in zip(("bottom", "mid", "top"), tiers):
        for m in members:
            tier_name[m] = name
    for rank, m in enumerate(ordered):
        tier = tier_name[m]
        tier_of[m] = tier
        model_entries.append(
            {
                "model": m,
                "rank": rank,
                "tier": tier,
                "n_trials": rates[m]["n_trials"],
                "n_succ": rates[m]["n_succ"],
                "solve_rate": rates[m]["solve_rate"],
            }
        )
    return {
        "ordered": ordered,
        "tiers": {"bottom": list(tiers[0]), "mid": list(tiers[1]), "top": list(tiers[2])},
        "tier_of": tier_of,
        "models": model_entries,
    }


def task_tier_cells(rows: list[dict], tier_of: dict) -> dict:
    """Per (benchmark, task_name): per-tier list of per-model (n, succ) cells."""
    per_task: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: [0, 0])))
    for r in rows:
        tier = tier_of.get(r.get("model"))
        if tier is None:
            continue
        cell = per_task[(r["benchmark"], r["task_name"])][tier][r["model"]]
        cell[0] += 1
        cell[1] += 1 if (r.get("reward") is not None and r["reward"] > 0) else 0
    return {
        key: {
            tier: dict(models)
            for tier, models in tiers.items()
        }
        for key, tiers in per_task.items()
    }


def _rate(cells: dict) -> tuple[float | None, int, int]:
    n = sum(c[0] for c in cells.values())
    s = sum(c[1] for c in cells.values())
    return (s / n if n else None), n, s


def capability_curve(tiers: dict) -> dict:
    """Solve rate per tier, slope (top minus bottom), level (mid rate)."""
    cells_b = tiers.get("bottom", {})
    cells_m = tiers.get("mid", {})
    cells_t = tiers.get("top", {})
    b, nb, sb = _rate(cells_b)
    m, nm, sm = _rate(cells_m)
    t, nt, st = _rate(cells_t)
    eligible = nb >= MIN_TIER_TRIALS and nt >= MIN_TIER_TRIALS
    slope = (t - b) if (b is not None and t is not None) else None
    level = m if m is not None else (
        ((b + t) / 2.0) if (b is not None and t is not None) else None
    )
    return {
        "rate_bottom": b,
        "rate_mid": m,
        "rate_top": t,
        "n_bottom": nb,
        "n_mid": nm,
        "n_top": nt,
        "succ_bottom": sb,
        "succ_mid": sm,
        "succ_top": st,
        "eligible": eligible,
        "slope": slope,
        "level": level,
        "cells": {"bottom": cells_b, "mid": cells_m, "top": cells_t},
    }


def slope_bootstrap(
    tiers: dict, n_reps: int = N_BOOT_SLOPE, seed: int = BOOT_SEED
) -> dict:
    """Percentile interval on the slope, per-model-cell parametric bootstrap.

    Each model cell in a tier redraws its success count from
    Binomial(n_cell, observed cell rate), so width reflects per-model
    heterogeneity inside a tier rather than treating all tier trials as
    exchangeable. Seeded per task for reproducibility.
    """
    rng = random.Random(seed)
    cells_b = list(tiers.get("bottom", {}).values())
    cells_t = list(tiers.get("top", {}).values())
    nb = sum(c[0] for c in cells_b)
    nt = sum(c[0] for c in cells_t)
    if nb < MIN_TIER_TRIALS or nt < MIN_TIER_TRIALS:
        return {"ci95": None, "n_bootstrap": n_reps, "n_defined": 0}
    slopes = []
    for _ in range(n_reps):
        sb = sum(
            rng.binomialvariate(c[0], c[1] / c[0]) for c in cells_b
        )
        st = sum(
            rng.binomialvariate(c[0], c[1] / c[0]) for c in cells_t
        )
        slopes.append(st / nt - sb / nb)
    slopes.sort()
    i_lo = 0.025 * (n_reps - 1)
    i_hi = 0.975 * (n_reps - 1)

    def _interp(i):
        lo = int(i)
        hi = min(lo + 1, n_reps - 1)
        w = i - lo
        return slopes[lo] * (1 - w) + slopes[hi] * w

    return {
        "ci95": [_interp(i_lo), _interp(i_hi)],
        "n_bootstrap": n_reps,
        "n_defined": n_reps,
    }


def classify(curve: dict) -> str:
    """floored / ceilinged / saturating / rising / durable.

    Floored: every measured tier rate <= LEVEL_EPS (level at or near zero
    in every tier). Ceilinged: every measured tier rate >= 1 - LEVEL_EPS.
    Saturating: slope above SLOPE_SATURATING. Durable: slope at or below
    SLOPE_DURABLE with the level neither floor nor ceiling. Rising: the
    residual mid-level tasks between the durable and saturating cutoffs.
    """
    rates = [
        r
        for r in (curve["rate_bottom"], curve["rate_mid"], curve["rate_top"])
        if r is not None
    ]
    if not curve["eligible"] or not rates or curve["slope"] is None:
        return "unmeasured"
    if all(r <= LEVEL_EPS for r in rates):
        return "floored"
    if all(r >= 1.0 - LEVEL_EPS for r in rates):
        return "ceilinged"
    if curve["slope"] > SLOPE_SATURATING:
        return "saturating"
    if curve["slope"] <= SLOPE_DURABLE:
        return "durable"
    return "rising"


def _pct(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    ys = sorted(xs)
    i = p * (len(ys) - 1)
    lo = int(i)
    hi = min(lo + 1, len(ys) - 1)
    w = i - lo
    return ys[lo] * (1 - w) + ys[hi] * w


def _median(xs: list[float]) -> float | None:
    return _pct(xs, 0.5)


def build_curves(rows: list[dict], tiers: dict) -> list[dict]:
    """One capability-curve record per in-scope task."""
    per_task = task_tier_cells(rows, tiers["tier_of"])
    out = []
    for (benchmark, task_name), t in sorted(per_task.items()):
        curve = capability_curve(t)
        rec = {
            "benchmark": benchmark,
            "task_name": task_name,
            "n_bottom": curve["n_bottom"],
            "succ_bottom": curve["succ_bottom"],
            "rate_bottom": curve["rate_bottom"],
            "n_mid": curve["n_mid"],
            "succ_mid": curve["succ_mid"],
            "rate_mid": curve["rate_mid"],
            "n_top": curve["n_top"],
            "succ_top": curve["succ_top"],
            "rate_top": curve["rate_top"],
            "slope": curve["slope"],
            "level": curve["level"],
            "eligible": curve["eligible"],
            "cls": classify(curve) if curve["eligible"] else "unmeasured",
        }
        out.append(rec)
    return out


def add_bootstrap(records: list[dict], per_task: dict, n_reps: int = N_BOOT_SLOPE) -> None:
    """Attach a seeded slope interval to each eligible record, in place."""
    for i, rec in enumerate(records):
        if not rec["eligible"]:
            rec["slope_ci95"] = None
            continue
        key = (rec["benchmark"], rec["task_name"])
        boot = slope_bootstrap(
            per_task[key], n_reps=n_reps, seed=BOOT_SEED + i
        )
        rec["slope_ci95"] = boot["ci95"]


def write_tiers(tiers: dict, out_path: Path = TIERS_PATH) -> dict:
    doc = {
        "protocol": PROTOCOL,
        "method": (
            "models ordered by overall solve rate over all in-scope "
            "harbor_adapter_trials.jsonl rows; ordered list split into "
            "three contiguous tiers of sizes 6/5/5 (array_split convention, "
            "first tiers take the remainder)"
        ),
        "circularity": (
            "ordering models by their own aggregate performance and then "
            "measuring per-task slope against that ordering is circular at "
            "the population level (the top tier is guaranteed a higher "
            "pooled rate, so the population median slope is positive by "
            "construction) but not at the task level: a per-task slope "
            "honestly measures how that task's solve rate changes between "
            "the weaker and stronger thirds of the ordering. The "
            "population median is descriptive; only per-task slopes are "
            "measurements."
        ),
        "tiers": tiers["tiers"],
        "models": tiers["models"],
    }
    out_path.write_text(json.dumps(doc, indent=1) + "\n")
    return doc


def curves_summary(records: list[dict]) -> dict:
    elig = [r for r in records if r["eligible"]]
    slopes = [r["slope"] for r in elig]
    levels = [r["level"] for r in elig if r["level"] is not None]
    classes = defaultdict(int)
    for r in elig:
        classes[r["cls"]] += 1
    by_bench = defaultdict(lambda: {"n": 0, "slopes": [], "levels": [], "classes": defaultdict(int)})
    for r in elig:
        s = by_bench[r["benchmark"]]
        s["n"] += 1
        s["slopes"].append(r["slope"])
        if r["level"] is not None:
            s["levels"].append(r["level"])
        s["classes"][r["cls"]] += 1
    bench_table = {
        b: {
            "n": s["n"],
            "slope_median": _median(s["slopes"]),
            "level_median": _median(s["levels"]),
            "classes": dict(s["classes"]),
        }
        for b, s in sorted(by_bench.items())
    }
    return {
        "protocol": PROTOCOL,
        "n_tasks_in_scope": len(records),
        "n_eligible": len(elig),
        "min_tier_trials": MIN_TIER_TRIALS,
        "level_eps": LEVEL_EPS,
        "slope_saturating": SLOPE_SATURATING,
        "slope_durable": SLOPE_DURABLE,
        "slope_median": _median(slopes),
        "slope_p10": _pct(slopes, 0.10),
        "slope_p90": _pct(slopes, 0.90),
        "level_median": _median(levels),
        "n_slope_le_0": sum(1 for s in slopes if s <= 0),
        "n_slope_gt_saturating": sum(1 for s in slopes if s > SLOPE_SATURATING),
        "classes": dict(classes),
        "by_benchmark": bench_table,
        "preliminary_pass_comparison": {
            "stated": {
                "n_eligible": 6613,
                "slope_median": 0.13,
                "slope_p10": 0.00,
                "slope_p90": 0.46,
                "n_flat_or_negative": 2234,
                "n_rising_gt_040": 921,
            },
            "note": (
                "n_eligible, median and p10 reproduce exactly under this "
                "module's definitions (6/5/5 tiers, >=3 trials per tier, "
                "pooled tier rates, success = reward > 0). p90, the flat "
                "count and the steep count do not: this pipeline computes "
                "p90 = %.4f, rise <= 0 = %d, rise > 0.40 = %d. The stated "
                "flat count would need a cutoff of rise <= ~0.058 and the "
                "steep count a cutoff of ~0.42; neither has a defensible "
                "reading, so the discrepancy is reported and this "
                "pipeline's frozen definitions stand."
                % (
                    _pct(slopes, 0.90),
                    sum(1 for s in slopes if s <= 0),
                    sum(1 for s in slopes if s > SLOPE_SATURATING),
                )
            ),
        },
    }


def _load_jsonl(path: Path) -> list[dict]:
    rows = []
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def build_prediction_records(
    stage1_rows: list[dict], task_traj_rows: list[dict], curves: list[dict]
) -> list[dict]:
    """Join curve labels onto stage-1 + trajectory features."""
    traj_by_pair = {(r["benchmark"], r["task_name"]): r for r in task_traj_rows}
    s1_by_pair = {(r["benchmark"], r["task_name"]): r for r in stage1_rows}
    records = []
    for c in curves:
        if not c["eligible"] or c["cls"] == "floored":
            continue
        key = (c["benchmark"], c["task_name"])
        s1 = s1_by_pair.get(key) or {}
        fb = (traj_by_pair.get(key) or {}).get("frontier") or {}
        feats = {k: s1.get(k) for k in EXEC_FEATURES}
        for dst, src in _FRONTIER_BUNDLE_MAP.items():
            if dst in PREDICTION_FEATURES:
                feats[dst] = fb.get(src)
        records.append(
            {
                "benchmark": c["benchmark"],
                "task_name": c["task_name"],
                "cls": c["cls"],
                "slope": c["slope"],
                "level": c["level"],
                "durable": int(c["cls"] == "durable"),
                "survived_stage1": s1.get("survived_stage1"),
                "features": feats,
            }
        )
    return records


def run_prediction(records: list[dict], seed: int = BOOT_SEED) -> dict:
    """Doc 40 model class on durable-vs-rest among non-floored tasks."""
    rows = records
    y = [r["durable"] for r in rows]
    feats = PREDICTION_FEATURES
    lobo = eval_label(rows, y, feats, fold_key="benchmark", fitter=_fit_logit_fast, seed=seed)
    oof, _fold_aurocs, _n_undef = _oof_predict(rows, y, feats, "benchmark", _fit_logit_fast)
    within = within_benchmark_eval(rows, y, oof, seed=seed)
    univariate = []
    for f in feats:
        e = eval_label(rows, y, (f,), fold_key="benchmark", fitter=_fit_logit_fast, seed=seed)
        univariate.append({"feature": f, "lobo_auroc": e["lobo_auroc"], "ci95": e["lobo_ci95"]})
    univariate.sort(key=lambda d: -(d["lobo_auroc"] or 0.0))
    return {
        "protocol": PROTOCOL,
        "label": "durable = slope <= 0.10 and mid-level, among non-floored eligible tasks",
        "features": list(feats),
        "n": len(y),
        "n_pos": sum(y),
        "lobo": lobo,
        "within_benchmark": within,
        "univariate_top10": univariate[:10],
        "univariate_all": univariate,
    }


def benchmark_table(records: list[dict], top_n: int = 20) -> list[dict]:
    elig = [r for r in records if r["eligible"]]
    by_b = defaultdict(list)
    for r in elig:
        by_b[r["benchmark"]].append(r)
    rows = sorted(by_b.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:top_n]
    table = []
    for b, rs in rows:
        slopes = [r["slope"] for r in rs]
        levels = [r["level"] for r in rs if r["level"] is not None]
        cls = defaultdict(int)
        for r in rs:
            cls[r["cls"]] += 1
        table.append(
            {
                "benchmark": b,
                "n": len(rs),
                "slope_median": _median(slopes),
                "slope_p25": _pct(slopes, 0.25),
                "slope_p75": _pct(slopes, 0.75),
                "level_median": _median(levels),
                "n_durable": cls["durable"],
                "n_rising": cls["rising"],
                "n_saturating": cls["saturating"],
                "n_floored": cls["floored"],
                "n_ceilinged": cls["ceilinged"],
            }
        )
    return table


def funnel_comparison(records: list[dict], stage1_rows: list[dict]) -> dict:
    """The 82 published survivors vs the stage-1 survivors the funnel rejected."""
    s1 = {(r["benchmark"], r["task_name"]): r for r in stage1_rows}
    kept_pairs = {pair for pair in INDEX_TO_MANIFEST.values() if pair is not None}
    groups = {"kept": [], "rejected_survivor": [], "not_stage1": []}
    for r in records:
        if not r["eligible"]:
            continue
        key = (r["benchmark"], r["task_name"])
        if key in kept_pairs:
            groups["kept"].append(r)
        elif s1.get(key, {}).get("survived_stage1"):
            groups["rejected_survivor"].append(r)
        else:
            groups["not_stage1"].append(r)

    def _dist(rs):
        slopes = [r["slope"] for r in rs]
        levels = [r["level"] for r in rs if r["level"] is not None]
        cls = defaultdict(int)
        for r in rs:
            cls[r["cls"]] += 1
        return {
            "n": len(rs),
            "slope_median": _median(slopes),
            "slope_p25": _pct(slopes, 0.25),
            "slope_p75": _pct(slopes, 0.75),
            "level_median": _median(levels),
            "classes": dict(cls),
        }

    kept, rejected = groups["kept"], groups["rejected_survivor"]
    mw = mann_whitney_u(
        [r["slope"] for r in kept], [r["slope"] for r in rejected]
    ) if kept and rejected else None
    return {
        "kept_82_pairs": len(kept_pairs),
        "kept_eligible": _dist(kept),
        "rejected_stage1_survivors": _dist(rejected),
        "not_stage1_survivors": _dist(groups["not_stage1"]),
        "slope_mann_whitney_kept_vs_rejected": mw,
    }


def score_tb4(raw_dir: Path = TB4_RAW) -> dict:
    """Capability curve over the 13 TB4 submissions (one model each).

    Each *.trials.json row is one scored trial (66 tasks x 5 trials per
    submission). Tiers come from the same data-derived ordering as the
    harbor analysis: models ordered by pooled solve rate over the 66
    tasks, split 5/4/4.
    """
    cells_by_task: dict = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    model_totals: dict = defaultdict(lambda: [0, 0])
    for path in sorted(raw_dir.glob("*.trials.json")):
        for entry in json.loads(path.read_text()):
            if entry.get("is_scored") is False:
                continue
            metrics = ((entry.get("evals") or {}).get("reward") or {}).get("metrics")
            if metrics:
                reward = metrics[0].get("reward")
            else:
                reward = entry.get("reward")
            succ = 1 if (reward is not None and reward > 0) else 0
            cell = cells_by_task[entry["task_name"]][entry["model_name"]]
            cell[0] += 1
            cell[1] += succ
            model_totals[entry["model_name"]][0] += 1
            model_totals[entry["model_name"]][1] += succ
    models = sorted(model_totals)
    model_stats = {
        m: {"n_trials": model_totals[m][0], "solve_rate": model_totals[m][1] / model_totals[m][0]}
        for m in models
    }
    ordered = sorted(models, key=lambda m: (model_stats[m]["solve_rate"], m))
    tiers = split_tiers(ordered, 3)
    tier_of = {
        m: "top" if m in tiers[2] else "mid" if m in tiers[1] else "bottom"
        for m in ordered
    }
    task_rows = []
    for task in sorted(cells_by_task):
        cells = {"bottom": {}, "mid": {}, "top": {}}
        for m, cell in cells_by_task[task].items():
            cells[tier_of[m]][m] = list(cell)
        curve = capability_curve(cells)
        task_rows.append(
            {
                "task": task,
                "n_bottom": curve["n_bottom"],
                "n_mid": curve["n_mid"],
                "n_top": curve["n_top"],
                "rate_bottom": curve["rate_bottom"],
                "rate_mid": curve["rate_mid"],
                "rate_top": curve["rate_top"],
                "slope": curve["slope"],
                "level": curve["level"],
                "cls": classify(curve),
                "per_model": {
                    m: (c[1] / c[0] if c[0] else None)
                    for m, c in cells_by_task[task].items()
                },
            }
        )
    cls_counts = defaultdict(int)
    for r in task_rows:
        cls_counts[r["cls"]] += 1
    return {
        "protocol": PROTOCOL,
        "source": str(raw_dir),
        "note": (
            "13 submissions, one model each, 5 scored trials per task; "
            "tiers are the same data-derived ordering as the harbor "
            "analysis (5/4/4 split over 13 models)."
        ),
        "models": [
            {
                "model": m,
                "tier": tier_of[m],
                "solve_rate": model_stats[m]["solve_rate"],
                "n_trials": model_stats[m]["n_trials"],
            }
            for m in ordered
        ],
        "tasks": task_rows,
        "classes": dict(cls_counts),
    }


def score_lot001(path: Path = LOT001_GATE_C) -> dict:
    summary = json.loads(path.read_text())
    tasks = [
        {"task": t["task"], "solve_rate": t["solve_rate"], "n_trials": t["n_trials"], "band": t["band"]}
        for t in summary["tasks"]
    ]
    return {
        "protocol": PROTOCOL,
        "source": str(path),
        "note": (
            "lot-001 gate C ran one agent only (devin/swe-2-max, k<=3 "
            "trials per task), so no capability ordering exists inside the "
            "lot: slope is unavailable and only the level (single-agent "
            "solve rate) is computable. The band labels are gate C's own "
            "[0.10, 0.70] difficulty band (doc 50)."
        ),
        "agent": summary.get("agent"),
        "band": summary.get("band"),
        "overall_solve_rate": summary.get("overall_solve_rate"),
        "n_tasks": len(tasks),
        "tasks": tasks,
    }


def run() -> dict:
    print("[durability] loading in-scope trials", flush=True)
    rows = load_in_scope_trials(TRIALS_PATH)
    rates = model_overall_rates(rows)
    tiers = assign_tiers(rates)
    tier_doc = write_tiers(tiers)
    print(f"[durability] tiers: {[(t, len(ms)) for t, ms in tiers['tiers'].items()]}", flush=True)

    per_task = task_tier_cells(rows, tiers["tier_of"])
    records = build_curves(rows, tiers)
    print(f"[durability] curves for {len(records)} tasks; bootstrapping slopes", flush=True)
    add_bootstrap(records, per_task)

    with CURVES_PATH.open("w") as fh:
        for rec in records:
            out = {k: v for k, v in rec.items()}
            fh.write(json.dumps(out) + "\n")
    summary = curves_summary(records)
    summary["inputs"] = {"trials": str(TRIALS_PATH), "tiers": str(TIERS_PATH), "curves": str(CURVES_PATH)}
    CURVES_SUMMARY_PATH.write_text(json.dumps(summary, indent=1) + "\n")
    print(f"[durability] eligible={summary['n_eligible']} classes={summary['classes']}", flush=True)

    stage1_rows = _load_jsonl(STAGE1_PATH)
    task_traj_rows = _load_jsonl(TASK_TRAJ_PATH)
    pred_records = build_prediction_records(stage1_rows, task_traj_rows, records)
    prediction = run_prediction(pred_records)
    PREDICTION_PATH.write_text(json.dumps(prediction, indent=1) + "\n")
    print(f"[durability] prediction n={prediction['n']} pos={prediction['n_pos']} lobo={prediction['lobo']['lobo_auroc']}", flush=True)

    bench = {
        "protocol": PROTOCOL,
        "top20_by_task_count": benchmark_table(records, top_n=20),
        "funnel_comparison": funnel_comparison(records, stage1_rows),
    }
    BENCH_PATH.write_text(json.dumps(bench, indent=1) + "\n")

    tb4 = score_tb4()
    TB4_PATH.write_text(json.dumps(tb4, indent=1) + "\n")
    lot001 = score_lot001()
    LOT001_PATH.write_text(json.dumps(lot001, indent=1) + "\n")

    return {
        "tiers": tier_doc,
        "summary": summary,
        "prediction": prediction,
        "benchmarks": bench,
        "tb4": tb4,
        "lot001": lot001,
    }


if __name__ == "__main__":
    run()

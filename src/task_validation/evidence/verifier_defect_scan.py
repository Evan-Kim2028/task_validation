"""Retrospective verifier-defect and anti-hack gate scan (doc 66).

Doc 64 found, by hand, a task whose verifier logged one score and wrote a
different reward (`sldbench-discover-vocab-scaling-law`: stdout claimed
0.966, reward.txt contained 0). The trajectory extract
(`harbor_adapter_traj.jsonl`) keeps both written reward channels:

* ``reward_txt_value`` — parsed from ``verifier/reward.txt`` (None when the
  member is absent or unparseable; unparseable is marked in
  ``parse_error`` as ``"verifier/reward.txt: not a float"``),
* ``reward`` — the counted reward: ``reward_txt_value`` when present, else
  ``result.json`` ``verifier_result.rewards.reward``.

Because ``reward`` collapses onto ``reward_txt_value`` whenever reward.txt
parses, the within-file "mismatch" is degenerate by construction; the
verifier's *logged* score is not in the extract at all (only
``test_stdout_bytes``). The computable form of the doc-64 defect is the
two-written-channel disagreement ``reward.txt`` vs ``result.json``
``verifier_result.rewards.reward``. ``harbor_funnel_rewards.jsonl`` keeps
the full ``result`` dict for every in-scope fetched trial, so the scan
joins it to the trajectory extract on ``trial_id``.

Anti-hack flags (``mentions_answer_file``, ``git_history_probe``,
``network_fetch``) are assistant-text regex counts; a trial trips a flag
when the count is > 0.

Everything here is eval-only evidence (doc 43): the funnel labels are
external and never enter a bound. All inputs are read-only; both files are
streamed line by line and only per-task counters are retained.

Outputs: ``data/gold/verifier_defect_scan.json`` (report) and
``data/gold/verifier_defect_scan_tasks.jsonl`` (one row per task).

    PYTHONPATH=src python -m task_validation.evidence.verifier_defect_scan
"""

from __future__ import annotations

import argparse
import json
import math
import resource
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from task_validation.evidence.harbor_funnel import (
    EXEC_FEATURES,
    FRONTIER_CELLS,
    _fit_logit_fast,
    _label_vector,
    benchmark_family,
    eval_label,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
GOLD = REPO_ROOT / "data" / "gold"

TRAJ_PATH = GOLD / "harbor_adapter_traj.jsonl"
FUNNEL_PATH = GOLD / "harbor_funnel_rewards.jsonl"
LABELS_PATH = GOLD / "harbor_funnel_labels.jsonl"
STAGE1_PATH = GOLD / "harbor_funnel_stage1.jsonl"
OUT_JSON = GOLD / "verifier_defect_scan.json"
OUT_TASKS = GOLD / "verifier_defect_scan_tasks.jsonl"

PROTOCOL = "verifier_defect_scan.2026-09-15"
DISAGREE_EPS = 1e-9
# A disagreement smaller than this is a repr/precision artifact, not a defect.
MATERIAL_EPS = 1e-6
FLAG_KEYS = ("mentions_answer_file", "git_history_probe", "network_fetch")
_FRONTIER_SET = frozenset(FRONTIER_CELLS)
MAX_STORED_DIFFS = 250_000
UNPARSEABLE_MARK = "reward.txt: not a float"
MIN_SOLVED_FOR_ELEVATION = 3  # solved trials needed before a flag lift is reported


# ---------------------------------------------------------------------------
# Small pure helpers
# ---------------------------------------------------------------------------


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _finite(v) -> bool:
    return _is_num(v) and math.isfinite(v)


def _solved(row: dict) -> bool:
    return row.get("reward") == 1.0


def channel_diff(txt_value, json_value) -> float | None:
    """|reward.txt - result.json reward|, or None when not comparable.

    Non-finite reward.txt values (nan/inf parse as floats) are reported
    separately by the caller, never as a diff.
    """
    if not _finite(txt_value) or not _finite(json_value):
        return None
    return abs(txt_value - json_value)


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float | None, float | None]:
    """Wilson score interval for a binomial proportion."""
    if n <= 0:
        return None, None
    p = k / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, center - half), min(1.0, center + half)


def cell_rate_var(rates: list[float]) -> float | None:
    """Population variance of per-cell solve rates; None with < 2 cells."""
    if len(rates) < 2:
        return None
    m = sum(rates) / len(rates)
    return sum((r - m) ** 2 for r in rates) / len(rates)


def json_channel_reward(row: dict):
    """result.verifier_result.rewards.reward from a funnel row, or None."""
    res = row.get("result")
    if not isinstance(res, dict):
        return None
    vr = res.get("verifier_result")
    if not isinstance(vr, dict):
        return None
    rw = vr.get("rewards")
    if not isinstance(rw, dict):
        return None
    v = rw.get("reward")
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Streaming accumulators
# ---------------------------------------------------------------------------


def _new_flag_acc() -> dict:
    return {
        "n_obs": 0,  # flag field present (trajectory parsed)
        "n_pos": 0,  # flag tripped (count > 0)
        "n_pos_robs": 0,  # tripped and reward observed
        "n_pos_solved": 0,  # tripped and reward == 1
        "n_neg": 0,
        "n_neg_robs": 0,
        "n_neg_solved": 0,
    }


def _new_bundle() -> dict:
    return {
        "n": 0,
        "n_robs": 0,
        "n_solved": 0,
        "n_partial": 0,  # 0 < reward < 1
        "flags": {f: _new_flag_acc() for f in FLAG_KEYS},
    }


def _bundle_add(b: dict, row: dict) -> None:
    reward = row.get("reward")
    robs = _is_num(reward)
    solved = reward == 1.0
    b["n"] += 1
    b["n_robs"] += int(robs)
    b["n_solved"] += int(solved)
    b["n_partial"] += int(robs and 0.0 < reward < 1.0)
    for f in FLAG_KEYS:
        v = row.get(f)
        if v is None:
            continue
        fa = b["flags"][f]
        fa["n_obs"] += 1
        pos = _is_num(v) and v > 0
        if pos:
            fa["n_pos"] += 1
            fa["n_pos_robs"] += int(robs)
            fa["n_pos_solved"] += int(solved)
        else:
            fa["n_neg"] += 1
            fa["n_neg_robs"] += int(robs)
            fa["n_neg_solved"] += int(solved)


def new_task_acc() -> dict:
    return {
        "all": _new_bundle(),
        "frontier": _new_bundle(),
        # reward-channel bookkeeping
        "n_txt_present": 0,
        "n_txt_absent": 0,
        "n_txt_unparseable": 0,
        "n_reward_from_json": 0,
        "n_no_reward": 0,
        "n_nonfinite_txt": 0,
        "n_internal_mismatch": 0,
        # cross-channel join vs funnel result.json
        "n_joined": 0,
        "n_join_both": 0,
        "n_join_disagree": 0,
        "n_join_disagree_material": 0,
        "n_join_txt_only": 0,
        "n_join_json_only": 0,
        "join_diff_sum": 0.0,
        "join_diff_max": 0.0,
        "join_pairs": Counter(),  # (txt, json) -> count over disagreeing trials
        "join_disagree_trials": [],  # capped sample for the report
    }


def acc_traj_row(acc: dict, row: dict, funnel_rb: dict | None) -> float | None:
    """Fold one trajectory row into the per-task accumulator.

    ``funnel_rb`` is the funnel-file channel for this trial_id:
    {"json_reward": float|None} or None when the trial is not in the
    funnel file. Returns the |txt - json| diff when the trial joined and
    disagreed, else None.
    """
    _bundle_add(acc["all"], row)
    if (row.get("agent"), row.get("model")) in _FRONTIER_SET:
        _bundle_add(acc["frontier"], row)

    txt = row.get("reward_txt_value")
    reward = row.get("reward")
    unparseable = UNPARSEABLE_MARK in (row.get("parse_error") or "")
    txt_ok = False
    if txt is None:
        if unparseable:
            acc["n_txt_unparseable"] += 1
        else:
            acc["n_txt_absent"] += 1
        if _is_num(reward):
            acc["n_reward_from_json"] += 1
        else:
            acc["n_no_reward"] += 1
    elif not math.isfinite(txt):
        acc["n_nonfinite_txt"] += 1
    else:
        txt_ok = True
        acc["n_txt_present"] += 1
        # reward collapses onto reward_txt_value at ingest, so this counts
        # extraction bugs, not verifier defects; kept as an invariant check.
        if not _is_num(reward) or abs(reward - txt) > DISAGREE_EPS:
            acc["n_internal_mismatch"] += 1

    if funnel_rb is None:
        return None
    acc["n_joined"] += 1
    rb = funnel_rb.get("json_reward")
    d = channel_diff(txt if txt_ok else None, rb)
    if d is not None:
        acc["n_join_both"] += 1
        if d > DISAGREE_EPS:
            acc["n_join_disagree"] += 1
            acc["join_diff_sum"] += d
            acc["join_diff_max"] = max(acc["join_diff_max"], d)
            acc["join_pairs"][(txt, rb)] += 1
            if d > MATERIAL_EPS:
                acc["n_join_disagree_material"] += 1
            if len(acc["join_disagree_trials"]) < 25:
                acc["join_disagree_trials"].append(
                    {"trial_id": row.get("trial_id"), "reward_txt": txt, "reward_json": rb}
                )
            return d
    elif txt_ok:
        acc["n_join_txt_only"] += 1
    elif rb is not None:
        acc["n_join_json_only"] += 1
    return None


def _frac(num: float, den: float):
    return num / den if den else None


def _flag_summary(fa: dict) -> dict:
    """Rates and solve-conditional rates for one flag accumulator."""
    n_flagged_solved_obs = fa["n_pos_solved"] + fa["n_neg_solved"]
    n_pos_unsolved = fa["n_pos_robs"] - fa["n_pos_solved"]
    n_neg_unsolved = fa["n_neg_robs"] - fa["n_neg_solved"]
    n_unsolved = n_pos_unsolved + n_neg_unsolved
    return {
        "n_obs": fa["n_obs"],
        "n_pos": fa["n_pos"],
        "p_flag": _frac(fa["n_pos"], fa["n_obs"]),
        "n_pos_robs": fa["n_pos_robs"],
        "n_pos_solved": fa["n_pos_solved"],
        "p_solved_given_flag": _frac(fa["n_pos_solved"], fa["n_pos_robs"]),
        "n_neg_robs": fa["n_neg_robs"],
        "n_neg_solved": fa["n_neg_solved"],
        "p_solved_given_noflag": _frac(fa["n_neg_solved"], fa["n_neg_robs"]),
        "n_solved_flag_obs": n_flagged_solved_obs,
        "p_flag_given_solved": _frac(fa["n_pos_solved"], n_flagged_solved_obs),
        "n_unsolved_flag_obs": n_unsolved,
        "n_pos_unsolved": n_pos_unsolved,
        "p_flag_given_unsolved": _frac(n_pos_unsolved, n_unsolved),
    }


def finalize_task(key: tuple[str, str], acc: dict) -> dict:
    """Flatten one task accumulator into the per-task report row."""
    benchmark, task_name = key
    n_both = acc["n_join_both"]
    rec = {
        "benchmark": benchmark,
        "task_name": task_name,
        "n_trials": acc["all"]["n"],
        "n_reward_obs": acc["all"]["n_robs"],
        "n_solved": acc["all"]["n_solved"],
        "solve_rate": _frac(acc["all"]["n_solved"], acc["all"]["n_robs"]),
        "n_partial": acc["all"]["n_partial"],
        "n_frontier_trials": acc["frontier"]["n"],
        "n_frontier_solved": acc["frontier"]["n_solved"],
        "n_txt_present": acc["n_txt_present"],
        "n_txt_absent": acc["n_txt_absent"],
        "n_txt_unparseable": acc["n_txt_unparseable"],
        "n_reward_from_json": acc["n_reward_from_json"],
        "n_no_reward": acc["n_no_reward"],
        "n_nonfinite_txt": acc["n_nonfinite_txt"],
        "n_internal_mismatch": acc["n_internal_mismatch"],
        "n_joined": acc["n_joined"],
        "n_join_both": acc["n_join_both"],
        "n_join_disagree": acc["n_join_disagree"],
        "n_join_disagree_material": acc["n_join_disagree_material"],
        "n_join_txt_only": acc["n_join_txt_only"],
        "n_join_json_only": acc["n_join_json_only"],
        "join_disagree_rate": _frac(acc["n_join_disagree"], n_both),
        "join_disagree_rate_material": _frac(acc["n_join_disagree_material"], n_both),
        "join_diff_max": acc["join_diff_max"] if acc["n_join_disagree"] else None,
        "join_diff_mean": _frac(acc["join_diff_sum"], acc["n_join_disagree"]),
        "top_disagree_pairs": [
            {"reward_txt": t, "reward_json": j, "n": c}
            for (t, j), c in acc["join_pairs"].most_common(3)
        ],
        "flags_all": {f: _flag_summary(acc["all"]["flags"][f]) for f in FLAG_KEYS},
        "flags_frontier": {
            f: _flag_summary(acc["frontier"]["flags"][f]) for f in FLAG_KEYS
        },
    }
    return rec


# ---------------------------------------------------------------------------
# File scans
# ---------------------------------------------------------------------------


def _peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


class _Stage:
    """Wall-clock and peak-RSS recorder; ru_maxrss is a running peak."""

    def __init__(self, costs: dict, name: str):
        self.costs, self.name = costs, name

    def __enter__(self):
        self.t0 = time.monotonic()
        return self

    def __exit__(self, *exc):
        self.costs[self.name] = {
            "wall_sec": round(time.monotonic() - self.t0, 3),
            "peak_rss_mb_at_end": round(_peak_rss_mb(), 1),
        }
        return False


def scan_funnel_rewards(path: Path) -> dict:
    """Stream the funnel file: trial channels, per-task cell stats, crosstab."""
    trial_channel: dict[str, dict] = {}
    cells: Counter = Counter()
    agents: Counter = Counter()
    models: Counter = Counter()
    task_cells: dict[tuple, dict] = {}
    n = n_dup = n_json_reward = n_merged = 0
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            n += 1
            tid = row.get("trial_id")
            jr = json_channel_reward(row)
            if tid in trial_channel:
                n_dup += 1
            trial_channel[tid] = {
                "json_reward": jr,
                "merged_reward": row.get("reward"),
            }
            n_json_reward += int(jr is not None)
            n_merged += int(row.get("reward") is not None)
            cell = (row.get("agent"), row.get("model"))
            cells[cell] += 1
            agents[row.get("agent")] += 1
            models[row.get("model")] += 1
            key = (row.get("benchmark"), row.get("task_name"))
            tc = task_cells.setdefault(key, defaultdict(lambda: [0, 0, 0]))
            cs = tc[cell]
            reward = row.get("reward")
            cs[0] += 1
            cs[1] += int(_is_num(reward))
            cs[2] += int(reward == 1.0)
    return {
        "trial_channel": trial_channel,
        "task_cells": task_cells,
        "cell_counts": {f"{a}|{m}": c for (a, m), c in cells.items()},
        "agent_counts": dict(agents),
        "model_counts": dict(models),
        "n_rows": n,
        "n_duplicate_trial_ids": n_dup,
        "n_json_reward": n_json_reward,
        "n_merged_reward": n_merged,
    }


def scan_traj(path: Path, trial_channel: dict) -> dict:
    """Stream the trajectory extract; one pass accumulates everything."""
    tasks: dict[tuple, dict] = {}
    glob = new_task_acc()
    per_benchmark: dict[str, dict] = {}
    all_diffs: list[float] = []
    n = n_scope = 0
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            n += 1
            n_scope += int(bool(row.get("in_scope")))
            fb = trial_channel.get(row.get("trial_id"))
            d = acc_traj_row(glob, row, fb)
            key = (row.get("benchmark"), row.get("task_name"))
            acc = tasks.get(key)
            if acc is None:
                acc = tasks[key] = new_task_acc()
            acc_traj_row(acc, row, fb)
            ba = per_benchmark.get(row.get("benchmark"))
            if ba is None:
                ba = per_benchmark[row.get("benchmark")] = new_task_acc()
            acc_traj_row(ba, row, fb)
            if d is not None and len(all_diffs) < MAX_STORED_DIFFS:
                all_diffs.append(d)
    return {
        "tasks": tasks,
        "global": glob,
        "per_benchmark": per_benchmark,
        "all_diffs": all_diffs,
        "n_rows": n,
        "n_in_scope": n_scope,
    }


# ---------------------------------------------------------------------------
# Task 1: reward-disagreement scan
# ---------------------------------------------------------------------------


def _quantiles(xs: list[float]) -> dict:
    if not xs:
        return {"n": 0}
    s = sorted(xs)
    n = len(s)

    def q(p):
        return s[min(n - 1, max(0, int(round(p * (n - 1)))))]

    return {
        "n": n,
        "min": s[0],
        "p50": q(0.5),
        "p90": q(0.9),
        "p99": q(0.99),
        "max": s[-1],
        "mean": sum(s) / n,
    }


def task1_report(scan: dict, task_recs: list[dict]) -> dict:
    g = scan["global"]
    glob_pairs = Counter()
    for acc in scan["tasks"].values():
        glob_pairs.update(acc["join_pairs"])
    affected = [r for r in task_recs if r["n_join_disagree"] > 0]
    affected.sort(
        key=lambda r: (
            -r["n_join_disagree"],
            -(r["join_diff_max"] or 0.0),
            r["benchmark"],
            r["task_name"],
        )
    )
    by_bench = Counter(r["benchmark"] for r in affected)
    trials_by_bench = Counter()
    for r in affected:
        trials_by_bench[r["benchmark"]] += r["n_join_disagree"]
    top20 = [
        {
            "benchmark": r["benchmark"],
            "task_name": r["task_name"],
            "n_trials": r["n_trials"],
            "n_join_both": r["n_join_both"],
            "n_disagree": r["n_join_disagree"],
            "disagree_rate": r["join_disagree_rate"],
            "max_abs_diff": r["join_diff_max"],
            "top_pairs": r["top_disagree_pairs"],
            "solve_rate": r["solve_rate"],
        }
        for r in affected[:20]
    ]
    return {
        "definition": (
            "reward.txt value vs result.json verifier_result.rewards.reward, "
            "joined on trial_id between harbor_adapter_traj.jsonl and "
            "harbor_funnel_rewards.jsonl; disagree when |diff| > 1e-9 "
            "(material when > 1e-6). Coverage is limited to the 6,627 "
            "funnel candidates' fetched trials."
        ),
        "n_traj_rows": scan["n_rows"],
        "n_traj_in_scope": scan["n_in_scope"],
        "within_file_invariant": {
            "n_txt_present": g["n_txt_present"],
            "n_internal_mismatch": g["n_internal_mismatch"],
            "note": (
                "reward collapses onto reward_txt_value at ingest, so a "
                "nonzero count is an extraction bug, not a verifier defect"
            ),
        },
        "channel_presence": {
            "n_txt_present": g["n_txt_present"],
            "n_txt_absent": g["n_txt_absent"],
            "n_txt_unparseable": g["n_txt_unparseable"],
            "n_nonfinite_txt": g["n_nonfinite_txt"],
            "n_reward_from_json_fallback": g["n_reward_from_json"],
            "n_no_reward": g["n_no_reward"],
        },
        "join": {
            "n_joined_trials": g["n_joined"],
            "n_both_channels": g["n_join_both"],
            "n_disagree": g["n_join_disagree"],
            "n_disagree_material": g["n_join_disagree_material"],
            "n_txt_only": g["n_join_txt_only"],
            "n_json_only": g["n_join_json_only"],
            "disagree_rate": _frac(g["n_join_disagree"], g["n_join_both"]),
            "n_tasks_affected": len(affected),
            "n_benchmarks_affected": len(by_bench),
            "tasks_affected_by_benchmark": dict(by_bench.most_common()),
            "trials_affected_by_benchmark": dict(trials_by_bench.most_common()),
            "diff_magnitude": _quantiles(scan["all_diffs"]),
            "top_disagree_pairs": [
                {"reward_txt": t, "reward_json": j, "n": c}
                for (t, j), c in glob_pairs.most_common(10)
            ],
        },
        "top20_tasks": top20,
    }


# ---------------------------------------------------------------------------
# Task 2: anti-hack flag base rates and solve-conditional rates
# ---------------------------------------------------------------------------


def _flag_block(fa_summary: dict) -> dict:
    """Attach Wilson intervals to one flag summary.

    Wilson rather than the repo's binomial_ci: _binom_sf underflows q**n to
    0.0 for n beyond ~1.5e3 at small p, so the Clopper-Pearson bounds in
    footprint.binomial_ci silently collapse on these cell sizes (verified:
    binomial_ci(35486, 783135) returns lo > hi).
    """
    out = dict(fa_summary)
    out["p_flag_ci95"] = wilson(fa_summary["n_pos"], fa_summary["n_obs"])
    out["p_solved_given_flag_ci95"] = wilson(
        fa_summary["n_pos_solved"], fa_summary["n_pos_robs"]
    )
    out["p_solved_given_noflag_ci95"] = wilson(
        fa_summary["n_neg_solved"], fa_summary["n_neg_robs"]
    )
    n_sf = fa_summary["n_solved_flag_obs"]
    out["p_flag_given_solved_ci95"] = (
        wilson(fa_summary["n_pos_solved"], n_sf) if n_sf else None
    )
    return out


def task2_report(scan: dict, task_recs: list[dict]) -> dict:
    g = scan["global"]
    pooled = {
        f: _flag_block(_flag_summary(g["all"]["flags"][f])) for f in FLAG_KEYS
    }
    per_benchmark = {}
    for bench, acc in sorted(scan["per_benchmark"].items()):
        per_benchmark[bench] = {
            "n_trials": acc["all"]["n"],
            "n_solved": acc["all"]["n_solved"],
            **{f: _flag_block(_flag_summary(acc["all"]["flags"][f])) for f in FLAG_KEYS},
        }
    # Tasks whose solved trials trip a flag at an elevated rate: Wilson lower
    # bound on P(flag|solved) strictly above the Wilson upper bound on
    # P(flag|unsolved) for the same task; plus tasks where every observed
    # solved trial tripped the flag.
    elevated = {}
    only_solved_flagged = {}
    for f in FLAG_KEYS:
        el, only = [], []
        for r in task_recs:
            fs = r["flags_all"][f]
            n_sf = fs["n_solved_flag_obs"]
            if n_sf >= MIN_SOLVED_FOR_ELEVATION:
                lo_s, _ = wilson(fs["n_pos_solved"], n_sf)
                _, hi_u = wilson(fs["n_pos_unsolved"], fs["n_unsolved_flag_obs"])
                if lo_s is not None and hi_u is not None and lo_s > hi_u:
                    el.append(
                        {
                            "benchmark": r["benchmark"],
                            "task_name": r["task_name"],
                            "n_solved_flag_obs": n_sf,
                            "n_solved_flagged": fs["n_pos_solved"],
                            "p_flag_given_solved": fs["p_flag_given_solved"],
                            "p_flag_given_solved_lo": lo_s,
                            "n_unsolved_flag_obs": fs["n_unsolved_flag_obs"],
                            "n_unsolved_flagged": fs["n_pos_unsolved"],
                            "p_flag_given_unsolved": fs["p_flag_given_unsolved"],
                            "p_flag_given_unsolved_hi": hi_u,
                            "solve_rate": r["solve_rate"],
                        }
                    )
            if n_sf >= 1 and fs["n_pos_solved"] == n_sf:
                only.append(
                    {
                        "benchmark": r["benchmark"],
                        "task_name": r["task_name"],
                        "n_solved_flag_obs": n_sf,
                        "p_flag_overall": fs["p_flag"],
                        "n_obs": fs["n_obs"],
                    }
                )
        el.sort(
            key=lambda d: (
                -(d["p_flag_given_solved_lo"] or 0),
                -d["n_solved_flag_obs"],
                d["benchmark"],
                d["task_name"],
            )
        )
        only.sort(key=lambda d: (-d["n_solved_flag_obs"], d["benchmark"], d["task_name"]))
        elevated[f] = el
        only_solved_flagged[f] = only
    return {
        "flag_definition": "trial trips flag iff assistant-text regex count > 0",
        "min_solved_for_elevation": MIN_SOLVED_FOR_ELEVATION,
        "elevation_rule": (
            "Wilson-95 lower bound on P(flag|solved) strictly above Wilson-95 "
            "upper bound on P(flag|unsolved) within the same task"
        ),
        "pooled": pooled,
        "per_benchmark": per_benchmark,
        "elevated_tasks": {f: v[:50] for f, v in elevated.items()},
        "n_elevated_tasks": {f: len(v) for f, v in elevated.items()},
        "all_solved_trips_flag_tasks": {f: v[:50] for f, v in only_solved_flagged.items()},
        "n_all_solved_trips_flag": {f: len(v) for f, v in only_solved_flagged.items()},
    }


# ---------------------------------------------------------------------------
# Task 4: per-cell discrimination
# ---------------------------------------------------------------------------


def cell_task_stats(task_cells: dict) -> dict[tuple, dict]:
    """Per task: pooled rate, across-cell variance, spread, cell count."""
    out = {}
    for key, cells in task_cells.items():
        rates = []
        per_cell = {}
        n_tot = n_obs = n_solved = 0
        terminus_rates = []
        for (agent, model), (n, nobs, nsol) in cells.items():
            rate = nsol / nobs if nobs else None
            per_cell[f"{agent}|{model}"] = {"n": n, "n_obs": nobs, "n_solved": nsol, "rate": rate}
            n_tot += n
            n_obs += nobs
            n_solved += nsol
            if rate is not None:
                rates.append(rate)
                if agent == "terminus-2":
                    terminus_rates.append(rate)
        out[key] = {
            "n_trials": n_tot,
            "n_cells": len(rates),
            "pooled_solve_rate": _frac(n_solved, n_obs),
            "cell_rate_var": cell_rate_var(rates),
            "cell_rate_spread": (max(rates) - min(rates)) if len(rates) >= 2 else None,
            "terminus_model_var": cell_rate_var(terminus_rates),
            "cells": per_cell,
        }
    return out


# ---------------------------------------------------------------------------
# Task 3/4 eval: join flags to funnel labels, LOBO/LOFO AUROC
# ---------------------------------------------------------------------------

DEFECT_FEATURES = (
    "def_disagree_rate",
    "def_n_disagree",
    "def_txt_absent_rate",
    "def_txt_unparseable_rate",
    "def_json_fallback_rate",
    "def_no_reward_rate",
    "def_max_abs_diff",
)
HACK_RATE_FEATURES = tuple(
    f"hack_{short}_rate_{scope}"
    for short in ("ans", "git", "net")
    for scope in ("all", "frontier")
)
HACK_COND_FEATURES = tuple(
    f"hack_{short}_{stat}"
    for short in ("ans", "git", "net")
    for stat in ("solved_share", "lift")
)
CELL_FEATURES = (
    "cell_pooled_rate",
    "cell_rate_var",
    "cell_rate_spread",
    "n_cells_obs",
    "cell_terminus_model_var",
)

_FLAG_SHORT = {
    "mentions_answer_file": "ans",
    "git_history_probe": "git",
    "network_fetch": "net",
}


def defect_features(rec: dict | None) -> dict:
    if rec is None:
        return {k: None for k in DEFECT_FEATURES}
    n = rec["n_trials"]
    return {
        "def_disagree_rate": rec["join_disagree_rate"],
        "def_n_disagree": float(rec["n_join_disagree"]) if rec["n_joined"] else None,
        "def_txt_absent_rate": _frac(rec["n_txt_absent"], n),
        "def_txt_unparseable_rate": _frac(rec["n_txt_unparseable"], n),
        "def_json_fallback_rate": _frac(rec["n_reward_from_json"], n),
        "def_no_reward_rate": _frac(rec["n_no_reward"], n),
        "def_max_abs_diff": rec["join_diff_max"],
    }


def hack_features(rec: dict | None) -> dict:
    out = {k: None for k in HACK_RATE_FEATURES + HACK_COND_FEATURES}
    if rec is None:
        return out
    for f, short in _FLAG_SHORT.items():
        for scope in ("all", "frontier"):
            fs = rec[f"flags_{scope}"][f]
            out[f"hack_{short}_rate_{scope}"] = fs["p_flag"]
        fs = rec["flags_all"][f]
        out[f"hack_{short}_solved_share"] = fs["p_flag_given_solved"]
        if (
            fs["p_flag_given_solved"] is not None
            and fs["p_flag_given_unsolved"] is not None
        ):
            out[f"hack_{short}_lift"] = (
                fs["p_flag_given_solved"] - fs["p_flag_given_unsolved"]
            )
    return out


def cell_features(cs: dict | None) -> dict:
    if cs is None:
        return {k: None for k in CELL_FEATURES}
    return {
        "cell_pooled_rate": cs["pooled_solve_rate"],
        "cell_rate_var": cs["cell_rate_var"],
        "cell_rate_spread": cs["cell_rate_spread"],
        "n_cells_obs": float(cs["n_cells"]),
        "cell_terminus_model_var": cs["terminus_model_var"],
    }


def build_eval_records(
    label_rows: list[dict],
    stage1_rows: list[dict],
    task_recs: list[dict],
    task_cell_stats: dict,
) -> list[dict]:
    s1 = {(r["benchmark"], r["task_name"]): r for r in stage1_rows}
    flags = {(r["benchmark"], r["task_name"]): r for r in task_recs}
    records = []
    for lab in label_rows:
        key = (lab["benchmark"], lab["task_name"])
        feats = {k: (s1.get(key) or {}).get(k) for k in EXEC_FEATURES}
        feats.update(defect_features(flags.get(key)))
        feats.update(hack_features(flags.get(key)))
        feats.update(cell_features(task_cell_stats.get(key)))
        records.append(
            {
                "benchmark": lab["benchmark"],
                "task_name": lab["task_name"],
                "family": benchmark_family(lab["benchmark"]),
                "survived_stage1": lab["survived_stage1"],
                "survived_funnel": lab["survived_funnel"],
                "survived_2_to_4": lab["survived_2_to_4"],
                "features": feats,
            }
        )
    return records


def run_evals(records: list[dict]) -> dict:
    sets = {
        "A": EXEC_FEATURES,
        "E": DEFECT_FEATURES,
        "H": HACK_RATE_FEATURES,
        "H_full": HACK_RATE_FEATURES + HACK_COND_FEATURES,
        "E+H": DEFECT_FEATURES + HACK_RATE_FEATURES,
        "A+E+H": EXEC_FEATURES + DEFECT_FEATURES + HACK_RATE_FEATURES,
        "V": CELL_FEATURES,
        "A+V": EXEC_FEATURES + CELL_FEATURES,
    }
    evals = {}
    for label in ("survived_2_to_4", "survived_funnel"):
        y, rows = _label_vector(records, label)
        per = {}
        for name, feats in sets.items():
            per[name] = {
                "lobo": eval_label(
                    rows, y, feats, fold_key="benchmark", fitter=_fit_logit_fast
                ),
                "lofo": eval_label(
                    rows, y, feats, fold_key="family", fitter=_fit_logit_fast
                ),
            }
            print(
                f"[defect_scan] {label} {name} "
                f"lobo={per[name]['lobo']['lobo_auroc']} "
                f"lofo={per[name]['lofo']['lobo_auroc']}",
                flush=True,
            )
        evals[label] = per
    # Univariate LOBO for every new feature (defect, hack, cell).
    new_feats = DEFECT_FEATURES + HACK_RATE_FEATURES + HACK_COND_FEATURES + CELL_FEATURES
    univariate = {}
    for label in ("survived_2_to_4", "survived_funnel"):
        y, rows = _label_vector(records, label)
        uv = []
        for f in new_feats:
            e = eval_label(rows, y, (f,), fold_key="benchmark", fitter=_fit_logit_fast)
            uv.append({"feature": f, "lobo_auroc": e["lobo_auroc"], "ci95": e["lobo_ci95"]})
        uv.sort(key=lambda d: -(d["lobo_auroc"] or 0.0))
        univariate[label] = uv
    return {"sets": evals, "univariate": univariate}


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def _load_jsonl(path: Path) -> list[dict]:
    rows = []
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def run_scan(
    traj_path: Path = TRAJ_PATH,
    funnel_path: Path = FUNNEL_PATH,
    labels_path: Path = LABELS_PATH,
    stage1_path: Path = STAGE1_PATH,
    out_json: Path = OUT_JSON,
    out_tasks: Path = OUT_TASKS,
) -> dict:
    costs: dict = {}
    t_all = time.monotonic()

    with _Stage(costs, "scan_funnel_rewards"):
        fun = scan_funnel_rewards(funnel_path)
    print(f"[defect_scan] funnel rows={fun['n_rows']}", flush=True)

    with _Stage(costs, "scan_traj"):
        scan = scan_traj(traj_path, fun["trial_channel"])
    print(
        f"[defect_scan] traj rows={scan['n_rows']} tasks={len(scan['tasks'])}",
        flush=True,
    )

    with _Stage(costs, "finalize_tasks"):
        task_recs = [
            finalize_task(k, acc)
            for k, acc in sorted(scan["tasks"].items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1])))
        ]

    with _Stage(costs, "task1_report"):
        t1 = task1_report(scan, task_recs)
    print(
        f"[defect_scan] disagree trials={t1['join']['n_disagree']} "
        f"tasks={t1['join']['n_tasks_affected']}",
        flush=True,
    )

    with _Stage(costs, "task2_report"):
        t2 = task2_report(scan, task_recs)

    with _Stage(costs, "cell_stats"):
        tcs = cell_task_stats(fun["task_cells"])
        crosstab = {
            "cell_counts": fun["cell_counts"],
            "agent_counts": fun["agent_counts"],
            "model_counts": fun["model_counts"],
            "n_funnel_rows": fun["n_rows"],
            "n_json_reward": fun["n_json_reward"],
            "n_merged_reward": fun["n_merged_reward"],
            "n_duplicate_trial_ids": fun["n_duplicate_trial_ids"],
            "design_note": (
                "terminus-2 crosses all three models; claude-code, codex and "
                "gemini-cli are each pinned to one model, so harness and "
                "model effects are separable only inside terminus-2"
            ),
        }

    with _Stage(costs, "eval_join_and_models"):
        labels = _load_jsonl(labels_path)
        stage1 = _load_jsonl(stage1_path)
        records = build_eval_records(labels, stage1, task_recs, tcs)
        evals = run_evals(records)

    costs["total"] = {
        "wall_sec": round(time.monotonic() - t_all, 3),
        "peak_rss_mb_at_end": round(_peak_rss_mb(), 1),
    }

    out = {
        "protocol": PROTOCOL,
        "inputs": {
            "traj": str(traj_path),
            "funnel_rewards": str(funnel_path),
            "labels": str(labels_path),
            "stage1": str(stage1_path),
        },
        "feature_groups": {
            "E_defect": list(DEFECT_FEATURES),
            "H_hack_rates": list(HACK_RATE_FEATURES),
            "H_hack_conditional": list(HACK_COND_FEATURES),
            "V_cell": list(CELL_FEATURES),
        },
        "task1_reward_disagreement": t1,
        "task2_antihack": t2,
        "task4_cells": {
            "crosstab": crosstab,
            "n_tasks_with_ge2_cells": sum(
                1 for v in tcs.values() if v["cell_rate_var"] is not None
            ),
            "n_tasks_full_terminus_cross": sum(
                1 for v in tcs.values() if v["terminus_model_var"] is not None
            ),
        },
        "task3_task4_evals": evals,
        "costs": costs,
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_json.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    tmp.replace(out_json)
    with out_tasks.open("w", encoding="utf-8") as fh:
        for r in task_recs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="verifier-defect-scan")
    p.add_argument("--traj", default=str(TRAJ_PATH))
    p.add_argument("--funnel", default=str(FUNNEL_PATH))
    p.add_argument("--labels", default=str(LABELS_PATH))
    p.add_argument("--stage1", default=str(STAGE1_PATH))
    p.add_argument("--out", default=str(OUT_JSON))
    p.add_argument("--out-tasks", default=str(OUT_TASKS))
    args = p.parse_args(argv)
    run_scan(
        traj_path=Path(args.traj),
        funnel_path=Path(args.funnel),
        labels_path=Path(args.labels),
        stage1_path=Path(args.stage1),
        out_json=Path(args.out),
        out_tasks=Path(args.out_tasks),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""One-class typicality of the expert-kept region (doc 60).

The question is descriptive, not discriminative: what region of feature
space do the 82 expert-kept Harbor-Index tasks occupy, and does a new
candidate task or lot land inside it. The kept set is described, not
separated from a contrast class.

Feature space is the union of what each population carries:

- harbor funnel populations (kept, rejected stage-1 survivors, and the
  non-stage-1 candidate pool) carry the doc 52/54 behaviour features:
  execution cost (group A), the frontier solve profile, trajectory (B),
  verifier (C) and shortcut (D) rates. Static layout features are
  unavailable for candidates because task directories were never fetched
  (doc 52).
- the kept set additionally carries the doc 40 static and execution-gate
  features from `data/gold/footprint.jsonl` population `harbor_index`.
- TB 2.1 and SWE-bench reference populations carry the doc 40 static set
  (footprint populations `tb21` and `swe`; the task-id sets equal
  `tb21_census.jsonl` and `swe_verified_features.jsonl` respectively).
- a generated lot (lot-001) carries the static set, the gate A execution
  fields, and the subset of behaviour features derivable from its gate C
  trial outputs (devin/swe-2-max, k=3) without docker.

Every distance is computed on the task's observed features intersected
with the features the reference fit informs (marginalized Mahalanobis):
a feature a population never observes contributes nothing rather than
being imputed. Typicality is the share of the kept set's leave-one-out
distances that are at least as large as the task's distance, so a kept
task scores about 0.5 at the median by construction.

Three variants handle the source confound (the kept set spans many
benchmarks, and much of its shape is benchmark identity):

- pooled: one region over the whole kept cloud.
- per_source: one region per benchmark's kept subset; a task's score is
  its best typicality over sources. This asks whether the task resembles
  any one expert-kept source rather than the average of all of them.
- desourced: the pooled region refit after dropping every feature whose
  one-way ANOVA across the kept set's benchmarks explains more than
  ANOVA_ETA2_MAX of its variance.

No label is imputed. External labels (survived_funnel) define the kept
set itself and remain eval-only (doc 43). Nothing here enters a bound.

Run: `python -m task_validation.evidence.typicality run`.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from task_validation.evidence.footprint import (
    FEATURE_NAMES as FOOTPRINT_FEATURE_NAMES,
    layout_static_features,
    load_jsonl,
    write_json,
    write_jsonl,
)
from task_validation.evidence.harbor_funnel import (
    EXEC_FEATURES,
    SHORTCUT_FEATURES,
    TRAJ_FEATURES,
    _FRONTIER_BUNDLE_MAP,
)
from task_validation.ingest.harbor_adapter_traj import _traj_stats

REPO_ROOT = Path(__file__).resolve().parents[3]
GOLD = REPO_ROOT / "data" / "gold"
EVAL_TASKS_ROOT = Path("/home/evan/Documents/eval_tasks")

LABELS_PATH = GOLD / "harbor_funnel_labels.jsonl"
STAGE1_PATH = GOLD / "harbor_funnel_stage1.jsonl"
TASK_TRAJ_PATH = GOLD / "harbor_adapter_task_traj.jsonl"
FOOTPRINT_PATH = GOLD / "footprint.jsonl"
STRATA_PATH = GOLD / "harbor_index_strata.json"
TB21_CENSUS_PATH = GOLD / "tb21_census.jsonl"
SWE_FEATURES_PATH = GOLD / "swe_verified_features.jsonl"

LOT001_ROOT = EVAL_TASKS_ROOT / "lots" / "lot-001"
OUT_REGION_PATH = GOLD / "typicality_kept_region.json"
OUT_LOT_PATH = GOLD / "typicality_lot001.jsonl"

PROTOCOL = "typicality_kept_region.2026-09-14"

# Behaviour features carried by harbor funnel populations. The six
# per-cell rates and frontier_n_succ are deterministic functions of the
# stage-1 solve rate and are dropped to keep the count near n.
REWARD_CORE = ("frontier_solve_rate", "reward_var", "all_trials_solve_rate")
VERIFIER_BUNDLE = (
    "ver_has_report_json_rate",
    "ver_n_tests_total_mean",
    "ver_n_tests_failed_mean",
    "ver_reward_partial_rate",
)
BEHAVIOR_FEATURES = (
    tuple(EXEC_FEATURES)
    + REWARD_CORE
    + tuple(TRAJ_FEATURES)
    + VERIFIER_BUNDLE
    + tuple(SHORTCUT_FEATURES)
)

# Doc 40 footprint features that are numeric and populated somewhere in
# footprint.jsonl. solve_rate_band is categorical and never enters.
EXEC_GATE_FEATURES = (
    "reference_pass",
    "nop_reject",
    "determinism",
    "environment_failure",
)
STATIC_FEATURES = tuple(
    f
    for f in FOOTPRINT_FEATURE_NAMES
    if f not in EXEC_GATE_FEATURES and f != "solve_rate_band"
)
ALL_FEATURES = BEHAVIOR_FEATURES + STATIC_FEATURES + EXEC_GATE_FEATURES

# Skewed counts and durations get log1p before kept-set statistics, the
# same convention as footprint.LOG1P_FEATURES extended to the traj analogs.
LOG1P_FEATURES = frozenset(
    {
        "n_all_trials",
        "input_tokens_mean",
        "cache_tokens_mean",
        "output_tokens_mean",
        "cost_usd_mean",
        "cost_usd_total",
        "agent_wall_sec_mean",
        "traj_n_steps_mean",
        "traj_n_tool_calls_mean",
        "traj_assistant_chars_mean",
        "traj_observation_chars_mean",
        "traj_agent_wall_sec_mean",
        "ver_n_tests_total_mean",
        "ver_n_tests_failed_mean",
        "ver_n_distinct_failed_tests",
        "instruction_chars",
        "instruction_lines",
        "stmt_n_identifiers",
        "test_file_count",
        "assertion_count",
        "literal_pins_absent",
        "solution_size",
        "resource_memory_mb",
        "timeout_sec",
        "n_fail_to_pass",
        "n_pass_to_pass",
        "patch_n_changed_lines",
        "test_n_changed_lines",
        "hints_chars",
        "n_attempted",
    }
)

# A feature enters the kept description only when at least this many kept
# tasks carry an observed value, and only when its kept-set spread is
# nonzero. Group C verifier fields fail the floor on the kept set (doc 54:
# named failed tests parse only for skillsbench in this extract).
MIN_KEPT_OBS = 10
# De-sourced variant: drop a feature when a one-way ANOVA across the kept
# set's benchmarks explains more than this share of its variance.
ANOVA_ETA2_MAX = 0.5
# Shrunk covariance: shrink toward the identity until the smallest
# eigenvalue reaches this fraction, with the plug-in ratio p/(n+p) as a
# floor on the shrinkage weight.
EIG_FLOOR_FRAC = 0.05
KDE_DIMS = 3
KDE_MIN_LOADING_MASS = 0.6
CAND_SAMPLE_N = 1000
CAND_SAMPLE_SEED = "typicality-v0"
# A feature counts toward a population's scoring mask when at least this
# share of the population's tasks observe it.
MASK_COVER_MIN = 0.5

VARIANTS = ("pooled", "per_source", "desourced")
CALIBRATION_POPS = ("kept", "rejected", "cand_sample", "tb21", "swe")


def _np():
    import numpy as np

    return np


def _transform(feature: str, value) -> float | None:
    if isinstance(value, bool):
        value = 1.0 if value else 0.0
    if value is None:
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    if feature in LOG1P_FEATURES:
        if x < 0:
            return None
        return math.log1p(x)
    return x


def transform_features(raw: dict) -> dict:
    return {f: _transform(f, raw.get(f)) for f in ALL_FEATURES}


# ---------------------------------------------------------------------------
# Feature assembly
# ---------------------------------------------------------------------------


def harbor_behavior_by_pair() -> dict[tuple[str, str], dict]:
    """Behaviour features per (benchmark, task_name): stage-1 execution
    and reward core plus the frontier bundle of the trajectory aggregate."""
    stage1 = {(r["benchmark"], r["task_name"]): r for r in load_jsonl(STAGE1_PATH)}
    out: dict[tuple[str, str], dict] = {}
    for r in load_jsonl(TASK_TRAJ_PATH):
        key = (r["benchmark"], r["task_name"])
        s1 = stage1.get(key) or {}
        fb = r.get("frontier") or {}
        feats = {f: s1.get(f) for f in EXEC_FEATURES}
        for f in REWARD_CORE:
            feats[f] = s1.get(f)
        for dst, src in _FRONTIER_BUNDLE_MAP.items():
            feats[dst] = fb.get(src)
        out[key] = feats
    for key, s1 in stage1.items():
        if key in out:
            continue
        feats = {f: s1.get(f) for f in EXEC_FEATURES}
        for f in REWARD_CORE:
            feats[f] = s1.get(f)
        out[key] = feats
    return out


def footprint_feature_rows(population: str) -> list[dict]:
    rows = []
    for r in load_jsonl(FOOTPRINT_PATH):
        if r.get("population") != population:
            continue
        rows.append(
            {
                "task_id": r["task_id"],
                "population": population,
                "features": transform_features(r.get("features") or {}),
            }
        )
    return rows


def build_populations() -> dict[str, list[dict]]:
    """Assemble every scored population.

    kept: the 82 harbor_index ids from harbor_index_strata.json, static
    features from footprint.jsonl, behaviour features joined through the
    funnel labels' index_task_id (81 of 82; dacode-predict-essay-scores
    has no manifest pair, doc 52).
    rejected: stage-1 survivors not on the published list.
    cand_sample: fixed-seed random draw of non-stage-1 candidates.
    tb21 / swe: footprint populations.
    """
    labels = load_jsonl(LABELS_PATH)
    behavior = harbor_behavior_by_pair()
    strata = json.loads(STRATA_PATH.read_text())
    kept_ids = set()
    for ids in strata["ids_by_stratum"].values():
        kept_ids |= set(ids)

    by_index = {r.get("index_task_id"): r for r in labels if r.get("index_task_id")}
    kept = []
    for fp in footprint_feature_rows("harbor_index"):
        tid = fp["task_id"]
        if tid not in kept_ids:
            continue
        lab = by_index.get(tid)
        feats = dict(fp["features"])
        benchmark = "dacode"
        if lab is not None:
            benchmark = lab["benchmark"]
            feats.update(behavior.get((lab["benchmark"], lab["task_name"])) or {})
        kept.append(
            {
                "task_id": tid,
                "population": "kept",
                "benchmark": benchmark,
                "features": feats,
            }
        )

    rejected, pool, survivors = [], [], []
    for lab in labels:
        key = (lab["benchmark"], lab["task_name"])
        feats = transform_features(behavior.get(key) or {})
        row = {
            "task_id": f"{lab['benchmark']}/{lab['task_name']}",
            "benchmark": lab["benchmark"],
            "index_task_id": lab.get("index_task_id"),
            "features": feats,
        }
        if lab.get("survived_stage1"):
            survivors.append(row)
        if lab.get("survived_stage1") and not lab.get("survived_funnel"):
            row["population"] = "rejected"
            rejected.append(row)
        elif not lab.get("survived_stage1"):
            row["population"] = "non_stage1"
            pool.append(row)

    seed = int.from_bytes(hashlib.sha256(CAND_SAMPLE_SEED.encode()).digest()[:8], "big")
    rng = random.Random(seed)
    cand_sample = rng.sample(pool, min(CAND_SAMPLE_N, len(pool)))
    for r in cand_sample:
        r["population"] = "cand_sample"

    tb21_ids = {r["task_id"] for r in load_jsonl(TB21_CENSUS_PATH)}
    tb21 = [r for r in footprint_feature_rows("tb21") if r["task_id"] in tb21_ids]
    swe = footprint_feature_rows("swe")

    return {
        "kept": kept,
        "rejected": rejected,
        "survivors": survivors,
        "cand_sample": cand_sample,
        "tb21": tb21,
        "swe": swe,
    }


# ---------------------------------------------------------------------------
# lot-001 feature derivation (no docker)
# ---------------------------------------------------------------------------


def _gate_a_features(lot_root: Path) -> dict[str, dict]:
    out = {}
    for r in load_jsonl(lot_root / "gate_a.jsonl"):
        oracle = r.get("oracle") or {}
        nop = r.get("nop") or {}
        orew = oracle.get("rewards") or []
        nrew = nop.get("rewards") or []
        ref = 1.0 if orew and all(x > 0 for x in orew) else (0.0 if orew else None)
        nopr = 1.0 if nrew and all(x == 0 for x in nrew) else (0.0 if nrew else None)
        det = None
        if oracle.get("deterministic") is not None or nop.get("deterministic") is not None:
            det = 1.0 if (oracle.get("deterministic") and nop.get("deterministic")) else 0.0
        env = None
        if oracle.get("harbor_rc") is not None or nop.get("harbor_rc") is not None:
            env = 0.0 if (oracle.get("harbor_rc") == 0 and nop.get("harbor_rc") == 0) else 1.0
        out[r["task_id"]] = {
            "reference_pass": ref,
            "nop_reject": nopr,
            "determinism": det,
            "environment_failure": env,
        }
    return out


def _ctrf_stats(path: Path) -> dict:
    try:
        c = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    res = c.get("results") or {}
    summary = res.get("summary") or {}
    tests = res.get("tests") or []
    failed = [
        t.get("name")
        for t in tests
        if str(t.get("status")).lower() in ("failed", "error")
    ]
    n_failed = summary.get("failed")
    return {
        "n_tests_total": summary.get("tests"),
        "n_tests_failed": n_failed if n_failed is not None else len(failed),
        "failed_names": [n for n in failed if n],
    }


def _gate_c_trial_features(trial_dir: Path) -> dict:
    """One gate C trial dir: reward, exception, wall, tokens, ATIF traj
    stats, CTRF verifier counts."""
    try:
        res = json.loads((trial_dir / "result.json").read_text())
    except (OSError, ValueError):
        return {}
    out: dict = {}
    out["reward"] = ((res.get("verifier_result") or {}).get("rewards") or {}).get("reward")
    exc = res.get("exception_info")
    out["exception"] = bool(exc)
    exc_type = ""
    if isinstance(exc, dict):
        exc_type = str(exc.get("exception_type") or exc.get("type") or "")
    out["timeout"] = "timeout" in exc_type.lower()
    ag = res.get("agent_execution") or {}
    try:
        t0 = datetime.fromisoformat(str(ag["started_at"]).replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(str(ag["finished_at"]).replace("Z", "+00:00"))
        out["agent_wall_sec"] = (t1 - t0).total_seconds()
    except (KeyError, ValueError, TypeError):
        out["agent_wall_sec"] = None
    try:
        traj = json.loads((trial_dir / "agent" / "trajectory.json").read_text())
    except (OSError, ValueError):
        traj = None
    if traj is not None:
        out["traj"] = _traj_stats(traj)
        fm = traj.get("final_metrics") or {}
        out["input_tokens"] = fm.get("total_prompt_tokens")
        out["output_tokens"] = fm.get("total_completion_tokens")
        out["cache_tokens"] = fm.get("total_cached_tokens")
        out["cost_usd"] = fm.get("total_cost_usd")
    out["ctrf"] = _ctrf_stats(trial_dir / "verifier" / "ctrf.json")
    return out


def _trial_mean(trials: list[dict], key: str) -> float | None:
    xs = [t.get(key) for t in trials if t.get(key) is not None]
    return sum(xs) / len(xs) if xs else None


def _traj_mean(trials: list[dict], key: str) -> float | None:
    xs = [
        t["traj"].get(key)
        for t in trials
        if isinstance(t.get("traj"), dict) and t["traj"].get(key) is not None
    ]
    return sum(xs) / len(xs) if xs else None


def lot001_rows(lot_root: Path = LOT001_ROOT) -> tuple[list[dict], dict]:
    """Per-task features for the candidate lot. Returns (rows, meta)."""
    gate_a = _gate_a_features(lot_root)
    tasks_root = lot_root / "tasks"
    rows = []
    unavail: dict[str, list[str]] = {}
    for task_dir in sorted(p for p in tasks_root.iterdir() if p.is_dir()):
        tid = task_dir.name
        feats = transform_features(layout_static_features(task_dir))
        for k, v in gate_a.get(tid, {}).items():
            feats[k] = v
        # Gate C: canonical k=3 devin job dir only (redo dirs are retries).
        job = lot_root / "gate_c" / "jobs" / f"{tid}-devin-k3"
        trials = []
        if job.is_dir():
            for td in sorted(job.iterdir()):
                if td.is_dir() and td.name.startswith(f"{tid}__"):
                    tf = _gate_c_trial_features(td)
                    if tf:
                        trials.append(tf)
        gate_c: dict = {"n_trials": len(trials)}
        if trials:
            rewards = [t.get("reward") for t in trials]
            obs = [x for x in rewards if x is not None]
            feats["n_attempted"] = float(len(trials))
            feats["solve_rate"] = (
                sum(1 for x in obs if x > 0) / len(obs) if obs else None
            )
            feats["exception_rate"] = sum(t["exception"] for t in trials) / len(trials)
            feats["traj_exception_rate"] = feats["exception_rate"]
            feats["traj_hit_timeout_rate"] = sum(t["timeout"] for t in trials) / len(trials)
            wall = _trial_mean(trials, "agent_wall_sec")
            if wall is not None:
                feats["agent_wall_sec_mean"] = wall
                feats["traj_agent_wall_sec_mean"] = wall
            feats["traj_n_steps_mean"] = _traj_mean(trials, "n_steps")
            feats["traj_n_tool_calls_mean"] = _traj_mean(trials, "n_tool_calls")
            feats["traj_assistant_chars_mean"] = _traj_mean(trials, "total_assistant_chars")
            feats["traj_observation_chars_mean"] = _traj_mean(trials, "total_observation_chars")
            feats["input_tokens_mean"] = _trial_mean(trials, "input_tokens")
            feats["output_tokens_mean"] = _trial_mean(trials, "output_tokens")
            feats["cache_tokens_mean"] = _trial_mean(trials, "cache_tokens")
            feats["cost_usd_mean"] = _trial_mean(trials, "cost_usd")
            if len(obs) >= 2:
                mu = sum(obs) / len(obs)
                feats["reward_var"] = sum((x - mu) ** 2 for x in obs) / (len(obs) - 1)
            n_rep = sum(1 for t in trials if t.get("ctrf"))
            if n_rep:
                feats["ver_has_report_json_rate"] = n_rep / len(trials)
            nt = [t["ctrf"]["n_tests_total"] for t in trials if t.get("ctrf")]
            nt = [x for x in nt if x is not None]
            if nt:
                feats["ver_n_tests_total_mean"] = sum(nt) / len(nt)
            nf = [t["ctrf"]["n_tests_failed"] for t in trials if t.get("ctrf")]
            nf = [x for x in nf if x is not None]
            if nf:
                feats["ver_n_tests_failed_mean"] = sum(nf) / len(nf)
            cnt: Counter = Counter()
            n_failing = 0
            for t in trials:
                names = (t.get("ctrf") or {}).get("failed_names") or []
                if names:
                    n_failing += 1
                    for n in set(names):
                        cnt[n] += 1
            feats["ver_n_distinct_failed_tests"] = float(len(cnt))
            if n_failing and cnt:
                feats["ver_top_failed_share"] = cnt.most_common(1)[0][1] / n_failing
            if obs:
                feats["ver_reward_partial_rate"] = (
                    sum(1 for x in obs if 0 < x < 1) / len(obs)
                )
            for dst, key in (
                ("shortcut_answer_file_rate", "mentions_answer_file"),
                ("shortcut_git_probe_rate", "git_history_probe"),
                ("shortcut_network_fetch_rate", "network_fetch"),
            ):
                vals = [
                    t["traj"].get(key)
                    for t in trials
                    if isinstance(t.get("traj"), dict) and t["traj"].get(key) is not None
                ]
                if vals:
                    feats[dst] = sum(1 for v in vals if v > 0) / len(vals)
            gate_c["rewards"] = rewards
            gate_c["n_exceptions"] = sum(1 for t in trials if t["exception"])
        rows.append(
            {
                "task_id": tid,
                "population": "lot001",
                "benchmark": "lot-001",
                "features": feats,
                "gate_c": gate_c,
            }
        )
        unavail[tid] = sorted(f for f in ALL_FEATURES if feats.get(f) is None)
    return rows, {"n_tasks": len(rows), "unavailable_by_task": unavail}


# ---------------------------------------------------------------------------
# One-class region fit and distances
# ---------------------------------------------------------------------------


def _obs_matrix(rows: list[dict], features: tuple[str, ...]):
    np = _np()
    X = np.full((len(rows), len(features)), np.nan)
    for i, r in enumerate(rows):
        f = r["features"]
        for j, name in enumerate(features):
            v = f.get(name)
            if v is not None:
                X[i, j] = v
    return X


def kept_feature_stats(kept: list[dict], features: tuple[str, ...]) -> dict:
    """Per-feature kept-set stats on transformed scale; the universe is
    the features with enough kept observations and nonzero spread."""
    np = _np()
    X = _obs_matrix(kept, features)
    stats = {}
    for j, name in enumerate(features):
        obs = X[:, j][~np.isnan(X[:, j])]
        if len(obs) < MIN_KEPT_OBS:
            stats[name] = {"n": int(len(obs)), "in_universe": False}
            continue
        qs = np.quantile(obs, [0.05, 0.25, 0.5, 0.75, 0.95])
        sd = float(obs.std(ddof=1)) if len(obs) > 1 else 0.0
        stats[name] = {
            "n": int(len(obs)),
            "mean": float(obs.mean()),
            "sd": sd,
            "min": float(obs.min()),
            "q05": float(qs[0]),
            "q25": float(qs[1]),
            "q50": float(qs[2]),
            "q75": float(qs[3]),
            "q95": float(qs[4]),
            "max": float(obs.max()),
            "in_universe": sd > 0,
        }
    return stats


def anova_eta2(rows: list[dict], features: tuple[str, ...]) -> dict:
    """One-way ANOVA eta^2 per feature across the rows' benchmarks."""
    np = _np()
    groups: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        groups[r.get("benchmark") or "?"].append(i)
    X = _obs_matrix(rows, features)
    out = {}
    for j, name in enumerate(features):
        col = X[:, j]
        if np.isfinite(col).sum() < 3 or len(groups) < 2:
            out[name] = None
            continue
        grand = float(np.nanmean(col))
        ss_tot = float(np.nansum((col - grand) ** 2))
        ss_b = 0.0
        for idxs in groups.values():
            sub = col[idxs]
            sub = sub[np.isfinite(sub)]
            if len(sub):
                ss_b += len(sub) * (float(sub.mean()) - grand) ** 2
        out[name] = (ss_b / ss_tot) if ss_tot > 0 else 0.0
    return out


def fit_region(rows: list[dict], features: tuple[str, ...]) -> dict:
    """Standardize on the row set, then pairwise-complete correlation
    shrunk toward identity until positive definite at the eigenvalue
    floor. Returns the fit used by mahalanobis()."""
    np = _np()
    X = _obs_matrix(rows, features)
    n, p = X.shape
    means = np.array(
        [float(np.nanmean(X[:, j])) if np.isfinite(X[:, j]).any() else np.nan for j in range(p)]
    )
    sds = np.array(
        [
            float(np.nanstd(X[:, j], ddof=1)) if np.isfinite(X[:, j]).sum() > 1 else np.nan
            for j in range(p)
        ]
    )
    sds = np.where(np.isfinite(sds) & (sds > 1e-12), sds, np.nan)
    Z = (X - means) / sds
    R = np.full((p, p), np.nan)
    for a in range(p):
        for b in range(a, p):
            m = np.isfinite(Z[:, a]) & np.isfinite(Z[:, b])
            if m.sum() < 3:
                continue
            if Z[m, a].std() <= 0 or Z[m, b].std() <= 0:
                continue
            ca = np.corrcoef(Z[m, a], Z[m, b])[0, 1]
            if np.isfinite(ca):
                R[a, b] = R[b, a] = float(np.clip(ca, -1.0, 1.0))
    R = np.where(np.isfinite(R), R, 0.0)
    np.fill_diagonal(R, 1.0)
    alpha = max(p / (n + p), 0.05)
    for _ in range(80):
        S = (1 - alpha) * R + alpha * np.eye(p)
        mn = float(np.linalg.eigvalsh(S).min())
        if mn >= EIG_FLOOR_FRAC:
            break
        alpha = min(1.0, alpha + (EIG_FLOOR_FRAC - mn) + 0.01)
    S = (1 - alpha) * R + alpha * np.eye(p)
    w, V = np.linalg.eigh(S)
    w = np.clip(w, 1e-6, None)
    return {
        "features": features,
        "means": means,
        "sds": sds,
        "cov": S,
        "eigvals": w,
        "eigvecs": V,
        "alpha": float(alpha),
        "n": n,
    }


_INV_CACHE: dict = {}


def _inv_sub(cov, idx):
    np = _np()
    key = (id(cov), tuple(int(i) for i in idx))
    hit = _INV_CACHE.get(key)
    if hit is None:
        hit = np.linalg.pinv(cov[np.ix_(idx, idx)], rcond=1e-8)
        _INV_CACHE[key] = hit
    return hit


def mahalanobis(
    feat_vec: dict, fit: dict, dims: tuple[str, ...] | None = None
) -> tuple[float | None, int]:
    """Mahalanobis distance of one feature dict under fit, restricted to
    dims intersected with the task's observed and the fit's informative
    features. Returns (d, p) with p the number of dims used."""
    np = _np()
    feats = fit["features"]
    allowed = set(dims) if dims is not None else set(feats)
    idx = [
        j
        for j, f in enumerate(feats)
        if f in allowed
        and np.isfinite(fit["sds"][j])
        and np.isfinite(fit["means"][j])
        and feat_vec.get(f) is not None
    ]
    if not idx:
        return None, 0
    z = np.array([(feat_vec[feats[j]] - fit["means"][j]) / fit["sds"][j] for j in idx])
    inv = _inv_sub(fit["cov"], np.array(idx))
    d2 = float(z @ inv @ z)
    return math.sqrt(max(d2, 0.0)), len(idx)


def loo_distances(
    rows: list[dict], features: tuple[str, ...], dims: tuple[str, ...] | None = None
) -> list[dict]:
    """Leave-one-out distances for a row set against its own fit."""
    out = []
    for i, r in enumerate(rows):
        fit = fit_region(rows[:i] + rows[i + 1 :], features)
        d, p = mahalanobis(r["features"], fit, dims)
        out.append({"task_id": r["task_id"], "d": d, "p": p})
    return out


def typicality(d: float | None, ref: list[float]) -> float | None:
    """Share of reference distances at least as large as d. A kept task
    lands near 0.5 at the median by exchangeability."""
    if d is None or not ref:
        return None
    return sum(1 for x in ref if x >= d) / len(ref)


def marginal_coverage(feat_vec: dict, stats: dict) -> tuple[float | None, int]:
    """Share of the task's observed universe features inside the kept
    [q05, q95] range."""
    inside = tot = 0
    for f, st in stats.items():
        if not st.get("in_universe"):
            continue
        v = feat_vec.get(f)
        if v is None:
            continue
        tot += 1
        if st["q05"] <= v <= st["q95"]:
            inside += 1
    return (inside / tot if tot else None), tot


def population_mask(rows: list[dict], universe: tuple[str, ...]) -> tuple[str, ...]:
    np = _np()
    X = _obs_matrix(rows, universe)
    return tuple(
        f
        for j, f in enumerate(universe)
        if float(np.isfinite(X[:, j]).mean()) >= MASK_COVER_MIN
    )


def kde_fit(rows: list[dict], fit: dict, dims: tuple[str, ...] | None = None, k: int = KDE_DIMS) -> dict:
    """Gaussian KDE on the top-k eigendirections of a region fit,
    restricted to dims (the eigendecomposition is of the mask-restricted
    kept covariance). A task projects with its observed coordinates only,
    rescaled by the observed share of each eigenvector's squared mass."""
    np = _np()
    feats = fit["features"]
    if dims is None:
        dims = feats
    idx = np.array(
        [j for j, f in enumerate(feats) if f in dims and np.isfinite(fit["sds"][j])]
    )
    if len(idx) == 0:
        return {"k": 0, "n": 0, "project": lambda fv: None, "pts": np.zeros((0, k)), "bw": np.ones(k), "eig_share": [], "vecs": np.zeros((0, 0))}
    sub = fit["cov"][np.ix_(idx, idx)]
    w, V = np.linalg.eigh(sub)
    order = np.argsort(-w)[:k]
    vecs = V[:, order]
    eig_share = w[order] / w.sum()
    means = fit["means"][idx]
    sds = fit["sds"][idx]
    sub_feats = [feats[j] for j in idx]

    def project(feat_vec):
        comps = []
        for c in range(vecs.shape[1]):
            v = vecs[:, c]
            mass = acc = 0.0
            for j, f in enumerate(sub_feats):
                val = feat_vec.get(f)
                if val is None:
                    continue
                mass += v[j] * v[j]
                acc += ((val - means[j]) / sds[j]) * v[j]
            if mass < KDE_MIN_LOADING_MASS:
                return None
            comps.append(acc / math.sqrt(mass))
        return np.array(comps)

    pts = [project(r["features"]) for r in rows]
    pts = [p for p in pts if p is not None]
    P = np.array(pts) if pts else np.zeros((0, vecs.shape[1]))
    n = P.shape[0]
    sd_p = P.std(axis=0, ddof=1) if n > 1 else np.ones(vecs.shape[1])
    sd_p = np.where(sd_p > 0, sd_p, 1.0)
    bw = sd_p * (n ** (-1.0 / (vecs.shape[1] + 4))) if n else np.ones(vecs.shape[1])
    return {
        "vecs": vecs,
        "eig_share": [float(x) for x in eig_share],
        "bw": bw,
        "pts": P,
        "project": project,
        "k": vecs.shape[1],
        "n": n,
        "dims": list(dims),
    }


def kde_density(kde: dict, feat_vec) -> float | None:
    np = _np()
    pr = kde["project"](feat_vec)
    if pr is None or kde["n"] == 0:
        return None
    d2 = ((kde["pts"] - pr) / kde["bw"]) ** 2
    dens = float(np.exp(-0.5 * d2.sum(axis=1)).mean())
    norm = (2 * math.pi) ** (kde["k"] / 2) * float(np.prod(kde["bw"]))
    return dens / norm


def kde_loo_densities(kde: dict) -> list[float]:
    """Each KDE point's density under the fit without it."""
    np = _np()
    P, bw = kde["pts"], kde["bw"]
    norm = (2 * math.pi) ** (kde["k"] / 2) * float(np.prod(bw))
    out = []
    for i in range(kde["n"]):
        rest = np.delete(P, i, axis=0)
        d2 = ((rest - P[i]) / bw) ** 2
        out.append(float(np.exp(-0.5 * d2.sum(axis=1)).mean() / norm))
    return out


def kde_typicality(dens: float | None, ref_dens: list[float]) -> float | None:
    """Share of reference LOO densities at most as large as the task's."""
    if dens is None or not ref_dens:
        return None
    return sum(1 for x in ref_dens if x <= dens) / len(ref_dens)


# ---------------------------------------------------------------------------
# Variants
# ---------------------------------------------------------------------------


def score_rows(
    pop_rows: list[dict], kept_fit: dict, ref_dists: list[float], mask: tuple[str, ...]
) -> list[dict]:
    out = []
    for r in pop_rows:
        d, p = mahalanobis(r["features"], kept_fit, mask)
        out.append(
            {
                "task_id": r["task_id"],
                "d": d,
                "p_dims": p,
                "typicality": typicality(d, ref_dists),
            }
        )
    return out


def source_fits(
    kept_rows: list[dict], features: tuple[str, ...], global_fit: dict | None = None
) -> dict:
    """One region fit per benchmark's kept subset. A singleton source has
    no estimable spread: it falls back to the member's vector as center,
    the pooled kept standardization, and identity covariance (standardized
    euclidean distance to that one task)."""
    np = _np()
    by_bench: dict[str, list[dict]] = defaultdict(list)
    for r in kept_rows:
        by_bench[r["benchmark"]].append(r)
    fits = {}
    for b, rows in sorted(by_bench.items()):
        dims = tuple(
            f
            for f in features
            if sum(1 for r in rows if r["features"].get(f) is not None)
            >= max(1, len(rows) // 2)
        )
        if len(rows) == 1 and global_fit is not None:
            vec = rows[0]["features"]
            means = np.array(
                [vec.get(f, np.nan) if vec.get(f) is not None else np.nan for f in dims],
                dtype=float,
            )
            gsd = {f: global_fit["sds"][j] for j, f in enumerate(global_fit["features"])}
            sds = np.array([gsd.get(f, np.nan) for f in dims], dtype=float)
            fits[b] = {
                "fit": {
                    "features": dims,
                    "means": means,
                    "sds": sds,
                    "cov": np.eye(len(dims)),
                    "eigvals": np.ones(len(dims)),
                    "eigvecs": np.eye(len(dims)),
                    "alpha": 1.0,
                    "n": 1,
                },
                "n": 1,
                "dims": dims,
            }
            continue
        fits[b] = {"fit": fit_region(rows, dims), "n": len(rows), "dims": dims}
    return fits


def per_source_distances(
    feat_vec: dict, sfits: dict, mask: tuple[str, ...]
) -> dict[str, float]:
    out = {}
    for b, s in sfits.items():
        dims = tuple(f for f in mask if f in s["dims"])
        d, _ = mahalanobis(feat_vec, s["fit"], dims)
        if d is not None:
            out[b] = d
    return out


def source_self_loo(members: list[dict], dims: tuple[str, ...]) -> list[float]:
    """Within-source LOO distances: each member's distance to the source
    fit without it. This is the reference cloud for 'resembles source s':
    a candidate is typical of s when it sits at least as deep in s's kept
    cloud as s's own members."""
    out = []
    for i, m in enumerate(members):
        rest = members[:i] + members[i + 1 :]
        fit = fit_region(rest, dims)
        d, _ = mahalanobis(m["features"], fit, dims)
        if d is not None:
            out.append(d)
    return out


def per_source_refs(
    kept: list[dict], sfits: dict, mask: tuple[str, ...], kept_rows_by_source: dict | None = None
) -> dict:
    """Reference distance clouds per source under a population mask.

    Sources with 2+ kept members get their own members' within-source LOO
    distances: the question is whether a candidate sits inside that
    benchmark's kept cloud. Singletons get the all-kept cloud instead: a
    candidate resembles a one-task source when it is closer to that task
    than kept tasks typically are.
    """
    if kept_rows_by_source is None:
        kept_rows_by_source = defaultdict(list)
        for r in kept:
            kept_rows_by_source[r["benchmark"]].append(r)
    refs = {}
    for b, s in sfits.items():
        dims = tuple(f for f in mask if f in s["dims"])
        if s["n"] >= 2:
            refs[b] = {"kind": "self_loo", "dists": source_self_loo(kept_rows_by_source[b], dims)}
        else:
            dd = []
            for k in kept:
                dk, _ = mahalanobis(k["features"], s["fit"], dims)
                if dk is not None:
                    dd.append(dk)
            refs[b] = {"kind": "all_kept", "dists": dd}
    return refs


def per_source_score(
    feat_vec: dict, sfits: dict, refs: dict, mask: tuple[str, ...]
) -> dict:
    dists = per_source_distances(feat_vec, sfits, mask)
    best = max(
        (
            (typicality(d, refs[b]["dists"]), b, d)
            for b, d in dists.items()
            if refs.get(b) and refs[b]["dists"]
        ),
        default=(None, None, None),
        key=lambda t: (t[0] is not None, t[0]),
    )
    return {"typicality": best[0], "best_source": best[1], "d_best": best[2], "d_by_source": dists}


def _dist_summary(scores: list[float | None]) -> dict:
    np = _np()
    arr = sorted(x for x in scores if x is not None)
    if not arr:
        return {"n": 0, "scores": []}
    return {
        "n": len(arr),
        "scores": arr,
        "median": float(np.quantile(arr, 0.5)),
        "p10": float(np.quantile(arr, 0.1)),
        "p90": float(np.quantile(arr, 0.9)),
        "share_ge_0.5": sum(1 for x in arr if x >= 0.5) / len(arr),
        "share_le_0.1": sum(1 for x in arr if x <= 0.1) / len(arr),
    }


def run(
    out_region: Path = OUT_REGION_PATH,
    out_lot: Path = OUT_LOT_PATH,
    lot_root: Path = LOT001_ROOT,
) -> dict:
    np = _np()
    pops = build_populations()
    kept = pops["kept"]

    universe_stats = kept_feature_stats(kept, ALL_FEATURES)
    universe = tuple(f for f in ALL_FEATURES if universe_stats[f].get("in_universe"))

    # eta^2 across benchmarks. Behaviour features are measured on the
    # 1,331 stage-1 survivors across 48 benchmarks, the frame where the
    # source confound operates; static and gate features exist only on
    # the kept 82 (29 benchmarks), so their eta^2 carries a
    # singleton-heavy upward floor reported as eta2_frame.
    eta2: dict = {}
    eta2_frame: dict = {}
    behav_set = set(BEHAVIOR_FEATURES)
    survivors = pops["survivors"]
    eta2_surv = anova_eta2(survivors, tuple(f for f in universe if f in behav_set))
    eta2_kept = anova_eta2(kept, tuple(f for f in universe if f not in behav_set))
    for f in universe:
        if f in behav_set:
            eta2[f] = eta2_surv.get(f)
            eta2_frame[f] = "stage1_survivors"
        else:
            eta2[f] = eta2_kept.get(f)
            eta2_frame[f] = "kept"
    dropped = sorted(f for f, e in eta2.items() if e is not None and e > ANOVA_ETA2_MAX)
    retained = tuple(f for f in universe if f not in set(dropped))

    kept_fit = fit_region(kept, universe)
    kept_fit_des = fit_region(kept, retained)
    sfits = source_fits(kept, universe, global_fit=kept_fit)

    masks = {name: population_mask(rows, universe) for name, rows in pops.items()}
    # The kept set scores on every informed dim; the coverage rule is for
    # populations that structurally lack a feature block.
    masks["kept"] = universe
    masks_des = {name: tuple(f for f in m if f in retained) for name, m in masks.items()}

    # Kept LOO distance clouds: one per population mask per variant.
    kept_loo_rows = {"pooled": {}, "desourced": {}}
    for name, mask in masks.items():
        kept_loo_rows["pooled"][name] = loo_distances(kept, universe, mask)
    for name, mask in masks_des.items():
        kept_loo_rows["desourced"][name] = loo_distances(kept, retained, mask)
    kept_loo = {
        v: {name: [r["d"] for r in rows if r["d"] is not None] for name, rows in m.items()}
        for v, m in kept_loo_rows.items()
    }

    # Per-source kept LOO: for kept task i in source s_i, s_i is refit
    # without i (and drops out entirely if i was its only member).
    # Singleton sources rank a task against the all-kept cloud minus i.
    kept_by_src: dict[str, list[dict]] = defaultdict(list)
    for r in kept:
        kept_by_src[r["benchmark"]].append(r)
    self_loo_full = {}
    for b, s in sfits.items():
        if s["n"] >= 2:
            dims = tuple(f for f in masks["kept"] if f in s["dims"])
            self_loo_full[b] = source_self_loo(kept_by_src[b], dims)
    kept_ps_loo = []
    for i, r in enumerate(kept):
        rest = kept[:i] + kept[i + 1 :]
        b_i = r["benchmark"]
        score_parts = []
        for b, s in sfits.items():
            dims = tuple(f for f in masks["kept"] if f in s["dims"])
            if b == b_i:
                if s["n"] < 2:
                    continue  # own source vanishes under LOO
                members = kept_by_src[b]
                rest_members = [m for m in members if m["task_id"] != r["task_id"]]
                fit_wo = fit_region(rest_members, dims)
                d_i, _ = mahalanobis(r["features"], fit_wo, dims)
                ref = source_self_loo(rest_members, dims)
            elif s["n"] >= 2:
                d_i, _ = mahalanobis(r["features"], s["fit"], dims)
                ref = self_loo_full[b]
            else:
                d_i, _ = mahalanobis(r["features"], s["fit"], dims)
                ref = []
                for k in rest:
                    dk, _ = mahalanobis(k["features"], s["fit"], dims)
                    if dk is not None:
                        ref.append(dk)
            score_parts.append((typicality(d_i, ref), b, d_i))
        best = max(
            score_parts,
            default=(None, None, None),
            key=lambda t: (t[0] is not None, t[0]),
        )
        kept_ps_loo.append(
            {"task_id": r["task_id"], "typicality": best[0], "best_source": best[1]}
        )

    # Calibration distributions
    calibration: dict = {v: {} for v in VARIANTS}
    for name in CALIBRATION_POPS:
        rows = pops[name]
        # pooled
        if name == "kept":
            rows_d = kept_loo_rows["pooled"]["kept"]
            scores = [typicality(r["d"], kept_loo["pooled"]["kept"]) for r in rows_d]
        else:
            scores = [
                r["typicality"]
                for r in score_rows(rows, kept_fit, kept_loo["pooled"][name], masks[name])
            ]
        calibration["pooled"][name] = _dist_summary(scores)
        # desourced
        if name == "kept":
            rows_d = kept_loo_rows["desourced"]["kept"]
            scores = [typicality(r["d"], kept_loo["desourced"]["kept"]) for r in rows_d]
        else:
            scores = [
                r["typicality"]
                for r in score_rows(rows, kept_fit_des, kept_loo["desourced"][name], masks_des[name])
            ]
        calibration["desourced"][name] = _dist_summary(scores)
        # per_source
        if name == "kept":
            scores = [r["typicality"] for r in kept_ps_loo]
        else:
            refs = per_source_refs(kept, sfits, masks[name])
            scores = [
                per_source_score(r["features"], sfits, refs, masks[name])["typicality"]
                for r in rows
            ]
        calibration["per_source"][name] = _dist_summary(scores)

    # KDE on the top-variance eigendirections of the mask-restricted
    # pooled kept covariance, one per population mask.
    kde_cal = {}
    kde_meta = {}
    for name in CALIBRATION_POPS:
        kde_p = kde_fit(kept, kept_fit, dims=masks[name])
        kde_loo = kde_loo_densities(kde_p)
        if name == "kept":
            scores = [kde_typicality(d, kde_loo) for d in kde_loo]
        else:
            scores = [
                kde_typicality(kde_density(kde_p, r["features"]), kde_loo)
                for r in pops[name]
            ]
        kde_cal[name] = _dist_summary(scores)
        kde_meta[name] = {
            "k": kde_p["k"],
            "eig_share": kde_p["eig_share"],
            "n_kept_projected": kde_p["n"],
            "bandwidth": [float(x) for x in kde_p["bw"]],
        }

    # lot-001
    lot_rows, lot_meta = lot001_rows(lot_root)
    pops["lot001"] = lot_rows
    lot_mask = population_mask(lot_rows, universe)
    masks["lot001"] = lot_mask
    masks_des["lot001"] = tuple(f for f in lot_mask if f in retained)
    kept_loo["pooled"]["lot001"] = [
        r["d"] for r in loo_distances(kept, universe, lot_mask) if r["d"] is not None
    ]
    kept_loo["desourced"]["lot001"] = [
        r["d"] for r in loo_distances(kept, retained, masks_des["lot001"]) if r["d"] is not None
    ]

    # Rejected distance clouds under the lot mask for pct_vs_rejected.
    rej_d = {
        "pooled": [
            r["d"]
            for r in score_rows(pops["rejected"], kept_fit, [], masks["lot001"])
            if r["d"] is not None
        ],
        "desourced": [
            r["d"]
            for r in score_rows(pops["rejected"], kept_fit_des, [], masks_des["lot001"])
            if r["d"] is not None
        ],
    }
    refs_ps_lot = per_source_refs(kept, sfits, lot_mask)
    rej_ps_typ = [
        per_source_score(r["features"], sfits, refs_ps_lot, lot_mask)["typicality"]
        for r in pops["rejected"]
    ]

    kde_lot = kde_fit(kept, kept_fit, dims=lot_mask)
    kde_loo_lot = kde_loo_densities(kde_lot)

    lot_out = []
    for r in lot_rows:
        rec = {
            "task_id": r["task_id"],
            "n_features_observed": sum(
                1 for f in universe if r["features"].get(f) is not None
            ),
            "features_observed": sorted(
                f for f in universe if r["features"].get(f) is not None
            ),
            "features_unavailable": lot_meta["unavailable_by_task"].get(r["task_id"], []),
            "gate_c": r.get("gate_c"),
        }
        mc, mc_n = marginal_coverage(r["features"], universe_stats)
        rec["marginal_coverage_q05_q95"] = mc
        rec["marginal_coverage_n"] = mc_n
        for variant, fit, mask, ref in (
            ("pooled", kept_fit, lot_mask, kept_loo["pooled"]["lot001"]),
            ("desourced", kept_fit_des, masks_des["lot001"], kept_loo["desourced"]["lot001"]),
        ):
            d, p = mahalanobis(r["features"], fit, mask)
            rec[variant] = {
                "d": d,
                "p_dims": p,
                "typicality": typicality(d, ref),
                "pct_vs_rejected": typicality(d, rej_d[variant]),
            }
        ps = per_source_score(r["features"], sfits, refs_ps_lot, lot_mask)
        rec["per_source"] = {
            "typicality": ps["typicality"],
            "best_source": ps["best_source"],
            "d_best": ps["d_best"],
            "pct_vs_rejected": (
                sum(1 for x in rej_ps_typ if x is not None and x <= ps["typicality"])
                / sum(1 for x in rej_ps_typ if x is not None)
                if ps["typicality"] is not None
                else None
            ),
        }
        rec["kde"] = {
            "density": kde_density(kde_lot, r["features"]),
            "typicality": kde_typicality(kde_density(kde_lot, r["features"]), kde_loo_lot),
        }
        lot_out.append(rec)

    region = {
        "protocol": PROTOCOL,
        "code": "src/task_validation/evidence/typicality.py",
        "kept_set": {
            "n": len(kept),
            "n_with_behavior": sum(
                1 for r in kept if r["features"].get("n_frontier_trials") is not None
            ),
            "benchmarks": dict(Counter(r["benchmark"] for r in kept)),
        },
        "features": {
            "universe": list(universe),
            "n_universe": len(universe),
            "min_kept_obs": MIN_KEPT_OBS,
            "per_feature": {
                f: {
                    **universe_stats[f],
                    "eta2_benchmark": eta2.get(f),
                    "transform": "log1p" if f in LOG1P_FEATURES else "none",
                }
                for f in ALL_FEATURES
            },
        },
        "anova_desourced": {
            "grouping": "one-way ANOVA across benchmarks",
            "eta2_threshold": ANOVA_ETA2_MAX,
            "eta2_frame": eta2_frame,
            "frames": {
                "stage1_survivors": {
                    "n": len(survivors),
                    "n_benchmarks": len({r["benchmark"] for r in survivors}),
                },
                "kept": {
                    "n": len(kept),
                    "n_benchmarks": len({r["benchmark"] for r in kept}),
                },
            },
            "dropped": dropped,
            "retained": list(retained),
        },
        "fit": {
            "shrinkage_alpha": kept_fit["alpha"],
            "eig_floor_frac": EIG_FLOOR_FRAC,
            "n_kept": kept_fit["n"],
            "top_eigval_shares": [
                float(x / kept_fit["eigvals"].sum())
                for x in sorted(kept_fit["eigvals"], reverse=True)[:5]
            ],
        },
        "masks": {k: list(v) for k, v in masks.items()},
        "masks_desourced": {k: list(v) for k, v in masks_des.items()},
        "calibration": calibration,
        "kde": {
            "per_population": kde_meta,
            "calibration": kde_cal,
        },
        "kept_loo_dists": kept_loo,
        "populations": {k: len(v) for k, v in pops.items()},
        "inputs": {
            "labels": str(LABELS_PATH),
            "stage1": str(STAGE1_PATH),
            "task_traj": str(TASK_TRAJ_PATH),
            "footprint": str(FOOTPRINT_PATH),
            "strata": str(STRATA_PATH),
            "tb21_census": str(TB21_CENSUS_PATH),
            "swe_features": str(SWE_FEATURES_PATH),
            "lot": str(lot_root),
        },
    }
    write_json(out_region, region)
    write_jsonl(out_lot, lot_out)
    return region


def main() -> None:
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "run":
        region = run()
        for variant in VARIANTS:
            line = [f"[{variant}]"]
            for name in CALIBRATION_POPS:
                c = region["calibration"][variant][name]
                med = c["median"]
                line.append(f"{name} n={c['n']} med={med:.3f}" if med is not None else f"{name} n=0")
            print(" ".join(line))
    else:
        print("usage: python -m task_validation.evidence.typicality run")


if __name__ == "__main__":
    main()

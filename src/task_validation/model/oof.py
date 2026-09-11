"""Grouped-by-repository out-of-fold predictions and evaluation."""

from __future__ import annotations

import json
from pathlib import Path

from task_validation.evidence.swe_artifacts import CHEAP_FEATURE_NAMES
from task_validation.model.calibration import calibration_slope_intercept
from task_validation.model.fit import assert_no_leakage
from task_validation.model.metrics import auprc, auroc, brier, log_loss, reliability_bins
from task_validation.model.risk_coverage import retain_curve, threshold_curve
from task_validation.model.selective import apply_lambda, select_lambda


def _xy_all(rows: list[dict], y_key: str) -> tuple[list[list[float]], list[int], list[str]]:
    X, y, groups = [], [], []
    for r in rows:
        X.append([float(r["features"][n]) for n in CHEAP_FEATURE_NAMES])
        y.append(int(r[y_key]))
        groups.append(r.get("repository") or "unknown")
    return X, y, groups


def bootstrap_ci(
    y: list[int],
    p: list[float],
    fn,
    n_boot: int = 400,
    seed: int = 0,
) -> dict:
    import numpy as np

    rng = np.random.default_rng(seed)
    n = len(y)
    y_a = np.asarray(y)
    p_a = np.asarray(p)
    stats = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        val = fn(y_a[idx].tolist(), p_a[idx].tolist())
        if val is not None:
            stats.append(val)
    if not stats:
        return {"mean": None, "lo": None, "hi": None}
    lo, hi = float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))
    return {"mean": float(sum(stats) / len(stats)), "lo": lo, "hi": hi, "n_boot": n_boot}


def _platt(p_raw: list[float], y_cal: list[int], p_cal: list[float]) -> list[float]:
    """Calibrate with logistic on logit(p). Apply to p_raw."""
    import math

    from task_validation.model.calibration import calibration_slope_intercept

    fit = calibration_slope_intercept(y_cal, p_cal)
    b0, b1 = fit["intercept"], fit["slope"]
    out = []
    for pi in p_raw:
        eps = 1e-6
        pi = min(1 - eps, max(eps, pi))
        z = math.log(pi / (1 - pi))
        eta = b0 + b1 * z
        if eta >= 0:
            out.append(1 / (1 + math.exp(-eta)))
        else:
            e = math.exp(eta)
            out.append(e / (1 + e))
    return out


def grouped_oof(
    rows: list[dict],
    y_key: str = "y",
    n_splits: int = 5,
    seed: int = 0,
) -> dict:
    try:
        import numpy as np
        from sklearn.ensemble import HistGradientBoostingClassifier
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import GroupKFold
        from sklearn.preprocessing import StandardScaler
    except ImportError as exc:
        raise RuntimeError("scikit-learn is required. Use the project .venv.") from exc

    assert_no_leakage(list(CHEAP_FEATURE_NAMES))
    X, y, groups = _xy_all(rows, y_key)
    X = np.asarray(X, dtype=float)
    y_a = np.asarray(y, dtype=int)
    groups_a = np.asarray(groups)
    n_groups = len(set(groups))
    splits = max(2, min(n_splits, n_groups))
    gkf = GroupKFold(n_splits=splits)
    p_logit = np.zeros(len(y), dtype=float)
    p_hgb = np.zeros(len(y), dtype=float)
    fold_id = np.zeros(len(y), dtype=int)
    for fold, (tr, te) in enumerate(gkf.split(X, y_a, groups_a), start=1):
        scaler = StandardScaler()
        Xtr = scaler.fit_transform(X[tr])
        Xte = scaler.transform(X[te])
        logit = LogisticRegression(max_iter=400, class_weight="balanced")
        logit.fit(Xtr, y_a[tr])
        p_logit[te] = logit.predict_proba(Xte)[:, 1]
        hgb = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.08, max_iter=200)
        hgb.fit(X[tr], y_a[tr])
        p_hgb[te] = hgb.predict_proba(X[te])[:, 1]
        fold_id[te] = fold

    def pack(name: str, p: np.ndarray) -> dict:
        p_list = p.tolist()
        y_list = y
        # Group-aware calib/eval split for SRC: hold out ~30% of repos.
        repos = sorted(set(groups))
        rng = np.random.default_rng(seed + 17)
        rng.shuffle(repos)
        n_cal_r = max(1, int(0.3 * len(repos)))
        cal_repos = set(repos[:n_cal_r])
        cal_idx = [i for i, g in enumerate(groups) if g in cal_repos]
        ev_idx = [i for i, g in enumerate(groups) if g not in cal_repos]
        y_cal = [y[i] for i in cal_idx]
        p_cal = [p_list[i] for i in cal_idx]
        y_ev = [y[i] for i in ev_idx]
        p_ev = [p_list[i] for i in ev_idx]
        p_calibrated_ev = _platt(p_ev, y_cal, p_cal)
        src = select_lambda(y_cal, p_cal, alpha=0.20)
        src_calibrated = select_lambda(y_cal, _platt(p_cal, y_cal, p_cal), alpha=0.20)
        # alpha=0.20 is a filter target, not the 5% population certificate.
        return {
            "model": name,
            "y_key": y_key,
            "n": len(y),
            "base_rate": float(sum(y) / len(y)),
            "auroc": auroc(y_list, p_list),
            "auprc": auprc(y_list, p_list),
            "brier": brier(y_list, p_list),
            "log_loss": log_loss(y_list, p_list),
            "auroc_ci": bootstrap_ci(y_list, p_list, auroc, n_boot=400, seed=seed),
            "auprc_ci": bootstrap_ci(y_list, p_list, auprc, n_boot=400, seed=seed + 1),
            "brier_ci": bootstrap_ci(y_list, p_list, brier, n_boot=400, seed=seed + 2),
            "calibration": calibration_slope_intercept(y_list, p_list),
            "reliability": reliability_bins(y_list, p_list, 10),
            "retain_curve": retain_curve(y_list, p_list),
            "threshold_curve": threshold_curve(y_list, p_list, [0.2, 0.3, 0.4, 0.5, 0.6, 0.7]),
            "src_alpha_0.20": {
                "calibration": src,
                "eval": apply_lambda(y_ev, p_ev, src.get("lambda")),
                "note": "alpha is residual-invalidity *filter* target on the accepted tail, not a population UCB.",
            },
            "calibrated_logistic_eval": {
                "retain_curve": retain_curve(y_ev, p_calibrated_ev),
                "src_alpha_0.20": {
                    "calibration": src_calibrated,
                    "eval": apply_lambda(y_ev, p_calibrated_ev, src_calibrated.get("lambda")),
                },
            },
        }

    return {
        "n_splits": splits,
        "n_groups": n_groups,
        "y_key": y_key,
        "logistic": pack("logistic", p_logit),
        "hgb": pack("hgb", p_hgb),
        "oof": [
            {
                "task_id": rows[i]["task_id"],
                "repository": groups[i],
                "y": int(y[i]),
                "p_logistic": float(p_logit[i]),
                "p_hgb": float(p_hgb[i]),
                "fold": int(fold_id[i]),
            }
            for i in range(len(rows))
        ],
    }


def write_oof(report: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    slim = {k: v for k, v in report.items() if k != "oof"}
    path.write_text(json.dumps(slim, indent=2) + "\n", encoding="utf-8")
    oof_path = path.with_suffix(".oof.jsonl")
    with oof_path.open("w", encoding="utf-8") as fh:
        for rec in report["oof"]:
            fh.write(json.dumps(rec) + "\n")

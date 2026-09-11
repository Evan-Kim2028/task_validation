"""Fit logistic regression and histogram gradient boosting.

Forbidden: any human severity field. The 2024 filter_out label is Y, not X.
"""

from __future__ import annotations

import json
from pathlib import Path

from task_validation.evidence.swe_artifacts import CHEAP_FEATURE_NAMES, FORBIDDEN_PREDICTORS
from task_validation.model.metrics import auprc, auroc, brier, log_loss, operating_point, reliability_bins


def assert_no_leakage(names: list[str]) -> None:
    leaked = set(names) & FORBIDDEN_PREDICTORS
    if leaked:
        raise ValueError(f"circular predictors: {sorted(leaked)}")
    unknown = [n for n in names if n not in CHEAP_FEATURE_NAMES]
    if unknown:
        raise ValueError(f"feature not in frozen cheap list: {unknown}")


def _split_by_repo(
    rows: list[dict],
    seed: str,
    test_frac: float = 0.3,
) -> tuple[list[int], list[int]]:
    """Hold out whole repositories. Not a random row split."""
    import hashlib

    repos = sorted({r["repository"] or "unknown" for r in rows})
    test_repos = set()
    for repo in repos:
        digest = hashlib.sha256(f"{seed}:{repo}".encode()).digest()
        u = int.from_bytes(digest[:8], "big") / 2**64
        if u < test_frac:
            test_repos.add(repo)
    if not test_repos or len(test_repos) == len(repos):
        test_repos = {repos[0]} if repos else set()
    train = [i for i, r in enumerate(rows) if (r["repository"] or "unknown") not in test_repos]
    test = [i for i, r in enumerate(rows) if (r["repository"] or "unknown") in test_repos]
    return train, test


def _xy(rows: list[dict], idx: list[int]) -> tuple[list[list[float]], list[int]]:
    X = []
    y = []
    for i in idx:
        r = rows[i]
        feats = r["features"]
        X.append([float(feats[n]) for n in CHEAP_FEATURE_NAMES])
        y.append(1 if r["y"] == 1 else 0)
    return X, y


def fit_and_eval(rows: list[dict], seed: str = "evalqa-risk-v0") -> dict:
    try:
        from sklearn.ensemble import HistGradientBoostingClassifier
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler
    except ImportError as exc:
        raise RuntimeError("scikit-learn is required for fit-risk. Use the project .venv.") from exc

    assert_no_leakage(list(CHEAP_FEATURE_NAMES))
    train_i, test_i = _split_by_repo(rows, seed)
    Xtr, ytr = _xy(rows, train_i)
    Xte, yte = _xy(rows, test_i)
    scaler = StandardScaler()
    Xtr_s = scaler.fit_transform(Xtr)
    Xte_s = scaler.transform(Xte)
    logit = LogisticRegression(max_iter=400, class_weight="balanced")
    logit.fit(Xtr_s, ytr)
    p_logit = logit.predict_proba(Xte_s)[:, 1].tolist()
    hgb = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.08, max_iter=200)
    hgb.fit(Xtr, ytr)
    p_hgb = hgb.predict_proba(Xte)[:, 1].tolist()
    coefs = {n: float(c) for n, c in zip(CHEAP_FEATURE_NAMES, logit.coef_[0])}
    return {
        "n": len(rows),
        "n_train": len(train_i),
        "n_test": len(test_i),
        "split": "by_repository",
        "seed": seed,
        "protocol": "openai-swe-bench-verified-2024-conservative",
        "predictors": list(CHEAP_FEATURE_NAMES),
        "forbidden_excluded": sorted(FORBIDDEN_PREDICTORS),
        "logistic": _pack(yte, p_logit, coefs=coefs),
        "hgb": _pack(yte, p_hgb),
    }


def _pack(y: list[int], p: list[float], coefs: dict | None = None) -> dict:
    out = {
        "auroc": auroc(y, p),
        "auprc": auprc(y, p),
        "brier": brier(y, p),
        "log_loss": log_loss(y, p),
        "base_rate": sum(y) / len(y) if y else None,
        "op_0.5": operating_point(y, p, 0.5),
        "op_0.7": operating_point(y, p, 0.7),
        "reliability": reliability_bins(y, p, 10),
    }
    if coefs is not None:
        out["coefficients"] = coefs
    return out


def load_feature_table(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            rows.append(json.loads(line))
    return rows

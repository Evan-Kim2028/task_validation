"""Discrimination and calibration. Numpy only."""

from __future__ import annotations

import math


def auroc(y: list[int], scores: list[float]) -> float | None:
    try:
        from sklearn.metrics import roc_auc_score
        import numpy as np

        y_a = np.asarray(y)
        if y_a.min() == y_a.max():
            return None
        return float(roc_auc_score(y_a, scores))
    except ImportError:
        pos = [s for s, t in zip(scores, y) if t == 1]
        neg = [s for s, t in zip(scores, y) if t == 0]
        if not pos or not neg:
            return None
        wins = 0.0
        for p in pos:
            for n in neg:
                if p > n:
                    wins += 1.0
                elif p == n:
                    wins += 0.5
        return wins / (len(pos) * len(neg))


def auprc(y: list[int], scores: list[float]) -> float | None:
    pairs = sorted(zip(scores, y), reverse=True)
    tp = 0
    fp = 0
    n_pos = sum(y)
    if n_pos == 0:
        return None
    prev_recall = 0.0
    area = 0.0
    for i, (_, label) in enumerate(pairs, start=1):
        if label == 1:
            tp += 1
        else:
            fp += 1
        precision = tp / (tp + fp)
        recall = tp / n_pos
        area += precision * (recall - prev_recall)
        prev_recall = recall
    return area


def brier(y: list[int], p: list[float]) -> float:
    return sum((pi - yi) ** 2 for pi, yi in zip(p, y)) / max(len(y), 1)


def operating_point(y: list[int], p: list[float], threshold: float) -> dict:
    pred = [1 if pi >= threshold else 0 for pi in p]
    tp = sum(1 for yi, yh in zip(y, pred) if yi == 1 and yh == 1)
    fp = sum(1 for yi, yh in zip(y, pred) if yi == 0 and yh == 1)
    tn = sum(1 for yi, yh in zip(y, pred) if yi == 0 and yh == 0)
    fn = sum(1 for yi, yh in zip(y, pred) if yi == 1 and yh == 0)
    n_acc = sum(1 for yh in pred if yh == 0)
    invalid_among_accepted = (
        sum(1 for yi, yh in zip(y, pred) if yh == 0 and yi == 1) / n_acc if n_acc else None
    )
    return {
        "threshold": threshold,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": tp / (tp + fp) if (tp + fp) else None,
        "recall": tp / (tp + fn) if (tp + fn) else None,
        "fpr": fp / (fp + tn) if (fp + tn) else None,
        "fnr": fn / (fn + tp) if (fn + tp) else None,
        "n_accepted": n_acc,
        "invalid_among_accepted": invalid_among_accepted,
    }


def reliability_bins(y: list[int], p: list[float], n_bins: int = 10) -> list[dict]:
    bins = []
    for b in range(n_bins):
        lo = b / n_bins
        hi = (b + 1) / n_bins
        idx = [i for i, pi in enumerate(p) if (pi >= lo and pi < hi) or (b == n_bins - 1 and pi == 1.0)]
        if not idx:
            continue
        mean_p = sum(p[i] for i in idx) / len(idx)
        mean_y = sum(y[i] for i in idx) / len(idx)
        bins.append({"lo": lo, "hi": hi, "n": len(idx), "mean_p": mean_p, "mean_y": mean_y})
    return bins


def log_loss(y: list[int], p: list[float]) -> float:
    eps = 1e-12
    total = 0.0
    for yi, pi in zip(y, p):
        pi = min(1 - eps, max(eps, pi))
        total += -(yi * math.log(pi) + (1 - yi) * math.log(1 - pi))
    return total / max(len(y), 1)

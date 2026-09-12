"""Reviewer-noise floor from the 3 SWE-bench raters. Does not train a model."""

from __future__ import annotations

import json
from pathlib import Path


def _confusion(pred: list[int], truth: list[int]) -> dict:
    tp = fp = tn = fn = 0
    for p, t in zip(pred, truth):
        if t == 1 and p == 1:
            tp += 1
        elif t == 0 and p == 1:
            fp += 1
        elif t == 0 and p == 0:
            tn += 1
        else:
            fn += 1
    n = max(tp + fp + tn + fn, 1)
    return {
        "n": n,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "fpr": fp / max(fp + tn, 1),
        "fnr": fn / max(fn + tp, 1),
        "agree": (tp + tn) / n,
    }


def rater_noise(targets_jsonl: Path) -> dict:
    rows = []
    with targets_jsonl.open(encoding="utf-8") as fh:
        for line in fh:
            rows.append(json.loads(line))
    maj = [int(r["majority_invalid"]) for r in rows]
    cons = [int(r["openai_2024_conservative"]) for r in rows]
    una = [int(r["unanimous_invalid"]) for r in rows]
    per_rater_vs_maj = []
    per_rater_vs_cons = []
    for idx in range(3):
        pred = [int(r["votes"][idx]) for r in rows if len(r.get("votes") or []) >= 3]
        truth_m = [int(r["majority_invalid"]) for r in rows if len(r.get("votes") or []) >= 3]
        truth_c = [int(r["openai_2024_conservative"]) for r in rows if len(r.get("votes") or []) >= 3]
        per_rater_vs_maj.append(_confusion(pred, truth_m))
        per_rater_vs_cons.append(_confusion(pred, truth_c))

    def mean_field(xs: list[dict], key: str) -> float:
        return sum(x[key] for x in xs) / len(xs)

    return {
        "n_tasks": len(rows),
        "base_rates": {
            "conservative_or": sum(cons) / len(cons),
            "majority": sum(maj) / len(maj),
            "unanimous": sum(una) / len(una),
        },
        "single_rater_vs_majority": {
            "mean_agree": mean_field(per_rater_vs_maj, "agree"),
            "mean_fpr": mean_field(per_rater_vs_maj, "fpr"),
            "mean_fnr": mean_field(per_rater_vs_maj, "fnr"),
            "per_rater": per_rater_vs_maj,
            "note": "If one human is the audit, majority of 3 is the reference.",
        },
        "single_rater_vs_conservative": {
            "mean_agree": mean_field(per_rater_vs_cons, "agree"),
            "mean_fpr": mean_field(per_rater_vs_cons, "fpr"),
            "mean_fnr": mean_field(per_rater_vs_cons, "fnr"),
            "per_rater": per_rater_vs_cons,
            "note": "Conservative is the union. A single rater systematically misses invalids the other two caught.",
        },
        "pairwise_already": "see swe_rater_targets.summary.json",
        "gate": "B1 / reviewer-noise floor for Gate 5 human minutes",
    }

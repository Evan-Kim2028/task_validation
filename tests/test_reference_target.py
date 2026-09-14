"""Fixture tests for the reference target (reference_target.py).

The synthetic case has a known answer: a tight kept cluster at the
origin and a rejected cloud far away must score near-perfect AUROC,
while a rejected cloud drawn from the same distribution must score near
chance. The robust stats are checked on values known by hand.
"""

from __future__ import annotations

import random

from task_validation.evidence.reference_target import (
    _row,
    auroc_kept_over_rejected,
    distance,
    fit_reference,
)

FEATS = ("f1", "f2")


def _rows(prefix, centers, n, seed, benchmark="s"):
    rng = random.Random(seed)
    return [
        _row(
            f"{prefix}-{i}",
            {"f1": centers[0] + rng.gauss(0, 0.5), "f2": centers[1] + rng.gauss(0, 0.5)},
            benchmark=benchmark,
        )
        for i in range(n)
    ]


def test_fit_reference_stats_known_values():
    rows = [
        _row(f"k{i}", {"f1": float(i), "f2": float(i % 2)}) for i in range(10)
    ]
    ref = fit_reference(rows, FEATS + ("absent",))
    st = ref["stats"]["f1"]
    assert st["n"] == 10
    assert st["median"] == 4.5
    assert st["q25"] <= st["median"] <= st["q75"]
    assert st["iqr"] == st["q75"] - st["q25"]
    assert 0.0 <= st["mid80_share"] <= 1.0
    # f2 is binary: every kept row sits inside the middle-80 band
    assert ref["stats"]["f2"]["mid80_share"] == 1.0
    # a feature nobody observes is not in the universe
    assert "absent" not in ref["universe"]
    assert ref["n"] == 10


def test_distance_ranks_kept_above_far_rejected():
    kept = _rows("k", (0.0, 0.0), 60, seed=1)
    far = _rows("r", (10.0, 10.0), 60, seed=2)
    ref = fit_reference(kept, FEATS)
    out = auroc_kept_over_rejected(kept, far, ref, tuple(ref["universe"]))
    assert out["auroc"] is not None and out["auroc"] >= 0.99


def test_distance_is_at_chance_on_same_distribution():
    kept = _rows("k", (0.0, 0.0), 60, seed=1)
    same = _rows("r", (0.0, 0.0), 60, seed=9)
    ref = fit_reference(kept, FEATS)
    out = auroc_kept_over_rejected(kept, same, ref, tuple(ref["universe"]))
    assert out["auroc"] is not None and 0.3 <= out["auroc"] <= 0.7


def test_distance_center_vs_edge():
    kept = _rows("k", (0.0, 0.0), 60, seed=1)
    ref = fit_reference(kept, FEATS)
    d_center, p_c = distance({"f1": 0.0, "f2": 0.0}, ref)
    d_edge, _p = distance({"f1": 8.0, "f2": 8.0}, ref)
    assert p_c == 2
    assert d_center < d_edge


def test_missing_features_marginalized_not_imputed():
    kept = _rows("k", (0.0, 0.0), 60, seed=1)
    ref = fit_reference(kept, FEATS)
    d_none, p_none = distance({"f1": None, "f2": None}, ref)
    assert d_none is None and p_none == 0
    d_one, p_one = distance({"f1": 0.0, "f2": None}, ref)
    assert p_one == 1 and d_one < 0.5

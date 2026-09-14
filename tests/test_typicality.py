"""Fixture tests for the one-class kept-region description (typicality.py).

The fixture is two clusters the answer is known for by hand: cluster A at
the origin is the "kept" set, cluster B ten standard deviations out is
rejected. Kept LOO typicality must center on 0.5 by exchangeability, B
points must score near zero, and a feature that encodes cluster identity
must be dropped by the ANOVA rule.
"""

from __future__ import annotations

import math
import random

from task_validation.evidence.typicality import (
    anova_eta2,
    fit_region,
    kde_density,
    kde_fit,
    kde_loo_densities,
    kde_typicality,
    loo_distances,
    mahalanobis,
    marginal_coverage,
    kept_feature_stats,
    per_source_score,
    population_mask,
    source_fits,
    per_source_refs,
    transform_features,
    typicality,
)

FEATS = ("f1", "f2", "f3")


def _row(tid, x, benchmark="A"):
    return {"task_id": tid, "benchmark": benchmark, "features": {"f1": x[0], "f2": x[1], "f3": x[2]}}


def _clusters(n=40, seed=1):
    rng = random.Random(seed)
    kept = [
        _row(f"kept-{i}", (rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1)), benchmark=f"s{i % 4}")
        for i in range(n)
    ]
    far = [
        _row(f"far-{i}", (rng.gauss(10, 1), rng.gauss(10, 1), rng.gauss(10, 1)), benchmark=f"t{i % 4}")
        for i in range(n)
    ]
    return kept, far


def test_mahalanobis_center_is_zero_far_is_large():
    kept, far = _clusters()
    fit = fit_region(kept, FEATS)
    d0, p0 = mahalanobis({"f1": 0.0, "f2": 0.0, "f3": 0.0}, fit)
    d10, p10 = mahalanobis({"f1": 10.0, "f2": 10.0, "f3": 10.0}, fit)
    assert p0 == p10 == 3
    assert d0 < 1.0  # near the center of a standard-normal kept set
    assert d10 > d0 + 5  # far cluster is far


def test_loo_typicality_centers_near_half():
    kept, _ = _clusters()
    loo = loo_distances(kept, FEATS)
    dists = [r["d"] for r in loo]
    typs = [typicality(r["d"], dists) for r in loo]
    med = sorted(typs)[len(typs) // 2]
    assert 0.35 <= med <= 0.65


def test_far_cluster_scores_atypical():
    kept, far = _clusters()
    fit = fit_region(kept, FEATS)
    dists = [r["d"] for r in loo_distances(kept, FEATS)]
    for r in far:
        d, _ = mahalanobis(r["features"], fit)
        t = typicality(d, dists)
        assert t is not None and t <= 0.1


def test_marginalized_distance_uses_observed_dims():
    kept, _ = _clusters()
    fit = fit_region(kept, FEATS)
    d_full, p_full = mahalanobis({"f1": 0.0, "f2": 0.0, "f3": 0.0}, fit)
    d_sub, p_sub = mahalanobis({"f1": 0.0, "f3": None}, fit)
    assert p_full == 3 and p_sub == 1
    # with only f1 observed at the center value the distance is ~0
    assert d_sub < 0.5
    # unobserved-everywhere task gets no distance
    d_none, p_none = mahalanobis({"f1": None, "f2": None, "f3": None}, fit)
    assert d_none is None and p_none == 0


def test_anova_drops_source_identifying_feature():
    rng = random.Random(7)
    kept = []
    for i in range(40):
        b = f"s{i % 4}"
        # f1 tracks the source exactly; f2 is homogeneous noise.
        kept.append(
            _row(f"k{i}", (i % 4 * 10.0 + rng.gauss(0, 0.01), rng.gauss(0, 1), rng.gauss(0, 1)), b)
        )
    eta2 = anova_eta2(kept, FEATS)
    assert eta2["f1"] > 0.9
    assert eta2["f2"] < 0.5


def test_population_mask_respects_coverage():
    rows = [
        {"task_id": "a", "benchmark": "x", "features": {"f1": 1.0, "f2": 2.0}},
        {"task_id": "b", "benchmark": "x", "features": {"f1": 1.5, "f2": None}},
        {"task_id": "c", "benchmark": "x", "features": {"f1": 1.2, "f2": None}},
    ]
    mask = population_mask(rows, FEATS)
    assert mask == ("f1",)


def test_per_source_prefers_matching_source():
    rng = random.Random(3)
    kept = []
    # two tight sources: source A at origin, source B at +10 on f1.
    for i in range(20):
        kept.append(_row(f"a{i}", (rng.gauss(0, 0.5), rng.gauss(0, 0.5), rng.gauss(0, 0.5)), "A"))
        kept.append(_row(f"b{i}", (10 + rng.gauss(0, 0.5), rng.gauss(0, 0.5), rng.gauss(0, 0.5)), "B"))
    sfits = source_fits(kept, FEATS)
    mask = FEATS
    refs = per_source_refs(kept, sfits, mask)
    near_b = per_source_score({"f1": 10.2, "f2": 0.1, "f3": -0.2}, sfits, refs, mask)
    assert near_b["best_source"] == "B"
    assert near_b["typicality"] > 0.5
    far_out = per_source_score({"f1": 100.0, "f2": 0.0, "f3": 0.0}, sfits, refs, mask)
    assert far_out["typicality"] < 0.5


def test_kde_density_orders_center_over_edge():
    kept, far = _clusters()
    fit = fit_region(kept, FEATS)
    kde = kde_fit(kept, fit, k=3)
    loo = kde_loo_densities(kde)
    d_center = kde_density(kde, {"f1": 0.0, "f2": 0.0, "f3": 0.0})
    d_far = kde_density(kde, {"f1": 10.0, "f2": 10.0, "f3": 10.0})
    assert d_center is not None and d_far is not None
    assert d_center > d_far
    t_center = kde_typicality(d_center, loo)
    t_far = kde_typicality(d_far, loo)
    assert t_center > 0.5
    assert t_far < 0.5


def test_kept_feature_stats_universe_floor():
    rows = [
        _row(f"k{i}", (float(i), float(i % 3), 1.0), "A") for i in range(20)
    ]
    rows[0]["features"]["extra_rare"] = 5.0
    stats = kept_feature_stats(rows, FEATS + ("extra_rare",))
    assert stats["f1"]["in_universe"] is True
    # f3 is constant on kept -> no spread -> out of universe
    assert stats["f3"]["in_universe"] is False
    # extra_rare has one observation -> below MIN_KEPT_OBS
    assert stats["extra_rare"]["in_universe"] is False
    # marginal coverage of a kept-like row
    mc, n = marginal_coverage({"f1": 10.0, "f2": 1.0, "f3": 1.0}, stats)
    assert n == 2 and 0.0 <= mc <= 1.0


def test_transform_log1p():
    out = transform_features({"instruction_chars": 999.0, "n_frontier_trials": 18})
    assert abs(out["instruction_chars"] - math.log1p(999.0)) < 1e-9
    assert out["n_frontier_trials"] == 18.0

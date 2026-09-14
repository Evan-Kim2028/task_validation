"""Fixture tests for doc 63 durability tiers and capability curves."""

from task_validation.evidence.durability import (
    assign_tiers,
    capability_curve,
    classify,
    slope_bootstrap,
    split_tiers,
)


def _rates(pairs):
    return {
        m: {"n_trials": n, "n_succ": s, "solve_rate": s / n}
        for m, n, s in pairs
    }


def test_split_tiers_sizes():
    assert [len(t) for t in split_tiers(list(range(16)))] == [6, 5, 5]
    assert [len(t) for t in split_tiers(list(range(13)))] == [5, 4, 4]
    assert [len(t) for t in split_tiers(list(range(7)))] == [3, 2, 2]
    assert [len(t) for t in split_tiers(list(range(6)))] == [2, 2, 2]


def test_assign_tiers_orders_by_rate():
    rates = _rates(
        [
            ("m1", 10, 1),  # 0.1 weakest
            ("m2", 10, 2),
            ("m3", 10, 3),
            ("m4", 10, 4),
            ("m5", 10, 5),
            ("m6", 10, 6),  # 0.6 strongest
        ]
    )
    out = assign_tiers(rates)
    assert out["ordered"] == ["m1", "m2", "m3", "m4", "m5", "m6"]
    assert out["tiers"]["bottom"] == ["m1", "m2"]
    assert out["tiers"]["mid"] == ["m3", "m4"]
    assert out["tiers"]["top"] == ["m5", "m6"]
    assert out["tier_of"]["m1"] == "bottom"
    assert out["tier_of"]["m6"] == "top"
    assert out["models"][0]["rank"] == 0
    assert out["models"][5]["rank"] == 5


def _cells(bottom, mid, top):
    """cells spec: {model: [n, succ]} per tier."""
    return {"bottom": bottom, "mid": mid, "top": top}


def test_capability_curve_known_slope():
    # Bottom tier 0/6, mid 3/6, top 6/6 -> slope 1.0, level 0.5, saturating.
    curve = capability_curve(
        _cells({"w1": [3, 0], "w2": [3, 0]}, {"m1": [3, 1], "m2": [3, 2]}, {"s1": [3, 3], "s2": [3, 3]})
    )
    assert curve["eligible"]
    assert curve["rate_bottom"] == 0.0
    assert curve["rate_mid"] == 0.5
    assert curve["rate_top"] == 1.0
    assert curve["slope"] == 1.0
    assert curve["level"] == 0.5
    assert classify(curve) == "saturating"


def test_capability_curve_flat_durable():
    # Every tier at 1/2 -> slope 0, mid level -> durable.
    curve = capability_curve(
        _cells({"w1": [4, 2]}, {"m1": [4, 2]}, {"s1": [4, 2]})
    )
    assert curve["eligible"]
    assert curve["slope"] == 0.0
    assert classify(curve) == "durable"


def test_capability_curve_floored_and_ceilinged():
    floored = capability_curve(
        _cells({"w1": [4, 0], "w2": [4, 0]}, {"m1": [8, 0]}, {"s1": [8, 0]})
    )
    assert classify(floored) == "floored"
    ceilinged = capability_curve(
        _cells({"w1": [4, 4]}, {"m1": [4, 4]}, {"s1": [4, 4]})
    )
    assert classify(ceilinged) == "ceilinged"


def test_capability_curve_rising_between_cutoffs():
    # 0.1 -> 0.4 -> 0.35+0.25: slope 0.25 > durable cutoff, <= saturating.
    curve = capability_curve(
        _cells({"w1": [10, 1]}, {"m1": [10, 4]}, {"s1": [10, 4], "s2": [10, 3]})
    )
    assert curve["eligible"]
    assert abs(curve["slope"] - 0.25) < 1e-9
    assert classify(curve) == "rising"


def test_capability_curve_ineligible_below_three_trials():
    curve = capability_curve(
        _cells({"w1": [2, 0]}, {"m1": [5, 2]}, {"s1": [5, 5]})
    )
    assert not curve["eligible"]
    assert classify(curve) == "unmeasured"


def test_slope_bootstrap_deterministic_extreme():
    # 0/N bottom vs N/N top: every parametric redraw gives slope 1.0.
    tiers = _cells({"w1": [10, 0], "w2": [10, 0]}, {}, {"s1": [10, 10], "s2": [10, 10]})
    boot = slope_bootstrap(tiers, n_reps=50, seed=1)
    assert boot["ci95"] == [1.0, 1.0]


def test_slope_bootstrap_orders_bounds():
    tiers = _cells({"w1": [20, 4]}, {}, {"s1": [20, 14]})
    boot = slope_bootstrap(tiers, n_reps=200, seed=7)
    lo, hi = boot["ci95"]
    assert lo <= hi
    assert -1.0 <= lo <= 1.0 and -1.0 <= hi <= 1.0


def test_classify_requires_slope():
    curve = capability_curve(_cells({"w1": [4, 2]}, {"m1": [4, 2]}, {}))
    assert classify(curve) == "unmeasured"
